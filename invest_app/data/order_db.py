"""
order_db.py – SQLite-basiertes Order-Tracking für InvestApp

Speichert alle Orders (pending/open/closed) persistent.
Watch Agent synct regelmäßig den Status mit MT5.
"""

import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Union


class OrderDB:
    """Thread-sicheres SQLite Order-Tracking."""

    def __init__(self, db_path: "Union[str, Path]"):
        self.db_path = Path(str(db_path))
        self._in_memory = str(db_path) == ":memory:"
        if not self._in_memory:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        # Für :memory: eine persistente shared connection halten
        self._shared_conn: Optional[sqlite3.Connection] = (
            sqlite3.connect(":memory:", check_same_thread=False)
            if self._in_memory else None
        )
        self._init_db()

    # ------------------------------------------------------------------
    # Initialisierung
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS orders (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol          TEXT    NOT NULL,
                    direction       TEXT    NOT NULL,   -- 'buy' | 'sell'
                    entry_price     REAL,
                    sl              REAL,
                    tp              REAL,
                    confidence      REAL    DEFAULT 0,
                    lot_size        REAL,
                    ticket          INTEGER,            -- MT5 Ticket-Nr
                    status          TEXT    DEFAULT 'pending',
                    -- pending | open | closed | cancelled | failed
                    magic           INTEGER DEFAULT 20260324,
                    comment         TEXT    DEFAULT '',
                    created_at      REAL    NOT NULL,   -- Unix-Timestamp
                    opened_at       REAL,
                    closed_at       REAL,
                    close_price     REAL,
                    pnl             REAL
                );

                CREATE INDEX IF NOT EXISTS idx_orders_symbol  ON orders(symbol);
                CREATE INDEX IF NOT EXISTS idx_orders_status  ON orders(status);
                CREATE INDEX IF NOT EXISTS idx_orders_ticket  ON orders(ticket);

                CREATE TABLE IF NOT EXISTS symbols (
                    symbol      TEXT PRIMARY KEY,
                    category    TEXT,               -- forex/crypto/stock
                    score       REAL DEFAULT 0,
                    active      INTEGER DEFAULT 1,  -- 1=aktiv, 0=inaktiv
                    last_seen   REAL,               -- Unix-Timestamp letzter Scanner-Lauf
                    updated_at  REAL
                );
            """)

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
    ) -> int:
        """Neue Order anlegen, gibt order_id zurück."""
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO orders
                    (symbol, direction, entry_price, sl, tp, confidence,
                     lot_size, comment, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (symbol, direction, entry_price, sl, tp, confidence,
                 lot_size, comment, datetime.utcnow().timestamp()),
            )
            return cur.lastrowid

    def update_ticket(self, order_id: int, ticket: int) -> None:
        """MT5-Ticket nach Ausführung eintragen."""
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE orders SET ticket=?, status='open', opened_at=? WHERE id=?",
                (ticket, datetime.utcnow().timestamp(), order_id),
            )

    def update_status(
        self,
        ticket: int,
        status: str,
        close_price: Optional[float] = None,
        pnl: Optional[float] = None,
        closed_at: Optional[float] = None,
    ) -> None:
        """Status einer Order aktualisieren (über MT5-Ticket)."""
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE orders
                SET status=?, close_price=?, pnl=?, closed_at=?
                WHERE ticket=?
                """,
                (
                    status,
                    close_price,
                    pnl,
                    closed_at or datetime.utcnow().timestamp(),
                    ticket,
                ),
            )

    def mark_failed(self, order_id: int) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE orders SET status='failed' WHERE id=?", (order_id,)
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
        with self._lock, self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM orders WHERE ticket=?", (ticket,)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE orders SET pnl=?, sl=?, tp=? WHERE ticket=?",
                    (profit, sl, tp, ticket),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO orders
                        (symbol, direction, entry_price, sl, tp, lot_size,
                         ticket, status, created_at, opened_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)
                    """,
                    (
                        symbol, direction, entry_price, sl, tp, lot_size,
                        ticket,
                        datetime.utcnow().timestamp(),
                        datetime.utcnow().timestamp(),
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
                "SELECT ticket FROM orders WHERE status IN ('open','pending') AND ticket IS NOT NULL"
            ).fetchall()
            return {r[0] for r in rows}

    # ------------------------------------------------------------------
    # Symbol-Persistenz
    # ------------------------------------------------------------------

    def save_symbols(self, symbols: list[dict]) -> None:
        """Speichert/aktualisiert Symbol-Liste (upsert), setzt last_seen auf jetzt."""
        now = datetime.utcnow().timestamp()
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
