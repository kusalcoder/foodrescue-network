"""Create the application schema in a new managed PostgreSQL database."""

from app import create_app
from app.extensions import db


app = create_app("production")

with app.app_context():
    db.create_all()
    print("Database schema is ready.")
