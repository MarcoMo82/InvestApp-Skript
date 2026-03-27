"""
order_db.py – SQLite-basiertes Order-Tracking für InvestApp

orders.db = operative Source of Truth für aktive Orders und Trades.
Jede Order hat eine interne UUID (PK) + optionales MT5-Ticket (nach Ausführung).
"""

import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union


class OrderDB:
    """Thread-sicheres SQLite Order-Tracking (UUID-PK + MT5-Ticket)."""

    def __init__(self, db_path: Union[str, Path]) -> None:
        self.db_path = Path(str(db_path))
        self._in_memory = str(db_path) == ":memory:"
        if not self._in_memory:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._shared_conn: Optional[sqlite3.Connection] = (
            sqlite3.connect(":memory:", check_same_thread=False)
            if self._in_memory else None
        )
        self._init_db()

    # ------------------------------------------------------------------
    # Initialisierung & Migration
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        with self._connect() as conn:
            self._migrate_schema(conn)
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS orders (
                    id              TEXT    PRIMARY KEY,
                    mt5_ticket      INTEGER UNIQUE,
                    symbol          TEXT    NOT NULL,
                    direction       TEXT    NOT NULL,
                    entry_price     REAL,
                    sl              REAL,
                    tp              REAL,
                    crv             REAL    DEFAULT 0,
                    confidence      REAL    DEFAULT 0,
                    lot_size        REAL,
                    signal_id       TEXT,
                    status          TEXT    DEFAULT 'pending',
                    magic           INTEGER DEFAULT 20260324,
                    comment         TEXT    DEFAULT '',
                    created_at      REAL    NOT NULL,
                    updated_at      REAL,
                    opened_at       REAL,
                    closed_at       REAL,
                    close_price     REAL,
                    pnl             REAL,
                    -- Trade-Kontext (beim Öffnen)
                    macro_bias          TEXT,
                    trend_direction     TEXT,
                    atr_value           REAL,
                    atr_pct             REAL,
                    rsi_value           REAL,
                    rsi_zone            TEXT,
                    volatility_phase    TEXT,
                    entry_type          TEXT,
                    -- Trade-Verlauf (laufend aktualisiert)
                    max_price_reached   REAL,
                    min_price_reached   REAL,
                    breakeven_set_at    TEXT,
                    last_sl             REAL,
                    last_checked_at     TEXT,
                    -- Trade-Abschluss
                    exit_price          REAL,
                    exit_reason         TEXT,
                    pnl_pips            REAL,
                    pnl_currency        REAL,
                    duration_seconds    INTEGER,
                    -- Learning Agent
                    learning_analyzed   INTEGER DEFAULT 0,
                    learning_notes      TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders(symbol);
                CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);

                CREATE TABLE IF NOT EXISTS symbols (
                    symbol      TEXT PRIMARY KEY,
                    category    TEXT,
                    score       REAL DEFAULT 0,
                    active      INTEGER DEFAULT 1,
                    last_seen   REAL,
                    updated_at  REAL
                );
            """)

    def _migrate_schema(self, conn: sqlite3.Connection) -> None:
        """Migriert altes INTEGER-ID-Schema (ticket) zu neuem UUID+mt5_ticket-Schema."""
        cursor = conn.execute("PRAGMA table_info(orders)")
        cols = {row[1]: row[2] for row in cursor.fetchall()}

        if not cols:
            return  # Tabelle existiert noch nicht → wird in _init_db erstellt

        has_mt5_ticket = "mt5_ticket" in cols

        if not has_mt5_ticket:
            # Vollmigration: altes Schema (INTEGER id, ticket) → neues Schema
            conn.executescript("""
                ALTER TABLE orders RENAME TO orders_v1;

                CREATE TABLE orders (
                    id              TEXT    PRIMARY KEY,
                    mt5_ticket      INTEGER UNIQUE,
                    symbol          TEXT    NOT NULL,
                    direction       TEXT    NOT NULL,
                    entry_price     REAL,
                    sl              REAL,
                    tp              REAL,
                    crv             REAL    DEFAULT 0,
                    confidence      REAL    DEFAULT 0,
                    lot_size        REAL,
                    signal_id       TEXT,
                    status          TEXT    DEFAULT 'pending',
                    magic           INTEGER DEFAULT 20260324,
                    comment         TEXT    DEFAULT '',
                    created_at      REAL    NOT NULL,
                    updated_at      REAL,
                    opened_at       REAL,
                    closed_at       REAL,
                    close_price     REAL,
                    pnl             REAL
                );

                INSERT INTO orders
                    (id, mt5_ticket, symbol, direction, entry_price, sl, tp,
                     confidence, lot_size, status, magic, comment,
                     created_at, opened_at, closed_at, close_price, pnl)
                SELECT
                    CAST(id AS TEXT), ticket, symbol, direction, entry_price, sl, tp,
                    confidence, lot_size, status, magic, comment,
                    created_at, opened_at, closed_at, close_price, pnl
                FROM orders_v1;

                DROP TABLE orders_v1;

                CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders(symbol);
                CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
            """)
        else:
            # Nur fehlende Spalten ergänzen (ALTER TABLE)
            new_cols = [
                ("crv",               "ALTER TABLE orders ADD COLUMN crv REAL DEFAULT 0"),
                ("signal_id",         "ALTER TABLE orders ADD COLUMN signal_id TEXT"),
                ("updated_at",        "ALTER TABLE orders ADD COLUMN updated_at REAL"),
                # Trade-Kontext (beim Öffnen)
                ("macro_bias",        "ALTER TABLE orders ADD COLUMN macro_bias TEXT"),
                ("trend_direction",   "ALTER TABLE orders ADD COLUMN trend_direction TEXT"),
                ("atr_value",         "ALTER TABLE orders ADD COLUMN atr_value REAL"),
                ("atr_pct",           "ALTER TABLE orders ADD COLUMN atr_pct REAL"),
                ("rsi_value",         "ALTER TABLE orders ADD COLUMN rsi_value REAL"),
                ("rsi_zone",          "ALTER TABLE orders ADD COLUMN rsi_zone TEXT"),
                ("volatility_phase",  "ALTER TABLE orders ADD COLUMN volatility_phase TEXT"),
                ("entry_type",        "ALTER TABLE orders ADD COLUMN entry_type TEXT"),
                # Trade-Verlauf (laufend aktualisiert)
                ("max_price_reached", "ALTER TABLE orders ADD COLUMN max_price_reached REAL"),
                ("min_price_reached", "ALTER TABLE orders ADD COLUMN min_price_reached REAL"),
                ("breakeven_set_at",  "ALTER TABLE orders ADD COLUMN breakeven_set_at TEXT"),
                ("last_sl",           "ALTER TABLE orders ADD COLUMN last_sl REAL"),
                ("last_checked_at",   "ALTER TABLE orders ADD COLUMN last_checked_at TEXT"),
                # Trade-Abschluss
                ("exit_price",        "ALTER TABLE orders ADD COLUMN exit_price REAL"),
                ("exit_reason",       "ALTER TABLE orders ADD COLUMN exit_reason TEXT"),
                ("pnl_pips",          "ALTER TABLE orders ADD COLUMN pnl_pips REAL"),
                ("pnl_currency",      "ALTER TABLE orders ADD COLUMN pnl_currency REAL"),
                ("duration_seconds",  "ALTER TABLE orders ADD COLUMN duration_seconds INTEGER"),
                # Learning Agent
                ("learning_analyzed", "ALTER TABLE orders ADD COLUMN learning_analyzed INTEGER DEFAULT 0"),
                ("learning_notes",    "ALTER TABLE orders ADD COLUMN learning_notes TEXT"),
            ]
            for col, ddl in new_cols:
                if col not in cols:
                    conn.execute(ddl)

    def _connect(self) -> sqlite3.Connection:
        if self._in_memory and self._shared_conn is not None:
            conn = self._shared_conn
            conn.row_factory = sqlite3.Row
            return conn
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------------
    # Schreiben
    # ------------------------------------------------------------------

    def add_order(
        self,
        symbol: str,
        direction: str,
        sl: float,
        tp: float,
        confidence: float,
        lot_size: float,
        entry_price: float = 0.0,
        comment: str = "InvestApp",
        id: Optional[str] = None,
        crv: float = 0.0,
        signal_id: Optional[str] = None,
        # Trade-Kontext (aus Signal/Agenten)
        entry_type: Optional[str] = None,
        atr_value: Optional[float] = None,
        atr_pct: Optional[float] = None,
        rsi_value: Optional[float] = None,
        rsi_zone: Optional[str] = None,
        volatility_phase: Optional[str] = None,
        macro_bias: Optional[str] = None,
        trend_direction: Optional[str] = None,
    ) -> str:
        """Neue Order anlegen. Generiert UUID automatisch wenn keine id übergeben wird.

        Returns:
            order_id (UUID als str)
        """
        order_id = id or str(uuid.uuid4())
        now = datetime.now(timezone.utc).timestamp()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO orders
                    (id, symbol, direction, entry_price, sl, tp, crv, confidence,
                     lot_size, comment, signal_id, status, created_at, updated_at,
                     entry_type, atr_value, atr_pct, rsi_value, rsi_zone,
                     volatility_phase, macro_bias, trend_direction)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (order_id, symbol, direction, entry_price, sl, tp, crv, confidence,
                 lot_size, comment, signal_id, now, now,
                 entry_type, atr_value, atr_pct, rsi_value, rsi_zone,
                 volatility_phase, macro_bias, trend_direction),
            )
        return order_id

    def set_mt5_ticket(self, order_id: str, ticket: int) -> None:
        """MT5-Ticket nach erfolgreicher Ausführung eintragen. Setzt Status → 'open'."""
        now = datetime.now(timezone.utc).timestamp()
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE orders SET mt5_ticket=?, status='open', opened_at=?, updated_at=? WHERE id=?",
                (ticket, now, now, order_id),
            )

    def update_order_status(
        self,
        status: str,
        order_id: Optional[str] = None,
        ticket: Optional[int] = None,
        close_price: Optional[float] = None,
        pnl: Optional[float] = None,
        closed_at: Optional[float] = None,
    ) -> None:
        """Status einer Order aktualisieren – Lookup über order_id (UUID) oder mt5_ticket."""
        now = datetime.now(timezone.utc).timestamp()
        with self._lock, self._connect() as conn:
            if order_id is not None:
                conn.execute(
                    """
                    UPDATE orders
                    SET status=?, close_price=?, pnl=?, closed_at=?, updated_at=?
                    WHERE id=?
                    """,
                    (status, close_price, pnl, closed_at or now, now, order_id),
                )
            elif ticket is not None:
                conn.execute(
                    """
                    UPDATE orders
                    SET status=?, close_price=?, pnl=?, closed_at=?, updated_at=?
                    WHERE mt5_ticket=?
                    """,
                    (status, close_price, pnl, closed_at or now, now, ticket),
                )

    def mark_failed(self, order_id: str) -> None:
        """Order als fehlgeschlagen markieren."""
        now = datetime.now(timezone.utc).timestamp()
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE orders SET status='failed', updated_at=? WHERE id=?",
                (now, order_id),
            )

    def upsert_open_position(
        self,
        symbol: str,
        direction: str,
        ticket: int,
        lot_size: float,
        entry_price: float,
        sl: float,
        tp: float,
        profit: float,
    ) -> None:
        """MT5-Position in DB eintragen falls noch nicht vorhanden."""
        now = datetime.now(timezone.utc).timestamp()
        with self._lock, self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM orders WHERE mt5_ticket=?", (ticket,)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE orders SET pnl=?, sl=?, tp=?, updated_at=? WHERE mt5_ticket=?",
                    (profit, sl, tp, now, ticket),
                )
            else:
                new_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO orders
                        (id, symbol, direction, entry_price, sl, tp, lot_size,
                         mt5_ticket, status, created_at, updated_at, opened_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?)
                    """,
                    (
                        new_id, symbol, direction, entry_price, sl, tp, lot_size,
                        ticket, now, now, now,
                    ),
                )

    # ------------------------------------------------------------------
    # Lesen
    # ------------------------------------------------------------------

    def get_open_orders(self, symbol: Optional[str] = None) -> list[dict]:
        """Alle pending/open Orders, optional gefiltert nach Symbol."""
        with self._connect() as conn:
            if symbol:
                rows = conn.execute(
                    "SELECT * FROM orders WHERE status IN ('pending','open') AND symbol=? ORDER BY created_at",
                    (symbol,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM orders WHERE status IN ('pending','open') ORDER BY created_at"
                ).fetchall()
            return [dict(r) for r in rows]

    def get_order_by_ticket(self, ticket: int) -> Optional[dict]:
        """Order über MT5-Ticket suchen."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM orders WHERE mt5_ticket=?", (ticket,)
            ).fetchone()
            return dict(row) if row else None

    def get_order_count(self, symbol: str) -> int:
        """Anzahl pending/open Orders für ein Symbol."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM orders WHERE symbol=? AND status IN ('pending','open')",
                (symbol,),
            ).fetchone()
            return row[0]

    def get_max_confidence(self, symbol: str) -> float:
        """Höchste Confidence unter offenen Orders für ein Symbol."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT MAX(confidence) FROM orders WHERE symbol=? AND status IN ('pending','open')",
                (symbol,),
            ).fetchone()
            return row[0] or 0.0

    def get_recent_closed(self, limit: int = 10) -> list[dict]:
        """Letzte geschlossene Orders."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM orders WHERE status='closed' ORDER BY closed_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_open_tickets(self) -> list[int]:
        """Alle MT5-Tickets mit Status open/pending (als Liste)."""
        return list(self.get_all_open_tickets())

    def get_all_open_tickets(self) -> set[int]:
        """Alle MT5-Tickets mit Status open/pending."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT mt5_ticket FROM orders WHERE status IN ('open','pending') AND mt5_ticket IS NOT NULL"
            ).fetchall()
            return {r[0] for r in rows}

    # ------------------------------------------------------------------
    # Trade-Begleitung (Polling + Learning)
    # ------------------------------------------------------------------

    def update_trade_progress(
        self,
        ticket: int,
        max_price: float,
        min_price: float,
        last_sl: float,
        last_checked_at: str,
    ) -> None:
        """Aktualisiert Höchst-/Tiefstkurs, letzten SL und Poll-Zeitstempel."""
        now = datetime.now(timezone.utc).timestamp()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE orders
                SET max_price_reached=?, min_price_reached=?, last_sl=?,
                    last_checked_at=?, updated_at=?
                WHERE mt5_ticket=?
                """,
                (max_price, min_price, last_sl, last_checked_at, now, ticket),
            )

    def mark_trade_closed(
        self,
        ticket: int,
        exit_price: Optional[float],
        exit_reason: str,
        pnl_pips: Optional[float],
        pnl_currency: Optional[float],
        closed_at: str,
    ) -> None:
        """Markiert einen Trade als geschlossen und setzt Exit-Felder."""
        now = datetime.now(timezone.utc).timestamp()
        # Laufzeit berechnen (opened_at → closed_at)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT opened_at FROM orders WHERE mt5_ticket=?", (ticket,)
            ).fetchone()
            opened_ts = row["opened_at"] if row else None

        duration = None
        try:
            closed_ts = datetime.fromisoformat(closed_at).timestamp()
            if opened_ts:
                duration = int(closed_ts - opened_ts)
        except Exception:
            pass

        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE orders
                SET status='closed', exit_price=?, exit_reason=?, pnl_pips=?,
                    pnl_currency=?, duration_seconds=?, closed_at=?, updated_at=?
                WHERE mt5_ticket=?
                """,
                (exit_price, exit_reason, pnl_pips, pnl_currency,
                 duration, closed_at, now, ticket),
            )

    def get_closed_unanalyzed_trades(self) -> list[dict]:
        """Alle geschlossenen Trades die noch nicht vom Learning Agent analysiert wurden."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM orders
                WHERE learning_analyzed=0 AND closed_at IS NOT NULL
                      AND status='closed'
                ORDER BY closed_at DESC
                """
            ).fetchall()
            return [dict(r) for r in rows]

    def mark_learning_analyzed(self, ticket: int, notes: dict) -> None:
        """Markiert einen Trade als vom Learning Agent analysiert."""
        import json as _json
        now = datetime.now(timezone.utc).timestamp()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE orders
                SET learning_analyzed=1, learning_notes=?, updated_at=?
                WHERE mt5_ticket=?
                """,
                (_json.dumps(notes, ensure_ascii=False), now, ticket),
            )

    def get_trade_context(self, ticket: int) -> Optional[dict]:
        """Vollständiger Trade-Datensatz für den Learning Agent."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM orders WHERE mt5_ticket=?", (ticket,)
            ).fetchone()
            return dict(row) if row else None

    # ------------------------------------------------------------------
    # Symbol-Persistenz
    # ------------------------------------------------------------------

    def save_symbols(self, symbols: list[dict]) -> None:
        """Speichert/aktualisiert Symbol-Liste (upsert), setzt last_seen auf jetzt."""
        now = datetime.now(timezone.utc).timestamp()
        with self._lock, self._connect() as conn:
            for sym in symbols:
                conn.execute(
                    """
                    INSERT INTO symbols (symbol, category, score, active, last_seen, updated_at)
                    VALUES (?, ?, ?, 1, ?, ?)
                    ON CONFLICT(symbol) DO UPDATE SET
                        category=excluded.category,
                        score=excluded.score,
                        active=1,
                        last_seen=excluded.last_seen,
                        updated_at=excluded.updated_at
                    """,
                    (
                        sym["symbol"],
                        sym.get("category", "other"),
                        sym.get("score", 0.0),
                        now,
                        now,
                    ),
                )

    def get_active_symbols(self) -> list[str]:
        """Gibt aktive Symbole zurück, sortiert nach score DESC."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT symbol FROM symbols WHERE active=1 ORDER BY score DESC"
            ).fetchall()
            return [r[0] for r in rows]

    def get_symbol_count(self) -> int:
        """Anzahl aller gespeicherten Symbole."""
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM symbols").fetchone()
            return row[0]

    # ------------------------------------------------------------------
    # Status-Anzeige
    # ------------------------------------------------------------------

    def format_status(self) -> str:
        """Kompakte Statuszeile für Konsolen-Output."""
        open_orders = self.get_open_orders()
        closed = self.get_recent_closed(limit=3)

        pending = [o for o in open_orders if o["status"] == "pending"]
        open_pos = [o for o in open_orders if o["status"] == "open"]

        lines = ["─" * 60, "📊 ORDER STATUS"]

        if pending:
            lines.append(f"  ⏳ Pending ({len(pending)}):")
            for o in pending:
                lines.append(f"     {o['symbol']} {o['direction'].upper()}  "
                             f"Conf={o['confidence']:.0f}%  Vol={o['lot_size']}")
        else:
            lines.append("  ⏳ Pending: keine")

        if open_pos:
            lines.append(f"  📈 Offen ({len(open_pos)}):")
            for o in open_pos:
                pnl_str = f"{o['pnl']:+.2f}" if o["pnl"] is not None else "n/a"
                lines.append(f"     {o['symbol']} {o['direction'].upper()}  "
                             f"PnL={pnl_str}  SL={o['sl']}  TP={o['tp']}")
        else:
            lines.append("  📈 Offen: keine")

        if closed:
            lines.append("  ✅ Zuletzt geschlossen:")
            for o in closed:
                pnl_str = f"{o['pnl']:+.2f}" if o["pnl"] is not None else "n/a"
                lines.append(f"     {o['symbol']} {o['direction'].upper()}  PnL={pnl_str}")

        lines.append("─" * 60)
        return "\n".join(lines)
