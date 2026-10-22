"""Expose the TTL-LAMa WSGI application.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from flask import Response, jsonify

from api.bootstrap import create_app

app = create_app()

@app.get("/")
def index() -> dict[str, str]:
    """Return a basic status message.

    :returns: A JSON response with a message indicating the service is running.
    :rtype: dict[str, str]
    """
    return {"message": "TTL-LAMa is running"}

@app.get("/health")
def health() -> tuple[Response, int]:
    """Return service readiness based on database connectivity.

    :returns: A JSON response and the corresponding HTTP status.
    :rtype: tuple[Response, int]
    """
    return jsonify(status="ok"), 200
