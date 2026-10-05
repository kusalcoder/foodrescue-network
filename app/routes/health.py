"""
Health-check route.

This is intentionally the very first API endpoint in the project.
It lets us verify that:
    1. Flask is running.
    2. The app factory / configuration loaded without errors.
    3. (Phase 2+) The PostgreSQL database connection is alive.

A monitoring tool, load balancer, or a developer running the project
for the first time can hit this endpoint to confirm the service is up
end-to-end, including the database.
"""

from flask import Blueprint, jsonify
from sqlalchemy import text

from app.extensions import db

health_bp = Blueprint("health", __name__)


@health_bp.route("/health", methods=["GET"])
def health_check():
    """
    GET /api/health

    Returns a JSON payload confirming the API — and, starting in
    Phase 2, the database — are reachable. No authentication required;
    this endpoint must always be reachable so external tools can
    monitor uptime.
    """
    db_status = "healthy"
    try:
        # A trivial query is the standard way to confirm the database
        # connection pool can actually reach PostgreSQL, not just that
        # SQLAlchemy is configured.
        db.session.execute(text("SELECT 1"))
    except Exception:
        db_status = "unreachable"

    overall_success = db_status == "healthy"

    return (
        jsonify(
            success=overall_success,
            message="FoodRescue Network API is running"
            if overall_success
            else "FoodRescue Network API is running, but the database is unreachable",
            data={
                "service": "foodrescue-network-api",
                "status": "healthy" if overall_success else "degraded",
                "database": db_status,
            },
        ),
        200 if overall_success else 503,
    )
