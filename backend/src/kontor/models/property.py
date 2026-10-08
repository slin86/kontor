"""Real estate: owner-occupied or rented, with modernisations, linked financings and cashflow."""

import enum
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kontor.core.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class PropertyUsage(enum.StrEnum):
    OWNER_OCCUPIED = "owner_occupied"
    RENTED = "rented"


class Property(Base):
    """A property. ``value`` is the market estimate at the start of ``value_as_of``; it then
    follows ``growth_percent`` per year. ``share_percent`` is the part the household owns."""

    __tablename__ = "properties"

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("households.id"), index=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("persons.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    usage: Mapped[PropertyUsage] = mapped_column(Enum(PropertyUsage, native_enum=False, length=16))
    purchase_month: Mapped[date] = mapped_column(Date)
    purchase_price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    closing_costs: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    value: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    value_as_of: Mapped[date] = mapped_column(Date)
    growth_percent: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0)
    share_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    works: Mapped[list["PropertyWork"]] = relationship(
        back_populates="property",
        cascade="all, delete-orphan",
        order_by="PropertyWork.month, PropertyWork.id",
    )


class PropertyWork(Base):
    """A modernisation or repair: what it cost and by how much it raises the value."""

    __tablename__ = "property_works"

    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    month: Mapped[date] = mapped_column(Date)
    name: Mapped[str] = mapped_column(String(120))
    cost: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    value_gain: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)

    property: Mapped[Property] = relationship(back_populates="works")
