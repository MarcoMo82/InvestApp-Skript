"""
Zentrales Logging-Setup für das InvestApp System.
File + Console Handler mit Rotation.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def get_logger(name: str, log_dir: Path | None = None, level: str = "INFO") -> logging.Logger:
    """
    Gibt einen konfigurierten Logger zurück.

    Args:
        name: Logger-Name (typischerweise __name__ des aufrufenden Moduls)
        log_dir: Verzeichnis für Log-Dateien. Wenn None, wird nur Console geloggt.
        level: Log-Level als String, z.B. 'INFO', 'DEBUG', 'WARNING'

    Returns:
        Konfigurierter Logger
    """
    logger = logging.getLogger(name)

    # Verhindert doppelte Handler bei wiederholtem Aufruf
    if logger.handlers:
        return logger

    log_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(log_level)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File Handler (mit Rotation)
    if log_dir is not None:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)

        log_file = log_dir / "invest_app.log"
        file_handler = RotatingFileHandler(
            filename=log_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # Separater Error-Log
        error_file = log_dir / "errors.log"
        error_handler = RotatingFileHandler(
            filename=error_file,
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=3,
            encoding="utf-8",
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        logger.addHandler(error_handler)

    # Verhindert Propagation zum Root-Logger
    logger.propagate = False

    return logger


def setup_root_logger(log_dir: Path, level: str = "INFO") -> None:
    """Konfiguriert den Root-Logger für das gesamte System."""
    get_logger("invest_app", log_dir=log_dir, level=level)
