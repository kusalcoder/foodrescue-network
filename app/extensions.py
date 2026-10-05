"""
Shared Flask extension instances.

Why a separate `extensions.py` file?
    If we created `db = SQLAlchemy()` directly inside `app/__init__.py`,
    every model file would need to import from `app` — which then
    imports `create_app`, which imports the routes, which import the
    models... a circular import.

    Instead, extensions live in their own tiny module with no other
    project imports. Models import `db` from here. `app/__init__.py`
    also imports `db` from here and calls `db.init_app(app)`. Nobody
    has to import `app/__init__.py` to get access to the database.
"""

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

db = SQLAlchemy()
migrate = Migrate()
