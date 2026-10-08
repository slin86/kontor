"""Net worth: depot, Bausparguthaben and further assets minus the debts of all financings."""

from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from kontor.api.depot import PersonParam, _scope
from kontor.api.depot import projection as depot_projection
from kontor.api.deps import CurrentUser, DbSession
from kontor.core.clock import add_months, current_month, month_range
from kontor.domain import cashflow as cf
from kontor.domain import depot as dep
from kontor.domain.financing import Schedule
from kontor.models import Asset, AssetKind, Financing, FinancingKind, Property
from kontor.schemas.wealth import (
    AssetIn,
    AssetOut,
    WealthOut,
    WealthPoint,
    WealthSeries,
)
from kontor.services.audit import record as audit
from kontor.services.financing_book import all_payouts, load_book
from kontor.services.people import get_person, own_person
from kontor.services.properties import property_value

router = APIRouter(prefix="/api", tags=["wealth"])


def _asset_out(a: Asset) -> AssetOut:
    return AssetOut(
        id=a.id,
        person_id=a.person_id,
        name=a.name,
        kind=a.kind.value,
        value=float(a.value),
        as_of=a.as_of,
        growth_percent=float(a.growth_percent),
    )


def _get(db: DbSession, user: CurrentUser, asset_id: int) -> Asset:
    a = db.get(Asset, asset_id)
    if a is None or a.household_id != user.household_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vermögenswert nicht gefunden")
    return a


@router.get("/assets", response_model=list[AssetOut])
def list_assets(user: CurrentUser, db: DbSession, person: PersonParam = None) -> list[AssetOut]:
    scope = _scope(db, user, person)
    query = db.query(Asset).filter(Asset.household_id == user.household_id)
    if scope is not None:
        query = query.filter(Asset.person_id == scope)
    return [_asset_out(a) for a in query.order_by(Asset.name, Asset.id)]


@router.post("/assets", response_model=AssetOut, status_code=status.HTTP_201_CREATED)
def create_asset(body: AssetIn, user: CurrentUser, db: DbSession) -> AssetOut:
    owner = (
        get_person(db, user.household_id, body.person_id)
        if body.person_id is not None
        else own_person(db, user)
    )
    a = Asset(
        household_id=user.household_id,
        person_id=owner.id,
        kind=AssetKind(body.kind),
        name=body.name.strip(),
        value=body.value,
        as_of=body.as_of,
        growth_percent=body.growth_percent,
    )
    db.add(a)
    db.flush()
    audit(db, user, "create", "asset", a.id, after={"name": a.name, "value": str(a.value)})
    return _asset_out(a)


@router.put("/assets/{asset_id}", response_model=AssetOut)
def update_asset(asset_id: int, body: AssetIn, user: CurrentUser, db: DbSession) -> AssetOut:
    a = _get(db, user, asset_id)
    before = {"name": a.name, "value": str(a.value), "as_of": str(a.as_of)}
    a.name = body.name.strip()
    a.kind = AssetKind(body.kind)
    a.value = body.value
    a.as_of = body.as_of
    a.growth_percent = body.growth_percent
    if body.person_id is not None:
        a.person_id = get_person(db, user.household_id, body.person_id).id
    db.flush()
    audit(
        db,
        user,
        "update",
        "asset",
        a.id,
        before=before,
        after={"name": a.name, "value": str(a.value), "as_of": str(a.as_of)},
    )
    return _asset_out(a)


@router.delete("/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_asset(asset_id: int, user: CurrentUser, db: DbSession) -> None:
    a = _get(db, user, asset_id)
    audit(db, user, "delete", "asset", a.id, before={"name": a.name, "value": str(a.value)})
    db.delete(a)


def asset_value(a: Asset, month: date, today: date) -> Decimal:
    """Value in a month. Before ``as_of`` a known asset stays at its stated value (no history is
    invented); one that is bought later does not exist yet."""
    if month < a.as_of:
        return a.value if a.as_of <= today else Decimal(0)
    months = (month.year - a.as_of.year) * 12 + month.month - a.as_of.month
    factor = (1 + Decimal(a.growth_percent) / 100) ** (Decimal(months) / 12)
    return cf.cents(Decimal(a.value) * factor)


def financing_position(f: Financing, schedule: Schedule, month: date) -> tuple[Decimal, Decimal]:
    """(saved, debt) of a financing at the end of a month."""
    row = schedule.at(month)
    if row is None:
        return Decimal(0), Decimal(0)
    if f.kind != FinancingKind.BUILDING_SAVINGS:
        return Decimal(0), row.balance
    if row.phase == "saving":
        advance = Decimal(0)
        if f.params.get("prefinance_rate_percent") is not None:
            advance = sum((a for m, a in all_payouts(f) if m <= month), Decimal(0))
        return row.balance, advance
    return Decimal(0), row.balance


@router.get("/wealth", response_model=WealthOut)
def wealth(
    user: CurrentUser,
    db: DbSession,
    years: Annotated[int, Query(ge=1, le=50)] = 20,
    back_months: Annotated[int, Query(ge=0, le=120)] = 12,
    return_shift: Annotated[Decimal, Query(ge=-15, le=15)] = Decimal(0),
    inflation: Annotated[Decimal, Query(ge=0, le=20)] = Decimal(0),
    person: PersonParam = None,
) -> WealthOut:
    today = current_month()
    scope = _scope(db, user, person)
    first = add_months(today, -back_months)
    last = add_months(today, years * 12)
    months = month_range(first, last)

    depot = depot_projection(
        user, db, years, first.strftime("%Y-%m"), return_shift, Decimal(0), person
    )
    depot_at = {p.month: p for p in depot.points}

    query = db.query(Asset).filter(Asset.household_id == user.household_id)
    if scope is not None:
        query = query.filter(Asset.person_id == scope)
    assets = query.order_by(Asset.name, Asset.id).all()
    pquery = db.query(Property).filter(Property.household_id == user.household_id)
    if scope is not None:
        pquery = pquery.filter(Property.person_id == scope)
    properties = pquery.order_by(Property.name, Property.id).all()
    book = load_book(db, user.household_id, scope)

    series: list[WealthSeries] = [WealthSeries(key="depot", name="Depot", group="depot")]
    for f, _ in book.items:
        if f.kind == FinancingKind.BUILDING_SAVINGS:
            series.append(
                WealthSeries(key=f"saved:{f.id}", name=f"Bausparguthaben {f.name}", group="bauspar")
            )
    series += [
        WealthSeries(key=f"property:{p.id}", name=p.name, group="property") for p in properties
    ]
    series += [WealthSeries(key=f"asset:{a.id}", name=a.name, group="asset") for a in assets]
    series += [WealthSeries(key=f"debt:{f.id}", name=f.name, group="debt") for f, _ in book.items]

    infl = inflation / 100
    raw: list[list[Decimal]] = []
    for m in months:
        ahead = (m.year - today.year) * 12 + m.month - today.month
        row: list[Decimal] = [Decimal(str(depot_at[m].value)) if m in depot_at else Decimal(0)]
        row += [
            financing_position(f, s, m)[0]
            for f, s in book.items
            if f.kind == FinancingKind.BUILDING_SAVINGS
        ]
        row += [cf.cents(property_value(p, m) * Decimal(p.share_percent) / 100) for p in properties]
        row += [asset_value(a, m, today) for a in assets]
        row += [financing_position(f, s, m)[1] for f, s in book.items]
        raw.append([dep.deflate(v, infl, ahead) for v in row])

    keep = [i for i in range(len(series)) if i == 0 or any(r[i] != 0 for r in raw)]
    series = [series[i] for i in keep]
    points: list[WealthPoint] = []
    for m, r in zip(months, raw, strict=True):
        ahead = (m.year - today.year) * 12 + m.month - today.month
        vals = [r[i] for i in keep]
        asset_total = sum(
            (v for v, s in zip(vals, series, strict=True) if s.group != "debt"), Decimal(0)
        )
        debt_total = sum(
            (v for v, s in zip(vals, series, strict=True) if s.group == "debt"), Decimal(0)
        )
        gross = Decimal(str(depot_at[m].value)) if m in depot_at else Decimal(0)
        net_depot = Decimal(str(depot_at[m].net_value)) if m in depot_at else Decimal(0)
        tax = dep.deflate(gross - net_depot, infl, ahead)
        points.append(
            WealthPoint(
                month=m,
                values=[float(cf.cents(v)) for v in vals],
                assets=float(cf.cents(asset_total)),
                debts=float(cf.cents(debt_total)),
                net=float(cf.cents(asset_total - debt_total)),
                net_after_tax=float(cf.cents(asset_total - debt_total - tax)),
            )
        )
    return WealthOut(
        first=first,
        last=last,
        today=today,
        inflation_percent=float(inflation),
        series=series,
        points=points,
    )
