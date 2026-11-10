"""Configure the Gunicorn WSGI server.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
import os
from typing import Any

from api.config import FlaskSettings
from api.logging_config import configure_logging

configure_logging("API", os.environ.get("TTL_LAMA_LOG_LEVEL", "info"))
settings = FlaskSettings()
configure_logging("API", settings.LOG_LEVEL)
bind = f"{settings.SERVER_HOST}:{settings.SERVER_PORT}" # pylint: disable=C0103
preload_app = True # pylint: disable=C0103
workers = 2 # pylint: disable=C0103
worker_class = "gthread" # pylint: disable=C0103
threads = 4 # pylint: disable=C0103
timeout = 30 # pylint: disable=C0103
accesslog = None # pylint: disable=C0103
errorlog = "-" # pylint: disable=C0103


def post_fork(_server: Any, _worker: Any) -> None:
    """Initialize process-owned handlers after each Gunicorn worker fork."""
    configure_logging("API", settings.LOG_LEVEL)


def when_ready(server: Any) -> None:
    """Release preloaded database sessions and connections before workers fork."""
    application = server.app.wsgi()
    application.extensions["database_config"].close()
