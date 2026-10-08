"""Financings (loans, building-society contracts) and their dated events."""

import enum
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Date, DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kontor.core.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class FinancingKind(enum.StrEnum):
    LOAN = "loan"
    BUILDING_SAVINGS = "building_savings"
    CREDIT_LINE = "credit_line"


class Financing(Base):
    """A loan (real-estate financing or consumer loan) or a Bausparvertrag.

    ``params`` holds the kind-specific contract data as JSON with decimals as strings and
    months as ``YYYY-MM``; the domain layer turns it into a schedule.
    """

    __tablename__ = "financings"

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("households.id"), index=True)
    kind: Mapped[FinancingKind] = mapped_column(Enum(FinancingKind, native_enum=False, length=24))
    name: Mapped[str] = mapped_column(String(120))
    purpose: Mapped[str | None] = mapped_column(String(24), nullable=True)
    params: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    events: Mapped[list["FinancingEvent"]] = relationship(
        back_populates="financing",
        cascade="all, delete-orphan",
        order_by="FinancingEvent.month, FinancingEvent.id",
    )


class FinancingEvent(Base):
    """A dated change: special repayment, drawdown, new monthly payment or new interest rate."""

    __tablename__ = "financing_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    financing_id: Mapped[int] = mapped_column(ForeignKey("financings.id"), index=True)
    month: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(
        String(24)
    )  # special_repayment | payment_change | rate_change | drawdown
    value: Mapped[Decimal] = mapped_column(Numeric(14, 6))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    financing: Mapped[Financing] = relationship(back_populates="events")
