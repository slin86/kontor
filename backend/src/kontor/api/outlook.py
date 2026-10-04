"""Budget outlook: how the free monthly budget develops as financings and items run out."""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query

from kontor.api.cashflow import (
    MonthParam,
    _active_items,
    _categories,
    _category_infos,
    _items,
    _month_query,
    _specs,
)
from kontor.api.deps import CurrentUser, DbSession
from kontor.core.clock import add_months, month_range
from kontor.domain import cashflow as dom
from kontor.models import CategoryKind
from kontor.schemas.financing import OutlookEvent, OutlookOut, OutlookPoint
from kontor.services.financing_book import load_book

router = APIRouter(prefix="/api", tags=["outlook"])


def _growth_factor(percent: Decimal, months_ahead: int) -> Decimal:
    """Compound growth: ``(1 + p/100) ** (months/12)``, as a Decimal."""
    if percent == 0 or months_ahead == 0:
        return Decimal(1)
    factor = (1 + float(percent) / 100) ** (months_ahead / 12)
    return Decimal(str(round(factor, 8)))


@router.get("/outlook", response_model=OutlookOut)
def outlook(
    user: CurrentUser,
    db: DbSession,
    start: MonthParam = None,
    years: Annotated[int, Query(ge=1, le=50)] = 30,
    income_growth: Annotated[Decimal, Query(ge=-10, le=20)] = Decimal(0),
    expense_growth: Annotated[Decimal, Query(ge=-10, le=20)] = Decimal(0),
) -> OutlookOut:
    first = _month_query(start)
    months = month_range(first, add_months(first, years * 12 - 1))

    cats = _categories(db, user.household_id)
    infos = _category_infos(cats)
    kind_of = {c.id: c.kind for c in cats}
    items = _items(db, user.household_id)
    book = load_book(db, user.household_id)

    points: list[OutlookPoint] = []
    for idx, m in enumerate(months):
        income_f = _growth_factor(income_growth, idx)
        expense_f = _growth_factor(expense_growth, idx)
        scaled = [
            dom.ActiveItem(
                a.item_id,
                a.name,
                a.category_id,
                a.monthly
                * (income_f if kind_of[a.category_id] == CategoryKind.INCOME else expense_f),
            )
            for a in _active_items(items, m)
        ]
        s = dom.summarize(infos, scaled, book.flows_at(m))
        points.append(
            OutlookPoint(
                month=m,
                income=float(s.income),
                expenses=float(s.expenses),
                financing=float(s.financing),
                free=float(s.balance),
            )
        )

    events: list[OutlookEvent] = []
    last = months[-1]

    for f, schedule in book.items:
        end = schedule.end_month
        if first < end <= last:
            events.append(
                OutlookEvent(
                    month=end,
                    kind="financing_end",
                    label=f"{f.name} ist abbezahlt",
                    monthly_change=float(schedule.regular_payment),
                )
            )

    for item in items:
        specs = _specs(item)
        final = max(specs, key=lambda v: v.valid_from)
        if final.valid_to is None or not (first < final.valid_to <= last):
            continue
        monthly = dom.monthly_amount(final.amount, final.frequency)
        sign = 1 if item.category.kind == CategoryKind.EXPENSE else -1
        events.append(
            OutlookEvent(
                month=final.valid_to,
                kind="item_end",
                label=f"{item.name} endet",
                monthly_change=float(dom.cents(monthly) * sign),
            )
        )

    events.sort(key=lambda e: (e.month, e.label))
    return OutlookOut(
        start=first,
        years=years,
        income_growth_percent=float(income_growth),
        expense_growth_percent=float(expense_growth),
        points=points,
        events=events,
    )
