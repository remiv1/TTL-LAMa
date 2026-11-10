"""Configure process-aware logging for the API and scheduler.

.. functions::
    - ``configure_logging``: Configure UTC log files for one application process.
    - ``log_event``: Emit an event with an explicit operation name.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from __future__ import annotations

import logging
import os
import re
import stat
import time
from pathlib import Path
from typing import Literal

from concurrent_log_handler import ConcurrentTimedRotatingFileHandler

LogComponent = Literal["API", "Scheduler"]
LOG_DIRECTORY = Path(os.environ.get("TTL_LAMA_LOG_DIRECTORY", "/data/logs"))
LOG_RETENTION_DAYS = 30
_OPERATION_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
_MINIMUM_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}
_LEVEL_FILES = (
    (logging.ERROR, "error.log"),
    (logging.WARNING, "warning.log"),
    (logging.INFO, "info.log"),
    (logging.DEBUG, "debug.log"),
)


class _ExactLevelFilter(logging.Filter):
    """Keep a record only in the file matching its severity.

    :param level: Severity level to filter.
    :type level: int

    .. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """

    def __init__(self, level: int) -> None:
        super().__init__()
        self.level = level

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter a log record based on its severity level.

        :param record: Log record to filter.
        :type record: logging.LogRecord
        :return: True if the record should be kept, False otherwise.
        :rtype: bool
        """
        if self.level == logging.ERROR:
            return record.levelno >= logging.ERROR
        return record.levelno == self.level


class TTLLogFormatter(logging.Formatter):
    """Format a one-line event without exception or stack trace contents.

    :param component: Process origin included in every log line.
    :type component: LogComponent

    .. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
    .. version:: 1.0.0
    """

    converter = time.gmtime

    def __init__(self, component: LogComponent) -> None:
        super().__init__(datefmt="%Y-%m-%d %H:%M:%S")
        self.component = component

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record into a single line string.

        :param record: Log record to format.
        :type record: logging.LogRecord
        :return: Formatted log line.
        :rtype: str
        """
        operation = getattr(record, "operation", record.name)
        if not isinstance(operation, str) or not _OPERATION_PATTERN.fullmatch(operation):
            operation = "runtime"
        message = " ".join(record.getMessage().splitlines())
        timestamp = self.formatTime(record, self.datefmt)
        return f"[TTL-LAMa {self.component}]-[{timestamp}] : {operation}-{message}"


def configure_logging(
    component: LogComponent,
    level: str,
    log_directory: Path | None = None,
) -> None:
    """Configure exact-level, UTC rotating files for the current process.

    :param component: Process origin included in every log line.
    :type component: LogComponent
    :param level: Minimum configured severity, such as ``INFO`` or ``DEBUG``.
    :type level: str
    :param log_directory: Optional log directory, primarily for isolated tests.
    :type log_directory: pathlib.Path | None
    :raises ValueError: If the component or logging level is invalid.
    :raises OSError: If the log directory cannot be created securely.
    """
    if component not in ("API", "Scheduler"):
        raise ValueError("Invalid TTL-LAMa log component")

    minimum_level = _MINIMUM_LEVELS.get(level.upper())
    if minimum_level is None:
        raise ValueError("Invalid TTL-LAMa log level")

    directory = log_directory or LOG_DIRECTORY
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if stat.S_IMODE(directory.stat().st_mode) & 0o077:
        raise PermissionError("TTL-LAMa log directory permissions must be 0700")

    formatter = TTLLogFormatter(component)
    handlers: list[ConcurrentTimedRotatingFileHandler] = []
    for severity, filename in _LEVEL_FILES:
        log_path = directory / filename
        descriptor = os.open(log_path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
        finally:
            os.close(descriptor)
        handler = ConcurrentTimedRotatingFileHandler(
            str(log_path),
            when="midnight",
            interval=1,
            backupCount=LOG_RETENTION_DAYS,
            utc=True,
            encoding="utf-8",
            chmod=0o600,
            umask=0o077,
        )
        handler.setLevel(logging.DEBUG)
        handler.addFilter(_ExactLevelFilter(severity))
        handler.setFormatter(formatter)
        handlers.append(handler)

    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        handler.close()
    root_logger.setLevel(minimum_level)
    for handler in handlers:
        root_logger.addHandler(handler)

    for logger_name in ("gunicorn.error", "gunicorn.access", "werkzeug", "main"):
        process_logger = logging.getLogger(logger_name)
        for handler in process_logger.handlers[:]:
            process_logger.removeHandler(handler)
            handler.close()
        process_logger.setLevel(logging.NOTSET)
        process_logger.propagate = True


def log_event(
    logger: logging.Logger,
    level: int,
    operation: str,
    message: str,
    *args: object,
) -> None:
    """Emit a one-line event with an explicit operation label.

    :param logger: Logger that owns the event.
    :type logger: logging.Logger
    :param level: Python logging severity.
    :type level: int
    :param operation: Stable, non-sensitive operation identifier.
    :type operation: str
    :param message: Safe, non-sensitive event description.
    :type message: str
    :param args: Safe values interpolated into the event description.
    :type args: object
    """
    logger.log(level, message, *args, extra={"operation": operation})
