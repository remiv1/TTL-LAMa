"""Scheduler entry point for TTL-LAMa.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""

import logging

from apscheduler.schedulers.blocking import BlockingScheduler


logger = logging.getLogger(__name__)


def main() -> None:
    """Main entry point for the TTL-LAMa scheduler."""
    logger.info("Starting TTL-LAMa scheduler")

    scheduler = BlockingScheduler()

    try:
        scheduler.start()   # type: ignore
    except (KeyboardInterrupt, SystemExit): # NOSONAR
        logger.info("Stopping TTL-LAMa scheduler")


if __name__ == "__main__":
    main()
