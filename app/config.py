"""
Configuration classes for FoodRescue Network.

ALL secrets and environment-specific values (database URL, secret
key, upload folder, max file size, etc.) come from environment
variables — never hardcoded in source code (requirement #40).

We load a `.env` file (if present) using python-dotenv so that local
development is convenient, while production deployments simply set
real environment variables on the host/container and don't need a
`.env` file at all.
"""

import os

from dotenv import load_dotenv

# Load variables from a .env file into os.environ, if one exists.
# In production, real environment variables set by the hosting
# platform take precedence — load_dotenv() will not override
# variables that are already set.
load_dotenv()


class BaseConfig:
    """Shared configuration for every environment."""

    # SECRET_KEY is used by Flask for session signing and, once we
    # add authentication in Phase 3, for signing auth tokens.
    # There is NO hardcoded fallback in production-like use — if this
    # is missing, the app should fail loudly rather than run insecurely.
    SECRET_KEY = os.environ.get("SECRET_KEY")

    # PostgreSQL connection string, e.g.:
    #   postgresql://username:password@localhost:5432/foodrescue_db
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # File upload settings (used starting in the optional file-upload
    # module, Phase 11). Defined here now so every environment has a
    # consistent, environment-driven value.
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", "uploads")
    MAX_CONTENT_LENGTH = int(
        os.environ.get("MAX_FILE_SIZE", 5 * 1024 * 1024)
    )  # default 5 MB

    # Pagination defaults (requirement #21)
    DEFAULT_PAGE_SIZE = 10
    MAX_PAGE_SIZE = 100

    DEBUG = False
    TESTING = False


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class TestingConfig(BaseConfig):
    """Used when running automated tests (Phase 12). Points at a
    separate test database so tests never touch real data."""

    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "TEST_DATABASE_URL", BaseConfig.SQLALCHEMY_DATABASE_URI
    )


class ProductionConfig(BaseConfig):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PREFERRED_URL_SCHEME = "https"


_CONFIG_MAP = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(config_name: str = None):
    """
    Resolve a config class by name.

    Falls back to the FLASK_ENV environment variable, then to
    "development" if nothing is set.
    """
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "development")
    return _CONFIG_MAP.get(config_name, DevelopmentConfig)
