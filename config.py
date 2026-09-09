import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = os.environ.get(
        "SECRET_KEY",
        "change-me-for-production"
    )

    DATABASE_PATH = os.environ.get(
        "DATABASE_PATH",
        str(BASE_DIR / "instance" / "bsc.db")
    )

    SQLALCHEMY_DATABASE_URI = f"sqlite:///{DATABASE_PATH}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 20 * 1024 * 1024