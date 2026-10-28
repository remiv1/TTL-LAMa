"""Expose the TTL-LAMa WSGI application.

.. module_author:: Rémi Verschuur <rverschuur@audit-io.fr>
.. version:: 1.0.0
"""
from flask import Response, jsonify
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from api.bootstrap import create_app, get_sessions

app = create_app()

@app.get("/health")
def health() -> tuple[Response, int]:
    """Return service readiness based on database connectivity.

    :returns: A JSON response and the corresponding HTTP status.
    :rtype: tuple[Response, int]
    """
    session = get_sessions()
    stmt = select(1)
    try:
        status = session.execute(stmt).scalar() is not None
    except SQLAlchemyError:
        return jsonify(
            status="error",
            database="unreachable",
        ), 500
    if not status:
        return jsonify(
            status="error",
            database="unreachable",
        ), 500
    return jsonify(
        status="ok",
        database="reachable",
    ), 200
