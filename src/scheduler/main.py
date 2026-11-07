"""Scheduler entry point for TTL-LAMa.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

import logging
import math
import os
from datetime import timezone
from collections.abc import Callable
from typing import TYPE_CHECKING

from apscheduler.schedulers.blocking import BlockingScheduler

from api.config.c_databases import DatabaseConfig, Settings
from scheduler.leases import LeaseScheduler

if TYPE_CHECKING:
    from scheduler_types import ScheduledJobs

logger = logging.getLogger(__name__)


def _schedule_poll(
    scheduler: ScheduledJobs,
    poll: Callable[[], None],
    interval: float,
) -> None:
    scheduler.add_job(poll, "interval", seconds=interval, max_instances=1)


def main() -> None:
    """Main entry point for the TTL-LAMa scheduler."""
    logger.info("Starting TTL-LAMa scheduler")

    scheduler = BlockingScheduler(timezone=timezone.utc)
    database = DatabaseConfig(Settings())
    lease_scheduler = LeaseScheduler(database, scheduler)
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
