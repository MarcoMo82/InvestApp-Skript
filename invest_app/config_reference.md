# InvestApp – config.json Parameterreferenz

> **Hinweis:** Secrets (API-Keys, Passwörter) gehören **nicht** in diese Datei, sondern in `.env`.
> Diese Datei dokumentiert alle Parameter der `config.json`. Änderungen werden beim nächsten Start der Anwendung übernommen.

---

## 1. `symbols` – Symbolkonfiguration

Steuert, welche Handelsinstrumente analysiert werden und wie sie bei Yahoo Finance abgerufen werden.

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `fallback_symbols` | Liste | 7 Symbole | Wird verwendet wenn MT5 keine `available_symbols.json` liefert. Enthält die Basis-Watchlist. |
| `yfinance_symbol_map` | Dict | Vordefiniert | Übersetzungstabelle von MT5-Symbolnamen zu Yahoo Finance Ticker-Symbolen (z.B. `EURUSD` → `EURUSD=X`). |
| `scanner_enabled` | bool | `true` | Aktiviert den automatischen Symbol-Scanner, der die Watchlist dynamisch erweitert. |
| `scanner_max_symbols` | int | `10` | Maximale Gesamtzahl gleichzeitig analysierter Symbole. |
| `scanner_min_score` | int | `10` | Mindest-Score für ein Symbol um in die Watchlist aufgenommen zu werden. |
| `scanner_top_n` | int | `5` | Maximale Anzahl Symbole aus dem Scanner-Ergebnis pro Zyklus. |
| `scanner_respect_category_limits` | bool | `true` | Wenn `true`, gelten die Limits aus `scanner_category_limits`. |
| `scanner_interval_minutes` | int | `5` | Wie oft (in Minuten) der Scanner läuft und die Watchlist aktualisiert. |
| `scanner_categories` | Liste | `["forex","indices","commodities"]` | Welche Anlageklassen der Scanner berücksichtigt. |
| `scanner_category_limits` | Dict | Vordefiniert | Maximale Symbolanzahl pro Kategorie (z.B. max. 5 Forex-Paare gleichzeitig). |
| `symbol_provider_max_file_age_minutes` | int | `5` | Maximales Alter (Minuten) der `available_symbols.json` bevor sie als veraltet gilt. |

**Praxistipp:** Um Krypto-Symbole zu aktivieren, `crypto` in `scanner_categories` eintragen und `scanner_category_limits.crypto` auf z.B. `2` setzen.

---

## 2. `ea_symbols` – MQL5 Symbol-Override

Optionale manuelle Symbollisten für die drei MQL5 Expert Advisors. Leer = EA lädt Symbole automatisch aus MT5 Market Watch.

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `forex` | Liste | `[]` | Symbole für `InvestApp_Forex.mq5` (z.B. `["EURUSD","GBPUSD"]`). |
| `indexes` | Liste | `[]` | Symbole für `InvestApp_Indexes.mq5`. |
| `nasdaq` | Liste | `[]` | Symbole für `InvestApp_NASDAQ.mq5`. |

---

## 3. `risk` – Risikomanagement ⚠️

> **Kritische Parameter.** Falsche Einstellungen können zu Kapitalverlust führen. Änderungen nur mit Bedacht vornehmen.

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `risk_per_trade` | float | `0.01` | Risikoanteil pro Trade als Dezimalzahl (0.01 = 1% des Kontos). |
| `risk_per_trade_pct` | float | `1.0` | Risiko in Prozent (wird parallel zu `risk_per_trade` verwendet). |
| `max_daily_loss` | float | `0.03` | ⚠️ Maximaler Tagesverlust (3% des Kontos). Bei Erreichen: kein neuer Trade für heute. |
| `max_daily_drawdown_pct` | float | `3.0` | Maximaler prozentualer Tages-Drawdown (identisch mit `max_daily_loss`, in Prozent). |
| `drawdown_enabled` | bool | `true` | Aktiviert den Drawdown-Schutz. Auf `false` setzen deaktiviert die Verlustbegrenzung! |
| `max_open_positions` | int | `3` | Maximale Anzahl gleichzeitig offener Positionen. |
| `max_open_trades` | int | `3` | Wie `max_open_positions` – zusätzliche Begrenzung auf Trade-Ebene. |
| `min_crv` | float | `2.0` | Mindest-Chance-Risiko-Verhältnis. Trades unter 2:1 werden abgelehnt. |
| `min_rr_ratio` | float | `2.0` | Identisch mit `min_crv`. Beide Felder werden geprüft. |
| `atr_period` | int | `14` | Perioden für ATR-Berechnung (Average True Range). Standard: 14 Kerzen. |
| `atr_sl_multiplier` | float | `2.0` | SL-Abstand = ATR × dieser Multiplikator. Höher = weiterer SL. |
| `atr_tp_multiplier` | float | `4.0` | TP-Abstand = ATR × dieser Multiplikator (ergibt CRV von 2:1). |
| `trailing_stop_atr_multiplier` | float | `2.0` | ATR-Multiplikator für den Trailing Stop (Nachlauf-Abstand). |
| `min_confidence_score` | float | `80.0` | ⚠️ Mindest-Confidence-Score (0–100%). Signale unter 80% werden verworfen. |
| `max_sl_pct` | float | `0.03` | Maximaler SL in Prozent vom Entry-Preis (3%). |
| `max_exposure_pct` | float | `0.03` | Maximales Gesamtrisiko aller offenen Positionen zusammen (3% des Kontos). |
| `forex_max_sl_pips` | int | `80` | Maximaler SL in Pips für Forex-Instrumente. |
| `stock_max_sl_pct` | float | `0.03` | Maximaler SL in Prozent für Aktien. |
| `swing_sl_buffer_pct` | float | `0.0002` | Puffer (0.02%) über/unter dem Swing-High/Low beim Swing-SL. |
| `max_orders_per_symbol` | int | `2` | Maximale offene Orders pro Symbol gleichzeitig. |
| `spread_filter_multiplier` | float | `3.0` | Trade wird blockiert wenn Spread > `normal_spread × multiplier`. |
| `normal_spread_pips` | Dict | Vordefiniert | Referenz-Spreads pro Symbol in Pips (für Spread-Filterung). |

---

## 4. `sessions` – Handelssessions

Definiert die Handelszeiten der drei großen Sessions (alle Zeiten in UTC).

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `london_open_hour` | int | `8` | London-Öffnung (08:00 UTC). |
| `london_close_hour` | int | `17` | London-Schluss (17:00 UTC). |
| `ny_open_hour` | int | `13` | New York Öffnung (13:00 UTC). |
| `ny_close_hour` | int | `22` | New York Schluss (22:00 UTC = Rollover). |
| `asian_open_hour` | int | `0` | Asien-Öffnung (00:00 UTC). |
| `asian_close_hour` | int | `8` | Asien-Schluss (08:00 UTC). |
| `asian_session_trend_block` | bool | `true` | Blockiert neue Einstiege während der Asien-Session (wenig Trend). |
| `session_scoring_enabled` | bool | `true` | Aktiviert Session-basierte Bonuspunkte im Confidence Score. |
| `session_overlap_bonus` | int | `5` | Bonus-Punkte während London-NY Overlap (13–16 UTC). |
| `session_solo_bonus` | int | `2` | Bonus-Punkte während aktiver Session (solo, kein Overlap). |

---

## 5. `pipeline` – Analyse-Pipeline

Steuert den Hauptzyklus der InvestApp.

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `cycle_interval_minutes` | int | `5` | Wie oft (in Minuten) die vollständige Agent-Pipeline läuft. |
| `watch_interval_seconds` | int | `15` | Wie oft (in Sekunden) der Watch-Agent Entry-Bedingungen prüft. |
| `news_cache_ttl` | int | `3600` | Cache-Lebensdauer für Wirtschaftskalender-Daten (Sekunden). |
| `confidence_threshold` | int | `80` | Freigabe-Schwelle für Signale (%). Identisch mit `risk.min_confidence_score`. |
| `news_yahoo_enabled` | bool | `false` | Yahoo Finance News als Makro-Quelle aktivieren. |
| `simulation_mode_enabled` | bool | `false` | Aktiviert den Simulations-Modus (keine echten Orders). |
| `simulation_trigger_after_watch_cycles` | int | `3` | Nach N Watch-Zyklen wird ein Test-Signal injiziert. |
| `simulation_symbol` | string | `"EURUSD"` | Symbol für Test-Signale im Simulations-Modus. |
| `simulation_direction` | string | `"long"` | Richtung für Test-Signale (`"long"` oder `"short"`). |
| `simulation_lot_size` | float | `0.01` | Lotgröße für Simulations-Orders. |
| `startup_analysis_enabled` | bool | `true` | Sofortiger Analyse-Zyklus beim Programmstart. |
| `news_block_enabled` | bool | `true` | Hochimpakt-News blockieren neue Einstiege. |
| `news_block_minutes_before` | int | `30` | Sperrzeit vor einem Hochimpakt-Event (Minuten). |
| `news_block_minutes_after` | int | `30` | Sperrzeit nach einem Hochimpakt-Event (Minuten). |
| `cycle_log_enabled` | bool | `true` | Aktiviert das Tages-Log (cycle_log_YYYY-MM-DD.json). |
| `cycle_log_dir` | string | `"logs/cycles"` | Verzeichnis für Tages-Log-Dateien. |
| `macro_unknown_risk_blocks_trading` | bool | `false` | Wenn `true`: unbekannte Makrolage blockiert alle Trades. |

---

## 6. `mt5` – MetaTrader 5 Integration

Verbindungs- und Dateipfade für die MT5-Kommunikation.

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `mt5_server` | string | `""` | Broker-Server (nur für direkte MT5-API-Verbindung, leer = deaktiviert). |
| `mt5_common_files_path` | string | `""` | ⚠️ Pfad zum MT5 Common Files Verzeichnis. Leer = Windows-Autoerkennung. Unter Windows: `C:\Users\[Name]\AppData\Roaming\MetaQuotes\Terminal\Common\Files`. |
| `mt5_symbols_file` | string | `"available_symbols.json"` | Dateiname für die Symbol-Liste (wird von InvestApp_Zones.mq5 geschrieben). |
| `mt5_order_file` | string | `"pending_order.json"` | Dateiname für ausstehende Orders (Python → MT5 Kommunikation). |
| `mt5_result_file` | string | `"order_result.json"` | Dateiname für Order-Ergebnisse (MT5 → Python Kommunikation). |
| `mt5_zones_file` | string | `"mt5_zones.json"` | ⚠️ Zielpfad für Zonen-Export. Nur Dateiname → Common Files. Vollständiger Pfad → direkt. |
| `mt5_zones_export_enabled` | bool | `true` | Aktiviert den Export der Zonen-Daten für MT5. |
| `mt5_path` | string | `"C:\\Program Files\\MetaTrader 5\\terminal64.exe"` | Pfad zur MT5 Installation (nur für automatischen Start). |

**Bekanntes Problem (Error 5002):** Wenn `mt5_zones_file` einen vollständigen Pfad enthält und gleichzeitig der EA `FILE_COMMON` + nur Dateinamen verwendet, schreibt Python an Ort A, MT5 liest von Ort B. Fix: `mt5_zones_file` = `"mt5_zones.json"` und `mt5_common_files_path` = korrekter Pfad zum MT5 Common Files Verzeichnis.

---

## 7. `chart` – Chart-Einstellungen

Zeitrahmen und Baranzahl für die technische Analyse.

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `htf_timeframe` | string | `"15m"` | Haupt-Zeitrahmen für Trend- und Strukturanalyse. |
| `entry_timeframe` | string | `"5m"` | Zeitrahmen für Entry-Suche. |
| `htf_bars` | int | `200` | Anzahl Kerzen für HTF-Analyse. |
| `entry_bars` | int | `100` | Anzahl Kerzen für Entry-Analyse. |
| `chart_entry_tolerance_pct` | float | `0.05` | Toleranzbereich (%) um den Entry-Preis für die Zone. |
| `ema_periods` | Liste | `[9,21,50,200]` | Berechnete EMA-Perioden. |

---

## 8. `economic_calendar` – Wirtschaftskalender

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `economic_calendar_provider` | string | `"auto"` | Datenquelle: `"auto"` (automatisch), `"jblanked"` oder `"investing"`. |
| `economic_calendar_jblanked_api_key` | string | `""` | API-Key für jblanked.com (optional, leer = kein Key nötig). |
| `economic_calendar_jblanked_url` | string | Vordefiniert | Basis-URL der jblanked API. |
| `economic_calendar_lookback_hours` | int | `12` | Wie weit zurückgeschaut wird für bereits vergangene Events (Stunden). |
| `economic_calendar_lookahead_hours` | int | `24` | Wie weit vorausgeschaut wird für kommende Events (Stunden). |
| `economic_calendar_high_impact_only` | bool | `true` | Nur Hochimpakt-Events (rote Nachrichten) berücksichtigen. |

---

## 9. `watch_agent` – Watch-Agent Einstellungen

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `watch_agent_zone_update_enabled` | bool | `true` | Aktiviert dynamische Zonen-Aktualisierung während Signalüberwachung. |
| `watch_agent_zone_update_entry_tolerance_pct` | float | `0.5` | Zone gilt als "aktiv" wenn Preis ≤ 0.5% vom Entry entfernt. |
| `watch_agent_zone_update_ob_consumed_threshold` | float | `0.3` | Order Block gilt als "konsumiert" wenn Preis mehr als 30% in den Block eingedrungen ist. |
| `watch_agent_heartbeat_interval` | int | `5` | Alle N Watch-Zyklen vollständige Statusausgabe und MT5-Sync. |

---

## 10. `model` – KI-Modelle

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `claude_model` | string | `"claude-opus-4-6"` | Anthropic Claude Modell für komplexe Analysen. |
| `claude_max_tokens` | int | `2048` | Maximale Antwortlänge für Claude. |
| `claude_retry_attempts` | int | `3` | Wiederholungsversuche bei API-Fehlern. |
| `claude_retry_delay` | float | `2.0` | Wartezeit zwischen Wiederholungsversuchen (Sekunden). |
| `openai_model` | string | `"gpt-4o"` | OpenAI Modell (falls OpenAI als Alternative konfiguriert). |
| `openai_temperature` | float | `0.2` | Kreativitätsfaktor (0 = deterministisch, 1 = kreativ). |
| `openai_max_tokens` | int | `2000` | Maximale Antwortlänge für OpenAI. |

---

## 11. `app` – Anwendungseinstellungen

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `trading_mode` | string | `"demo"` | ⚠️ `"demo"` oder `"live"`. Im Live-Modus werden echte Orders platziert! |
| `log_level` | string | `"INFO"` | Log-Detailstufe: `"DEBUG"`, `"INFO"`, `"WARNING"`, `"ERROR"`. |
| `log_dir` | string | `"logs"` | Verzeichnis für Log-Dateien. |
| `output_dir` | string | `"Output"` | Verzeichnis für generierte Ausgabedateien. |
| `db_path` | string | `"invest_app.db"` | Pfad zur SQLite-Datenbank. |
| `show_startup_banner` | bool | `true` | InvestApp-Banner beim Start anzeigen. |
| `show_cycle_banner` | bool | `true` | Zyklusnummer und Zeitstempel bei jedem Analyse-Zyklus anzeigen. |
| `verbose_terminal_output` | bool | `true` | Detaillierte Symbol-Analyse-Ergebnisse in der Konsole ausgeben. |
| `verbose_show_rejected` | bool | `true` | Auch verworfene Signale (< 80%) in der Konsolenausgabe zeigen. |

---

## 12. `volatility` – Volatilitätsfilter

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `min_atr_ratio` | float | `0.5` | Mindest-ATR-Verhältnis. Zu geringe Volatilität → kein Trade. |
| `max_atr_ratio` | float | `2.0` | Maximal-ATR-Verhältnis. Zu hohe Volatilität → kein Trade. |
| `forecast_zone_atr_threshold` | float | `2.0` | Schwellenwert für Forecast-Zonen (ATR-Multiplikator). |
| `rsi_period` | int | `14` | Perioden für RSI-Berechnung. |
| `rsi_overbought` | int | `70` | RSI-Wert ab dem Überkauft gilt (Long-Block). |
| `rsi_oversold` | int | `30` | RSI-Wert ab dem Überverkauft gilt (Short-Block). |
| `bb_period` | int | `20` | Bollinger Band Periode. |
| `bb_std_dev` | float | `2.0` | Bollinger Band Standardabweichung (Bandbreite). |
| `bb_squeeze_threshold` | float | `0.01` | Bandbreite unter diesem Wert = Squeeze-Markt (niedrige Volatilität). |
| `compression_range_ratio` | float | `0.6` | High-Low-Range < 60% der ATR = Kompressions-Marktphase. |
| `expansion_atr_multiplier` | float | `1.5` | Range > 150% der ATR = Expansions-Marktphase. |

---

## 13. `entry` – Entry-Strategien

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `wick_body_ratio_min` | float | `2.0` | Rejection-Wick: Wick muss mindestens 2× so lang wie der Kerzenkörper sein. |
| `volume_confirmation_multiplier` | float | `1.5` | Volumen-Bestätigung: aktuelles Volumen > Ø-Volumen × 1.5. |
| `pullback_max_fib` | float | `0.618` | Maximaler Fib-Retracement für Pullback-Einstiege (61.8%). |
| `stop_hunt_sweep_min_atr` | float | `0.1` | Minimale Wick-Länge für Stop-Hunt-Erkennung (10% der ATR). |
| `stop_hunt_sweep_max_atr` | float | `0.5` | Maximale Wick-Länge für Stop-Hunt-Erkennung (50% der ATR). |
| `bull_flag_confidence_bonus` | int | `5` | Bonus-Punkte bei erkannter Bull-Flag-Formation. |
| `bear_flag_confidence_bonus` | int | `5` | Bonus-Punkte bei erkannter Bear-Flag-Formation. |
| `triangle_confidence_bonus` | int | `5` | Bonus-Punkte bei erkanntem Dreieck-Muster. |
| `sl_atr_multiplier` | float | `2.0` | SL-Abstand für Entry-Agent = ATR × 2.0. |
| `tp_rr_ratio` | float | `2.0` | Ziel-CRV für Entry-Agent (TP = 2 × SL-Abstand). |
| `signal_confidence_threshold` | float | `0.65` | Interner Schwellenwert für Entry-Signale (65%). |

---

## 14. `filters` – MQL5-Filterparameter

Parameter für den MQL5 `VolatilityFilter` und `TrendAnalysis`.

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `min_atr_multiplier` | float | `0.5` | Mindest-ATR-Ratio für Volatilitätsfreigabe. |
| `max_atr_multiplier` | float | `2.0` | Maximal-ATR-Ratio für Volatilitätsfreigabe. |
| `max_spread_pips` | float | `2.0` | Maximaler Spread (Pips) für Handelsfreigabe. |
| `adx_min_threshold` | int | `20` | ADX unter 20 = kein Trend → Einstieg blockiert. |
| `rsi_overbought` | int | `70` | RSI-Schwelle überkauft (MQL5). |
| `rsi_oversold` | int | `30` | RSI-Schwelle überverkauft (MQL5). |
| `bypass_session_filter` | bool | `true` | Wenn `true`: Session-Filter wird ignoriert (alle Zeiten handelbar). |

---

## 15. `trade_exit` – Trade-Schließungsregeln

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `use_fixed_tp` | bool | `false` | Wenn `true`: fixer TP statt dynamischem Smart-TP. |
| `close_before_rollover_enabled` | bool | `true` | Positionen vor Rollover schließen. |
| `close_before_rollover_minutes` | int | `30` | 30 Minuten vor Rollover werden alle Positionen geschlossen. |
| `close_only_if_profitable` | bool | `false` | Rollover-Schließung nur bei profitablen Positionen. |
| `rollover_time_utc` | string | `"22:00"` | Rollover-Uhrzeit in UTC (entspricht 22:00 NY-Schluss). |

---

## 16. `session` – MQL5 Handelssessions

Einstellungen speziell für die MQL5 EAs (parallel zu `sessions`).

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `trade_london` | bool | `true` | Handel während London-Session aktiviert. |
| `trade_new_york` | bool | `true` | Handel während NY-Session aktiviert. |
| `trade_asian` | bool | `true` | Handel während Asien-Session aktiviert. |

---

## 17. `trade_management` – Breakeven & Trailing

Phasenbasiertes Trade-Management (vollständig durch MQL5 EA verwaltet).

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `breakeven_trigger_atr` | float | `1.0` | Phase 1→2: Breakeven-Setzung wenn Preis 1× ATR im Gewinn. |
| `breakeven_buffer_pips` | int | `2` | Puffer über Entry-Preis beim Breakeven-SL (2 Pips). |
| `structure_trigger_atr` | float | `2.0` | Phase 2→3: Struktur-Trailing startet bei 2× ATR Gewinn. |
| `structure_sl_buffer_atr` | float | `0.25` | SL-Puffer beim Struktur-Trailing (0.25× ATR unter Swing-Low). |
| `trailing_atr_multiplier` | float | `1.5` | ATR-Trailing Abstand (Phase 3): SL folgt 1.5× ATR hinter Preis. |
| `watch_poll_interval_seconds` | int | `60` | Polling-Intervall für Trade-Status-Überwachung (Sekunden). |

---

## 18. `smart_tp` – Intelligenter Take Profit

Passt den TP dynamisch an wenn Markt seitwärts läuft und Session-Ende naht.

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `enabled` | bool | `true` | Smart-TP aktivieren. |
| `activate_minutes_before_rollover` | int | `60` | Smart-TP greift N Minuten vor dem Rollover. |
| `range_candles_lookback` | int | `12` | Anzahl M5-Kerzen für die Range-Berechnung. |
| `range_buffer_pips` | int | `2` | Puffer (Pips) vom Range-High/Low zum neuen TP. |
| `sideways_atr_ratio` | float | `0.5` | Range < ATR × 0.5 = Seitwärtsmarkt. Nur dann greift Smart-TP. |
| `min_profit_pips` | int | `5` | Position muss mindestens 5 Pips im Gewinn sein bevor Smart-TP aktiv wird. |

**Logik:** Smart-TP wird nur gesetzt wenn (1) Rollover in ≤ 60 Min, (2) Markt konsolidiert (Range < 0.5 × ATR), (3) Position ≥ 5 Pips im Plus. TP wird auf Range-High (Long) bzw. Range-Low (Short) minus Puffer gesetzt.

---

## 19. `learning_agent` – Lernagent

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `pattern_threshold` | int | `10` | Mindestanzahl Datenpunkte für statistisch signifikante Muster. |
| `confidence_adjustment_step` | int | `5` | Schrittgröße für Confidence-Anpassungen (Prozentpunkte). |
| `max_confidence_threshold` | int | `95` | Maximaler Confidence-Wert den der Learning Agent setzen darf (%). |

---

## 20. `level_agent` – Level-Agent

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `swing_lookback` | int | `5` | Anzahl Kerzen für Swing-High/Low Erkennung. |
| `cluster_threshold_pct` | float | `0.001` | Preiszonen innerhalb von 0.1% werden zu einem Cluster zusammengefasst. |
| `top_n_zones` | int | `5` | Maximale Anzahl ausgegebener Key-Level-Zonen. |

---

## 21. `smc` – Smart Money Concepts

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `fvg_enabled` | bool | `true` | Fair Value Gaps aktivieren. |
| `fvg_confidence_bonus` | int | `10` | Bonus-Punkte bei FVG-Konfluenz. |
| `fvg_min_size_pct` | float | `0.0002` | Minimale FVG-Größe (0.02% des Preises). |
| `ob_enabled` | bool | `true` | Order Blocks aktivieren. |
| `ob_confidence_bonus` | int | `15` | Bonus-Punkte bei OB-Konfluenz. |
| `ob_tolerance_pips` | float | `5.0` | Toleranzbereich für Order-Block-Erkennung (Pips). |
| `ob_impulse_atr_multiplier` | float | `1.5` | Impuls muss > 1.5× ATR sein um als Order Block zu gelten. |
| `level_dedup_threshold_pct` | float | `0.0005` | Doppeltzonen-Bereinigung: Zonen < 0.05% voneinander werden zusammengeführt. |
| `smc_triple_confluence_enabled` | bool | `true` | Dreifach-Konfluenz (FVG + OB + Key Level) aktivieren. |
| `smc_triple_bonus` | int | `20` | Bonus bei Dreifach-Konfluenz. |
| `smc_double_bonus` | int | `10` | Bonus bei Zweifach-Konfluenz. |

---

## 22. `volatility` (Erweiterung), `correlation`, `safe_haven`

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `correlation_check_enabled` | bool | `true` | Korrelationscheck zwischen offenen Positionen aktivieren. |
| `safe_haven_enabled` | bool | `true` | Safe-Haven-Erkennung aktivieren (VIX, Gold, JPY). |
| `vix_risk_off_threshold` | int | `25` | VIX > 25 = Risk-Off-Modus. Beeinträchtigt Confidence-Scoring. |
| `safe_haven_confidence_bonus` | int | `10` | Bonus bei Safe-Haven-Konfluenz in Risk-Off-Phase. |

---

## 23. `execution` – Order-Ausführung (MQL5)

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `magic_number` | int | `20260101` | Eindeutige ID für alle von InvestApp platzierten Orders in MT5. |
| `slippage_points` | int | `10` | Maximaler Slippage in Points bei Market Orders. |
| `order_comment` | string | `"InvestApp_v1"` | Kommentar für alle Orders (sichtbar in MT5 History). |
| `filling_mode` | string | `"IOC"` | Order-Füllmodus: `"IOC"` (Immediate Or Cancel) oder `"FOK"`. |

---

## Häufige Konfigurationsfehler

### Error 5002 – Zonendatei nicht gefunden
**Problem:** MT5 findet `mt5_zones.json` nicht.
**Ursache:** `mt5_zones_file` enthält einen Pfad der nicht mit dem MT5 Common Files Verzeichnis übereinstimmt.
**Fix:** `mt5_zones_file` auf `"mt5_zones.json"` setzen und `mt5_common_files_path` auf den korrekten MT5 Common Files Pfad (z.B. `C:\Users\Mosi\AppData\Roaming\MetaQuotes\Terminal\Common\Files`). In MT5 den EA-Parameter `InpZonesFile` auf `mt5_zones.json` (nur Dateiname, kein Pfad) zurücksetzen.

### Überwachte Symbole = 0
**Problem:** Watch-Agent zeigt "Überwachte Symbole: 0".
**Ursache:** Keine pending Signale und `chart_exporter` kennt keine Symbole.
**Fix:** Prüfen ob `symbols.fallback_symbols` korrekt konfiguriert ist und die Pipeline mindestens einen Analyse-Zyklus abgeschlossen hat.

### Alle Signale werden verworfen
**Problem:** Keine freigegebenen Signale.
**Ursache:** `risk.min_confidence_score` zu hoch oder Agent-Pipeline blockiert.
**Fix:** Temporär `verbose_show_rejected: true` setzen und die Ablehnungsgründe im Log prüfen. `confidence_threshold` erst dann anpassen wenn die Ablehnungsgründe verstanden sind.

### Drawdown-Schutz schlägt sofort an
**Problem:** Keine neuen Trades möglich obwohl kaum Verlust.
**Ursache:** `max_daily_loss` zu niedrig oder falsch als Dezimalzahl gesetzt.
**Fix:** `max_daily_loss: 0.03` = 3%. Nicht als Prozent (3) sondern als Dezimalzahl eintragen.

### Smart-TP greift nie an
**Problem:** Smart-TP wird nie aktiviert obwohl Rollover naht.
**Ursache:** Markt trendet (kein Seitwärtsmarkt) oder Position hat zu wenig Gewinn.
**Fix:** `sideways_atr_ratio` erhöhen (z.B. auf `0.7`) oder `min_profit_pips` reduzieren. Smart-TP ist absichtlich konservativ kalibriert.
