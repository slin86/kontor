"""Instrument catalog: built-in ETF reference data plus household-specific entries."""

from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from kontor.core.db import Base


class CatalogEntry(Base):
    """An instrument that can be searched, compared and adopted into the depot plan.

    ``household_id`` is ``None`` for the built-in reference data (shared by all households) and set
    for entries a household added itself, e.g. a private-equity fund.
    """

    __tablename__ = "catalog_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int | None] = mapped_column(
        ForeignKey("households.id"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(24), default="etf")
    isin: Mapped[str | None] = mapped_column(String(12), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    index_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    ter_percent: Mapped[Decimal] = mapped_column(Numeric(7, 3))
    distribution: Mapped[str | None] = mapped_column(String(24), nullable=True)
    replication: Mapped[str | None] = mapped_column(String(32), nullable=True)
    domicile: Mapped[str | None] = mapped_column(String(40), nullable=True)
    fund_size_m_eur: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    as_of: Mapped[str | None] = mapped_column(String(7), nullable=True)  # YYYY-MM
