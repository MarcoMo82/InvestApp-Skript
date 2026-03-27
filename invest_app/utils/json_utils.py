"""
Hilfsfunktionen für robustes JSON-Lesen aus MT5-generierten Dateien.

MQL5 schreibt JSON-Dateien standardmäßig in UTF-16 LE mit BOM (0xFF 0xFE).
Diese Hilfsfunktion erkennt die Kodierung automatisch und dekodiert korrekt.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_json_robust(path: str | Path) -> Any:
    """
    Liest eine JSON-Datei encoding-robust (UTF-16 BOM, UTF-8 BOM, UTF-8).

    MQL5 schreibt ohne FILE_ANSI in UTF-16 LE mit BOM (0xFF 0xFE).
    Diese Funktion erkennt den BOM und dekodiert entsprechend.

    Args:
        path: Pfad zur JSON-Datei.

    Returns:
        Geparste JSON-Daten (dict, list, …).

    Raises:
        FileNotFoundError: Wenn die Datei nicht existiert.
        json.JSONDecodeError: Bei ungültigem JSON-Inhalt.
    """
    raw = Path(path).read_bytes()

    if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
        content = raw.decode('utf-16')
    elif raw[:3] == b'\xef\xbb\xbf':
        content = raw.decode('utf-8-sig')
    else:
        content = raw.decode('utf-8')

    return json.loads(content)
