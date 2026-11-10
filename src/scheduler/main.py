"""Scheduler entry point for TTL-LAMa.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

import logging
import math
import os
import subprocess
from datetime import timezone
from collections.abc import Callable
from typing import TYPE_CHECKING

from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy.exc import SQLAlchemyError

from api.config import FlaskSettings
from api.config.c_databases import DatabaseConfig, Settings
from api.logging_config import configure_logging, log_event
from scheduler.leases import LeaseScheduler
from scheduler.panic import PanicMode, PanicSettings
from scheduler.ssh import format_subprocess_failure

if TYPE_CHECKING:
    from scheduler_types import ScheduledJobs

logger = logging.getLogger(__name__)
_STARTUP_RECONCILIATION_OPERATION = "reconciliation.startup"


def _schedule_poll(
    scheduler: ScheduledJobs,
    poll: Callable[[], None],
    interval: float,
) -> None:
    scheduler.add_job(poll, "interval", seconds=interval, max_instances=1)


def _reconcile_on_startup(
    lease_scheduler: LeaseScheduler,
    panic_mode: PanicMode,
) -> bool:
    """Retry startup reconciliation and trigger configured panic actions on failure.

    :param lease_scheduler: Scheduler that reconciles persisted leases.
    :type lease_scheduler: LeaseScheduler
    :param panic_mode: Configured panic actions.
    :type panic_mode: PanicMode
    :returns: Whether reconciliation succeeded.
    :rtype: bool
    """
    attempts = panic_mode.settings.retry
    for attempt in range(1, attempts + 1):
        try:
            lease_scheduler.reconcile()
        except (
            SQLAlchemyError,
            OSError,
            subprocess.SubprocessError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as error:
            if isinstance(error, subprocess.CalledProcessError):
                detail = format_subprocess_failure(error)
            else:
                detail = type(error).__name__
            log_event(
                logger,
                logging.WARNING,
                _STARTUP_RECONCILIATION_OPERATION,
                "failed attempt=%s/%s error=%s",
                attempt,
                attempts,
                detail,
            )
        else:
            log_event(
                logger,
                logging.INFO,
                "reconciliation.startup",
                "succeeded attempt=%s/%s",
                attempt,
                attempts,
            )
            return True
    log_event(
        logger,
        logging.ERROR,
        _STARTUP_RECONCILIATION_OPERATION,
        "failed after %s attempts",
        attempts,
    )
    panic_mode.trigger(f"Reconciliation failed after {attempts} attempts.")
    return False


def main() -> None:
    """Main entry point for the TTL-LAMa scheduler."""
    configure_logging("Scheduler", os.environ.get("TTL_LAMA_LOG_LEVEL", "info"))
    flask_settings = FlaskSettings()
    configure_logging("Scheduler", flask_settings.LOG_LEVEL)
    log_event(logger, logging.INFO, "scheduler.start", "started")

    scheduler = BlockingScheduler(timezone=timezone.utc)
    panic_mode = PanicMode(PanicSettings.from_file())
    database = DatabaseConfig(Settings())
    lease_scheduler = LeaseScheduler(database, scheduler)
    _reconcile_on_startup(lease_scheduler, panic_mode)
    interval = float(os.environ.get("TTL_LAMA_SCHEDULER_POLL_INTERVAL", "1"))
    if not math.isfinite(interval) or interval <= 0:
        raise ValueError("The scheduler poll interval must be positive")
    _schedule_poll(scheduler, lease_scheduler.poll, interval)

    try:
        scheduler.start()   # type: ignore
    except (KeyboardInterrupt, SystemExit): # NOSONAR
        log_event(logger, logging.INFO, "scheduler.stop", "stopped")
    finally:
        database.close()


if __name__ == "__main__":
    main()
