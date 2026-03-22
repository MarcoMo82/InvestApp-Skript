"""
Pydantic-Modell für einen ausgeführten Trade.
Wird nach erfolgreicher Orderplatzierung via MT5 erstellt.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TradeStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    ERROR = "error"


class Trade(BaseModel):
    """Ausgeführter Trade mit vollständigem Lifecycle."""

    # Identifikation
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    signal_id: str = Field(..., description="Referenz auf das auslösende Signal")
    mt5_ticket: Optional[int] = Field(default=None, description="MT5 Order-Ticket")

    # Instrument & Richtung
    instrument: str = Field(..., description="Symbol, z.B. 'EURUSD'")
    direction: str = Field(..., description="long oder short")

    # Preise
    entry_price: float = Field(..., ge=0)
    sl: float = Field(..., ge=0, description="Stop Loss")
    tp: float = Field(..., ge=0, description="Take Profit")
    lot_size: float = Field(..., gt=0)

    # Zeitstempel
    open_time: datetime = Field(default_factory=datetime.utcnow)
    close_time: Optional[datetime] = Field(default=None)
    close_price: Optional[float] = Field(default=None, ge=0)

    # Ergebnis
    pnl: Optional[float] = Field(default=None, description="Profit/Loss in Kontowährung")
    pnl_pips: Optional[float] = Field(default=None, description="Profit/Loss in Pips")
    status: TradeStatus = Field(default=TradeStatus.OPEN)

    # Metadaten
    comment: str = Field(default="InvestApp", description="MT5 Order-Kommentar")

    def close(self, close_price: float, pnl: float, pnl_pips: float = 0.0) -> None:
        """Schließt den Trade und setzt alle Schluss-Felder."""
        self.close_price = close_price
        self.close_time = datetime.utcnow()
        self.pnl = round(pnl, 2)
        self.pnl_pips = round(pnl_pips, 1)
        self.status = TradeStatus.CLOSED

    def is_profitable(self) -> Optional[bool]:
        if self.pnl is None:
            return None
        return self.pnl > 0

    def duration_minutes(self) -> Optional[float]:
        if self.close_time is None:
            return None
        delta = self.close_time - self.open_time
        return round(delta.total_seconds() / 60, 1)

    def summary(self) -> str:
        pnl_str = f"{self.pnl:+.2f}" if self.pnl is not None else "offen"
        return (
            f"[{self.instrument}] {self.direction.upper()} | "
            f"Ticket: {self.mt5_ticket} | Lot: {self.lot_size} | "
            f"Entry: {self.entry_price:.5f} | PnL: {pnl_str} | "
            f"Status: {self.status.value}"
        )
