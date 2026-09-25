"""
FoodRescue Network — Application Factory

This module wires together the Flask app instance. We use the
"application factory" pattern (a function that builds and returns
the app) instead of a single global `app = Flask(__name__)` object.

Why use a factory instead of a global app object?
    1. Testing: tests can create a fresh app instance with test
       configuration, without interfering with a "real" running app.
    2. Multiple configurations: you can build a "development" app
       and a "production" app from the same code with different
       config values (e.g. a different DATABASE_URL).
    3. Avoids circular imports: routes/models can import `db`
       (the database extension) without needing the app object to
       already exist.

Phase 1 registered a health-check route and basic error handling.
Phase 2 adds the PostgreSQL/SQLAlchemy database layer: `db.init_app()`
wires SQLAlchemy to this app, `migrate.init_app()` wires up
Flask-Migrate (Alembic) for schema migrations, and every model is
imported so Flask-Migrate can see the full schema.

Phase 12 (frontend polish): error handlers now return JSON for
/api/* requests (unchanged behavior) but render HTML error pages
for regular frontend page requests.
"""

import logging

from flask import Flask, jsonify, render_template, request

from app.config import get_config
from app.extensions import db, migrate


def create_app(config_name: str = None) -> Flask:
    """
    Application factory.

    Args:
        config_name: which config class to load ("development",
            "testing", "production"). If None, it is read from the
            FLASK_ENV environment variable (defaults to "development").

    Returns:
        A fully configured Flask application instance.
    """
    app = Flask(__name__)

    # Load configuration (see app/config.py). This pulls values such
    # as SECRET_KEY and DATABASE_URL from environment variables —
    # never hardcoded here.
    app.config.from_object(get_config(config_name))

    _configure_logging(app)
    _init_extensions(app)
    _register_error_handlers(app)
    _register_blueprints(app)

    return app


def _init_extensions(app: Flask) -> None:
    """
    Wire up Flask-SQLAlchemy and Flask-Migrate.

    Importing `app.models` here (not at the top of the file) is
    deliberate: models import `db` from `app.extensions`, and we want
    that import to happen only after `db` already exists, keeping the
    dependency direction one-way (models -> extensions, never
    extensions -> models) and avoiding circular imports.
    """
    db.init_app(app)
    migrate.init_app(app, db)

    with app.app_context():
        import app.models  # noqa: F401  (registers models with SQLAlchemy)


def _configure_logging(app: Flask) -> None:
    """Basic logging setup so we can see request/error info in the
    console during development. Later phases (audit logging) build
    a persistent, database-backed log on top of this — this is just
    plain process logging, not the audit trail."""
    logging.basicConfig(
        level=logging.DEBUG if app.config.get("DEBUG") else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _wants_json() -> bool:
    """True for /api/* requests, which should keep getting the JSON
    error envelope. False for regular frontend page requests, which
    should get a rendered HTML error page instead."""
    return request.path.startswith("/api/")


def _register_error_handlers(app: Flask) -> None:
    """
    Central error handling (requirement #41 in the spec).

    /api/* requests get the JSON envelope (requirement #29):

        {"success": false, "message": "...", "error": "SOME_CODE"}

    Frontend page requests get a rendered HTML error page instead
    (Phase 12 polish).

    We never leak Python stack traces or internal exception text to
    the client — only a safe, generic message plus a machine-readable
    error code.
    """

    @app.errorhandler(404)
    def handle_not_found(e):
        if _wants_json():
            return (
                jsonify(
                    success=False,
                    message="The requested resource was not found.",
                    error="NOT_FOUND",
                ),
                404,
            )
        return render_template("errors/404.html"), 404

    @app.errorhandler(405)
    def handle_method_not_allowed(e):
        return (
            jsonify(
                success=False,
                message="This HTTP method is not allowed for this endpoint.",
                error="METHOD_NOT_ALLOWED",
            ),
            405,
        )

    @app.errorhandler(500)
    def handle_internal_error(e):
        # Log the real exception server-side for debugging, but never
        # send its details back to the client.
        app.logger.exception("Unhandled server error")
        if _wants_json():
            return (
                jsonify(
                    success=False,
                    message="An unexpected server error occurred.",
                    error="INTERNAL_SERVER_ERROR",
                ),
                500,
            )
        return render_template("errors/500.html"), 500

    @app.errorhandler(Exception)
    def handle_uncaught_exception(e):
        # Flask's HTTPExceptions (404, 405, etc.) already have status
        # codes; anything else is an unexpected bug — treat as 500.
        from werkzeug.exceptions import HTTPException

        if isinstance(e, HTTPException):
            return e
        app.logger.exception("Unhandled exception")
        if _wants_json():
            return (
                jsonify(
                    success=False,
                    message="An unexpected server error occurred.",
                    error="INTERNAL_SERVER_ERROR",
                ),
                500,
            )
        return render_template("errors/500.html"), 500


def _register_blueprints(app: Flask) -> None:
    """
    Register Flask blueprints (route modules).

    Phase 3 adds authentication (/api/auth/*) and a minimal protected
    profile endpoint (/api/profile). Phase 4 adds the provider module
    (/api/providers/*, /api/listings/*). Phase 5 adds the recipient
    module (/api/recipients/*) and public browsing/search/pagination
    on GET /api/listings. Phase 6 adds the request workflow
    (/api/requests/*). Phase 7 adds pickup scheduling/confirmation
    (/api/pickups/*, plus POST /api/requests/<id>/schedule-pickup) and
    distribution history (/api/distributions/*). Phase 9 adds
    in-app notifications (/api/notifications/*). Phase 10 adds
    read-only reporting/aggregation endpoints (/api/reports/*). Phase
    11 adds admin-only user management (/api/admin/*) and the
    audit-log read endpoint (/api/audit-logs).
    """
    from app.routes.health import health_bp
    from app.routes.auth import auth_bp
    from app.routes.profile import profile_bp
    from app.routes.providers import providers_bp
    from app.routes.recipients import recipients_bp
    from app.routes.listings import listings_bp
    from app.routes.requests import requests_bp
    from app.routes.pickups import pickups_bp
    from app.routes.distributions import distributions_bp
    from app.routes.notifications import notifications_bp
    from app.routes.reports import reports_bp
    from app.routes.admin import admin_bp
    from app.routes.audit import audit_bp
    from app.routes.frontend import frontend_bp

    app.register_blueprint(health_bp, url_prefix="/api")
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(profile_bp, url_prefix="/api")
    app.register_blueprint(providers_bp, url_prefix="/api/providers")
    app.register_blueprint(recipients_bp, url_prefix="/api/recipients")
    app.register_blueprint(listings_bp, url_prefix="/api/listings")
    app.register_blueprint(requests_bp, url_prefix="/api/requests")
    app.register_blueprint(pickups_bp, url_prefix="/api/pickups")
    app.register_blueprint(distributions_bp, url_prefix="/api/distributions")
    app.register_blueprint(notifications_bp, url_prefix="/api/notifications")
    app.register_blueprint(reports_bp, url_prefix="/api/reports")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(audit_bp, url_prefix="/api/audit-logs")

    # Frontend Phase 1: server-rendered pages at the site root,
    # separate from the /api/* JSON blueprints above.
    app.register_blueprint(frontend_bp)