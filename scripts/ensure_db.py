import time
from app import create_app
from app.extensions import db


app = create_app("production")

with app.app_context():
    max_retries = 5
    for attempt in range(1, max_retries + 1):
        try:
            db.create_all()
            print("Database schema is ready.")
            break
        except Exception as e:
            print(f"Database setup attempt {attempt}/{max_retries} note: {e}")
            if attempt < max_retries:
                time.sleep(2)
            else:
                print("Proceeding with application startup...")
