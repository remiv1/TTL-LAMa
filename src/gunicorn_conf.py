"""Configure the Gunicorn WSGI server.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from api.config import FlaskSettings

settings = FlaskSettings()
bind = f"{settings.SERVER_HOST}:{settings.SERVER_PORT}" # pylint: disable=C0103
workers = 1 # pylint: disable=C0103
timeout = 30 # pylint: disable=C0103
accesslog = "-" # pylint: disable=C0103
errorlog = "-" # pylint: disable=C0103
