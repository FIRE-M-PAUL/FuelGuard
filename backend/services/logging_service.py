"""Append-only system logging to logs/system.log."""
from __future__ import annotations

import logging
from pathlib import Path

from flask import current_app


def _log_path() -> Path:
    logs_dir = current_app.config.get("LOGS_DIR")
    if logs_dir:
        base = Path(str(logs_dir))
    else:
        root = current_app.config.get("PROJECT_ROOT")
        base = Path(root) / "logs" if root else Path(current_app.root_path).parent / "logs"
    base.mkdir(parents=True, exist_ok=True)
    return base / "system.log"


def get_system_logger() -> logging.Logger:
    logger = logging.getLogger("fuelguard.system")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    path = _log_path()
    fh = logging.FileHandler(path, encoding="utf-8")
    fh.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    )
    logger.addHandler(fh)
    logger.propagate = False
    return logger


def log_event(message: str, level: str = "info") -> None:
    try:
        logger = get_system_logger()
        getattr(logger, level.lower(), logger.info)(message)
    except Exception:
        pass
