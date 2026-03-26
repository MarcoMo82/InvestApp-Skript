"""
Gemeinsame MT5 Pfad-Ermittlung für SymbolProvider und andere Komponenten.

Zentrale Logik für die Erkennung des MT5 Common Files Verzeichnisses.
Wird von symbol_provider.py genutzt – nicht duplizieren.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from utils.logger import get_logger

logger = get_logger(__name__)


def get_common_files_path(config: Any = None) -> Path:
    """
    Ermittelt den MT5 Common Files Pfad.

    Priorität:
    1. mt5_common_files_path aus Config (Override)
    2. Windows-Standard-Pfad via APPDATA (wenn Verzeichnis existiert)
    3. Fallback: Output-Verzeichnis des Projekts

    Args:
        config: Config-Objekt mit optionalem mt5_common_files_path-Attribut

    Returns:
        Path zum MT5 Common Files Verzeichnis
    """
    configured = getattr(config, "mt5_common_files_path", "") if config else ""
    if configured:
        return Path(configured)

    appdata = os.environ.get("APPDATA", "")
    if appdata:
        default = Path(appdata) / "MetaQuotes" / "Terminal" / "Common" / "Files"
        if default.exists():
            logger.info(f"[MT5Paths] Common Files Pfad auto-erkannt: {default}")
            return default

    output = Path(getattr(config, "output_dir", "Output")) if config else Path("Output")
    output.mkdir(exist_ok=True)
    logger.info(f"[MT5Paths] Common Files Pfad: Output-Verzeichnis {output}")
    return output
