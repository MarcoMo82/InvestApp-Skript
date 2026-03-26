"""
Korrelations-Utilities: Verhindert gleichzeitige Trades auf hoch-korrelierten Symbolen.

Korrelationsgruppen (stellvertretend für historische Preis-Korrelation > 0.75):
- EUR-Gruppe: EURUSD ↔ GBPUSD ↔ EURGBP
- AUD/NZD-Gruppe: AUDUSD ↔ NZDUSD
- JPY-Gruppe: USDJPY ↔ EURJPY ↔ GBPJPY
- Gold (XAUUSD): isoliert – keine Korrelationsblockade
- CHF: USDCHF ist negativ zu EURUSD korreliert → Blockade aktiv
"""

from __future__ import annotations

# Symmetrische Korrelations-Map: pro Symbol die eng-korrelierten Partner
CORRELATED_PAIRS: dict[str, list[str]] = {
    "EURUSD":  ["GBPUSD", "EURGBP", "USDCHF"],
    "GBPUSD":  ["EURUSD", "EURGBP", "GBPJPY"],
    "EURGBP":  ["EURUSD", "GBPUSD"],
    "USDCHF":  ["EURUSD"],
    "AUDUSD":  ["NZDUSD"],
    "NZDUSD":  ["AUDUSD"],
    "USDJPY":  ["EURJPY", "GBPJPY"],
    "EURJPY":  ["USDJPY", "GBPJPY", "EURUSD"],
    "GBPJPY":  ["USDJPY", "EURJPY", "GBPUSD"],
    "USDCAD":  [],
    "XAUUSD":  [],   # Gold: isoliert – keine Blockade
    "BTCUSD":  [],
    "ETHUSD":  ["BTCUSD"],
}


def get_correlated_symbols(symbol: str) -> list[str]:
    """
    Gibt alle hoch-korrelierten Symbole für das übergebene Symbol zurück.

    Args:
        symbol: Trading-Symbol (z.B. "EURUSD")

    Returns:
        Liste korrelierter Symbole. Leere Liste wenn keine Korrelation definiert.
    """
    return CORRELATED_PAIRS.get(symbol, [])


def has_correlated_open_position(
    symbol: str, open_symbols: list[str]
) -> tuple[bool, str]:
    """
    Prüft ob bereits ein korreliertes Symbol in den offenen Positionen vorhanden ist.

    Args:
        symbol: Zu prüfendes Symbol
        open_symbols: Liste der aktuell offenen Symbole

    Returns:
        (True, blockierendes_symbol) wenn Korrelation gefunden
        (False, "") wenn kein Konflikt
    """
    correlated = get_correlated_symbols(symbol)
    for open_sym in open_symbols:
        if open_sym in correlated:
            return True, open_sym
    return False, ""
