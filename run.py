"""
Entry point for running the FoodRescue Network API locally.

Usage:
    python run.py

This is only used for local development. In production you would
run the app through a WSGI server (e.g. gunicorn) instead of Flask's
built-in dev server — that's noted in the README.
"""

import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 5000))
    # debug=True is fine for local development because it's driven by
    # the DevelopmentConfig.DEBUG flag (from FLASK_ENV), not hardcoded.
    app.run(host=host, port=port, debug=app.config.get("DEBUG", False))
