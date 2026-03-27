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
                    id              TEXT    PRIMARY KEY,           -- UUID, intern generiert
                    mt5_ticket      INTEGER UNIQUE,                -- MT5-Ticket nach Ausführung (nullable)
                    symbol          TEXT    NOT NULL,
                    direction       TEXT    NOT NULL,              -- 'buy' | 'sell'
                    entry_price     REAL,
                    sl              REAL,
                    tp              REAL,
                    crv             REAL    DEFAULT 0,
                    confidence      REAL    DEFAULT 0,
                    lot_size        REAL,
                    signal_id       TEXT,                          -- FK zu invest_app.db signals (nullable)
                    status          TEXT    DEFAULT 'pending',
                    -- pending | open | closed | cancelled | failed
                    magic           INTEGER DEFAULT 20260324,
                    comment         TEXT    DEFAULT '',
                    created_at      REAL    NOT NULL,
                    updated_at      REAL,
                    opened_at       REAL,
                    closed_at       REAL,
                    close_price     REAL,
                    pnl             REAL
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
            for col, ddl in [
                ("crv",       "ALTER TABLE orders ADD COLUMN crv REAL DEFAULT 0"),
                ("signal_id", "ALTER TABLE orders ADD COLUMN signal_id TEXT"),
                ("updated_at","ALTER TABLE orders ADD COLUMN updated_at REAL"),
            ]:
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
                     lot_size, comment, signal_id, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (order_id, symbol, direction, entry_price, sl, tp, crv, confidence,
                 lot_size, comment, signal_id, now, now),
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

    def get_all_open_tickets(self) -> set[int]:
        """Alle MT5-Tickets mit Status open/pending."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT mt5_ticket FROM orders WHERE status IN ('open','pending') AND mt5_ticket IS NOT NULL"
            ).fetchall()
            return {r[0] for r in rows}

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
