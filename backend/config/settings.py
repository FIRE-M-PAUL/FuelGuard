"""Application configuration (FuelGuard backend)."""
from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_ROOT.parent


def default_sqlite_path() -> Path:
    """
    Default SQLite location when ``DATABASE_PATH`` is not set.

    Prefer ``fuelguard.db`` or ``database.db`` at the project root (where local
    dev and older assignments often store data), then fall back to
    ``backend/database/fuelguard.db`` for a clean tree.
    """
    root_primary = PROJECT_ROOT / "fuelguard.db"
    root_legacy = PROJECT_ROOT / "database.db"
    packaged = BACKEND_ROOT / "database" / "fuelguard.db"
    if root_primary.is_file():
        return root_primary
    if root_legacy.is_file():
        return root_legacy
    return packaged


class Config:
    """Default configuration."""

    BASE_DIR = PROJECT_ROOT
    _IS_DEV = os.getenv("FLASK_ENV", "production").strip().lower() == "development"
    SECRET_KEY = os.getenv(
        "SECRET_KEY",
        "43532047726F757020536978" if _IS_DEV else None,
    )
    JWT_SECRET_KEY = os.getenv(
        "JWT_SECRET",
        "43532047726F757020536978" if _IS_DEV else None,
    )
    DEBUG = os.getenv("DEBUG", "False").strip().lower() == "true"
    TESTING = False

    # Override with DATABASE_PATH env for Docker/production.
    DATABASE_PATH = os.environ.get("DATABASE_PATH", str(default_sqlite_path()))

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0").strip() in {"1", "true", "yes", "on"}
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
    SESSION_IDLE_MINUTES = int(os.environ.get("SESSION_IDLE_MINUTES", "10"))
    SESSION_IDLE_SECONDS = SESSION_IDLE_MINUTES * 60
    SESSION_COOKIE_MAX_AGE_MINUTES = int(os.environ.get("SESSION_COOKIE_MAX_AGE_MINUTES", "15"))
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=SESSION_COOKIE_MAX_AGE_MINUTES)

    WTF_CSRF_TIME_LIMIT = None

    ADMIN_INITIAL_PASSWORD = os.environ.get("ADMIN_INITIAL_PASSWORD")
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@fuelguard.local")
    ADMIN_SYNC_PASSWORD_AT_STARTUP = os.environ.get(
        "ADMIN_SYNC_PASSWORD_AT_STARTUP", ""
    ).strip().lower() in {"1", "true", "yes", "on"}

    # Logs directory (system.log written by logging_service / audit file log).
    LOGS_DIR = os.environ.get("FUELGUARD_LOGS_DIR", str(BACKEND_ROOT / "logs"))


class TestConfig(Config):
    """Testing configuration."""

    TESTING = True
    DEBUG = True
    WTF_CSRF_ENABLED = False
    SECRET_KEY = os.environ.get("SECRET_KEY", "t" * 48)
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET", "j" * 48)


def validate_production_config(config_class: type) -> None:
    if getattr(config_class, "TESTING", False):
        return
    if not getattr(config_class, "SECRET_KEY", None):
        raise RuntimeError("SECRET_KEY environment variable is required.")
    if not getattr(config_class, "JWT_SECRET_KEY", None):
        raise RuntimeError("JWT_SECRET environment variable is required.")
