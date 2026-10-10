"""Pure depot projection: positions with savings rates, one-off payments and compound growth.

Nothing in here touches the database or HTTP. All amounts are ``Decimal``.

Model per position and month ``m`` (from its start month on)::

    growth   = balance * monthly_return
    deposit  = savings_rate(m) + one_off(m)         # one-offs may be negative (withdrawal)
    fee      = entry_fee * max(deposit, 0)          # taken from the deposit before it is invested
    balance += growth + deposit - fee

The annual return is reduced by the running cost (TER) and converted to a monthly rate with
``(1 + net) ** (1/12) - 1``, so twelve months compound to exactly the annual figure.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from kontor.core.clock import month_range
from kontor.domain.cashflow import VersionSpec, active_version

ZERO = Decimal(0)
MAX_MONTHS = 1800
MIN_NET_RETURN = Decimal("-0.95")


class DepotError(ValueError):
    """The plan cannot be projected, e.g. a withdrawal exceeds the balance."""


@dataclass(frozen=True)
class Position:
    """One instrument in the plan with everything the projection needs."""

    id: int
    name: str
    kind: str  # "etf" | "private_equity"
    annual_return: Decimal  # gross, as a fraction (0.06 = 6 %)
    annual_cost: Decimal  # running cost (TER), as a fraction
    entry_fee: Decimal  # fraction of every deposit
    start: date
    start_value: Decimal
    rates: list[VersionSpec] = field(default_factory=list)
    one_offs: dict[date, Decimal] = field(default_factory=dict)
    tax_exempt: Decimal = ZERO  # Teilfreistellung as a fraction (0.3 = 30 % of gains are tax free)


@dataclass(frozen=True)
class PositionMonth:
    month: date
    balance: Decimal  # end of month
    growth: Decimal
    deposit: Decimal  # savings rate plus one-offs (negative for withdrawals)
    fee: Decimal
    paid_in: Decimal  # cumulative deposits including the start value


def monthly_return(annual_return: Decimal, annual_cost: Decimal, shift: Decimal = ZERO) -> Decimal:
    """Monthly growth rate after costs; ``shift`` moves the gross return (scenarios)."""
    net = max(annual_return + shift - annual_cost, MIN_NET_RETURN)
    return Decimal(str((1 + float(net)) ** (1 / 12) - 1))


def rate_at(position: Position, month: date) -> Decimal:
    v = active_version(position.rates, month)
    return v.amount if v else ZERO


def project_position(position: Position, last: date, shift: Decimal = ZERO) -> list[PositionMonth]:
    """Month-by-month development from the position's start to ``last`` (inclusive)."""
    if last < position.start:
        return []
    months = month_range(position.start, last)
    if len(months) > MAX_MONTHS:
        raise DepotError("Der Zeitraum ist zu lang.")

    r = monthly_return(position.annual_return, position.annual_cost, shift)
    balance = position.start_value
    paid_in = position.start_value
    rows: list[PositionMonth] = []
    for m in months:
        growth = balance * r
        deposit = rate_at(position, m) + position.one_offs.get(m, ZERO)
        fee = position.entry_fee * deposit if deposit > 0 else ZERO
        available = balance + growth
        if deposit < 0 and -deposit > available:
            raise DepotError(
                f"{position.name}: Die Entnahme im Monat {m:%Y-%m} übersteigt das Guthaben."
            )
        balance = available + deposit - fee
        paid_in += deposit
        rows.append(PositionMonth(m, balance, growth, deposit, fee, paid_in))
    return rows


def forecast_position(
    position: Position, anchor: date, anchor_balance: Decimal, last: date
) -> dict[date, Decimal]:
    """Balances after ``anchor``, continuing from a real value instead of the planned one.

    ``anchor_balance`` is what the position really was worth at the end of ``anchor``; the months
    after it use the plan's return, costs, savings rates and one-offs.
    """
    months = month_range(anchor, last)[1:]
    if len(months) > MAX_MONTHS:
        raise DepotError("Der Zeitraum ist zu lang.")
    r = monthly_return(position.annual_return, position.annual_cost)
    balance = anchor_balance
    out: dict[date, Decimal] = {}
    for m in months:
        deposit = rate_at(position, m) + position.one_offs.get(m, ZERO)
        fee = position.entry_fee * deposit if deposit > 0 else ZERO
        available = balance * (1 + r)
        if deposit < 0 and -deposit > available:
            raise DepotError(
                f"{position.name}: Die Entnahme im Monat {m:%Y-%m} übersteigt das Guthaben."
            )
        balance = available + deposit - fee
        out[m] = balance
    return out


@dataclass(frozen=True)
class DepotMonth:
    month: date
    balances: dict[int, Decimal]  # per position id, end of month
    value: Decimal
    paid_in: Decimal
    deposit: Decimal  # all savings rates and one-offs of the month
    fees: Decimal

    @property
    def gain(self) -> Decimal:
        return self.value - self.paid_in


def project_depot(
    positions: Iterable[Position], first: date, last: date, shift: Decimal = ZERO
) -> list[DepotMonth]:
    """Total development for the months ``first`` to ``last``.

    Positions start growing at their own start month; before that they contribute nothing.
    Months before ``first`` are computed but not returned, so the history stays consistent.
    """
    if last < first:
        raise DepotError("Das Ende liegt vor dem Start.")
    per_position = {p.id: {r.month: r for r in project_position(p, last, shift)} for p in positions}

    out: list[DepotMonth] = []
    for m in month_range(first, last):
        balances: dict[int, Decimal] = {}
        paid_in = deposit = fees = ZERO
        for pid, rows in per_position.items():
            row = rows.get(m)
            if row is None:
                # not started yet (zero), or ended before ``m`` (cannot happen: runs to ``last``)
                balances[pid] = ZERO
                continue
            balances[pid] = row.balance
            paid_in += row.paid_in
            deposit += row.deposit
            fees += row.fee
        out.append(DepotMonth(m, balances, sum(balances.values(), ZERO), paid_in, deposit, fees))
    return out


def base_rate(positions: Iterable[Position], month: date) -> Decimal:
    """Sum of all savings rates in a month (the depot's base rate)."""
    return sum((rate_at(p, month) for p in positions if p.start <= month), ZERO)


def deflate(value: Decimal, inflation: Decimal, months_ahead: int) -> Decimal:
    """Express a nominal amount in today's purchasing power."""
    if inflation == 0 or months_ahead <= 0:
        return value
    factor = (1 + float(inflation)) ** (months_ahead / 12)
    return value / Decimal(str(factor))


__all__ = [
    "DepotError",
    "DepotMonth",
    "Position",
    "PositionMonth",
    "base_rate",
    "deflate",
    "forecast_position",
    "monthly_return",
    "project_depot",
    "project_position",
    "rate_at",
]
