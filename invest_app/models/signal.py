"""
Pydantic-Modell für ein Trading-Signal.
Enthält alle Felder die von der Agent-Pipeline erzeugt und validiert werden.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class Direction(str, Enum):
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"


class SignalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    EXPIRED = "expired"


class Signal(BaseModel):
    """Vollständiges Trading-Signal mit allen Agent-Bewertungen."""

    # Identifikation
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Instrument & Richtung
    instrument: str = Field(..., description="Symbol, z.B. 'EURUSD'")
    direction: Direction = Field(..., description="long / short / neutral")

    # Agent-Status
    trend_status: str = Field(default="", description="z.B. 'bullish structure intact'")
    macro_status: str = Field(default="", description="z.B. 'bullish bias, low event risk'")

    # Preise
    entry_price: float = Field(default=0.0, ge=0)
    stop_loss: float = Field(default=0.0, ge=0)
    take_profit: float = Field(default=0.0, ge=0)

    # Risiko
    crv: float = Field(default=0.0, ge=0, description="Chance-Risiko-Verhältnis, z.B. 2.5 = 1:2.5")
    lot_size: float = Field(default=0.0, ge=0)

    # Qualität
    confidence_score: float = Field(default=0.0, ge=0, le=100)
    status: SignalStatus = Field(default=SignalStatus.PENDING)

    # Begründung
    reasoning: str = Field(default="", description="Zusammenfassung der Signal-Logik")
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)

    # Einzelbewertungen der Agenten
    agent_scores: dict[str, Any] = Field(
        default_factory=dict,
        description="Raw-Outputs aller Agenten, z.B. {'trend': {...}, 'volatility': {...}}",
    )

    @field_validator("crv", mode="before")
    @classmethod
    def round_crv(cls, v: float) -> float:
        return round(float(v), 2)

    @field_validator("confidence_score", mode="before")
    @classmethod
    def round_confidence(cls, v: float) -> float:
        return round(float(v), 1)

    def is_valid(self) -> bool:
        """Gibt True zurück wenn das Signal alle Mindestanforderungen erfüllt."""
        return (
            self.entry_price > 0
            and self.stop_loss > 0
            and self.take_profit > 0
            and self.crv >= 2.0
            and self.confidence_score >= 80.0
            and self.direction != Direction.NEUTRAL
        )

    def summary(self) -> str:
        """Kurze Textzusammenfassung für Logging und Reports."""
        return (
            f"[{self.instrument}] {self.direction.value.upper()} | "
            f"Entry: {self.entry_price:.5f} | SL: {self.stop_loss:.5f} | "
            f"TP: {self.take_profit:.5f} | CRV: 1:{self.crv} | "
            f"Conf: {self.confidence_score}% | Status: {self.status.value}"
        )

    class Config:
        use_enum_values = False
