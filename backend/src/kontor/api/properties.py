"""Real estate: properties with modernisations and links to financings and cashflow items."""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from kontor.api.depot import PersonParam, _scope
from kontor.api.deps import CurrentUser, DbSession
from kontor.api.financings import _summary as summary
from kontor.api.wealth import financing_position
from kontor.core.clock import current_month
from kontor.domain import cashflow as cf
from kontor.domain.financing import Schedule
from kontor.models import (
    CashflowItem,
    CategoryKind,
    Financing,
    Property,
    PropertyUsage,
    PropertyWork,
)
from kontor.schemas.property import (
    LinkedFinancing,
    LinkedItem,
    LinksIn,
    PropertyIn,
    PropertyOut,
    WorkIn,
    WorkOut,
)
from kontor.services.audit import record as audit
from kontor.services.financing_book import schedule_for
from kontor.services.people import get_person, own_person
from kontor.services.properties import amount_factor, property_value

router = APIRouter(prefix="/api", tags=["properties"])
HUNDRED = Decimal(100)


def _get(db: DbSession, user: CurrentUser, property_id: int) -> Property:
    p = db.get(Property, property_id)
    if p is None or p.household_id != user.household_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Immobilie nicht gefunden")
    return p


def _item_monthly(item: CashflowItem, month: date) -> Decimal:
    specs = [
        cf.VersionSpec(v.amount, v.frequency.value, v.valid_from, v.valid_to, v.id)
        for v in item.versions
    ]
    spec = cf.active_version(specs, month)
    return cf.monthly_amount(spec.amount, spec.frequency) if spec else Decimal(0)


def _initial_debt(schedule: Schedule) -> Decimal | None:
    """Highest debt of the loan phase, which is what gets paid off over time."""
    loan = [r for r in schedule.rows if r.phase == "loan"]
    if not loan:
        return None
    first = loan[0]
    return max(first.balance + first.principal - first.drawn, *(r.balance for r in loan))


def _out(db: DbSession, p: Property) -> PropertyOut:
    today = current_month()
    factor = amount_factor(p)
    financings: list[LinkedFinancing] = []
    debt = payment = repaid_part = repaying_total = Decimal(0)
    for f in db.scalars(
        select(Financing)
        .where(Financing.property_id == p.id)
        .options(selectinload(Financing.events))
    ):
        schedule = schedule_for(f)
        info = summary(f, schedule)
        remaining = financing_position(f, schedule, today)[1]
        row = schedule.at(today)
        pay = row.outflow if row else Decimal(0)
        initial = _initial_debt(schedule)
        loan_rows = [r for r in schedule.rows if r.phase == "loan"]
        # a Bauspar contract that is still saving has not started to repay anything
        repaying = info.phase in ("loan", "finished") and initial is not None
        debt += remaining
        payment += pay
        if repaying and initial:
            repaid_part += max(Decimal(0), initial - remaining)
            repaying_total += max(initial, remaining)
        else:
            repaying_total += remaining  # still saving: advance loan counts as debt, not repaid
        financings.append(
            LinkedFinancing(
                id=f.id,
                name=f.name,
                remaining_debt=float(remaining),
                payment_this_month=float(pay),
                initial_debt=float(initial) if initial is not None else None,
                repaid_percent=(
                    float(cf.cents(max(Decimal(0), 1 - remaining / initial) * HUNDRED))
                    if repaying and initial
                    else None
                ),
                end_month=schedule.end_month,
                kind=f.kind.value,
                phase=info.phase,
                prefinanced=info.prefinanced,
                saved=info.saved,
                loan_start=loan_rows[0].month if loan_rows else None,
            )
        )
    debt, payment = debt * factor, payment * factor
    repaid = repaid_part * factor

    items: list[LinkedItem] = []
    income = costs = Decimal(0)
    for item in db.scalars(
        select(CashflowItem)
        .where(CashflowItem.property_id == p.id)
        .options(selectinload(CashflowItem.versions), selectinload(CashflowItem.category))
        .order_by(CashflowItem.name)
    ):
        monthly = _item_monthly(item, today)
        is_income = item.category.kind == CategoryKind.INCOME
        if is_income:
            income += monthly
        else:
            costs += monthly
        items.append(
            LinkedItem(
                id=item.id,
                name=item.name,
                kind="income" if is_income else "expense",
                monthly=float(cf.cents(monthly)),
            )
        )
    income, costs = income * factor, costs * factor

    value = property_value(p, today)
    my_value = cf.cents(value * Decimal(p.share_percent) / HUNDRED)
    my_works = Decimal(p.share_percent) / HUNDRED
    invested = Decimal(p.purchase_price) + Decimal(p.closing_costs)
    invested += sum((Decimal(w.cost) for w in p.works if w.month <= today), Decimal(0))
    surplus = income - costs
    return PropertyOut(
        id=p.id,
        person_id=p.person_id,
        name=p.name,
        usage=p.usage.value,
        purchase_month=p.purchase_month,
        purchase_price=float(p.purchase_price),
        closing_costs=float(p.closing_costs),
        value=float(p.value),
        value_as_of=p.value_as_of,
        growth_percent=float(p.growth_percent),
        share_percent=float(p.share_percent),
        own_share_entered=p.own_share_entered,
        works=[
            WorkOut(
                id=w.id,
                month=w.month,
                name=w.name,
                cost=float(w.cost),
                value_gain=float(w.value_gain),
            )
            for w in p.works
        ],
        current_value=float(value),
        my_value=float(my_value),
        debt=float(cf.cents(debt)),
        repaid=float(cf.cents(repaid)),
        repaid_percent=(
            float(cf.cents(repaid_part / repaying_total * HUNDRED)) if repaying_total > 0 else None
        ),
        equity=float(cf.cents(my_value - debt)),
        invested=float(cf.cents(invested * my_works)),
        value_gain=float(cf.cents(value * my_works - invested * my_works)),
        income=float(cf.cents(income)),
        costs=float(cf.cents(costs)),
        financing_payment=float(cf.cents(payment)),
        net_cashflow=float(cf.cents(surplus - payment)),
        yield_percent=float(cf.cents(surplus * 12 / my_value * HUNDRED)) if my_value > 0 else None,
        financings=financings,
        items=items,
    )


def _apply(p: Property, body: PropertyIn) -> None:
    p.name = body.name.strip()
    p.usage = PropertyUsage(body.usage)
    p.purchase_month = body.purchase_month
    p.purchase_price = body.purchase_price
    p.closing_costs = body.closing_costs
    p.value = body.value
    p.value_as_of = body.value_as_of
    p.growth_percent = body.growth_percent
    p.share_percent = body.share_percent
    p.own_share_entered = body.own_share_entered


@router.get("/properties", response_model=list[PropertyOut])
def list_properties(
    user: CurrentUser, db: DbSession, person: PersonParam = None
) -> list[PropertyOut]:
    scope = _scope(db, user, person)
    query = db.query(Property).filter(Property.household_id == user.household_id)
    if scope is not None:
        query = query.filter(Property.person_id == scope)
    return [_out(db, p) for p in query.order_by(Property.name, Property.id)]


@router.get("/properties/{property_id}", response_model=PropertyOut)
def get_property(property_id: int, user: CurrentUser, db: DbSession) -> PropertyOut:
    return _out(db, _get(db, user, property_id))


@router.post("/properties", response_model=PropertyOut, status_code=status.HTTP_201_CREATED)
def create_property(body: PropertyIn, user: CurrentUser, db: DbSession) -> PropertyOut:
    owner = (
        get_person(db, user.household_id, body.person_id)
        if body.person_id is not None
        else own_person(db, user)
    )
    p = Property(household_id=user.household_id, person_id=owner.id)
    _apply(p, body)
    db.add(p)
    db.flush()
    audit(db, user, "create", "property", p.id, after={"name": p.name, "value": str(p.value)})
    return _out(db, p)


@router.put("/properties/{property_id}", response_model=PropertyOut)
def update_property(
    property_id: int, body: PropertyIn, user: CurrentUser, db: DbSession
) -> PropertyOut:
    p = _get(db, user, property_id)
    before = {"name": p.name, "value": str(p.value), "as_of": str(p.value_as_of)}
    _apply(p, body)
    if body.person_id is not None:
        p.person_id = get_person(db, user.household_id, body.person_id).id
    db.flush()
    audit(
        db,
        user,
        "update",
        "property",
        p.id,
        before=before,
        after={"name": p.name, "value": str(p.value), "as_of": str(p.value_as_of)},
    )
    return _out(db, p)


@router.delete("/properties/{property_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_property(property_id: int, user: CurrentUser, db: DbSession) -> None:
    p = _get(db, user, property_id)
    for f in db.scalars(select(Financing).where(Financing.property_id == p.id)):
        f.property_id = None
    for item in db.scalars(select(CashflowItem).where(CashflowItem.property_id == p.id)):
        item.property_id = None
    audit(db, user, "delete", "property", p.id, before={"name": p.name})
    db.delete(p)


@router.post(
    "/properties/{property_id}/works",
    response_model=PropertyOut,
    status_code=status.HTTP_201_CREATED,
)
def add_work(property_id: int, body: WorkIn, user: CurrentUser, db: DbSession) -> PropertyOut:
    p = _get(db, user, property_id)
    p.works.append(
        PropertyWork(
            month=body.month, name=body.name.strip(), cost=body.cost, value_gain=body.value_gain
        )
    )
    db.flush()
    audit(
        db, user, "create", "property_work", p.id, after={"name": body.name, "cost": str(body.cost)}
    )
    db.refresh(p)
    return _out(db, p)


@router.delete("/properties/{property_id}/works/{work_id}", response_model=PropertyOut)
def delete_work(property_id: int, work_id: int, user: CurrentUser, db: DbSession) -> PropertyOut:
    p = _get(db, user, property_id)
    work = next((w for w in p.works if w.id == work_id), None)
    if work is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Maßnahme nicht gefunden")
    audit(db, user, "delete", "property_work", p.id, before={"name": work.name})
    p.works.remove(work)
    db.flush()
    return _out(db, p)


@router.put("/properties/{property_id}/links", response_model=PropertyOut)
def set_links(property_id: int, body: LinksIn, user: CurrentUser, db: DbSession) -> PropertyOut:
    """Replace which financings and cashflow items belong to the property."""
    p = _get(db, user, property_id)
    fin_ids, item_ids = set(body.financing_ids), set(body.item_ids)
    fins = list(
        db.scalars(
            select(Financing).where(
                Financing.household_id == user.household_id,
                (Financing.property_id == p.id) | Financing.id.in_(fin_ids),
            )
        )
    )
    items = list(
        db.scalars(
            select(CashflowItem).where(
                CashflowItem.household_id == user.household_id,
                (CashflowItem.property_id == p.id) | CashflowItem.id.in_(item_ids),
            )
        )
    )
    if not (fin_ids <= {f.id for f in fins} and item_ids <= {i.id for i in items}):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unbekannte Verknüpfung")
    for f in fins:
        f.property_id = p.id if f.id in fin_ids else None
    for i in items:
        i.property_id = p.id if i.id in item_ids else None
    db.flush()
    audit(
        db,
        user,
        "update",
        "property",
        p.id,
        after={"financings": sorted(fin_ids), "items": sorted(item_ids)},
    )
    return _out(db, p)
