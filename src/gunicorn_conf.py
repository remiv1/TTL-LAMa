"""Configure the Gunicorn WSGI server.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from api.config import FlaskSettings

settings = FlaskSettings()
bind = f"{settings.SERVER_HOST}:{settings.SERVER_PORT}"
workers = 1
timeout = 30
accesslog = "-"
errorlog = "-"
