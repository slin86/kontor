"""Further assets next to the depot: cash, property, vehicles. They only enter the net worth."""

import enum
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from kontor.core.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class AssetKind(enum.StrEnum):
    CASH = "cash"
    PROPERTY = "property"
    VEHICLE = "vehicle"
    OTHER = "other"


class Asset(Base):
    """A value the household owns. ``value`` is the worth at the start of ``as_of``; from there it
    grows (or shrinks, for a car) with ``growth_percent`` per year."""

    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("households.id"), index=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("persons.id"), index=True)
    kind: Mapped[AssetKind] = mapped_column(Enum(AssetKind, native_enum=False, length=16))
    name: Mapped[str] = mapped_column(String(120))
    value: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    as_of: Mapped[date] = mapped_column(Date)
    growth_percent: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
