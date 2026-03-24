# Lückenanalyse: Handbuch vs. aktueller Code

**Erstellt:** 2026-03-24
**Analysierte Dateien:** `agents/macro_agent.py`, `agents/trend_agent.py`, `agents/entry_agent.py`, `agents/risk_agent.py`, `agents/validation_agent.py`, `agents/scanner_agent.py`, `config.py`
**Referenz:** `Referenz/Handbuch.md` – besonders Kapitel 12–19 (Forex-Marktstruktur)

---

## Status-Übersicht

| Bereich | Punkt | Status |
|---------|-------|--------|
| **Trading Sessions** | London/NY Overlap bevorzugen | ⚠️ teilweise |
| | Asian Session → kein Trend-Trading | ❌ fehlt |
| | 30 min Sperre vor/nach High-Impact News | ❌ fehlt |
| **Risikomanagement** | Max 1–2 % Risiko pro Trade | ✅ implementiert |
| | Max 5 % Tagesverlust (Daily Drawdown Stop) | ⚠️ teilweise |
| | Max 3 gleichzeitige Positionen | ❌ fehlt |
| | Spread-Filter >3× Normal-Spread | ❌ fehlt |
| **SMC-Konzepte** | Order Blocks (OB) | ⚠️ teilweise |
| | Fair Value Gaps (FVG) | ❌ fehlt |
| | Break of Structure (BoS) | ✅ implementiert |
| | Change of Character (ChoCh) | ✅ implementiert |
| **Technische Regeln** | ATR-basierte Stops | ✅ implementiert |
| | CRV minimum 1:2 erzwingen | ✅ implementiert |
| | Korrelations-Check (korrelierte Paare) | ❌ fehlt |
| | Safe-Haven Logik (Risk-Off Sentiment) | ❌ fehlt |

---

## Detailbefunde

### Trading Sessions

**London/NY Overlap bevorzugen (13:00–17:00 UTC) — ⚠️ teilweise**

`config.py` hat `london_open_hour=8`, `ny_open_hour=13` usw. Der `volatility_agent` übergibt `session` ans Validation-Prompt. Aber: Es gibt keine aktive Logik, die Signale im Overlap-Fenster bevorzugt oder außerhalb abwertet. Das Feld `session` im Validation-Prompt wird nur informativ weitergegeben — kein Score-Modifier, keine Priorität.

**Asian Session → kein Trend-Trading (00:00–08:00 UTC) — ❌ fehlt**

`config.py` hat keine Asian Session definiert (`asian_open_hour` / `asian_close_hour` fehlen). Kein Agent prüft, ob die aktuelle Uhrzeit in die Asian Session fällt. In dieser Session soll laut Handbuch kein Trend-Trading stattfinden (nur Range-Strategien). Diese Regel ist nirgends implementiert.

**30 min Sperre vor/nach High-Impact News — ❌ fehlt**

Der `MacroAgent` setzt `trading_allowed=False` wenn `event_risk="high"` — das ist gut. Aber: Es gibt keine zeitbasierte Sperre. Die Logik prüft nicht, ob ein High-Impact Event in den nächsten 30 Minuten stattfindet oder gerade stattgefunden hat. Dafür wäre ein Wirtschaftskalender-API-Abruf (z.B. investing.com oder ForexFactory) nötig. Derzeit wird News-Sentiment retrospektiv bewertet, nicht prospektiv-zeitbasiert.

---

### Risikomanagement

**Max 1–2 % Risiko pro Trade — ✅ implementiert**

`config.py`: `risk_per_trade=0.01` (1 %), `risk_agent.py` berechnet daraus `risk_amount = balance * risk_per_trade`. Handbuch-konform.

**Max 5 % Tagesverlust (Daily Drawdown Stop) — ⚠️ teilweise**

`config.py` hat `max_daily_loss=0.03` (3 %) — aber das Handbuch schreibt 5 %. Wichtiger: Es gibt keine sichtbare Enforcement-Logik. Kein Agent oder Orchestrator trackt die kumulierten Tagesverluste und blockiert neue Signale wenn `max_daily_loss` erreicht ist. Der Parameter existiert in der Config, wird aber anscheinend nirgends aktiv geprüft.

**Max 3 gleichzeitige Positionen — ❌ fehlt**

Weder in `config.py` noch in einem der Agents gibt es einen Parameter `max_open_positions` oder eine Prüfung der aktuell offenen Positionen. Der Risk-Agent gibt `trade_allowed=True/False` zurück, aber ohne Berücksichtigung der Anzahl bereits laufender Trades.

**Spread-Filter: kein Trade wenn Spread > 3× Normal-Spread — ❌ fehlt**

`scanner_agent.py` Zeile 128–129: `# Spread-Bonus (default OK, kein Tick-Abruf erforderlich) / score += 15` — Spread wird nicht geprüft, stattdessen pauschal Bonus vergeben. Kein normaler Spread-Wert je Pair definiert, keine Echtzeit-Spread-Abfrage, kein Filter im Entry-Agent.

---

### SMC-Konzepte

**Order Blocks (OB) — ⚠️ teilweise**

`config.py` hat Farb-Definitionen (`chart_color_order_block_bull`, `chart_color_order_block_bear`) und `watch_agent_zone_update_ob_consumed_threshold`. Das deutet auf eine vorgesehene OB-Logik hin. Im `entry_agent.py` ist aber keine OB-Erkennungsroutine sichtbar — keine Funktion die die letzte bearishe Kerze vor einer starken Aufwärtsbewegung identifiziert. OBs werden in `mt5_zones.json` exportiert (für Chart-Visualisierung), aber nicht aktiv in Entry-Entscheidungen genutzt.

**Fair Value Gaps (FVG) / Imbalance — ❌ fehlt**

Keine FVG-Logik in irgendeinem Agent. Handbuch Kapitel 19: Kerze 2 muss so stark sein dass Lücke zwischen Kerze-1-High und Kerze-3-Low entsteht. Diese 3-Kerzen-Prüfung fehlt im `entry_agent.py` und `level_agent.py` komplett.

**Break of Structure (BoS) — ✅ implementiert**

`trend_agent.py` `_detect_bos_choch()` erkennt BoS korrekt: Schlusskurs über letztem Swing-Hoch (long) bzw. unter Swing-Tief (short). Ausgabe als `bos_detected` im Trend-Result.

**Change of Character (ChoCh) — ✅ implementiert**

`trend_agent.py` `_detect_bos_choch()` erkennt CHoCH: Bruch entgegen der aktuellen Trendrichtung. Ausgabe als `choch_detected`. Konform mit Handbuch-Definition.

---

### Technische Regeln

**ATR-basierte Stops — ✅ implementiert**

`risk_agent.py`: `atr_sl_distance = atr * self.sl_atr_multiplier` (Standard: 2.0×). Technischer Swing-SL als primärer SL, ATR-SL als Fallback. Trailing Stop mit `calculate_trailing_stop()`. Handbuch-konform (1,5–2,5× ATR(14)).

**CRV minimum 1:2 erzwingen — ✅ implementiert**

`risk_agent.py` prüft `crv < self.min_crv` und gibt `trade_allowed=False` zurück. `config.py`: `min_crv=2.0`. Klar implementiert.

**Korrelations-Check (z.B. kein EURUSD + GBPUSD gleichzeitig long) — ❌ fehlt**

Keine Korrelationsmatrix, keine Prüfung ob gleichzeitig offene Positionen in korrelierte Paare kein Doppel-Exposure erzeugen. Handbuch Kapitel 14 listet Korrelationspaare (EUR/USD ↔ GBP/USD: +0,81–0,95). Dies wäre im Risk-Agent oder Orchestrator zu implementieren.

**Safe-Haven Logik (JPY/CHF/USD/Gold bei Risk-Off) — ❌ fehlt**

`macro_agent.py` gibt `macro_bias: bullish/bearish/neutral` aus, berücksichtigt aber keine Risk-On/Risk-Off Klassifikation. Kein Agent identifiziert Safe-Haven-Währungen (JPY, CHF) oder Rohstoffe (Gold) als bevorzugte Richtung bei Risikoaversion. Handbuch Kapitel 15 definiert die Hierarchie klar.

---

## Priorisierte Implementierungsempfehlungen

### 🔴 Prio 1 – Kritisch (Risikoschutz)

Diese Lücken können zu unkontrollierten Verlusten führen. Höchste Dringlichkeit.

#### P1.1 – Max 3 offene Positionen (Risk-Agent + Orchestrator)

**Was fehlt:** Keine Begrenzung gleichzeitiger Positionen.

**Implementierung:**
- `config.py`: `max_open_positions: int = 3` hinzufügen
- `risk_agent.py`: Parameter `open_positions: int = 0` in `analyze()` aufnehmen; wenn `open_positions >= max_open_positions` → `trade_allowed=False`, `rejection_reason="Max. offene Positionen erreicht"`
- `orchestrator.py`: MT5-Connector abfragen (`get_open_positions_count()`), Wert an Risk-Agent übergeben

**Aufwand:** Klein (1–2h)

---

#### P1.2 – Daily Drawdown Stop Enforcement (Orchestrator)

**Was fehlt:** `max_daily_loss` in config existiert, wird aber nicht durchgesetzt. Wert weicht ab (3 % statt 5 %).

**Implementierung:**
- `config.py`: Wert auf `0.05` (5 %) korrigieren gemäß Handbuch
- `orchestrator.py`: Beim Zyklusbeginn kumulierten Tagesverlust aus DB oder MT5 abrufen. Wenn `daily_loss >= max_daily_loss * account_balance` → alle weiteren Analysezyklen für diesen Tag blockieren, Log-Eintrag schreiben
- Alternativ: `base_agent.py` um `DailyDrawdownGuard`-Klasse erweitern

**Aufwand:** Mittel (2–4h)

---

#### P1.3 – Spread-Filter im Entry-Agent

**Was fehlt:** Spread wird nicht geprüft, Scanner vergibt Pauschal-Bonus.

**Implementierung:**
- `config.py`: Normalspread-Werte je Pair definieren:
  ```python
  normal_spread_pips: dict = field(default_factory=lambda: {
      "EURUSD": 0.5, "GBPUSD": 1.0, "USDJPY": 0.5, "USDCHF": 1.0,
      "AUDUSD": 0.8, "USDCAD": 1.0, "NZDUSD": 1.0, "GBPJPY": 1.5,
      "EURJPY": 0.8, "EURGBP": 0.7,
  })
  spread_filter_multiplier: float = 3.0  # kein Trade wenn Spread > 3x Normal
  ```
- `entry_agent.py`: Spread als optionalen Input `current_spread_pips` aufnehmen; wenn `current_spread > normal * spread_filter_multiplier` → kein Entry
- `scanner_agent.py`: Spread-Bonus entfernen oder durch echten Spread-Check ersetzen (wenn MT5 Tick-Daten verfügbar)

**Aufwand:** Klein (1–2h)

---

#### P1.4 – 30-Minuten-Sperre um High-Impact Events

**Was fehlt:** Keine zeitbasierte News-Sperre.

**Implementierung:**
- Neues Modul `data/economic_calendar.py`:
  - Abruf von ForexFactory oder investing.com Economic Calendar API
  - Gibt Liste von `(datetime_utc, impact_level, event_name)` zurück
  - Funktion `is_news_window_active(minutes_before=30, minutes_after=30) -> bool`
- `macro_agent.py`: Wenn `is_news_window_active()` → `trading_allowed=False`, `event_risk="high"`, `reasoning="High-Impact Event innerhalb ±30 Minuten"`
- Fallback: Manuelle Hinterlegung der nächsten NFP/FOMC-Termine in `config.py`

**Aufwand:** Mittel-Groß (4–8h, abhängig von API-Wahl)

---

### 🟡 Prio 2 – Wichtig (Strategische Integrität)

Diese Lücken beeinflussen die Signalqualität und Strategie-Konsistenz.

#### P2.1 – Korrelations-Check (Risk-Agent)

**Was fehlt:** Doppel-Exposure durch korrelierte Paare nicht erkannt.

**Implementierung:**
- `config.py`: Korrelationsgruppen definieren:
  ```python
  correlation_groups: list = field(default_factory=lambda: [
      ["EURUSD", "GBPUSD", "AUDUSD"],   # USD-Long-Gruppe
      ["USDCHF", "USDJPY"],             # USD-Short-Gruppe / Safe-Haven
      ["EURUSD", "USDCHF"],             # natürliches Hedge-Paar (neg. Korrelation)
  ])
  ```
- `risk_agent.py`: Bei Signal-Prüfung: wenn ein Paar aus derselben Gruppe bereits offen ist und in gleicher Richtung → Score abwerten oder `trade_allowed=False`
- Schwellenwert: 2 gleichläufige Positionen in einer Korrelationsgruppe = blockiert

**Aufwand:** Mittel (3–5h)

---

#### P2.2 – Asian Session Enforcement (Volatility-Agent oder Orchestrator)

**Was fehlt:** Kein Trend-Trading in Asian Session (00:00–08:00 UTC).

**Implementierung:**
- `config.py`: `asian_open_hour: int = 0`, `asian_close_hour: int = 8` hinzufügen
- `volatility_agent.py` oder `orchestrator.py`: Session-Erkennung erweitern:
  ```python
  if asian_open <= current_hour_utc < asian_close:
      session = "asian"
      # Trend-Trading blockieren, nur Range-Strategien erlauben
      trend_trading_allowed = False
  ```
- Wenn `session == "asian"`: Validation-Agent soll Trend-basierte Setups abwerten (Confidence-Abzug), Range-Bounce-Setups an Level-Grenzen bevorzugen

**Aufwand:** Klein (2–3h)

---

#### P2.3 – Safe-Haven Logik im Macro-Agent

**Was fehlt:** Keine Risk-On/Risk-Off Klassifikation, keine Safe-Haven-Währungspräferenz.

**Implementierung:**
- `macro_agent.py`: Prompt um Risk-Sentiment erweitern:
  ```
  "risk_sentiment": "risk_on" | "risk_off" | "neutral"
  "safe_haven_active": true | false
  ```
- Bei `risk_off` + `safe_haven_active`: Short-Bias auf AUD/USD, NZD/USD; Long-Bias auf USD/JPY short (JPY stärker), XAUUSD long
- `validation_agent.py`: Wenn Signal-Richtung dem Risk-Sentiment widerspricht → Confidence-Abzug (z.B. −15 Punkte)
- Indikatoren für Risk-Off: VIX > 25, JPY-Stärke, Gold-Rally (aus yfinance abrufbar)

**Aufwand:** Mittel (3–5h)

---

#### P2.4 – London/NY Overlap aktiv priorisieren (Scoring)

**Was fehlt:** Session-Stunden in Config, aber keine Score-Modifikation.

**Implementierung:**
- `validation_agent.py` MTF-Confluence: Session-Faktor in `_calculate_mtf_confluence()` einbauen:
  - Overlap-Fenster (13:00–17:00 UTC): `confluence_score += 1`, Label "Optimale Session"
  - London-Only (08:00–13:00): neutral
  - Asian / NY-Late (17:00–22:00): `confluence_score -= 1`
- Alternativ: `volatility_agent.py` gibt `session_quality: "optimal" | "good" | "poor"` aus

**Aufwand:** Klein (1–2h)

---

### 🟢 Prio 3 – Optimierung (SMC-Vertiefung)

Diese Features verbessern die Signalpräzision, sind aber nicht für Grundfunktionalität kritisch.

#### P3.1 – Fair Value Gaps (FVG) im Level/Entry-Agent

**Was fehlt:** Keine FVG-Erkennungslogik.

**Implementierung:**
- `entry_agent.py`: Neue Methode `_detect_fvg(df, direction)`:
  ```python
  # 3-Kerzen-Check:
  # FVG bullish: kerze[i].high < kerze[i+2].low → Lücke
  # FVG bearish: kerze[i].low > kerze[i+2].high → Lücke
  for i in range(len(df) - 2):
      gap_size = df["low"].iloc[i+2] - df["high"].iloc[i]
      if gap_size > atr * 0.1:  # Mindestgröße: 10% ATR
          fvg_zones.append({"top": df["low"].iloc[i+2], "bottom": df["high"].iloc[i]})
  ```
- FVGs als Entry-Zone nutzen: wenn Kurs in unberührtem FVG + Trendrichtung → Entry-Signal
- `level_agent.py`: FVG-Zonen in Level-Score einbeziehen (unberührter FVG auf H1/H4 = starkes Level)

**Aufwand:** Mittel (3–5h)

---

#### P3.2 – Order Blocks vollständig in Entry-Logik integrieren

**Was fehlt:** OB-Farben in Config vorhanden, aber keine OB-Erkennungsroutine im Entry-Agent.

**Implementierung:**
- `entry_agent.py`: Neue Methode `_detect_order_block(df, direction)`:
  ```python
  # Bullish OB: letzte bearishe Kerze vor starker Aufwärtsbewegung
  # Erkennung: wenn df["close"].iloc[i] > df["open"].iloc[i]  (starke Aufwärtskerze)
  #   → OB = letzte bearishe Kerze davor (df["close"] < df["open"])
  # Stärke: Impulsstärke = (df["close"].iloc[i] - df["open"].iloc[i]) / atr
  ```
- OB gilt als konsumiert wenn Kurs > `watch_agent_zone_update_ob_consumed_threshold` × ATR eingedrungen ist (bereits in Config)
- Entry bei Retest des OB → Entry-Typ `"order_block_retest"` mit hohem Confidence-Modifier

**Aufwand:** Mittel (4–6h)

---

#### P3.3 – SMC Triple-Confluence für Scoring

**Was fehlt:** Handbuch Kapitel 19: OB + FVG + Liquidity Sweep = stärkstes Signal.

**Implementierung:**
- `validation_agent.py` `_calculate_mtf_confluence()`: Punkte für SMC-Elemente vergeben:
  - Order Block Retest: `+1`
  - FVG vorhanden: `+1`
  - BoS bestätigt (aus Trend-Agent): `+1`
  - Premium/Discount Zone (Fibonacci 0,5+): `+1`
- Wenn alle 4 SMC-Elemente aktiv: Label `"smc_triple_confluence"`, Modifier `+0.40`

**Aufwand:** Klein (1–2h, nach P3.1+P3.2)

---

## Zusammenfassung nach Dringlichkeit

| Prio | Punkt | Agent/Datei | Aufwand |
|------|-------|-------------|---------|
| 🔴 P1.1 | Max 3 offene Positionen | `risk_agent.py`, `orchestrator.py` | 1–2h |
| 🔴 P1.2 | Daily Drawdown Enforcement | `config.py`, `orchestrator.py` | 2–4h |
| 🔴 P1.3 | Spread-Filter | `config.py`, `entry_agent.py` | 1–2h |
| 🔴 P1.4 | 30-min News-Sperre | `data/economic_calendar.py`, `macro_agent.py` | 4–8h |
| 🟡 P2.1 | Korrelations-Check | `config.py`, `risk_agent.py` | 3–5h |
| 🟡 P2.2 | Asian Session kein Trend | `config.py`, `volatility_agent.py` | 2–3h |
| 🟡 P2.3 | Safe-Haven / Risk-Off Logik | `macro_agent.py`, `validation_agent.py` | 3–5h |
| 🟡 P2.4 | Overlap Session Scoring | `validation_agent.py` | 1–2h |
| 🟢 P3.1 | Fair Value Gaps (FVG) | `entry_agent.py`, `level_agent.py` | 3–5h |
| 🟢 P3.2 | Order Blocks in Entry | `entry_agent.py` | 4–6h |
| 🟢 P3.3 | SMC Triple-Confluence Score | `validation_agent.py` | 1–2h |

**Empfohlene Reihenfolge:** P1.1 → P1.3 → P1.2 → P2.4 → P2.2 → P2.1 → P1.4 → P2.3 → P3.2 → P3.1 → P3.3
