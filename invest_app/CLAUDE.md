# CLAUDE.md — InvestApp Projektspeicher

> Dieses Dokument ist das vollständige Gedächtnis für neue Sessions.
> Zuletzt aktualisiert: 2026-03-23

---

## 1. Projekt-Übersicht

| Eigenschaft | Wert |
|---|---|
| **Name** | InvestApp — KI-gestütztes Trading-System |
| **Python** | 3.14 |
| **Platform** | Windows 11 + MetaTrader 5 |
| **Windows-Pfad** | `C:\Users\Mosi\Dokumente investApp\InvestApp\invest_app` |
| **GitHub** | https://github.com/MarcoMo82/InvestApp.git |
| **Hauptbranch** | `main` |
| **Letzter Commit** | `7e295ef` — feat: einmaliger Trade-Simulations-Test-Modus (merge) |

**Zweck:** Operative Entscheidungsunterstützung für **manuelles Trading** — keine Vollautomatisierung. KI-Agenten analysieren Märkte und generieren Signale mit Entry/SL/TP/Confidence-Score.

---

## 2. Architektur — Alle Agenten (13 total)

### Pipeline-Agenten (strikt sequenziell)

| # | Datei | Klasse | Hauptaufgabe |
|---|---|---|---|
| 1 | `agents/orchestrator.py` | `Orchestrator` | Ablaufsteuerung aller Agenten, Scheduler, Signal-Aggregation |
| 2 | `agents/macro_agent.py` | *(LLM-Funktion)* | Makro-Bias, Event-Risiko, Freigabe ja/nein (Claude LLM) |
| 3 | `agents/trend_agent.py` | `TrendAgent` | Trendrichtung per EMA/HH-HL/BoS/CHoCH, Long/Short erlaubt |
| 4 | `agents/volatility_agent.py` | `VolatilityAgent` | ATR-Bewertung, Session-Qualität, Marktphase, Freigabe |
| 5 | `agents/level_agent.py` | `LevelAgent` | Schlüsselzonen, S/R-Level, Fair Value Gaps, Distanz |
| 6 | `agents/entry_agent.py` | `EntryAgent` | Einstiegs-Setups auf 5m-Chart, Entry-Typ/Preis/Trigger |
| 7 | `agents/risk_agent.py` | `RiskAgent` | SL, TP, CRV, Positionsgröße, Trade zulässig ja/nein |
| 8 | `agents/validation_agent.py` | *(LLM-Funktion)* | Confidence Score %, pro/contra, validiert ja/nein (Claude LLM) |
| 9 | `agents/reporting_agent.py` | `ReportingAgent` | Priorisierte Signalliste, Markdown-Report → Output/ |
| 10 | `agents/learning_agent.py` | `LearningAgent` | Post-Trade-Analyse, Muster-Erkennung, Parameter-Empfehlungen |

### Spezial-Agenten

| Datei | Klasse | Hauptaufgabe |
|---|---|---|
| `agents/watch_agent.py` | `WatchAgent` | 1min-Zyklus: Entry-Präzision + Positions-Monitoring; **einziger Agent der place_order() aufruft** |
| `agents/chart_exporter.py` | `ChartExporter` | Exportiert Analyse als JSON → `Output/mt5_zones.json` für MQL5-Indikator |
| `agents/simulation_agent.py` | `SimulationAgent` | Einmaliger Test-Modus: injiziert synthetisches Signal zur Pipeline-Validierung |

### Daten-Schicht

| Datei | Zweck |
|---|---|
| `data/mt5_connector.py` | MetaTrader 5 Connector (nur Windows); Marktdaten + Order-Execution |
| `data/yfinance_connector.py` | Fallback-Connector (Mac/Linux/Demo); identische Schnittstelle wie MT5 |
| `data/news_fetcher.py` | Yahoo Finance News; zweistufiges Caching (in-memory + Disk, TTL 60 min) |

---

## 3. Scheduler-Zyklen

| Zyklus | Auslöser | Aufgabe |
|---|---|---|
| **5 Minuten** | APScheduler (Orchestrator) | Vollständige Strategie-Analyse aller Symbole |
| **1 Minute** | APScheduler (WatchAgent) | Entry-Präzision auf 1m-Chart + offene Positionen überwachen |
| **60 Minuten** | News-Cache TTL | News-Daten werden neu abgerufen (disk-basierter Cache) |

Konfigurierbar über `.env`:
- `CYCLE_INTERVAL_MINUTES=5`
- `NEWS_CACHE_TTL=3600`

---

## 4. Wichtige Regeln — NIEMALS vergessen

### Code-Qualität
- **Keine hardcodierten Werte** — alles in `config.py` / `.env`
- **Kein `except: pass`** — Fehler sinnvoll loggen und weitergeben
- **Modularer Aufbau** — jede Komponente eigenständig testbar
- `datetime.utcnow()` ist deprecated → immer `datetime.now(timezone.utc)` verwenden

### Git-Workflow
- **Vor jedem Push**: vollständiger Test — `pytest + import + syntax + methoden-check`
- **Worktree-Branches** immer in `main` mergen vor dem Push
- **Verify nach Push**: `git show origin/main:<datei> | grep <feature>`
- Keine Merge-Commits direkt auf `main` pushen — nur über PR oder squash

### Trading-Pflichtregeln
- Kein Trade gegen den Haupttrend
- Kein Signal ohne Volatilitätsfreigabe
- Kein Entry ohne bestätigte Level-Logik
- Kein Trade ohne sauberes Risiko-Setup
- Signale unter 80 % Confidence nur nachrangig / verworfen
- Hohe News-Risiken blockieren neue Einstiege

---

## 5. Konfiguration — config.py alle Keys

| Key | Default | Zweck |
|---|---|---|
| `anthropic_api_key` | `$ANTHROPIC_API_KEY` | Claude API Authentifizierung |
| `mt5_login` | `0` | MT5 Account-Nummer |
| `mt5_password` | `""` | MT5 Passwort |
| `mt5_server` | `""` | MT5 Broker-Server |
| `mt5_path` | `C:\Program Files\MetaTrader 5\terminal64.exe` | MT5 Pfad |
| `trading_mode` | `"demo"` | `"demo"` oder `"live"` |
| `risk_per_trade` | `0.01` | Risiko pro Trade (1% des Kapitals) |
| `max_daily_loss` | `0.03` | Max. Tagesverlust (3%) |
| `min_confidence_score` | `80.0` | Schwellenwert für Signalfreigabe |
| `min_crv` | `2.0` | Mindest-CRV (Chance-Risiko-Verhältnis) |
| `atr_period` | `14` | ATR-Berechnungsperiode |
| `atr_sl_multiplier` | `2.0` | SL = ATR × 2.0 |
| `atr_tp_multiplier` | `4.0` | TP = ATR × 4.0 |
| `htf_timeframe` | `"15m"` | Higher Timeframe für Trendanalyse |
| `entry_timeframe` | `"5m"` | Entry-Zeitrahmen |
| `htf_bars` | `200` | Anzahl HTF-Bars |
| `entry_bars` | `100` | Anzahl Entry-Bars |
| `ema_periods` | `[9, 21, 50, 200]` | EMA-Perioden |
| `forex_symbols` | `[EURUSD, GBPUSD, USDJPY, ...]` | 10 Forex-Paare |
| `stock_symbols` | `[AAPL, MSFT, GOOGL, ...]` | 7 US-Aktien |
| `crypto_symbols` | `[BTCUSD, ETHUSD]` | 2 Krypto-Paare |
| `cycle_interval_minutes` | `5` | Scheduler-Intervall |
| `news_cache_ttl` | `3600` | News-Cache TTL in Sekunden (60 min) |
| `claude_model` | `"claude-opus-4-6"` | LLM-Modell |
| `claude_max_tokens` | `2048` | Max. Tokens pro LLM-Aufruf |
| `claude_retry_attempts` | `3` | Anzahl API-Retries |
| `claude_retry_delay` | `2.0` | Sekunden zwischen Retries |
| `db_path` | `invest_app.db` | SQLite-Datenbank |
| `log_dir` | `logs/` | Log-Verzeichnis |
| `output_dir` | `Output/` | Output-Verzeichnis |
| `log_level` | `"INFO"` | Log-Level |
| `MT5_ZONES_FILE` | `"Output/mt5_zones.json"` | MT5-Zonen-Export-Datei |
| `MT5_ZONES_EXPORT_ENABLED` | `true` | MT5-Export aktiviert |
| `simulation_mode_enabled` | `False` | Simulation-Testmodus |
| `simulation_trigger_after_watch_cycles` | `3` | Auslösung nach N Watch-Zyklen |
| `simulation_symbol` | `"EURUSD"` | Symbol für Simulation |
| `simulation_direction` | `"long"` | Richtung für Simulation |
| `simulation_lot_size` | `0.01` | Lot-Größe für Simulation |
| `CHART_ENTRY_TOLERANCE_PCT` | `0.05` | Toleranz für Zonen-Berechnung (% vom Preis) |
| `london_open_hour` | `8` (UTC) | London Session Öffnung |
| `london_close_hour` | `17` (UTC) | London Session Schluss |
| `ny_open_hour` | `13` (UTC) | New York Session Öffnung |
| `ny_close_hour` | `22` (UTC) | New York Session Schluss |

---

## 6. Implementierte Features — vollständige Liste

### Technische Analyse
- **ATR-Ratio Filter** (0.5–2.0): Filtert ungeeignete Volatilitätsphasen heraus
- **Trailing Stop** (ATR×2, EMA21, strukturell): Aktiviert bei 1:1 CRV
- **Partial Exit** (50% bei TP1, Rest mit Break-Even SL)
- **RSI(14)**: Overbought/Oversold-Erkennung + Divergenz-Analyse
- **Bollinger Bands** (20, 2.0): Squeeze, BB-Walk, Expansion-Erkennung
- **Order Blocks**: Letzte gegenläufige Kerze vor Impuls >ATR×1.5
- **Psychologische Preislevel**: Runde Zahlen nach Preisgröße (Forex, Aktien, Krypto)
- **MTF Confluence Score**: 6 Faktoren; triple=+35%, dual=+15%
- **Sideways-Erkennung**: ATR-Ratio <0.7 ODER kein klares HH/HL
- **Forex SL-Limit**: max. 80 Pips; Aktien: max. 3%

### Agenten-Features
- **Watch Agent**: `signal-pending` + `positions-monitoring` Modi; 1min-Takt
- **Learning Agent**: Post-Trade-Analyse + Parameter-Optimierungsempfehlungen (regelbasiert, kein LLM)
- **Chart Exporter**: `mt5_zones.json` → MQL5-Indikator-Integration
- **Simulation Agent**: Auto-Test nach N Watch-Zyklen; Auto-Deaktivierung nach Erfolg

### Infrastruktur & Fixes
- **Persistenter News-Cache**: Disk-basiert, TTL 60 min (zweistufig: memory + disk)
- **JSON-Serialisierungs-Fix**: `_make_json_safe()` für bool/numpy-Typen in `agent_scores`
- **datetime.utcnow() → datetime.now(timezone.utc)**: Python 3.14 Kompatibilität
- **Confidence Cap**: `min(max(score, 0.0), 100.0)` verhindert Out-of-Range-Scores
- **pytest Test-Framework**: 221 Tests, alle grün

---

## 7. Datei-Struktur

```
invest_app/
├── __init__.py
├── config.py                          # Zentrale Konfiguration (dataclass)
├── main.py                            # Einstiegspunkt, startet Scheduler
├── test_simulation.py                 # Standalone Simulations-Test
│
├── agents/
│   ├── __init__.py
│   ├── base_agent.py                  # Basisklasse für alle Agenten
│   ├── chart_exporter.py              # MT5-Zonen-Export nach JSON
│   ├── entry_agent.py                 # Entry-Suche auf 5m-Chart
│   ├── learning_agent.py              # Post-Trade-Analyse, regelbasiert
│   ├── level_agent.py                 # Schlüsselzonen, S/R, FVG
│   ├── macro_agent.py                 # Makro + News via Claude LLM
│   ├── orchestrator.py                # Hauptsteuerung, APScheduler
│   ├── reporting_agent.py             # Signalliste + Markdown-Report
│   ├── risk_agent.py                  # SL/TP/CRV/Positionsgröße
│   ├── simulation_agent.py            # Einmaliger Pipeline-Test
│   ├── trend_agent.py                 # EMA/HH-HL/BoS/CHoCH
│   ├── validation_agent.py            # Confidence Score via Claude LLM
│   ├── volatility_agent.py            # ATR, Session, Marktphase
│   └── watch_agent.py                 # 1min Entry-Präzision + Monitoring
│
├── data/
│   ├── __init__.py
│   ├── mt5_connector.py               # MetaTrader 5 (nur Windows)
│   ├── news_fetcher.py                # Yahoo Finance News + Cache
│   └── yfinance_connector.py          # Fallback-Connector (Mac/Linux)
│
├── models/
│   ├── __init__.py
│   ├── signal.py                      # Signal-Datenmodell (Pydantic)
│   └── trade.py                       # Trade-Datenmodell (Pydantic)
│
├── utils/
│   ├── __init__.py
│   ├── claude_client.py               # Claude API Wrapper
│   ├── database.py                    # SQLite Datenbankschicht
│   └── logger.py                      # Logging-Konfiguration
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_chart_exporter.py
│   ├── test_claude_client.py
│   ├── test_config.py
│   ├── test_database.py
│   ├── test_database_full.py
│   ├── test_entry_agent.py
│   ├── test_learning_agent.py
│   ├── test_level_agent.py
│   ├── test_news_fetcher.py
│   ├── test_orchestrator_gates.py
│   ├── test_risk_agent.py
│   ├── test_simulation_agent.py
│   ├── test_trade_execution.py
│   ├── test_trend_agent.py
│   ├── test_validation_agent.py
│   ├── test_volatility_agent.py
│   └── test_watch_agent.py
│
├── mql5/
│   └── InvestApp_Zones.mq5            # MQL5-Indikator für MT5-Visualisierung
│
├── Output/                            # Generierte Berichte und Exporte
│   ├── mt5_zones.json                 # MT5-Zonen (wird alle 5 Min aktualisiert)
│   └── simulation_result.json         # Simulation-Testergebnis
│
└── logs/                              # Log-Dateien
```

---

## 8. Test-Status

| Eigenschaft | Wert |
|---|---|
| **Anzahl Tests** | 221 (alle grün) |
| **Coverage** | ~79% |
| **Nicht abgedeckt (erwartet)** | `main.py`, `data/mt5_connector.py`, `data/yfinance_connector.py` |

**Ausführung:**
```bash
python3 -m pytest tests/ -v --tb=short
python3 -m pytest tests/ --cov=. --cov-report=term-missing
```

---

## 9. MT5-Visualisierung

- **MQL5-Indikator:** `mql5/InvestApp_Zones.mq5`
- **JSON-Quelle:** `Output/mt5_zones.json` (wird nach jedem 5-Min-Zyklus neu geschrieben)
- **Einrichtung:**
  1. `InvestApp_Zones.mq5` in MT5 MetaEditor kompilieren
  2. Indikator auf Chart laden
  3. Parameter `JsonFilePath` auf absoluten Pfad zur `mt5_zones.json` setzen
- **Inhalt:** Entry-Zonen, SL/TP-Level, Order Blocks, Psychologische Levels, Key-Levels

---

## 10. Simulation Test-Modus

**Aktivierung in `.env`:**
```
SIMULATION_MODE_ENABLED=True
SIMULATION_TRIGGER_AFTER_WATCH_CYCLES=3
SIMULATION_SYMBOL=EURUSD
SIMULATION_DIRECTION=long
SIMULATION_LOT_SIZE=0.01
```

**Ablauf:**
1. Nach Watch-Zyklus 3 (konfigurierbar) injiziert `SimulationAgent` ein synthetisches Signal
2. Alle Agenten-Bedingungen werden als "grün" gesetzt
3. Pipeline läuft vollständig durch (Reporting + ChartExport)
4. Ergebnis wird in `Output/simulation_result.json` gespeichert
5. **Auto-Deaktivierung** nach erfolgreichem Test (kein weiterer Durchlauf)

---

## 11. Offene Punkte / Nächste Schritte

| Priorität | Thema | Beschreibung |
|---|---|---|
| Mittel | **Backtesting-Modul** | Nach 1 Woche Live-Demo: historische Trade-Simulation |
| Niedrig | **Pydantic V2 Migration** | `models/signal.py`: `class Config` → `model_config = ConfigDict(...)` |
| Niedrig | **Learning Agent Echtdaten** | Parameter-Optimierung auf Basis echter abgeschlossener Trades |
| Info | **Test Coverage** | `main.py` und Connectors absichtlich nicht abgedeckt (externe Deps) |

---

## 12. Windows Setup-Befehle

```powershell
# Projektverzeichnis
cd "C:\Users\Mosi\Dokumente investApp\InvestApp\invest_app"

# Aktuellen Stand holen
git pull origin main

# Virtual Environment aktivieren
venv\Scripts\activate

# Tests ausführen
python -m pytest tests/ -v --tb=short

# Anwendung starten
python main.py
```

**Mac/Linux (Entwicklung):**
```bash
cd /Users/marcomoser/Documents/InvestApp/Skript/invest_app
source venv/bin/activate  # falls vorhanden
python3 -m pytest tests/ -v --tb=short
```

---

## 13. Git Log — Letzte 10 Commits

```
7e295ef feat: einmaliger Trade-Simulations-Test-Modus (merge)
adfbd43 feat: einmaliger Trade-Simulations-Test-Modus implementiert
5a9da80 fix: JSON-Serialisierungsfehler bei bool-Werten in agent_scores (merge)
17cc4cd fix: JSON-Serialisierungsfehler bei bool-Werten in agent_scores behoben
673656e feat: pytest Test-Framework, Unit-Tests für alle Agenten und DB (merge)
a1434c0 feat: Watch-Agent Lebenszeichen mit Statistik in Konsole und Log (merge)
80d2a50 feat: Watch-Agent (1min-Takt) für Entry-Präzision + Positions-Monitoring, MT5-News-Abruf (merge)
f8797d1 config: News-Cache-Intervall von 5 auf 60 Minuten erhöht (merge)
1900328 feat: Analyse-Zyklus von 15 auf 5 Minuten reduziert, Signal-Timeout angepasst (merge)
fd12275 feat: MT5-Zonen-Visualisierung – ChartExporter + MQL5-Indikator (merge)
```
