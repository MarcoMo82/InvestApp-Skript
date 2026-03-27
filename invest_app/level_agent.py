"""
Level-Agent Standalone: Liest market_data.json vom MT5 Common Files Pfad,
berechnet S/R-Zonen und schreibt zones.json zurück.

Aufruf durch den MQL5-EA nach jedem WriteMarketData()-Zyklus (alle 15 Min).

Ausgabe-Format zones.json (von LevelDetection.mqh konsumiert):
{
  "timestamp": "2026-03-27T14:00:00",
  "generated_at": "2026-03-27T14:00:00",
  "valid_until":  "2026-03-27T14:20:00",
  "zones": {
    "EURUSD": {
      "resistance": [1.0850, 1.0920, 1.1000],
      "support":    [1.0780, 1.0720, 1.0650]
    }
  }
}
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Pfad-Setup für standalone-Ausführung: invest_app/ ins sys.path
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from utils.json_utils import read_json_robust  # noqa: E402

from utils.logger import get_logger  # noqa: E402
from utils.mt5_paths import get_common_files_path  # noqa: E402


class LevelAgent:
    """
    Standalone Level-Agent.
    Liest market_data.json, berechnet S/R-Zonen, schreibt zones.json.

    Konfigurationsparameter (config.json → "level_agent"):
        swing_lookback        int   Kerzen links/rechts für Swing-Erkennung (Default: 5)
        cluster_threshold_pct float Abstand für Level-Clustering in % (Default: 0.001 = 0.1 %)
        top_n_zones           int   Maximale Anzahl Resistance/Support-Level pro Symbol (Default: 5)
    """

    def __init__(self, config_path: Path | None = None) -> None:
        self._cfg = self._load_config(config_path)

        la_cfg = self._cfg.get("level_agent", {})
        self.swing_lookback: int = int(la_cfg.get("swing_lookback", 5))
        self.cluster_threshold_pct: float = float(la_cfg.get("cluster_threshold_pct", 0.001))
        self.top_n_zones: int = int(la_cfg.get("top_n_zones", 5))

        # MT5 Pfad-Ermittlung über gemeinsame Hilfsfunktion
        mt5_raw = self._cfg.get("mt5", {})
        app_raw = self._cfg.get("app", {})

        _mt5_cfg = type("_Cfg", (), {
            "mt5_common_files_path": mt5_raw.get("mt5_common_files_path", ""),
            "output_dir": app_raw.get("output_dir", "Output"),
        })()
        self.common_files_path: Path = get_common_files_path(_mt5_cfg)

        log_level = app_raw.get("log_level", "INFO")
        log_dir = Path(app_raw.get("log_dir", "logs"))
        self.logger = get_logger("level_agent", log_dir=log_dir, level=log_level)

    # ------------------------------------------------------------------
    # Öffentliche Schnittstellen
    # ------------------------------------------------------------------

    def run(self) -> bool:
        """Hauptablauf: Daten laden → berechnen → schreiben."""
        self.logger.info("[LevelAgent] Starte Zonen-Berechnung ...")

        market_data = self.load_market_data()
        if market_data is None:
            return False

        symbols = market_data.get("symbols", {})
        if not symbols:
            self.logger.error("[LevelAgent] Keine Symbole in market_data.json")
            return False

        zones: dict[str, dict] = {}
        for symbol, tf_data in symbols.items():
            try:
                resistance, support = self._process_symbol(symbol, tf_data)
                zones[symbol] = {"resistance": resistance, "support": support}
                self.logger.info(
                    "[LevelAgent] %s: %d Resistance-Level, %d Support-Level",
                    symbol, len(resistance), len(support),
                )
            except Exception as exc:
                self.logger.error("[LevelAgent] Fehler bei %s: %s", symbol, exc, exc_info=True)

        return self.write_zones(zones)

    def load_market_data(self) -> dict | None:
        """
        Liest market_data.json aus dem MT5 Common Files Pfad.

        Returns:
            Geparstes Dict oder None bei Fehler.
        """
        path = self.common_files_path / "market_data.json"
        if not path.exists():
            self.logger.error("[LevelAgent] market_data.json nicht gefunden: %s", path)
            return None
        try:
            data = read_json_robust(path)
            self.logger.debug("[LevelAgent] market_data.json geladen: %s", path)
            return data
        except json.JSONDecodeError as exc:
            self.logger.error("[LevelAgent] JSON-Fehler in market_data.json: %s", exc)
            return None

    def detect_swings(self, df: pd.DataFrame) -> tuple[list[float], list[float]]:
        """
        Erkennt Swing-Highs und Swing-Lows im DataFrame.

        Ein Bar i ist ein Swing High, wenn sein High größer ist als alle
        High-Werte im Fenster [i-lookback … i+lookback].
        Analog für Swing Lows.

        Args:
            df: OHLCV DataFrame (Spalten: open, high, low, close, volume)

        Returns:
            (swing_highs, swing_lows) – Listen von Rohpreisen
        """
        lb = self.swing_lookback
        highs = df["high"].values
        lows = df["low"].values
        n = len(highs)

        swing_highs: list[float] = []
        swing_lows: list[float] = []

        for i in range(lb, n - lb):
            window_h = highs[i - lb: i + lb + 1]
            window_l = lows[i - lb: i + lb + 1]

            if float(highs[i]) == float(np.max(window_h)):
                swing_highs.append(float(highs[i]))

            if float(lows[i]) == float(np.min(window_l)):
                swing_lows.append(float(lows[i]))

        return swing_highs, swing_lows

    def cluster_zones(self, prices: list[float]) -> list[dict[str, Any]]:
        """
        Clustert nahe beieinanderliegende Preislevel.

        Levels innerhalb von cluster_threshold_pct (relativ zum ersten Level
        im Cluster) werden zusammengefasst. Rückgabe ist der Mittelwert des
        Clusters plus die Anzahl der zusammengefassten Rohpreise (= Touches).

        Args:
            prices: unsortierte Liste von Rohpreisen

        Returns:
            Liste von {'price': float, 'count': int}, aufsteigend nach Preis.
        """
        if not prices:
            return []

        sorted_prices = sorted(prices)
        clusters: list[dict[str, Any]] = []
        current: list[float] = [sorted_prices[0]]

        for price in sorted_prices[1:]:
            ref = current[0]
            if ref > 0 and abs(price - ref) / ref <= self.cluster_threshold_pct:
                current.append(price)
            else:
                clusters.append({
                    "price": float(np.mean(current)),
                    "count": len(current),
                })
                current = [price]

        clusters.append({
            "price": float(np.mean(current)),
            "count": len(current),
        })

        return clusters

    def score_zones(
        self,
        clusters: list[dict[str, Any]],
        df: pd.DataFrame,
    ) -> list[dict[str, Any]]:
        """
        Bewertet Zonen nach Anzahl Touches, Volume und Alter.

        Score = count × 2  +  vol_ratio  +  recency × 2

        - count:    Anzahl Swing-Punkte im Cluster (aus cluster_zones)
        - vol_ratio: mittleres Volumen an Touch-Bars / Gesamt-Durchschnitt
        - recency:  normierter Mittelwert der Touch-Bar-Indizes (0=älteste, 1=neueste)

        Args:
            clusters: Ausgabe von cluster_zones()
            df:       OHLCV DataFrame

        Returns:
            clusters mit 'score'-Feld, absteigend sortiert.
        """
        if df.empty or not clusters:
            return clusters

        n = len(df)
        highs = df["high"].values
        lows = df["low"].values
        volumes = df["volume"].values if "volume" in df.columns else np.ones(n)
        avg_vol = float(np.mean(volumes)) if np.mean(volumes) > 0 else 1.0

        for cluster in clusters:
            price = cluster["price"]
            threshold = price * self.cluster_threshold_pct

            # Bars ermitteln, bei denen High oder Low das Level berührt hat
            touch_idx = [
                i for i in range(n)
                if abs(highs[i] - price) <= threshold or abs(lows[i] - price) <= threshold
            ]

            vol_score = 0.0
            recency_score = 0.0
            if touch_idx:
                vol_score = float(np.mean(volumes[touch_idx])) / avg_vol
                # Normierter Index: 0 = ältester Bar, 1 = neuester Bar
                recency_score = float(np.mean([idx / (n - 1) for idx in touch_idx]))

            cluster["score"] = cluster["count"] * 2.0 + vol_score + recency_score * 2.0

        return sorted(clusters, key=lambda x: x["score"], reverse=True)

    def write_zones(self, zones: dict[str, dict]) -> bool:
        """
        Schreibt zones.json in den MT5 Common Files Pfad.

        Args:
            zones: Dict Symbol → {'resistance': [...], 'support': [...]}

        Returns:
            True bei Erfolg, False bei Fehler.
        """
        now = datetime.now(timezone.utc)
        valid_until = now + timedelta(minutes=20)

        output = {
            "timestamp":    now.strftime("%Y-%m-%dT%H:%M:%S"),
            "generated_at": now.strftime("%Y-%m-%dT%H:%M:%S"),
            "valid_until":  valid_until.strftime("%Y-%m-%dT%H:%M:%S"),
            "zones": zones,
        }

        path = self.common_files_path / "zones.json"
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(output, fh, indent=2)
            self.logger.info("[LevelAgent] zones.json geschrieben: %s", path)
            return True
        except OSError as exc:
            self.logger.error("[LevelAgent] Fehler beim Schreiben von zones.json: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Interne Hilfsmethoden
    # ------------------------------------------------------------------

    def _process_symbol(
        self, symbol: str, tf_data: dict
    ) -> tuple[list[float], list[float]]:
        """
        Berechnet Resistance- und Support-Level für ein Symbol.

        Verarbeitet H1 und M15 (H1 zuerst – strukturell wichtiger), kombiniert
        Swing-Highs/-Lows beider Timeframes, clustert und bewertet die Zonen.

        Args:
            symbol:  Symbolname (nur für Logging)
            tf_data: Dict {'M15': [...], 'H1': [...]} aus market_data.json

        Returns:
            (resistance, support) – je bis zu top_n_zones Preise,
            Resistance aufsteigend (nächste zuerst),
            Support absteigend (nächste zuerst).
        """
        all_swing_highs: list[float] = []
        all_swing_lows: list[float] = []
        primary_df: pd.DataFrame | None = None
        last_close: float = 0.0

        for tf_name in ("H1", "M15"):
            bars = tf_data.get(tf_name)
            if not bars:
                self.logger.warning("[LevelAgent] %s: Keine %s-Daten", symbol, tf_name)
                continue

            df = self._bars_to_df(bars)
            if len(df) < self.swing_lookback * 2 + 1:
                self.logger.warning(
                    "[LevelAgent] %s/%s: Zu wenige Bars (%d)", symbol, tf_name, len(df)
                )
                continue

            highs, lows = self.detect_swings(df)
            all_swing_highs.extend(highs)
            all_swing_lows.extend(lows)

            if primary_df is None:
                # M15 als primären DataFrame für Scoring nutzen (mehr Datenpunkte)
                primary_df = df
                last_close = float(df["close"].iloc[-1])

        if last_close == 0.0:
            self.logger.warning("[LevelAgent] %s: Kein Close-Preis ermittelbar", symbol)
            return [], []

        # Resistance: Swing-Highs über aktuellem Preis
        res_raw = [p for p in all_swing_highs if p > last_close]
        res_clusters = self.cluster_zones(res_raw)
        if primary_df is not None:
            res_clusters = self.score_zones(res_clusters, primary_df)
        resistance = [
            round(c["price"], 5) for c in res_clusters[: self.top_n_zones]
        ]
        resistance.sort()  # aufsteigend: nächste Resistance zuerst

        # Support: Swing-Lows unter aktuellem Preis
        sup_raw = [p for p in all_swing_lows if p < last_close]
        sup_clusters = self.cluster_zones(sup_raw)
        if primary_df is not None:
            sup_clusters = self.score_zones(sup_clusters, primary_df)
        support = [
            round(c["price"], 5) for c in sup_clusters[: self.top_n_zones]
        ]
        support.sort(reverse=True)  # absteigend: nächste Support zuerst

        return resistance, support

    @staticmethod
    def _bars_to_df(bars: list[dict] | dict) -> pd.DataFrame:
        """
        Konvertiert Bar-Daten aus market_data.json in einen DataFrame.

        Unterstützt das MQL5-Format (Array von Bar-Objekten mit Kurznamen
        t/o/h/l/c/v) sowie das erweiterte Format (Dict mit Spalten-Arrays).
        """
        if isinstance(bars, list):
            return pd.DataFrame({
                "open":   [float(b.get("o", b.get("open",  0.0))) for b in bars],
                "high":   [float(b.get("h", b.get("high",  0.0))) for b in bars],
                "low":    [float(b.get("l", b.get("low",   0.0))) for b in bars],
                "close":  [float(b.get("c", b.get("close", 0.0))) for b in bars],
                "volume": [float(b.get("v", b.get("tick_volume", b.get("volume", 0)))) for b in bars],
            })
        if isinstance(bars, dict):
            return pd.DataFrame({
                "open":   bars.get("open",  []),
                "high":   bars.get("high",  []),
                "low":    bars.get("low",   []),
                "close":  bars.get("close", []),
                "volume": bars.get("tick_volume", bars.get("volume", [])),
            })
        raise ValueError(f"Unbekanntes Bars-Format: {type(bars)}")

    @staticmethod
    def _load_config(config_path: Path | None) -> dict:
        if config_path is None:
            config_path = _HERE / "config.json"
        with open(config_path, encoding="utf-8") as fh:
            return json.load(fh)


# ---------------------------------------------------------------------------
# Standalone-Ausführung (Dauerschleife)
# ---------------------------------------------------------------------------

def _run_loop() -> None:
    agent = LevelAgent()

    interval: int = int(
        agent._cfg.get("analysis", {}).get("interval_seconds", 900)
    )

    print(
        f"[LevelAgent] Dauerschleife gestartet – Intervall: {interval}s "
        f"({interval // 60} min). CTRL+C zum Beenden.",
        flush=True,
    )

    while True:
        run_start = datetime.now(timezone.utc)
        ts = run_start.strftime("%Y-%m-%dT%H:%M:%S")
        print(f"[{ts}] [LevelAgent] Starte Durchlauf ...", flush=True)

        try:
            success = agent.run()
            status = "OK" if success else "FEHLER (run() gab False zurück)"
        except Exception as exc:  # noqa: BLE001
            success = False
            status = f"FEHLER: {exc}"
            agent.logger.error("[LevelAgent] Unbehandelter Fehler im Durchlauf: %s", exc, exc_info=True)

        end_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        next_run = datetime.now(timezone.utc) + timedelta(seconds=interval)
        next_ts = next_run.strftime("%Y-%m-%dT%H:%M:%S")

        print(
            f"[{end_ts}] [LevelAgent] Durchlauf beendet – Status: {status}. "
            f"Nächste Ausführung: {next_ts}",
            flush=True,
        )

        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    try:
        _run_loop()
    except KeyboardInterrupt:
        pass
    print("[LevelAgent] Graceful Shutdown – Auf Wiedersehen.", flush=True)
    sys.exit(0)
