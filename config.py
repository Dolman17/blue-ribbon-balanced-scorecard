import os
import secrets
import warnings
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    if not SECRET_KEY:
        if os.environ.get("BSC_DEV_MODE") == "1":
            warnings.warn("BSC_DEV_MODE uses an ephemeral session key. Never set this in production.", RuntimeWarning)
            SECRET_KEY = secrets.token_hex(32)
        else:
            raise RuntimeError("SECRET_KEY is required. Set a random 32+ character SECRET_KEY in Railway variables.")
    if len(SECRET_KEY) < 32 and os.environ.get("BSC_DEV_MODE") != "1":
        raise RuntimeError("SECRET_KEY must contain at least 32 characters.")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("BSC_DEV_MODE") != "1"
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = os.environ.get("BSC_DEV_MODE") != "1"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 12
    ADMIN_SETUP_TOKEN = os.environ.get("ADMIN_SETUP_TOKEN", "")
    if ADMIN_SETUP_TOKEN and len(ADMIN_SETUP_TOKEN) < 32:
        raise RuntimeError("ADMIN_SETUP_TOKEN must contain at least 32 characters.")
    DATABASE_PATH = os.environ.get("DATABASE_PATH", str(BASE_DIR / "instance" / "bsc.db"))
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{DATABASE_PATH}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 20 * 1024 * 1024
