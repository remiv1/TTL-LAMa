"""Configure the Gunicorn WSGI server.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from typing import Any

from api.config import FlaskSettings

settings = FlaskSettings()
bind = f"{settings.SERVER_HOST}:{settings.SERVER_PORT}" # pylint: disable=C0103
preload_app = True # pylint: disable=C0103
workers = 2 # pylint: disable=C0103
worker_class = "gthread" # pylint: disable=C0103
threads = 4 # pylint: disable=C0103
timeout = 30 # pylint: disable=C0103
accesslog = "-" # pylint: disable=C0103
errorlog = "-" # pylint: disable=C0103


def when_ready(server: Any) -> None:
    """Release preloaded database sessions and connections before workers fork."""
    application = server.app.wsgi()
    application.extensions["database_config"].close()
