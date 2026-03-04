"""Application logging setup with rotating file output."""

import logging
from logging.handlers import RotatingFileHandler

from .constants import LOG_DIR


def configure_logging() -> None:
    """Configure root logger once for file+console diagnostics."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "app.log"

    root = logging.getLogger()
    if root.handlers:
        return

    root.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    rotating = RotatingFileHandler(str(log_path), maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    rotating.setFormatter(formatter)
    root.addHandler(rotating)

    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    root.addHandler(stream)

