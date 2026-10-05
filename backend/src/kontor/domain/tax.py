"""Estimate of German capital gains tax for the depot plan (an approximation, not tax advice).

Modelled, per household and calendar year:

* **Vorabpauschale** for accumulating funds. For year ``Y`` it is taxed in January ``Y+1``::

      basisertrag = value * basiszins(Y) * 70 %      # every purchase counts for the months held
      vorab       = max(0, min(basisertrag, fund gain in Y))

  The part that is not tax free (``1 - Teilfreistellung``) is taxed after the allowance.
* **Tax on sale** if everything were sold at the end of a month: gains minus all Vorabpauschalen
  already taxed, less the Teilfreistellung, less what is left of the year's allowance.

The tax rate is 25 % plus solidarity surcharge (5.5 % of it) and optional church tax, which
lowers the base rate (``25 % / (1 + 25 % * church rate)``). Gains and losses of all positions
are netted, and the Vorabpauschale is assumed to be paid from outside the depot. Planned
withdrawals are not taxed individually and distributions are not modelled.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from kontor.core.clock import month_range
from kontor.domain.depot import ZERO, Position, PositionMonth, project_position

BASE_RATE = Decimal("0.25")
SOLIDARITY = Decimal("0.055")
BASISERTRAG_FACTOR = Decimal("0.7")
# Basiszins published by the Bundesbank per year; earlier years had none that mattered.
PUBLISHED_BASE_INTEREST = {
    2023: Decimal("0.0255"),
    2024: Decimal("0.0229"),
    2025: Decimal("0.0253"),
    2026: Decimal("0.032"),
}
LAST_PUBLISHED_YEAR = max(PUBLISHED_BASE_INTEREST)


@dataclass(frozen=True)
class TaxConfig:
    church_tax: Decimal = ZERO  # fraction of the income tax, 0.08 or 0.09
    allowance: Decimal = Decimal(1000)  # Sparer-Pauschbetrag per year (2000 for couples)
    future_base_interest: Decimal = Decimal("0.032")  # assumed for years after the last published


@dataclass(frozen=True)
class TaxMonth:
    month: date
    vorab_paid: Decimal  # cumulative tax paid on Vorabpauschalen up to this month
    sale_tax: Decimal  # tax due if everything were sold at the end of this month

    @property
    def total(self) -> Decimal:
        return self.vorab_paid + self.sale_tax


def tax_rate(church_tax: Decimal) -> Decimal:
    """Effective rate on taxable gains, including solidarity surcharge and church tax."""
    income_tax = BASE_RATE / (1 + BASE_RATE * church_tax)
    return income_tax * (1 + SOLIDARITY + church_tax)


def base_interest(year: int, config: TaxConfig) -> Decimal:
    if year > LAST_PUBLISHED_YEAR:
        return config.future_base_interest
    return PUBLISHED_BASE_INTEREST.get(year, ZERO)


def vorabpauschale(
    position: Position, rows: list[PositionMonth], config: TaxConfig
) -> dict[int, Decimal]:
    """Vorabpauschale (before Teilfreistellung) per year, for years complete in ``rows``."""
    by_month = {r.month: r for r in rows}
    out: dict[int, Decimal] = {}
    for year in range(
        position.start.year, rows[-1].month.year + 1 if rows else position.start.year
    ):
        december = by_month.get(date(year, 12, 1))
        if december is None:
            continue
        previous = by_month.get(date(year - 1, 12, 1))
        opening = previous.balance if previous else ZERO
        deposits = ZERO
        weighted = opening
        net_in = ZERO
        if year == position.start.year:
            weighted += position.start_value * Decimal(13 - position.start.month) / 12
            net_in += position.start_value
        for month in range(1, 13):
            row = by_month.get(date(year, month, 1))
            if row is None:
                continue
            net_in += row.deposit
            if row.deposit > 0:
                deposits += row.deposit
                weighted += row.deposit * Decimal(13 - month) / 12
        gain = december.balance - opening - net_in
        basis = weighted * base_interest(year, config) * BASISERTRAG_FACTOR
        out[year] = max(ZERO, min(basis, gain))
    return out


def project_tax(
    positions: Iterable[Position],
    first: date,
    last: date,
    config: TaxConfig,
    shift: Decimal = ZERO,
) -> list[TaxMonth]:
    """Tax estimate for the months ``first`` to ``last`` (see the module docstring)."""
    rate = tax_rate(config.church_tax)
    projected = [(p, project_position(p, last, shift)) for p in positions]
    vorab = {p.id: vorabpauschale(p, rows, config) for p, rows in projected}
    by_month = {p.id: {r.month: r for r in rows} for p, rows in projected}

    # Vorabpauschale taxed in January of year Y, per household (one shared allowance).
    vorab_tax: dict[int, Decimal] = {}
    taxable_in_year: dict[int, Decimal] = {}
    earliest = min((p.start.year for p, _ in projected), default=first.year)
    for year in range(min(earliest, first.year), last.year + 1):
        taxable = sum(
            (vorab[p.id].get(year - 1, ZERO) * (1 - p.tax_exempt) for p, _ in projected), ZERO
        )
        taxable_in_year[year] = taxable
        vorab_tax[year] = max(ZERO, taxable - config.allowance) * rate

    out: list[TaxMonth] = []
    for m in month_range(first, last):
        paid = sum((t for y, t in vorab_tax.items() if y <= m.year), ZERO)
        gains = ZERO
        for p, _ in projected:
            row = by_month[p.id].get(m)
            if row is None:
                continue
            credited = sum((v for y, v in vorab[p.id].items() if y + 1 <= m.year), ZERO)
            gains += (row.balance - row.paid_in - credited) * (1 - p.tax_exempt)
        remaining = max(ZERO, config.allowance - taxable_in_year.get(m.year, ZERO))
        out.append(TaxMonth(m, paid, max(ZERO, gains - remaining) * rate))
    return out


__all__ = [
    "TaxConfig",
    "TaxMonth",
    "base_interest",
    "project_tax",
    "tax_rate",
    "vorabpauschale",
]
