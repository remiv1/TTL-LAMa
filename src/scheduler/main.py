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

from api.config.c_databases import DatabaseConfig, Settings
from scheduler.leases import LeaseScheduler
from scheduler.panic import PanicMode, PanicSettings

if TYPE_CHECKING:
    from scheduler_types import ScheduledJobs

logger = logging.getLogger(__name__)


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
            logger.warning(
                "Startup reconciliation failed (%s/%s; %s)",
                attempt,
                attempts,
                type(error).__name__,
            )
        else:
            return True
    panic_mode.trigger(f"Reconciliation failed after {attempts} attempts.")
    return False


def main() -> None:
    """Main entry point for the TTL-LAMa scheduler."""
    logger.info("Starting TTL-LAMa scheduler")

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
        logger.info("Stopping TTL-LAMa scheduler")
    finally:
        database.close()


if __name__ == "__main__":
    main()
