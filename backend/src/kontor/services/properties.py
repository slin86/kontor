"""Value of a property over time."""

from datetime import date
from decimal import Decimal

from kontor.domain.cashflow import cents
from kontor.models import Property


def _years(a: date, b: date) -> Decimal:
    return Decimal((b.year - a.year) * 12 + b.month - a.month) / 12


def property_value(p: Property, month: date) -> Decimal:
    """Value of the whole property in a month: the estimate grown from its stand month, plus
    modernisations done afterwards (their value gain grows with the property from then on).
    Before the purchase the property does not exist."""
    if month < p.purchase_month:
        return Decimal(0)
    rate = 1 + Decimal(p.growth_percent) / 100
    since = max(Decimal(0), _years(p.value_as_of, month))
    total = Decimal(p.value) * rate**since
    for w in p.works:
        if w.month > p.value_as_of and w.month <= month:
            total += Decimal(w.value_gain) * rate ** _years(w.month, month)
    return cents(total)
