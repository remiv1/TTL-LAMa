"""Type hints for scheduler-related classes and protocols used in job scheduling systems."""
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Protocol

from apscheduler.triggers.base import BaseTrigger

class ScheduledJob(Protocol): # pylint: disable R0903
    """Protocol representing a scheduled job."""
    misfire_grace_time: int | None

    def remove(self) -> None: ... # pylint: disable=C0116


class ScheduledJobs(Protocol):
    """Protocol for the subset of APScheduler used by TTL-LAMa."""

    def add_job( # pylint: disable=C0116, R0913
        self,  # NOSONAR
        func: Callable[..., object] | str,
        trigger: str | BaseTrigger | None = ...,
        args: Sequence[object] | None = ...,
        kwargs: Mapping[str, object] | None = ...,
        id: str | None = ...,  # pylint: disable=W0622
        name: str | None = ...,
        misfire_grace_time: int | None = ...,
        coalesce: bool = ...,
        max_instances: int = ...,
        next_run_time: datetime | None = ...,
        jobstore: str = ...,
        executor: str = ...,
        replace_existing: bool = ...,
        **trigger_args: object,
    ) -> ScheduledJob: ...

    def get_job(self, job_id: str) -> ScheduledJob | None: ... # pylint: disable=C0116

    def start(self, paused: bool = False) -> None: ... # pylint: disable=C0116

    def shutdown(self, wait: bool = True) -> None: ... # pylint: disable=C0116
