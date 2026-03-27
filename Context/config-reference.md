# config.json – Vollständige Parameterdokumentation

> **Hinweis:** Diese Datei wurde automatisch aus `Skript/invest_app/config.json` generiert.
> Bei Änderungen an `config.json` muss diese Dokumentation entsprechend aktuell gehalten werden.
> Secrets (API-Keys, Passwörter) verbleiben in `.env` und sind hier nicht aufgeführt.

---

## Inhaltsverzeichnis

1. [Symbole & Scanner](#1-symbole--scanner)
2. [Risikomanagement](#2-risikomanagement)
3. [Handelssessions](#3-handelssessions)
4. [Pipeline & Ablaufsteuerung](#4-pipeline--ablaufsteuerung)
5. [MetaTrader 5 (MT5)](#5-metatrader-5-mt5)
6. [Chart & Zeitrahmen](#6-chart--zeitrahmen)
7. [Chart-Farben & Visualisierung](#7-chart-farben--visualisierung)
8. [Wirtschaftskalender](#8-wirtschaftskalender)
9. [Watch-Agent](#9-watch-agent)
10. [KI-Modelle](#10-ki-modelle)
11. [Anwendung & Logging](#11-anwendung--logging)
12. [Korrelationsfilter](#12-korrelationsfilter)
13. [Safe-Haven-Filter](#13-safe-haven-filter)
14. [Smart Money Concepts (SMC)](#14-smart-money-concepts-smc)
15. [Volatilität & Indikatoren](#15-volatilität--indikatoren)
16. [Entry-Logik](#16-entry-logik)

---

## 1. Symbole & Scanner

Steuert, welche Märkte analysiert werden und wie der dynamische Symbol-Scanner arbeitet.

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `fallback_symbols` | Array\<string\> | `["EURUSD","GBPUSD","USDJPY","USDCHF","AUDUSD","XAUUSD","BTCUSD"]` | Symbolliste, die genutzt wird, wenn MT5 keine `available_symbols.json` liefert. Enthält die wichtigsten Forex-Paare plus Gold und Bitcoin. |
| `yfinance_symbol_map` | Objekt | *(siehe config)* | Mapping von internen Symbol-Namen (z. B. `EURUSD`) auf yfinance-Ticker-Symbole (z. B. `EURUSD=X`). Wird auf Mac/Linux oder im Demo-Modus benötigt. |
| `scanner_enabled` | Boolean | `true` | **true:** Der Scanner wählt die zu analysierenden Symbole dynamisch nach Score aus. **false:** Es wird ausschließlich die `fallback_symbols`-Liste verwendet. |
| `scanner_max_symbols` | Integer | `10` | Maximale Anzahl Symbole, die der Scanner insgesamt auswertet. Höhere Werte erhöhen Abdeckung, aber auch Laufzeit und API-Kosten. |
| `scanner_min_score` | Integer | `10` | Mindest-Score (0–100), den ein Symbol erreichen muss, um in die Analyse aufgenommen zu werden. Höherer Wert → strengere Vorauswahl. |
| `scanner_top_n` | Integer | `5` | Anzahl der besten Symbole, die nach dem Scoring in die vollständige Pipeline gegeben werden. |
| `scanner_respect_category_limits` | Boolean | `true` | **true:** Die in `scanner_category_limits` definierten Obergrenzen pro Kategorie werden eingehalten. **false:** Keine kategorische Begrenzung, reine Score-Sortierung. |
| `scanner_interval_minutes` | Integer | `5` | Intervall in Minuten, in dem der Scanner neu ausgeführt wird. Sollte dem `cycle_interval_minutes` entsprechen. |
| `scanner_categories` | Array\<string\> | `["forex","indices","commodities"]` | Kategorien, die der Scanner berücksichtigt. Mögliche Werte: `forex`, `indices`, `commodities`, `crypto`. |
| `scanner_category_limits` | Objekt | forex: 5, indices: 3, commodities: 2, crypto: 0 | Maximale Anzahl Symbole pro Kategorie im Analyse-Zyklus. `0` bedeutet, die Kategorie ist deaktiviert (hier: Krypto). |
| `symbol_provider_max_file_age_minutes` | Integer | `5` | Maximales Alter der `available_symbols.json` von MT5 in Minuten. Ist die Datei älter, wird auf `fallback_symbols` zurückgegriffen. |

---

## 2. Risikomanagement

Kernparameter für Positionsgrößen, Stop-Loss, Take-Profit und Risikofreigabe.

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `risk_per_trade` | Float | `0.01` | Maximales Risiko pro Trade als Anteil des Gesamtkapitals (0.01 = 1%). Niedrigerer Wert → konservativere Positionsgröße. |
| `max_daily_loss` | Float | `0.03` | Maximaler Tagesverlust als Kapitalanteil (0.03 = 3%). Wird dieses Limit erreicht, werden keine neuen Trades eröffnet. |
| `drawdown_enabled` | Boolean | `true` | **true:** Tagesverlust-Limit wird aktiv überwacht und erzwingt Handelssperre. **false:** Kein automatischer Handelsstopp bei Verlustlimit. |
| `max_open_positions` | Integer | `3` | Maximale Anzahl gleichzeitig offener Positionen. Verhindert Überexposition bei mehreren Signalen. |
| `min_crv` | Float | `2.0` | Mindest-Chance-Risiko-Verhältnis (CRV). Ein Trade mit SL=50 Pips erfordert TP ≥ 100 Pips. Höherer Wert → nur asymmetrischere Setups. |
| `atr_period` | Integer | `14` | Anzahl Perioden für die ATR-Berechnung (Average True Range). Standardwert nach Wilder. Höher → glatterer ATR; niedriger → reaktiver. |
| `atr_sl_multiplier` | Float | `2.0` | SL-Distanz = ATR × Multiplikator. Höherer Wert → weiterer Stop, weniger vorzeitige Ausstopper, aber größeres Verlustrisiko. |
| `atr_tp_multiplier` | Float | `4.0` | TP-Distanz = ATR × Multiplikator. Sollte stets mindestens `atr_sl_multiplier × min_crv` entsprechen. |
| `trailing_stop_atr_multiplier` | Float | `2.0` | ATR-Multiplikator für den Trailing Stop (aktiviert ab 1:1 CRV). Höherer Wert → mehr Spielraum für den Kurs, aber späterer Ausstieg. |
| `min_confidence_score` | Float | `80.0` | Mindest-Confidence-Score (0–100) für ein freigegebenes Signal. Signale unter diesem Schwellenwert werden als nachrangig oder verworfen eingestuft. |
| `max_sl_pct` | Float | `0.03` | Maximaler Stop-Loss als prozentualer Preisabstand (3%). Schützt vor übermäßig weiten Stops bei teuren Instrumenten. |
| `max_exposure_pct` | Float | `0.03` | Maximale Gesamtexposition eines einzelnen Symbols gegenüber dem Gesamtkapital (3%). |
| `forex_max_sl_pips` | Integer | `80` | Absolutes Pip-Limit für Forex-Stops. Trades, bei denen der ATR-basierte SL diesen Wert überschreitet, werden abgelehnt. |
| `stock_max_sl_pct` | Float | `0.03` | Maximaler SL-Abstand für Aktien als Prozentanteil vom Einstiegspreis (3%). |
| `swing_sl_buffer_pct` | Float | `0.0002` | Zusätzlicher Puffer (0.02%) über/unter einem Swing-High/Low beim Setzen des strukturellen SL. |
| `max_orders_per_symbol` | Integer | `2` | Maximale Anzahl offener Orders pro Symbol gleichzeitig. |
| `spread_filter_multiplier` | Float | `3.0` | Signals werden blockiert, wenn der aktuelle Spread größer als `normal_spread × Multiplikator` ist. Höherer Wert → toleranter gegenüber erhöhtem Spread. |
| `normal_spread_pips` | Objekt | *(je Symbol)* | Normaler Spread in Pips pro Symbol unter typischen Marktbedingungen. Basis für den Spread-Filter. |

---

## 3. Handelssessions

Definiert die Öffnungs- und Schlusstzeiten der Hauptbörsenzeiten (alle Angaben in UTC).

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `london_open_hour` | Integer | `8` | Stunde (UTC), ab der die London Session gilt (08:00 UTC). |
| `london_close_hour` | Integer | `17` | Stunde (UTC), bis zu der die London Session gilt (17:00 UTC). |
| `ny_open_hour` | Integer | `13` | Stunde (UTC), ab der die New York Session gilt (13:00 UTC). |
| `ny_close_hour` | Integer | `22` | Stunde (UTC), bis zu der die New York Session gilt (22:00 UTC). |
| `asian_open_hour` | Integer | `0` | Stunde (UTC), ab der die Asien Session gilt (00:00 UTC). |
| `asian_close_hour` | Integer | `8` | Stunde (UTC), bis zu der die Asien Session gilt (08:00 UTC). |
| `asian_session_trend_block` | Boolean | `true` | **true:** Während der Asien-Session werden Trend-Trades blockiert (typisch choppy/seitwärts). **false:** Kein Session-basierter Trendblock. |
| `asian_session_start_utc` | Integer | `0` | Asien-Session-Start für den Scoring-Mechanismus (UTC-Stunde). |
| `asian_session_end_utc` | Integer | `9` | Asien-Session-Ende für den Scoring-Mechanismus (UTC-Stunde). |
| `session_scoring_enabled` | Boolean | `true` | **true:** Die aktive Session beeinflusst den Signal-Score (Bonus für Overlap/Solo). **false:** Kein Session-basierter Score-Einfluss. |
| `session_overlap_bonus` | Integer | `5` | Score-Bonus wenn London und New York gleichzeitig aktiv sind (höchste Liquidität). |
| `session_solo_bonus` | Integer | `2` | Score-Bonus wenn eine einzelne Haupt-Session aktiv ist (London oder NY, aber nicht beide). |

---

## 4. Pipeline & Ablaufsteuerung

Steuert den Analyse-Zyklus, Simulation, News-Blocking und Logging.

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `cycle_interval_minutes` | Integer | `5` | Intervall in Minuten zwischen vollständigen Analyse-Zyklen (alle Agenten). Kürzeres Intervall → aktuellere Signale, höhere API-Kosten. |
| `watch_interval_seconds` | Integer | `15` | Intervall in Sekunden für den Watch-Agent (1min-Takt für Entry-Präzision). |
| `news_cache_ttl` | Integer | `3600` | Time-to-Live des News-Cache in Sekunden (3600 = 60 Minuten). Nach Ablauf werden News neu abgerufen. |
| `confidence_threshold` | Integer | `80` | Confidence-Schwellenwert (0–100) für die Signalfreigabe in der Pipeline. Identisch mit `risk.min_confidence_score`, steuert den Reporting-Filter. |
| `news_yahoo_enabled` | Boolean | `false` | **true:** News werden zusätzlich über Yahoo Finance abgerufen. **false:** Nur Wirtschaftskalender-Daten werden genutzt. |
| `simulation_mode_enabled` | Boolean | `false` | **true:** Aktiviert den einmaligen Test-Modus (SimulationAgent injiziert synthetisches Signal). **false:** Normalbetrieb. |
| `simulation_trigger_after_watch_cycles` | Integer | `3` | Anzahl Watch-Zyklen, nach denen die Simulation ausgelöst wird (nur wenn `simulation_mode_enabled=true`). |
| `simulation_symbol` | String | `"EURUSD"` | Symbol, das im Simulations-Modus verwendet wird. |
| `simulation_direction` | String | `"long"` | Handelsrichtung für die Simulation. Erlaubte Werte: `"long"`, `"short"`. |
| `simulation_lot_size` | Float | `0.01` | Lot-Größe für den simulierten Trade. |
| `startup_analysis_enabled` | Boolean | `true` | **true:** Beim Programmstart wird sofort ein vollständiger Analyse-Zyklus durchgeführt. **false:** Erster Zyklus startet erst nach dem ersten Scheduler-Intervall. |
| `news_block_enabled` | Boolean | `true` | **true:** Neue Einstiege werden vor/nach Hochrisiko-News-Ereignissen blockiert. **false:** Keine News-basierte Handelssperre. |
| `news_block_minutes_before` | Integer | `30` | Minuten vor einem Hochrisiko-News-Ereignis, ab denen keine neuen Entries eröffnet werden. |
| `news_block_minutes_after` | Integer | `30` | Minuten nach einem Hochrisiko-News-Ereignis, während denen keine neuen Entries eröffnet werden. |
| `cycle_log_enabled` | Boolean | `true` | **true:** Jeder Analyse-Zyklus wird als separate JSON-Datei in `cycle_log_dir` protokolliert. **false:** Kein Zyklus-Logging. |
| `cycle_log_dir` | String | `"logs/cycles"` | Verzeichnis für die Zyklus-Logdateien (relativ zum Projektverzeichnis). |
| `macro_unknown_risk_blocks_trading` | Boolean | `false` | **true:** Unbekanntes/nicht auswertbares Makro-Risiko blockiert alle neuen Trades. **false:** Bei unklarer Makrolage wird der Trade trotzdem freigegeben (ggf. mit Warnung). |

---

## 5. MetaTrader 5 (MT5)

Verbindungs- und Dateipfad-Konfiguration für die MT5-Integration.

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `mt5_server` | String | `""` | Broker-Server-Adresse für die MT5-Verbindung (z. B. `"ICMarketsSC-Demo"`). Leer = keine MT5-Verbindung. |
| `mt5_common_files_path` | String | `""` | Pfad zum MT5 Common Files-Verzeichnis (z. B. `C:\Users\...\AppData\Roaming\MetaQuotes\Terminal\Common\Files`). |
| `mt5_symbols_file` | String | `"available_symbols.json"` | Dateiname für die von MT5 exportierte Symbolliste (relativ zu `mt5_common_files_path`). |
| `mt5_order_file` | String | `"pending_order.json"` | Dateiname, in den InvestApp eine Order-Anfrage schreibt (wird von MQL5 ausgelesen). |
| `mt5_result_file` | String | `"order_result.json"` | Dateiname, in den MQL5 das Ausführungsergebnis einer Order schreibt. |
| `mt5_zones_file` | String | `"C:/MT5/MQL5/Files/mt5_zones.json"` | Absoluter Pfad zur JSON-Datei mit Analyse-Zonen für den MQL5-Chart-Indikator. |
| `mt5_zones_export_enabled` | Boolean | `true` | **true:** Nach jedem Analyse-Zyklus wird `mt5_zones.json` für den MQL5-Indikator aktualisiert. **false:** Kein Chart-Export. |
| `mt5_path` | String | `"C:\\Program Files\\MetaTrader 5\\terminal64.exe"` | Absoluter Pfad zur MetaTrader 5 Executable (nur Windows). Wird für den automatischen MT5-Start verwendet. |

---

## 6. Chart & Zeitrahmen

Definiert die Analyse-Zeitrahmen und technische Indikatoren.

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `htf_timeframe` | String | `"15m"` | Higher Timeframe (HTF) für die Trendanalyse (Trend-Agent). Erlaubte Werte: `"1m"`, `"5m"`, `"15m"`, `"1h"`, `"4h"`, `"1d"`. Höherer Zeitrahmen → stärkere Trendsignale, weniger Rauschen. |
| `entry_timeframe` | String | `"5m"` | Entry-Zeitrahmen für die Einstiegssuche (Entry-Agent). Sollte niedriger sein als `htf_timeframe`. |
| `htf_bars` | Integer | `200` | Anzahl der geladenen Kerzen im Higher Timeframe. Mehr Bars → bessere Trendanalyse, aber höhere Ladezeiten. |
| `entry_bars` | Integer | `100` | Anzahl der geladenen Kerzen im Entry-Zeitrahmen. |
| `chart_entry_tolerance_pct` | Float | `0.05` | Preistoleranz in Prozent, innerhalb derer ein aktueller Kurs als "in der Entry-Zone" gilt (0.05 = 0.05% vom Preis). |
| `ema_periods` | Array\<Integer\> | `[9, 21, 50, 200]` | EMA-Perioden für die Trendanalyse. Die EMA 200 dient als Haupttrend-Filter; EMA 9/21 für kurzfristige Richtung; EMA 50 als mittelfristiger Filter. |

---

## 7. Chart-Farben & Visualisierung

Farbcodes für die MQL5-Visualisierung (Windows GDI-Farbformat: BGR als Integer).

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `chart_color_entry_long` | Integer | `33023` | Farbe für Long-Entry-Linien im Chart (Blau-Ton). |
| `chart_color_entry_short` | Integer | `255` | Farbe für Short-Entry-Linien im Chart (Rot). |
| `chart_color_sl` | Integer | `255` | Farbe für Stop-Loss-Linien (Rot). |
| `chart_color_tp` | Integer | `65280` | Farbe für Take-Profit-Linien (Grün). |
| `chart_color_order_block_bull` | Integer | `16776960` | Farbe für bullische Order Blocks (Gelb). |
| `chart_color_order_block_bear` | Integer | `16744272` | Farbe für bärische Order Blocks (Orange). |
| `chart_color_psych_level` | Integer | `8421504` | Farbe für psychologische Preislevel (Grau). |
| `chart_color_key_level_support` | Integer | `65280` | Farbe für Support-Level (Grün). |
| `chart_color_key_level_resistance` | Integer | `255` | Farbe für Resistance-Level (Rot). |
| `chart_color_fvg` | Integer | `5087744` | Farbe für Fair Value Gaps (Dunkelgrün). |
| `chart_color_liquidity` | Integer | `10235616` | Farbe für Liquiditätszonen (Türkis). |
| `chart_line_width_main` | Integer | `2` | Linienbreite für Hauptlinien (Entry, SL, TP). Wert 1–5. |
| `chart_line_width_secondary` | Integer | `1` | Linienbreite für sekundäre Linien (Zonen, Level). |

---

## 8. Wirtschaftskalender

Konfiguration für den Abruf von Wirtschaftsdaten und News-Events.

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `economic_calendar_provider` | String | `"auto"` | Anbieter für den Wirtschaftskalender. `"auto"` wählt den verfügbaren Anbieter automatisch. Weitere mögliche Werte: `"jblanked"`. |
| `economic_calendar_jblanked_api_key` | String | `""` | API-Key für den jblanked.com-Wirtschaftskalender-Dienst. Leer = kein jblanked-Zugriff. (Achtung: Key gehört in `.env`) |
| `economic_calendar_jblanked_url` | String | *(URL)* | API-Endpoint für den jblanked Forex Factory Calendar. |
| `economic_calendar_lookback_hours` | Integer | `12` | Wie viele Stunden in die Vergangenheit der Kalender nach bereits eingetretenen Ereignissen sucht. |
| `economic_calendar_lookahead_hours` | Integer | `24` | Wie viele Stunden in die Zukunft der Kalender nach bevorstehenden Ereignissen sucht. Bestimmt, wie weit im Voraus ein News-Block ausgelöst wird. |
| `economic_calendar_high_impact_only` | Boolean | `true` | **true:** Nur Hochrisiko-Ereignisse (rote Nachrichten) werden für den News-Block berücksichtigt. **false:** Auch mittelhohe Ereignisse lösen den Block aus. |

---

## 9. Watch-Agent

Parameter für den Watch-Agent, der im 1-Minuten-Takt Entry-Präzision und offene Positionen überwacht.

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `watch_agent_zone_update_enabled` | Boolean | `true` | **true:** Der Watch-Agent aktualisiert Zonendaten in jedem Zyklus. **false:** Keine Zonen-Aktualisierung durch den Watch-Agent. |
| `watch_agent_zone_update_entry_tolerance_pct` | Float | `0.5` | Toleranzbereich in Prozent, innerhalb dessen eine Zone als "aktiv" (Kurs befindet sich in der Zone) gilt. Höherer Wert → mehr Zonen werden als aktiv gewertet. |
| `watch_agent_zone_update_ob_consumed_threshold` | Float | `0.3` | Schwellenwert (0–1), ab dem ein Order Block als "konsumiert" gilt (30% Überschneidung). Überschrittene Blöcke werden deaktiviert. |
| `watch_agent_heartbeat_interval` | Integer | `5` | Anzahl Watch-Zyklen zwischen zwei Heartbeat-Log-Einträgen (Lebenszeichen in Konsole und Log). |

---

## 10. KI-Modelle

Konfiguration der verwendeten Large Language Models (Claude und OpenAI).

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `claude_model` | String | `"claude-opus-4-6"` | Claude-Modell-ID für Macro- und Validation-Agent. Aktuell verfügbar: `claude-opus-4-6`, `claude-sonnet-4-6`, `claude-haiku-4-5-20251001`. Opus = höchste Qualität, Haiku = schnellster/günstigster. |
| `claude_max_tokens` | Integer | `2048` | Maximale Anzahl Output-Tokens pro Claude-API-Aufruf. Höherer Wert → ausführlichere Analysen, höhere Kosten. |
| `claude_retry_attempts` | Integer | `3` | Anzahl Wiederholungsversuche bei fehlgeschlagenem Claude-API-Aufruf. |
| `claude_retry_delay` | Float | `2.0` | Wartezeit in Sekunden zwischen zwei Retry-Versuchen. |
| `openai_model` | String | `"gpt-4o"` | OpenAI-Modell für optionale GPT-basierte Analyse. |
| `openai_temperature` | Float | `0.2` | Kreativitätsparameter für OpenAI-Antworten (0 = deterministisch, 1 = kreativ). Niedrig ist für Trading-Analyse empfohlen. |
| `openai_max_tokens` | Integer | `2000` | Maximale Anzahl Output-Tokens pro OpenAI-API-Aufruf. |

---

## 11. Anwendung & Logging

Allgemeine Anwendungsparameter, Betriebsmodus und Log-Konfiguration.

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `trading_mode` | String | `"demo"` | Betriebsmodus. `"demo"` = kein echtes Kapital, sichere Tests. `"live"` = echte Order-Ausführung (erfordert explizite Freigabe). |
| `log_level` | String | `"INFO"` | Log-Detailgrad. Werte: `"DEBUG"` (alles), `"INFO"` (Standard), `"WARNING"`, `"ERROR"`, `"CRITICAL"`. Debug-Level deutlich gesprächiger. |
| `log_dir` | String | `"logs"` | Verzeichnis für Log-Dateien (relativ zum Projektverzeichnis). |
| `output_dir` | String | `"Output"` | Verzeichnis für generierte Signallisten, Berichte und Exporte. |
| `db_path` | String | `"invest_app.db"` | Pfad zur SQLite-Datenbankdatei (relativ zum Projektverzeichnis). |
| `show_startup_banner` | Boolean | `true` | **true:** Beim Programmstart wird ein ASCII-Banner in der Konsole angezeigt. **false:** Kein Banner. |
| `show_cycle_banner` | Boolean | `true` | **true:** Zu Beginn jedes Analyse-Zyklus wird ein Trenn-Banner ausgegeben. **false:** Kompaktere Konsolenausgabe. |
| `verbose_terminal_output` | Boolean | `true` | **true:** Detaillierte Ausgabe jedes Agenten-Schritts in der Konsole. **false:** Nur wesentliche Meldungen (ruhigere Konsole). |
| `verbose_show_rejected` | Boolean | `true` | **true:** Verworfene Signale (unter Confidence-Schwellenwert) werden ebenfalls in der Konsole angezeigt. **false:** Nur freigegebene Signale werden ausgegeben. |

---

## 12. Korrelationsfilter

Verhindert überkorrelierte Positionen bei eng verwandten Märkten.

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `correlation_check_enabled` | Boolean | `true` | **true:** Bevor ein neues Signal freigegeben wird, prüft das System die Korrelation zu bereits offenen Positionen. Stark korrelierte Zusatz-Trades werden blockiert. **false:** Keine Korrelationsprüfung. |

---

## 13. Safe-Haven-Filter

Erkennt Risk-Off-Phasen anhand des VIX und passt das Signalverhalten an.

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `safe_haven_enabled` | Boolean | `true` | **true:** Safe-Haven-Logik ist aktiv; bei hohem VIX werden Safe-Haven-Instrumente bevorzugt. **false:** Kein VIX-basierter Filter. |
| `vix_risk_off_threshold` | Integer | `25` | VIX-Schwellenwert, ab dem eine Risk-Off-Phase erkannt wird. VIX > 25 → erhöhte Marktangst, Safe-Haven-Bonus aktiv. Niedrigerer Wert → empfindlicherer Filter. |
| `safe_haven_confidence_bonus` | Integer | `10` | Score-Bonus (Confidence-Punkte), der Safe-Haven-Instrumenten (z. B. Gold, JPY) bei aktiver Risk-Off-Phase gewährt wird. |

---

## 14. Smart Money Concepts (SMC)

Parameter für die Erkennung institutioneller Preisstrukturen (Order Blocks, Fair Value Gaps, Confluence).

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `fvg_enabled` | Boolean | `true` | **true:** Fair Value Gaps (Kurslücken zwischen Kerzen) werden erkannt und als Level gewertet. **false:** FVG-Erkennung deaktiviert. |
| `fvg_confidence_bonus` | Integer | `10` | Confidence-Bonus, wenn sich ein Entry-Signal in einem bestätigten FVG befindet. |
| `fvg_min_size_pct` | Float | `0.0002` | Mindestgröße eines FVG als Preisanteil (0.02%), um als signifikant zu gelten. Kleinere Lücken werden ignoriert. |
| `ob_enabled` | Boolean | `true` | **true:** Order Blocks werden erkannt (letzte Gegenrichtungskerze vor einem Impuls). **false:** OB-Erkennung deaktiviert. |
| `ob_confidence_bonus` | Integer | `15` | Confidence-Bonus für ein Signal im Bereich eines bestätigten Order Blocks. |
| `ob_tolerance_pips` | Float | `5.0` | Toleranz in Pips, um die ein Order Block nach oben/unten ausgedehnt wird (buffer für Fehlausbrüche). |
| `ob_impulse_atr_multiplier` | Float | `1.5` | Mindest-Impulsstärke für die OB-Erkennung: Impuls muss ≥ ATR × 1.5 groß sein. Höherer Wert → nur stärkere, "sauberere" Order Blocks. |
| `level_dedup_threshold_pct` | Float | `0.0005` | Preistoleranz für das Zusammenführen nahe beieinanderliegender Level (0.05%). Level innerhalb dieses Abstands werden dedupliziert. |
| `smc_triple_confluence_enabled` | Boolean | `true` | **true:** Dreifach-Confluence (FVG + OB + Key-Level) wird erkannt und mit Bonus versehen. **false:** Nur Einzel- und Doppel-Confluences. |
| `smc_triple_bonus` | Integer | `20` | Confidence-Bonus für dreifache SMC-Confluence (z. B. FVG + OB + S/R-Zone). |
| `smc_double_bonus` | Integer | `10` | Confidence-Bonus für zweifache SMC-Confluence (z. B. FVG + OB). |

---

## 15. Volatilität & Indikatoren

Parameter für ATR-Filter, RSI und Bollinger Bands zur Marktphasen-Erkennung.

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `min_atr_ratio` | Float | `0.5` | Minimales ATR-Verhältnis (aktueller ATR / ATR-Durchschnitt). Unterhalb dieses Werts gilt der Markt als zu "ruhig" → keine Freigabe. |
| `max_atr_ratio` | Float | `2.0` | Maximales ATR-Verhältnis. Oberhalb dieses Werts gilt der Markt als zu volatil → keine Freigabe. |
| `forecast_zone_atr_threshold` | Float | `2.0` | ATR-Multiplikator-Schwellenwert für die Forecast-Zone; Märkte oberhalb gelten als im Expansionsmodus. |
| `rsi_period` | Integer | `14` | Berechnungsperiode für den RSI (Relative Strength Index). Standard nach Wilder. |
| `rsi_overbought` | Integer | `70` | RSI-Wert, ab dem ein Markt als überkauft gilt. Long-Entries werden in dieser Zone erschwert. |
| `rsi_oversold` | Integer | `30` | RSI-Wert, unterhalb dessen ein Markt als überverkauft gilt. Short-Entries werden in dieser Zone erschwert. |
| `bb_period` | Integer | `20` | Anzahl Perioden für die Bollinger-Band-Berechnung. |
| `bb_std_dev` | Float | `2.0` | Standardabweichungs-Multiplikator für die Bollinger-Band-Breite. Höherer Wert → breitere Bänder, weniger Band-Touches. |
| `bb_squeeze_threshold` | Float | `0.01` | Schwellenwert für die BB-Squeeze-Erkennung (Bandbreite / Mittelpreis). Werte unter diesem Threshold signalisieren eine Kompressions-Phase. |
| `compression_range_ratio` | Float | `0.6` | Verhältnis von aktuellem Kursbereich zum ATR. Unterhalb dieses Werts wird eine Seitwärtsphase erkannt. |
| `expansion_atr_multiplier` | Float | `1.5` | ATR-Multiplikator als Schwellenwert für die Expansionsphasen-Erkennung. Überschreitet der Kursbereich ATR × 1.5, gilt der Markt als im Ausbruch. |

---

## 16. Entry-Logik

Fein-Parameter für die Erkennung von Entry-Mustern (Candlestick-Analyse, Fibonacci, Flags).

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `wick_body_ratio_min` | Float | `2.0` | Minimales Verhältnis von Docht zu Kerzenkörper für die Erkennung einer Pin Bar / Rejection Candle. Höherer Wert → nur markantere Pin Bars. |
| `volume_confirmation_multiplier` | Float | `1.5` | Das Volumen einer Entry-Kerze muss mindestens Durchschnittsvolumen × 1.5 betragen, um als bestätigt zu gelten. |
| `pullback_max_fib` | Float | `0.618` | Maximales Fibonacci-Retracement-Level für gültige Pullback-Entries (0.618 = 61.8%). Tiefere Pullbacks werden nicht als Entry-Zone gewertet. |
| `stop_hunt_sweep_min_atr` | Float | `0.1` | Minimale Sweep-Distanz (× ATR) für die Erkennung einer Liquiditätsjagd (Stop Hunt). |
| `stop_hunt_sweep_max_atr` | Float | `0.5` | Maximale Sweep-Distanz (× ATR) für die Erkennung einer Liquiditätsjagd. Größere Sweeps gelten als normaler Ausbruch, nicht als Stop Hunt. |
| `bull_flag_confidence_bonus` | Integer | `5` | Confidence-Bonus, wenn ein Bull-Flag-Muster erkannt wird. |
| `bear_flag_confidence_bonus` | Integer | `5` | Confidence-Bonus, wenn ein Bear-Flag-Muster erkannt wird. |
| `triangle_confidence_bonus` | Integer | `5` | Confidence-Bonus, wenn ein Dreieck-Muster (symmetrisch, aufsteigend oder absteigend) erkannt wird. |

---

*Letzte Aktualisierung: 2026-03-27 | Generiert aus `Skript/invest_app/config.json` v1.0*
