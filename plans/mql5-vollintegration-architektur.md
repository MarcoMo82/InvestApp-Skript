# MQL5 Vollintegration – Architekturplan InvestApp

**Version:** 1.0 · **Stand:** März 2026
**Ziel:** Verlagerung der gesamten Trading-Pipeline (Signal → Order → Trade-Begleitung) in MQL5 Expert Advisors. Python verbleibt ausschließlich als Learning-Agent-Backend + News-Fetcher.

---

## Getroffene Architekturentscheidungen

| Punkt | Entscheidung |
|---|---|
| Ausführungsrhythmus | `OnTimer()` jede Sekunde, vollständige Analyse alle 30–60s |
| EA-Aufteilung | 3 EAs: Forex / Indexes / NASDAQ – jeder betreut alle Symbole seines Bereichs |
| News-Sperre | High Impact fix gesperrt, Medium Impact per config.json steuerbar |
| Paralleltest | Entfällt (Demokonto, Findungsphase) |
| Monitoring | Expert-Fenster (`Print`/`Alert`) + optionale `ea_status.json` |
| Level-Erkennung | Hybrid: MT5 schreibt `market_data.json`, Python berechnet Zonen, EA liest `zones.json` |

---

## 1. Zielarchitektur-Übersicht

### Wo läuft was?

| Komponente | Aktuell (Python) | Ziel (MQL5 EA) | Schnittstelle |
|---|---|---|---|
| Makro-Filter | Python `MacroAgent` | MQL5 Modul `MacroFilter` | `macro_context.json` (Common Files) |
| News-Sperre | Python (Kalender-API) | Python schreibt → EA liest | `news_events.json` (Common Files) |
| Trend-Analyse | Python `TrendAgent` | MQL5 Modul `TrendAnalysis` | — (intern im EA) |
| Volatilität | Python `VolatilityAgent` | MQL5 Modul `VolatilityFilter` | — (intern im EA) |
| Level-Erkennung | Python `LevelAgent` | **Hybrid** | `market_data.json` → Python → `zones.json` |
| Entry-Signal | Python `EntryAgent` | MQL5 Modul `EntrySignal` | — (intern im EA) |
| Risk-Berechnung | Python `RiskAgent` | MQL5 Modul `RiskManager` | `config.json` (Parameter) |
| Validierung | Python `ValidationAgent` | MQL5 Modul `TradeValidator` | — (intern im EA) |
| Order-Ausführung | Python → MT5 via `mt5` lib | MQL5 nativ (`OrderSend`) | — |
| Trade-Begleitung | MQL5 EA (bereits impl.) | MQL5 EA (bleibt) | — |
| Learning Agent | Python `LearningAgent` | **Python bleibt** | `config.json` (schreibt) |
| News-Fetcher | Python | **Python bleibt** | `news_events.json` (schreibt) |

### Datenfluss

```
┌─────────────────────────────────────────────────────────────┐
│               MQL5 Expert Advisor (OnTimer, 1s)             │
│                                                             │
│  Alle 30–60s: vollständige Analyse                          │
│       │                                                     │
│       ├── config.json lesen (Parameter, alle 15 Min)        │
│       ├── macro_context.json lesen (Makro-Status)           │
│       ├── news_events.json lesen (News-Sperre)              │
│       ├── zones.json lesen (S/R-Zonen von Python)           │
│       │                                                     │
│       ├── MacroFilter ──────────── PASS / BLOCK             │
│       ├── TrendAnalysis ─────────── Trend-Bias              │
│       ├── VolatilityFilter ──────── ATR / Spread            │
│       ├── LevelDetection ─────────── Zonen aus zones.json   │
│       ├── EntrySignal ──────────── Long/Short/None          │
│       ├── TradeValidator ─────────── Final Check            │
│       ├── RiskManager ──────────── Lot / SL / TP            │
│       └── OrderSend() ──────────── Execution                │
│                                                             │
│  Alle 15 Min: market_data.json schreiben (für Python)       │
│  Kontinuierlich: TradeManagement (Breakeven + Trailing)     │
└─────────────────────────────────────────────────────────────┘
     │ market_data.json        │ MT5 History
     ▼                         ▼
┌──────────────────┐  ┌──────────────────────┐  ┌─────────────────────┐
│  Python Level    │  │  Python Learning     │  │  Python News        │
│  Agent           │  │  Agent               │  │  Fetcher            │
│  (alle 15 Min)   │  │  (täglich/wöchentl.) │  │  (stündlich)        │
│  → zones.json    │  │  → config.json       │  │  → news_events.json │
└──────────────────┘  └──────────────────────┘  └─────────────────────┘
```

---

## 2. EA-Struktur: 3 spezialisierte Expert Advisors

### Dateistruktur

```
Experts/
├── InvestApp_Forex/
│   ├── InvestApp_Forex.mq5
│   └── modules/              ← gemeinsame Module (shared)
├── InvestApp_Indexes/
│   ├── InvestApp_Indexes.mq5
│   └── modules/              ← shared
└── InvestApp_NASDAQ/
    ├── InvestApp_NASDAQ.mq5
    └── modules/              ← shared

Include/InvestApp/
├── ConfigReader.mqh
├── MacroFilter.mqh
├── TrendAnalysis.mqh
├── VolatilityFilter.mqh
├── LevelDetection.mqh        ← liest zones.json
├── EntrySignal.mqh
├── TradeValidator.mqh
├── RiskManager.mqh
├── TradeManagement.mqh       ← bereits implementiert
├── JsonReader.mqh
└── Logger.mqh
```

Die Module sind in `Include/InvestApp/` als `.mqh`-Dateien shared – alle 3 EAs nutzen dieselben Module, nur die EA-Hauptdatei enthält bereichsspezifische Symbol-Listen und Parameter.

### Risiko-Koordination über 3 EAs

Jeder EA kennt sein eigenes Exposure. Für Gesamt-Risiko-Kontrolle schreibt jeder EA seinen aktuellen Status in eine gemeinsame `portfolio_state.json`:

```json
{
  "forex": { "open_trades": 2, "current_drawdown_pct": 1.2 },
  "indexes": { "open_trades": 1, "current_drawdown_pct": 0.4 },
  "nasdaq": { "open_trades": 0, "current_drawdown_pct": 0.0 },
  "total_drawdown_pct": 1.6
}
```

Jeder EA liest diese Datei und blockiert neue Entries wenn Gesamt-Drawdown > Limit.

---

## 3. Hybrid Level-Erkennung

### Ablauf

1. **EA schreibt alle 15 Min** `market_data.json` mit OHLC-Daten aller überwachten Symbole (letzte 200 Kerzen, 15m + 1h Timeframe)
2. **Python Level Agent** liest die Daten, berechnet:
   - Swing Highs / Swing Lows (N-Bar-Lookback)
   - Pivot-Punkte (Daily OHLC)
   - Zonen-Clustering (nahe Levels zusammenfassen)
   - Reaktionswahrscheinlichkeit (wie oft wurde diese Zone respektiert?)
3. **Python schreibt** `zones.json` zurück
4. **EA liest** `zones.json` in `LevelDetection.mqh` – verwendet Zonen direkt, keine eigene Berechnung

### `zones.json` Struktur

```json
{
  "generated_at": "2026-03-27T14:00:00",
  "valid_until": "2026-03-27T14:15:00",
  "symbols": {
    "EURUSD": {
      "resistance": [1.0890, 1.0950, 1.1020],
      "support": [1.0820, 1.0760, 1.0700],
      "nearest_resistance": 1.0890,
      "nearest_support": 1.0820,
      "distance_to_resistance_pips": 45,
      "distance_to_support_pips": 30
    }
  }
}
```

---

## 4. JSON-Dateien als Brücke

| Datei | Schreibt | Liest | Intervall |
|---|---|---|---|
| `config.json` | Learning Agent | EA (alle 15 Min) | Bei Änderung |
| `news_events.json` | Python News-Fetcher | EA (jeden Zyklus) | Stündlich |
| `macro_context.json` | Python (manuell/täglich) | EA (jeden Zyklus) | Täglich |
| `market_data.json` | EA | Python Level Agent | Alle 15 Min |
| `zones.json` | Python Level Agent | EA | Alle 15 Min |
| `portfolio_state.json` | Alle 3 EAs | Alle 3 EAs | Jeder Zyklus |
| `ea_status.json` | EA | Python (optional) | Jeder Zyklus |

---

## 5. Python nach der Migration

Python reduziert sich auf 3 Aufgaben:

| Aufgabe | Frequenz | Input | Output |
|---|---|---|---|
| Level Agent | Alle 15 Min | `market_data.json` | `zones.json` |
| News-Fetcher | Stündlich | MT5-Kalender / API | `news_events.json` |
| Learning Agent | Täglich / Wöchentlich | MT5-Historie | `config.json` |

---

## 6. Migrationsplan

### Phase 0 – Fundament (aktuell)
- [ ] `JsonReader.mqh` für alle 3 JSON-Typen validieren
- [ ] `Logger.mqh` erstellen (strukturiertes Logging ins Experten-Fenster + Datei)
- [ ] `ConfigReader.mqh` – config.json lesen, alle Parameter in structs laden
- [ ] `ea_status.json` schreiben (Heartbeat, letzte Aktivität)
- [ ] Grundgerüst der 3 EAs mit Symbol-Listen und OnTimer()-Schleife

### Phase 1 – Einfache Module
- [ ] `RiskManager.mqh`
- [ ] `VolatilityFilter.mqh`
- [ ] `TrendAnalysis.mqh`
- [ ] `TradeValidator.mqh`

### Phase 2 – Komplexe Module
- [ ] `MacroFilter.mqh` (liest news_events.json + macro_context.json)
- [ ] `LevelDetection.mqh` (liest zones.json)
- [ ] `EntrySignal.mqh`
- [ ] Python Level Agent (schreibt zones.json)

### Phase 3 – Integration
- [ ] Alle Module zusammenführen
- [ ] Vollständiger Durchlauf auf Demo ohne echte Orders (nur Logging)
- [ ] Python Learning Agent + News-Fetcher als Standalone testen

### Phase 4 – Live Demo
- [ ] EAs mit echter Order-Ausführung auf Demo
- [ ] Monitoring via Experten-Fenster aktiv

---

## 7. Vorteile und Risiken

| Vorteil | Erläuterung |
|---|---|
| Latenz eliminiert | Keine Python-MT5-Kommunikation im Trading-Loop |
| Zuverlässigkeit | EA läuft in MT5, keine Python-Prozess-Abstürze |
| Native Backtest-Fähigkeit | Strategy Tester kann vollständigen Prozess testen |
| Einfachere Architektur | Weniger bewegliche Teile, weniger Fehlerquellen |
| Level-Erkennung best-of-both | Python-Stärke (Clustering) + MT5-Stärke (Daten) |

| Risiko | Mitigation |
|---|---|
| Logik-Übersetzungsfehler | Umfassendes Logging von Beginn an |
| JSON-Datei-Latenz | Config nur alle 15 Min lesen; zones.json hat valid_until |
| Datei-Race-Condition | Atomisches Schreiben (temp + rename) auf Python-Seite |
| Gesamt-Risiko über 3 EAs | portfolio_state.json als gemeinsame Koordination |

---

*Erstellt: März 2026 · Alle Entscheidungen mit Nutzer abgestimmt*
