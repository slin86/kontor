"""Actual depot data: month-end values entered by hand and transactions (manual or imported)."""

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from kontor.core.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class ActualValue(Base):
    """What a position was really worth at the end of a month."""

    __tablename__ = "actual_values"
    __table_args__ = (UniqueConstraint("instrument_id", "month"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    month: Mapped[date] = mapped_column(Date)
    value: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class DepotTransaction(Base):
    """A real buy, sell or dividend; ``amount`` is the money moved (positive for orders)."""

    __tablename__ = "depot_transactions"
    __table_args__ = (UniqueConstraint("household_id", "external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("households.id"), index=True)
    instrument_id: Mapped[int | None] = mapped_column(
        ForeignKey("instruments.id"), nullable=True, index=True
    )
    day: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(16))  # buy | sell | dividend
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    shares: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    isin: Mapped[str | None] = mapped_column(String(12), nullable=True)
    name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="manual")  # manual | csv
    external_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
