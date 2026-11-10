"""Tests for process-aware application log configuration."""
from __future__ import annotations

import logging
import multiprocessing
import re
import stat
import subprocess
from pathlib import Path

from concurrent_log_handler import ConcurrentTimedRotatingFileHandler

from api.logging_config import (
    LOG_RETENTION_DAYS,
    LogComponent,
    TTLLogFormatter,
    configure_logging,
    log_event,
)
from scheduler.ssh import format_subprocess_failure


def _configure_and_emit(
    directory: str,
    component: LogComponent,
    count: int = 1,
    force_rotation: bool = False,
) -> None:
    log_directory = Path(directory)
    configure_logging(component, "DEBUG", log_directory)
    handlers = logging.getLogger().handlers
    timed_handlers = [
        handler for handler in handlers
        if isinstance(handler, ConcurrentTimedRotatingFileHandler)
    ]
    if len(timed_handlers) != 4:
        raise AssertionError("Expected one concurrent handler per severity")
    if any(
        handler.backupCount != LOG_RETENTION_DAYS
        or not handler.utc for handler in timed_handlers
    ):
        raise AssertionError("Expected daily UTC rotation with configured retention")

    logger = logging.getLogger(f"test.{component.lower()}")
    log_event(logger, logging.DEBUG, "test.debug", "debug message")
    log_event(logger, logging.WARNING, "test.warning", "warning message")
    log_event(logger, logging.ERROR, "test.error", "error message")
    for index in range(count):
        log_event(logger, logging.INFO, "test.concurrent", "event=%s", index)

    if force_rotation:
        info_handler = next(
            handler for handler in timed_handlers if handler.baseFilename.endswith("info.log")
        )
        info_handler.doRollover()
        log_event(logger, logging.INFO, "test.rotation", "after rollover")

    for handler in handlers:
        handler.flush()


def test_formatter_uses_utc_and_component_prefix() -> None:
    """Test that the TTL formatter uses UTC and includes the component prefix."""
    record = logging.LogRecord(
        "api.test", logging.INFO, __file__, 1, "created", (), None,
    )
    record.created = 0
    record.operation = "lease.create"

    assert TTLLogFormatter("API").format(record) == (
        "[TTL-LAMa API]-[1970-01-01 00:00:00] : lease.create-created"
    )
    assert TTLLogFormatter("Scheduler").format(record).startswith(
        "[TTL-LAMa Scheduler]-[1970-01-01 00:00:00] : "
    )


def test_formatter_does_not_include_exception_details() -> None:
    """Test that exception messages are not appended to the log line."""
    secret = "private-key-sentinel"
    error = RuntimeError(secret)
    record = logging.LogRecord(
        "scheduler.test", logging.ERROR, __file__, 1, "operation failed", (),
        (type(error), error, None),
    )
    record.operation = "lease.provisioning.apply"
    formatted = TTLLogFormatter("Scheduler").format(record)

    assert formatted.endswith("lease.provisioning.apply-operation failed")
    assert secret not in formatted


def test_logs_are_routed_to_exact_level_files_and_rotate_daily(tmp_path: Path) -> None:
    """Test that logs are routed to exact-level files and rotate daily."""
    directory = tmp_path / "logs"
    process = multiprocessing.get_context("fork").Process(
        target=_configure_and_emit,
        args=(str(directory), "API", 1, True),
    )
    process.start()
    process.join(timeout=10)

    assert process.exitcode == 0
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    for filename in ("debug.log", "info.log", "warning.log", "error.log"):
        path = directory / filename
        assert path.exists()
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    info_content = (directory / "info.log").read_text(encoding="utf-8")
    assert "test.rotation-after rollover" in info_content
    archived_files = list(directory.glob("info.log.*"))
    assert archived_files
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in archived_files)
    assert re.search(r"\[TTL-LAMa API\]-\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]", info_content)
    archived_info = "\n".join(
        path.read_text(encoding="utf-8") for path in directory.glob("info.log.*")
    )
    assert "test.concurrent-event=0" in archived_info
    debug_content = (directory / "debug.log").read_text(encoding="utf-8")
    warning_content = (directory / "warning.log").read_text(encoding="utf-8")
    error_content = (directory / "error.log").read_text(encoding="utf-8")
    assert "test.debug-debug message" in debug_content
    assert "test.warning-warning message" in warning_content
    assert "test.error-error message" in error_content
    assert "test.debug" not in info_content + warning_content + error_content
    assert "test.warning" not in info_content + debug_content + error_content
    assert "test.error" not in info_content + debug_content + warning_content


def test_api_and_scheduler_processes_write_concurrently(tmp_path: Path) -> None:
    """Test that API and Scheduler processes can write logs concurrently."""
    directory = tmp_path / "logs"
    context = multiprocessing.get_context("fork")
    processes = [
        context.Process(target=_configure_and_emit, args=(str(directory), component, 25))
        for component in ("API", "Scheduler")
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=10)

    assert all(process.exitcode == 0 for process in processes)
    lines = (directory / "info.log").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 50
    assert sum(line.startswith("[TTL-LAMa API]-[") for line in lines) == 25
    assert sum(line.startswith("[TTL-LAMa Scheduler]-[") for line in lines) == 25


def test_subprocess_failure_summary_never_includes_stderr_secrets() -> None:
    """Test that the summary of a subprocess failure does not include secrets from stderr."""
    secret = "private-key-sentinel"
    error = subprocess.CalledProcessError(
        255,
        ["ssh"],
        stderr=f"remote failure included {secret}",
    )

    summary = format_subprocess_failure(error)

    assert summary == "exit status 255"
    assert secret not in summary
