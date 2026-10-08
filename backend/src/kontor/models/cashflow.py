"""Cashflow: categories, items with effective-dated versions, and the audit log."""

import enum
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Date, DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kontor.core.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class CategoryKind(enum.StrEnum):
    INCOME = "income"
    EXPENSE = "expense"


class Frequency(enum.StrEnum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    SEMIANNUAL = "semiannual"
    YEARLY = "yearly"

    @property
    def months(self) -> int:
        return {"monthly": 1, "quarterly": 3, "semiannual": 6, "yearly": 12}[self.value]


class Category(Base):
    """Two-level category tree (group -> sub-category) per household."""

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("households.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[CategoryKind] = mapped_column(Enum(CategoryKind, native_enum=False, length=16))
    sort_order: Mapped[int] = mapped_column(default=0)


class CashflowItem(Base):
    """A recurring income or expense. Its amounts live in ``CashflowVersion`` rows."""

    __tablename__ = "cashflow_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("households.id"), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), index=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("persons.id"), index=True)
    # Set for a transfer: the booking is an expense of ``person_id`` and income of this person.
    transfer_to_id: Mapped[int | None] = mapped_column(
        ForeignKey("persons.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    category: Mapped[Category] = relationship()
    versions: Mapped[list["CashflowVersion"]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="CashflowVersion.valid_from",
    )


class CashflowVersion(Base):
    """Amount valid for the months ``valid_from`` (inclusive) to ``valid_to`` (exclusive).

    ``valid_to`` is ``None`` for open-ended versions. Versions of one item never overlap.
    """

    __tablename__ = "cashflow_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("cashflow_items.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    frequency: Mapped[Frequency] = mapped_column(Enum(Frequency, native_enum=False, length=16))
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)

    item: Mapped[CashflowItem] = relationship(back_populates="versions")


class AuditLog(Base):
    """Append-only trail of changes, in particular corrections to locked history."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("households.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(40))
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[int] = mapped_column()
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
