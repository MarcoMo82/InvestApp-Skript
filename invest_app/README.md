# InvestApp Trading System

KI-gestützte Trading-Plattform zur systematischen Markt- und Signal-Analyse. Operative Entscheidungsunterstützung für **manuelles Trading** – keine Vollautomatisierung.

---

## Voraussetzungen

- Python 3.11+
- MetaTrader 5 (MT5-Terminal installiert)
- Anthropic API Key

---

## Installation

### Automatisch (empfohlen)

Starte den Setup-Wizard:

```powershell
.\install_wizard.ps1
```

Der Wizard richtet die virtuelle Umgebung ein, installiert alle Abhängigkeiten und erstellt die `.env`-Datei.

### Manuelles Setup (für Entwickler)

```bash
# 1. Virtuelle Umgebung erstellen und aktivieren
python -m venv venv
source venv/bin/activate        # macOS/Linux
# venv\Scripts\activate         # Windows

# 2. Abhängigkeiten installieren
pip install -r requirements.txt

# 3. .env-Datei anlegen (NICHT ins Repo committen!)
cp .env.example .env
# Dann .env mit Editor öffnen und API-Keys eintragen
```

#### Inhalt der `.env`-Datei

```env
ANTHROPIC_API_KEY=sk-ant-...
MT5_LOGIN=123456
MT5_PASSWORD=geheimespasswort
MT5_SERVER=MetaQuotes-Demo
```

> **Wichtig:** Die `.env`-Datei enthält sensible Zugangsdaten und ist in `.gitignore` eingetragen. Sie darf **niemals** in das Repository committet werden.

---

## Projektstruktur

```
invest_app/
├── agents/                  # Agent-Module der Pipeline
│   ├── orchestrator.py      # Ablaufsteuerung
│   ├── macro_agent.py       # Makro & News-Analyse
│   ├── trend_agent.py       # Trendfilter (15m)
│   ├── volatility_agent.py  # Marktbedingungen
│   ├── level_agent.py       # Schlüsselzonen
│   ├── entry_agent.py       # Einstiegssuche (5m/Tick)
│   ├── risk_agent.py        # Risikosteuerung
│   ├── reporting_agent.py   # Nutzer-Output
│   ├── validation_agent.py  # Qualitätsprüfung
│   └── base_agent.py        # Basis-Klasse für alle Agents
├── data/                    # Datenquellen-Konnektoren
│   ├── mt5_connector.py     # MetaTrader 5 Integration
│   ├── yfinance_connector.py# Yahoo Finance Daten
│   └── news_fetcher.py      # News-Feed Abruf
├── models/                  # Datenmodelle
│   ├── signal.py            # Signal-Modell
│   └── trade.py             # Trade-Modell
├── utils/                   # Hilfsfunktionen
│   ├── claude_client.py     # Anthropic API Client
│   ├── database.py          # Datenbankzugriff
│   └── logger.py            # Logging
├── Output/                  # Generierte Signallisten & Reports
├── main.py                  # Einstiegspunkt
├── config.py                # Konfiguration
├── requirements.txt         # Python-Abhängigkeiten
├── Dockerfile               # Container-Setup
├── .env                     # Secrets (NICHT committen!)
└── .gitignore
```

---

## Agent-Pipeline

```
Orchestrator → Macro → Trend → Volatility → Level → Entry → Risk → Validation → Reporting
```

Signale mit Confidence Score ≥ 80 % werden als Top-Signale ausgewiesen. Alle anderen gelten als nachrangig oder werden verworfen.

---

## Hinweise

- `.env` **niemals** ins Repository committen – sie enthält API-Keys und MT5-Zugangsdaten
- Keine vollautomatische Trade-Ausführung – alle Signale erfordern manuelle Freigabe
- Primäre Märkte: Forex, Aktien, Krypto
