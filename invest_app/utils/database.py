"""
SQLite-Datenbankanbindung via SQLAlchemy für Signale, Trades und Performance.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import (
    Column, DateTime, Float, Integer, JSON, String, Text, create_engine, text
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from utils.logger import get_logger

logger = get_logger(__name__)


class Base(DeclarativeBase):
    pass


class SignalRecord(Base):
    __tablename__ = "signals"

    id = Column(String, primary_key=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    instrument = Column(String(20), nullable=False, index=True)
    direction = Column(String(10))
    trend_status = Column(Text)
    macro_status = Column(Text)
    entry_price = Column(Float)
    stop_loss = Column(Float)
    take_profit = Column(Float)
    crv = Column(Float)
    lot_size = Column(Float)
    confidence_score = Column(Float)
    status = Column(String(20))
    reasoning = Column(Text)
    pros = Column(JSON)
    cons = Column(JSON)
    agent_scores = Column(JSON)


class TradeRecord(Base):
    __tablename__ = "trades"

    id = Column(String, primary_key=True)
    signal_id = Column(String, nullable=False, index=True)
    mt5_ticket = Column(Integer)
    instrument = Column(String(20), nullable=False, index=True)
    direction = Column(String(10))
    entry_price = Column(Float)
    sl = Column(Float)
    tp = Column(Float)
    lot_size = Column(Float)
    open_time = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    close_time = Column(DateTime)
    close_price = Column(Float)
    pnl = Column(Float)
    pnl_pips = Column(Float)
    status = Column(String(20))
    comment = Column(String(100))


class AgentLogRecord(Base):
    __tablename__ = "agent_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    agent_name = Column(String(50), nullable=False)
    instrument = Column(String(20))
    input_data = Column(JSON)
    output_data = Column(JSON)
    duration_ms = Column(Float)
    error = Column(Text)


class PerformanceRecord(Base):
    __tablename__ = "performance"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    total_pnl = Column(Float, default=0.0)
    win_rate = Column(Float, default=0.0)
    avg_crv = Column(Float, default=0.0)
    daily_pnl = Column(Float, default=0.0)


class Database:
    """SQLite-Handler mit SQLAlchemy ORM."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.engine = create_engine(f"sqlite:///{db_path}", echo=False)
        self._Session = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)
        logger.info(f"Datenbank initialisiert: {db_path}")

    def _session(self) -> Session:
        return self._Session()

    # --- Signale ---

    def save_signal(self, signal: Any) -> None:
        """Speichert ein Signal-Objekt (Signal-Pydantic-Modell oder dict)."""
        data = signal.model_dump() if hasattr(signal, "model_dump") else signal
        record = SignalRecord(
            id=data["id"],
            timestamp=data.get("timestamp", datetime.now(timezone.utc)),
            instrument=data["instrument"],
            direction=str(data["direction"]),
            trend_status=data.get("trend_status", ""),
            macro_status=data.get("macro_status", ""),
            entry_price=data.get("entry_price", 0.0),
            stop_loss=data.get("stop_loss", 0.0),
            take_profit=data.get("take_profit", 0.0),
            crv=data.get("crv", 0.0),
            lot_size=data.get("lot_size", 0.0),
            confidence_score=data.get("confidence_score", 0.0),
            status=str(data.get("status", "pending")),
            reasoning=data.get("reasoning", ""),
            pros=data.get("pros", []),
            cons=data.get("cons", []),
            agent_scores=data.get("agent_scores", {}),
        )
        with self._session() as session:
            session.merge(record)
            session.commit()
        logger.debug(f"Signal gespeichert: {data['id']} | {data['instrument']}")

    def get_recent_signals(self, hours: int = 24, min_confidence: float = 0.0) -> list[dict]:
        """Gibt Signale der letzten N Stunden zurück, optional gefiltert nach Confidence."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        with self._session() as session:
            records = (
                session.query(SignalRecord)
                .filter(SignalRecord.timestamp >= cutoff)
                .filter(SignalRecord.confidence_score >= min_confidence)
                .order_by(SignalRecord.confidence_score.desc())
                .all()
            )
        return [self._signal_to_dict(r) for r in records]

    # --- Trades ---

    def save_trade(self, trade: Any) -> None:
        """Speichert ein Trade-Objekt (Trade-Pydantic-Modell oder dict)."""
        data = trade.model_dump() if hasattr(trade, "model_dump") else trade
        record = TradeRecord(
            id=data["id"],
            signal_id=data["signal_id"],
            mt5_ticket=data.get("mt5_ticket"),
            instrument=data["instrument"],
            direction=data["direction"],
            entry_price=data.get("entry_price", 0.0),
            sl=data.get("sl", 0.0),
            tp=data.get("tp", 0.0),
            lot_size=data.get("lot_size", 0.0),
            open_time=data.get("open_time", datetime.now(timezone.utc)),
            close_time=data.get("close_time"),
            close_price=data.get("close_price"),
            pnl=data.get("pnl"),
            pnl_pips=data.get("pnl_pips"),
            status=str(data.get("status", "open")),
            comment=data.get("comment", "InvestApp"),
        )
        with self._session() as session:
            session.merge(record)
            session.commit()
        logger.debug(f"Trade gespeichert: {data['id']} | {data['instrument']}")

    def get_open_trades(self) -> list[dict]:
        with self._session() as session:
            records = (
                session.query(TradeRecord)
                .filter(TradeRecord.status == "open")
                .all()
            )
        return [self._trade_to_dict(r) for r in records]

    def get_closed_trades(self, days: int = 30) -> list[dict]:
        """Gibt geschlossene Trades der letzten N Tage zurück."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        with self._session() as session:
            records = (
                session.query(TradeRecord)
                .filter(TradeRecord.status == "closed")
                .filter(TradeRecord.close_time >= cutoff)
                .order_by(TradeRecord.close_time.desc())
                .all()
            )
        return [self._trade_to_dict(r) for r in records]

    def get_daily_pnl(self) -> float:
        """Gibt den heutigen kumulierten PnL zurück."""
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        with self._session() as session:
            result = session.execute(
                text(
                    "SELECT COALESCE(SUM(pnl), 0) FROM trades "
                    "WHERE close_time >= :today AND status = 'closed'"
                ),
                {"today": today},
            ).scalar()
        return float(result or 0.0)

    # --- Agent-Logs ---

    def log_agent(
        self,
        agent_name: str,
        instrument: str,
        input_data: dict,
        output_data: dict,
        duration_ms: float = 0.0,
        error: Optional[str] = None,
    ) -> None:
        record = AgentLogRecord(
            agent_name=agent_name,
            instrument=instrument,
            input_data=input_data,
            output_data=output_data,
            duration_ms=duration_ms,
            error=error,
        )
        with self._session() as session:
            session.add(record)
            session.commit()

    # --- Performance ---

    def get_performance_stats(self, days: int = 30) -> dict:
        """Berechnet Performance-Kennzahlen der letzten N Tage."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        with self._session() as session:
            trades = (
                session.query(TradeRecord)
                .filter(TradeRecord.close_time >= cutoff)
                .filter(TradeRecord.status == "closed")
                .all()
            )

        if not trades:
            return {
                "total_trades": 0, "winning_trades": 0, "losing_trades": 0,
                "win_rate": 0.0, "total_pnl": 0.0, "avg_pnl_per_trade": 0.0,
            }

        total = len(trades)
        winners = [t for t in trades if t.pnl and t.pnl > 0]
        losers = [t for t in trades if t.pnl and t.pnl <= 0]
        total_pnl = sum(t.pnl for t in trades if t.pnl is not None)

        return {
            "total_trades": total,
            "winning_trades": len(winners),
            "losing_trades": len(losers),
            "win_rate": round(len(winners) / total * 100, 1),
            "total_pnl": round(total_pnl, 2),
            "avg_pnl_per_trade": round(total_pnl / total, 2),
        }

    # --- Hilfsmethoden ---

    @staticmethod
    def _signal_to_dict(r: SignalRecord) -> dict:
        return {
            "id": r.id, "timestamp": r.timestamp, "instrument": r.instrument,
            "direction": r.direction, "entry_price": r.entry_price,
            "stop_loss": r.stop_loss, "take_profit": r.take_profit,
            "crv": r.crv, "confidence_score": r.confidence_score,
            "status": r.status, "reasoning": r.reasoning,
            "agent_scores": r.agent_scores or {},
        }

    @staticmethod
    def _trade_to_dict(r: TradeRecord) -> dict:
        return {
            "id": r.id, "signal_id": r.signal_id, "mt5_ticket": r.mt5_ticket,
            "instrument": r.instrument, "direction": r.direction,
            "entry_price": r.entry_price, "sl": r.sl, "tp": r.tp,
            "lot_size": r.lot_size, "open_time": r.open_time,
            "close_time": r.close_time, "pnl": r.pnl, "status": r.status,
        }
