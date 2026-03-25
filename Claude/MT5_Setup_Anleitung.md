# MT5 Setup-Anleitung für InvestApp

## 1. AutoTrading aktivieren

### Globaler Button (Toolbar)
1. MetaTrader 5 öffnen
2. In der Toolbar oben den Button **"AutoTrading"** (grüner Play-Button) aktivieren
3. Status: Grünes Symbol = AutoTrading aktiv | Rotes Symbol = deaktiviert

> **Wichtig:** Der globale AutoTrading-Button ist von den EA-Properties unabhängig.
> Beide müssen aktiviert sein damit Orders funktionieren.

### EA-Properties "Allow live trading"
1. Rechtsklick auf den EA im Navigator
2. **"Eigenschaften"** → Tab **"Allgemein"**
3. Haken bei **"Live Trading erlauben"** setzen
4. OK bestätigen und EA neu auf den Chart ziehen

---

## 2. InvestApp_Zones EA laden

### Voraussetzung
- `mql5/InvestApp_Zones.mq5` im MT5 MetaEditor kompilieren
- Kompilierte `.ex5`-Datei befindet sich in: `MQL5\Experts\InvestApp_Zones.ex5`

### EA auf Chart laden
1. MT5 öffnen → gewünschtes Symbol wählen (z.B. EURUSD, M1 oder M5)
2. Im Navigator: **Expert Advisors → InvestApp_Zones**
3. Doppelklick oder auf Chart ziehen
4. In den EA-Properties:
   - **"Live Trading erlauben"** aktivieren (siehe oben)
   - **"DLL-Importe erlauben"** ggf. aktivieren
5. Empfohlener Chart: EURUSD M1 (Watch-Agent arbeitet auf 1-Minuten-Basis)

---

## 3. config.json: mt5_common_files_path korrekt setzen

Der `mt5_common_files_path` zeigt auf das MT5 Common Files Verzeichnis.
Hier schreibt InvestApp die `pending_order.json` und der EA liest sie aus.

### Standard-Pfad (Windows)
```
C:\Users\<Username>\AppData\Roaming\MetaQuotes\Terminal\Common\Files
```

### config.json anpassen
```json
{
  "mt5": {
    "mt5_common_files_path": "C:\\Users\\Mosi\\AppData\\Roaming\\MetaQuotes\\Terminal\\Common\\Files"
  }
}
```

> **Hinweis:** InvestApp erkennt den Pfad automatisch via `APPDATA`-Umgebungsvariable,
> falls `mt5_common_files_path` leer bleibt. Zur Diagnose beim Start im Log prüfen:
> `[MT5 Diagnose] common_files_path: ...`

### Pfad im MT5 MetaEditor finden
1. MetaEditor öffnen (F4)
2. Datei → Öffnen → Oben in der Adressleiste ist der `Common`-Pfad sichtbar
3. Alternativ: MT5 → Extras → Datenordner → dort ist auch `Common\Files` sichtbar

### Wo landet mt5_zones.json?

Beim App-Start loggt InvestApp den exakten Pfad:
```
[ChartExporter] Schreibe mt5_zones.json nach: C:\Users\...\Common\Files\mt5_zones.json
```
Wenn `mt5_common_files_path` leer ist und Windows erkannt wird, wird der Pfad automatisch über die `APPDATA`-Umgebungsvariable ermittelt. Auf Mac/Linux (Entwicklung) landet die Datei als Fallback relativ zum Skript-Verzeichnis.

---

## 4. Häufige Fehler und Lösungen

### retcode-Tabelle

| retcode | Bedeutung | Lösung |
|---------|-----------|--------|
| **5004** | ERR_FILE_NOT_FOUND (mt5_zones.json) | Normal beim ersten Start – InvestApp schreibt die Datei erst nach dem ersten Analyse-Zyklus. EA wartet still. Wenn Fehler dauerhaft: `mt5_common_files_path` in config.json prüfen (siehe Abschnitt 3). |
| **10027** | AutoTrading disabled by client | Globalen AutoTrading-Button aktivieren UND EA-Property "Allow live trading" setzen |
| **10004** | Requote | Normale Marktsituation – InvestApp wiederholt automatisch |
| **10006** | Request rejected | Kontotyp prüfen (Nur-Lesen-Demo?) |
| **10007** | Request canceled by trader | Manuell abgebrochen |
| **10010** | Only part of the request was completed | Partial Fill – nicht kritisch |
| **10013** | Invalid request | Symbol-Name falsch oder Lot-Größe ungültig |
| **10014** | Invalid volume | `simulation_lot_size` in config.json prüfen (min. 0.01) |
| **10018** | Market is closed | Außerhalb der Handelszeiten |
| **10019** | Insufficient funds | Konto-Guthaben prüfen |
| **10030** | Position already exists | Doppel-Entry-Schutz greift |
| **10034** | Limit of pending orders reached | Zu viele offene Pending Orders im MT5 |

---

### Fehler: retcode=10027 – was genau prüfen?

**Ursache 1: Globaler AutoTrading-Button deaktiviert**
- Toolbar: AutoTrading-Button muss grün/aktiv sein

**Ursache 2: EA-Properties "Allow live trading" nicht gesetzt**
- EA auf Chart → Doppelklick → Tab "Allgemein" → Haken setzen

**Ursache 3: EA läuft auf falschem Account/Terminal**
- MT5 als Administrator starten
- Sicherstellen dass MT5-Login in `.env` mit dem laufenden Terminal übereinstimmt

**Ursache 4: Nur-Lesen-Demo-Konto**
- Kontodetails prüfen: Kontotyp "Demo" mit Schreibrechten nötig

---

### Fehler: pending_order.json wird nicht verarbeitet

1. EA läuft nicht auf einem Chart → InvestApp_Zones EA laden (Schritt 2)
2. `mt5_common_files_path` falsch gesetzt → Diagnose-Log beim Start prüfen
3. Datei-Rechte: MT5 muss Schreibrechte auf den Common-Files-Ordner haben

---

### Diagnose beim App-Start

Beim Start gibt InvestApp automatisch folgende Infos aus:
```
[MT5 Diagnose] mt5_connected: True
[MT5 Diagnose] common_files_path: C:\Users\Mosi\AppData\Roaming\MetaQuotes\Terminal\Common\Files
[MT5 Diagnose] common_files_path_exists: True
[MT5 Diagnose] autotrading_available: True
```

Wenn `autotrading_available: False` → AutoTrading im MT5-Terminal aktivieren.
Wenn `common_files_path_exists: False` → Pfad in config.json korrigieren.

---

## 5. File-basierter Order-Fallback

Falls AutoTrading deaktiviert ist, schreibt InvestApp automatisch eine `pending_order.json`:

```json
{
  "timestamp": 1710000000.0,
  "symbol": "EURUSD",
  "direction": "buy",
  "volume": 0.01,
  "sl": 1.0900,
  "tp": 1.1200,
  "comment": "InvestApp",
  "status": "pending"
}
```

Der **InvestApp_Zones EA** liest diese Datei und führt die Order aus.
Nach Ausführung schreibt der EA `status: "executed"` zurück.

**Wichtig:** Ohne laufenden EA wird `status: "timeout"` gemeldet – keine Order wird ausgeführt.
