"""Turns stored instruments into domain positions."""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from kontor.domain.cashflow import VersionSpec
from kontor.domain.depot import Position
from kontor.domain.tax import TaxConfig
from kontor.models import Instrument, TaxSettings

PERCENT = Decimal(100)


def rate_specs(i: Instrument) -> list[VersionSpec]:
    return [VersionSpec(r.amount, "monthly", r.valid_from, r.valid_to, r.id) for r in i.rates]


def to_position(i: Instrument) -> Position:
    return Position(
        id=i.id,
        name=i.name,
        kind=i.kind.value,
        annual_return=Decimal(i.expected_return_percent) / PERCENT,
        annual_cost=Decimal(i.cost_percent) / PERCENT,
        entry_fee=Decimal(i.entry_fee_percent) / PERCENT,
        start=i.start,
        start_value=Decimal(i.start_value),
        rates=rate_specs(i),
        one_offs=_summed(i),
        tax_exempt=Decimal(i.tax_exempt_percent) / PERCENT,
    )


def _summed(i: Instrument) -> dict[date, Decimal]:
    """Several one-offs in the same month add up."""
    out: dict[date, Decimal] = {}
    for o in i.one_offs:
        out[o.month] = out.get(o.month, Decimal(0)) + Decimal(o.amount)
    return out


def load_instruments(db: Session, household_id: int) -> list[Instrument]:
    return list(
        db.scalars(
            select(Instrument)
            .where(Instrument.household_id == household_id)
            .options(selectinload(Instrument.rates), selectinload(Instrument.one_offs))
            .order_by(Instrument.name, Instrument.id)
        )
    )


def tax_config(db: Session, household_id: int) -> TaxConfig:
    """The household's tax settings, or the defaults when none were saved."""
    row = db.get(TaxSettings, household_id)
    if row is None:
        return TaxConfig()
    return TaxConfig(
        church_tax=Decimal(row.church_tax_percent) / PERCENT,
        allowance=Decimal(row.allowance),
        future_base_interest=Decimal(row.base_interest_percent) / PERCENT,
    )
