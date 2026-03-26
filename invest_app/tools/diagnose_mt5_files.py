"""
Diagnose-Skript: MT5 Datei-Kommunikation
Prüft ob Python und MT5 EA die gleichen Pfade verwenden.
Ausführen auf Windows: python tools/diagnose_mt5_files.py
"""
import os
import json
import sys
from pathlib import Path

def main():
    print("=" * 60)
    print("InvestApp – MT5 Datei-Kommunikation Diagnose")
    print("=" * 60)

    # 1. Common Files Pfad bestimmen
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        common_files = Path(appdata) / "MetaQuotes" / "Terminal" / "Common" / "Files"
    else:
        common_files = None

    print(f"\n[1] APPDATA: {appdata or 'NICHT GESETZT (kein Windows?)'}")
    print(f"[2] Erwarteter Common Files Pfad:\n    {common_files}")

    if common_files:
        exists = common_files.exists()
        print(f"[3] Pfad existiert: {'✅ JA' if exists else '❌ NEIN – MT5 noch nie gestartet?'}")
    else:
        print("[3] Pfad: ❌ APPDATA nicht verfügbar")

    # 2. mt5_zones.json prüfen
    print("\n--- mt5_zones.json ---")
    if common_files:
        zones_file = common_files / "mt5_zones.json"
        if zones_file.exists():
            print(f"✅ Gefunden: {zones_file}")
            try:
                data = json.loads(zones_file.read_text(encoding="utf-8"))
                symbols = list(data.keys()) if isinstance(data, dict) else "Liste"
                print(f"   Inhalt: {len(data) if isinstance(data, dict) else len(data)} Einträge – Symbole: {symbols[:5]}")
            except Exception as e:
                print(f"   ⚠️  Lesefehler: {e}")
        else:
            print(f"❌ NICHT gefunden: {zones_file}")
            print("   → main.py starten damit ChartExporter die Datei schreibt")

    # Output-Fallback prüfen
    output_zones = Path(__file__).parent.parent / "Output" / "mt5_zones.json"
    if output_zones.exists():
        print(f"⚠️  Datei liegt im Output-Ordner (FALSCHER Pfad für EA): {output_zones}")
        print("   → config.json: mt5_common_files_path muss leer sein für Auto-Erkennung")

    # 3. pending_order.json prüfen
    print("\n--- pending_order.json ---")
    if common_files:
        order_file = common_files / "pending_order.json"
        if order_file.exists():
            print(f"✅ Gefunden: {order_file}")
            try:
                data = json.loads(order_file.read_text(encoding="utf-8"))
                print(f"   Status: {data.get('status', 'unbekannt')}")
            except Exception as e:
                print(f"   ⚠️  Lesefehler: {e}")
        else:
            print(f"ℹ️  Noch nicht vorhanden: {order_file}")
            print("   → Normal, wird erst bei Order-Ausführung erstellt")

    # 4. available_symbols.json prüfen
    print("\n--- available_symbols.json ---")
    if common_files:
        sym_file = common_files / "available_symbols.json"
        if sym_file.exists():
            print(f"✅ Gefunden: {sym_file}")
            try:
                data = json.loads(sym_file.read_text(encoding="utf-8"))
                count = len(data) if isinstance(data, list) else len(data.get("symbols", []))
                print(f"   {count} Symbole verfügbar")
            except Exception as e:
                print(f"   ⚠️  Lesefehler: {e}")
        else:
            print(f"❌ NICHT gefunden: {sym_file}")
            print("   → EA auf Chart laden und einmal ticken lassen (ExportAvailableSymbols)")

    # 5. config.json prüfen
    print("\n--- config.json ---")
    config_path = Path(__file__).parent.parent / "config.json"
    if config_path.exists():
        try:
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            mt5_cfg = cfg.get("mt5", {})
            explicit_path = mt5_cfg.get("mt5_common_files_path", "")
            zones_file_cfg = mt5_cfg.get("mt5_zones_file", "")
            print(f"   mt5_common_files_path: '{explicit_path}' {'✅ leer = Auto-Erkennung' if not explicit_path else '⚠️ explizit gesetzt'}")
            print(f"   mt5_zones_file:        '{zones_file_cfg}' {'✅' if zones_file_cfg == 'mt5_zones.json' else '⚠️ unerwartet'}")
        except Exception as e:
            print(f"   ❌ Lesefehler: {e}")
    else:
        print(f"❌ config.json nicht gefunden: {config_path}")

    # 6. Zusammenfassung
    print("\n" + "=" * 60)
    print("FAZIT")
    print("=" * 60)
    if common_files and common_files.exists():
        print("✅ Pfad korrekt – EA und Python verwenden denselben Ordner")
        print("✅ EA muss auf Chart laufen (AutoTrading aktiv)")
        if not (common_files / "mt5_zones.json").exists():
            print("⚠️  mt5_zones.json fehlt noch → main.py einmal starten")
        if not (common_files / "available_symbols.json").exists():
            print("⚠️  available_symbols.json fehlt → EA neu laden")
    else:
        print("❌ Common Files Pfad nicht gefunden")
        print("   → MT5 installieren und einmal starten")
        print("   → Oder mt5_common_files_path in config.json manuell setzen")

if __name__ == "__main__":
    main()
