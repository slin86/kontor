"""Depot plan: instruments (positions), their dated savings rates and one-off payments."""

import enum
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kontor.core.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class InstrumentKind(enum.StrEnum):
    ETF = "etf"
    PRIVATE_EQUITY = "private_equity"


class Instrument(Base):
    """A position of the household's depot plan.

    Percentages are stored as entered (``6.5`` means 6.5 %); the API layer converts them.
    ``start_value`` is the balance at the beginning of ``start``.
    """

    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("households.id"), index=True)
    kind: Mapped[InstrumentKind] = mapped_column(Enum(InstrumentKind, native_enum=False, length=24))
    name: Mapped[str] = mapped_column(String(120))
    isin: Mapped[str | None] = mapped_column(String(12), nullable=True)
    expected_return_percent: Mapped[Decimal] = mapped_column(Numeric(7, 3))
    cost_percent: Mapped[Decimal] = mapped_column(Numeric(7, 3), default=0)
    entry_fee_percent: Mapped[Decimal] = mapped_column(Numeric(7, 3), default=0)
    start: Mapped[date] = mapped_column(Date)
    start_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    rates: Mapped[list["SavingsRate"]] = relationship(
        back_populates="instrument",
        cascade="all, delete-orphan",
        order_by="SavingsRate.valid_from",
    )
    one_offs: Mapped[list["OneOffPayment"]] = relationship(
        back_populates="instrument",
        cascade="all, delete-orphan",
        order_by="OneOffPayment.month",
    )


class SavingsRate(Base):
    """Monthly savings rate valid from ``valid_from`` (inclusive) to ``valid_to`` (exclusive)."""

    __tablename__ = "savings_rates"

    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)

    instrument: Mapped[Instrument] = relationship(back_populates="rates")


class OneOffPayment(Base):
    """A single deposit (positive) or withdrawal (negative) in one month."""

    __tablename__ = "one_off_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    month: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    instrument: Mapped[Instrument] = relationship(back_populates="one_offs")
