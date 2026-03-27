"""
SymbolProvider: Eigenständige Symbol-Discovery – unabhängig vom Daten-Connector.

Priorität:
1. available_symbols.json vom MT5 EA (Common Files)
2. OrderDB.get_active_symbols() (Crash-Recovery / letzter Zyklus)

Kein Fallback auf hardcodierte Symbole.
Wenn keine Quelle verfügbar → SymbolProviderError (System stoppt).
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Optional


class SymbolProviderError(Exception):
    """Wird geworfen wenn keine Symbol-Quelle verfügbar ist."""
    pass


class SymbolProvider:
    """
    Eigenständige Symbol-Discovery – unabhängig vom Daten-Connector.

    Priorität:
    1. available_symbols.json vom MT5 EA (Common Files)
    2. OrderDB.get_active_symbols() (Crash-Recovery / letzter Zyklus)

    Kein Fallback auf hardcodierte Symbole.
    Wenn keine Quelle verfügbar → SymbolProviderError (System stoppt).
    """

    def __init__(self, config: Any, order_db: Optional[Any] = None) -> None:
        self.config = config
        self.order_db = order_db
        self.logger = logging.getLogger(__name__)

    def get_symbols(self) -> list[str]:
        """
        Gibt verfügbare Symbole zurück.

        1. Sucht available_symbols.json im MT5 Common Files Pfad
        2. Prüft Datei-Alter (max. symbol_provider_max_file_age_minutes)
        3. Falls nicht gefunden + OrderDB vorhanden → DB-Symbole als Fallback
        4. Falls weder Datei noch DB-Symbole → SymbolProviderError

        Returns:
            Liste der verfügbaren Symbol-Namen

        Raises:
            SymbolProviderError: Wenn keine Quelle verfügbar ist
        """
        max_age = getattr(self.config, "symbol_provider_max_file_age_minutes", 5)
        common_path = self._find_common_files_path()
        filename = getattr(self.config, "mt5_symbols_file", "available_symbols.json")
        symbols_file = common_path / filename

        if symbols_file.exists():
            age_minutes = (time.time() - symbols_file.stat().st_mtime) / 60
            if age_minutes > max_age:
                raise SymbolProviderError(
                    f"available_symbols.json ist {age_minutes:.0f} Min alt "
                    f"(max. {max_age} Min erlaubt) – MT5 EA nicht aktiv"
                )

            try:
                with open(symbols_file, encoding="utf-8") as f:
                    data = json.load(f)

                symbols = self._parse_symbols(data)
                if symbols:
                    self.logger.info(
                        f"[SymbolProvider] {len(symbols)} Symbole aus available_symbols.json geladen "
                        f"(Alter: {age_minutes:.1f} Min)"
                    )
                    return symbols
                self.logger.warning("[SymbolProvider] available_symbols.json vorhanden aber leer")
            except SymbolProviderError:
                raise
            except Exception as e:
                self.logger.warning(
                    f"[SymbolProvider] Fehler beim Lesen von available_symbols.json: {e}"
                )

        # Fallback: OrderDB (Crash-Recovery / letzter bekannter Zustand)
        if self.order_db is not None:
            try:
                db_symbols = self.order_db.get_active_symbols()
                if db_symbols:
                    self.logger.warning(
                        "[SymbolProvider] MT5 EA nicht erreichbar – verwende letzte bekannte Symbole aus DB"
                    )
                    return db_symbols
            except Exception as e:
                self.logger.warning(f"[SymbolProvider] OrderDB-Abruf fehlgeschlagen: {e}")

        raise SymbolProviderError(
            "MT5 EA nicht erreichbar und keine Symbole in DB – System stoppt"
        )

    def _find_common_files_path(self) -> Path:
        """Gibt den MT5 Common Files Pfad zurück (via gemeinsamer Pfad-Logik)."""
        from utils.mt5_paths import get_common_files_path
        return get_common_files_path(self.config)

    def _parse_symbols(self, data: Any) -> list[str]:
        """
        Parst Symbole aus JSON-Daten.

        Unterstützte Formate:
        - Einfaches Array: ["EURUSD", "GBPUSD", ...]
        - Array mit Objekten: [{"name": "EURUSD"}, ...]
        - Dict mit symbols-Key: {"symbols": [{"name": "EURUSD"}, ...]}
        """
        if isinstance(data, list):
            symbols = []
            for item in data:
                if isinstance(item, str):
                    symbols.append(item)
                elif isinstance(item, dict) and item.get("name"):
                    symbols.append(item["name"])
            return symbols
        elif isinstance(data, dict):
            return [s["name"] for s in data.get("symbols", []) if s.get("name")]
        return []
