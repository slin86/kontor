"""Depot plan: instruments with dated savings rates and one-off payments, plus the projection."""

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from kontor.api.deps import CurrentUser, DbSession
from kontor.core.clock import add_months, current_month, format_month
from kontor.domain import cashflow as cf
from kontor.domain import depot as dom
from kontor.domain import tax as tax_dom
from kontor.models import (
    ActualValue,
    DepotTransaction,
    Instrument,
    InstrumentKind,
    OneOffPayment,
    SavingsRate,
)
from kontor.schemas.depot import (
    Assumptions,
    DepotOut,
    InstrumentCorrection,
    InstrumentDetailOut,
    InstrumentIn,
    InstrumentOut,
    OneOffIn,
    OneOffOut,
    OwnerChange,
    ProjectionInstrument,
    ProjectionOut,
    ProjectionPoint,
    RateChange,
    RateOut,
)
from kontor.services.audit import record as audit
from kontor.services.depot_book import load_instruments, rate_specs, tax_config, to_position
from kontor.services.people import get_person, own_person

router = APIRouter(prefix="/api/depot", tags=["depot"])

LOCKED_MESSAGE = (
    "Dieser Monat ist abgeschlossen. Der Plan für vergangene Monate lässt sich nicht ändern; "
    "korrigiere stattdessen Startmonat und Startwert mit einer Begründung."
)
MAX_YEARS = 100


def _get(db: Session, user: CurrentUser, instrument_id: int) -> Instrument:
    i = db.get(Instrument, instrument_id)
    if i is None or i.household_id != user.household_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Position nicht gefunden")
    return i


def _default_exempt(body: InstrumentIn) -> Decimal:
    if body.tax_exempt_percent is not None:
        return body.tax_exempt_percent
    return Decimal(30) if body.kind == "etf" else Decimal(0)


def _check(i: Instrument) -> None:
    """Reject plans that cannot be projected (a withdrawal larger than the balance)."""
    try:
        dom.project_position(to_position(i), add_months(current_month(), 12))
    except dom.DepotError as e:
        raise HTTPException(422, str(e)) from e


def _snapshot(i: Instrument) -> dict[str, Any]:
    return {
        "name": i.name,
        "isin": i.isin,
        "expected_return_percent": str(i.expected_return_percent),
        "cost_percent": str(i.cost_percent),
        "entry_fee_percent": str(i.entry_fee_percent),
        "tax_exempt_percent": str(i.tax_exempt_percent),
        "start": format_month(i.start),
        "start_value": str(i.start_value),
    }


def _summary(i: Instrument) -> InstrumentOut:
    today = current_month()
    position = to_position(i)
    rows = dom.project_position(position, today)
    last = rows[-1] if rows else None
    return InstrumentOut(
        id=i.id,
        person_id=i.person_id,
        kind=i.kind.value,
        name=i.name,
        isin=i.isin,
        expected_return_percent=float(i.expected_return_percent),
        cost_percent=float(i.cost_percent),
        entry_fee_percent=float(i.entry_fee_percent),
        tax_exempt_percent=float(i.tax_exempt_percent),
        start=i.start,
        start_value=float(i.start_value),
        current_rate=float(dom.rate_at(position, today)) if i.start <= today else 0.0,
        planned_value=float(cf.cents(last.balance)) if last else 0.0,
        paid_in=float(last.paid_in) if last else 0.0,
    )


def _detail(i: Instrument) -> InstrumentDetailOut:
    today = current_month()
    return InstrumentDetailOut(
        **_summary(i).model_dump(),
        rates=[
            RateOut(
                id=r.id,
                amount=float(r.amount),
                valid_from=r.valid_from,
                valid_to=r.valid_to,
                locked=r.valid_from < today,
            )
            for r in i.rates
        ],
        one_offs=[
            OneOffOut(
                id=o.id, month=o.month, amount=float(o.amount), note=o.note, locked=o.month < today
            )
            for o in i.one_offs
        ],
    )


def _sync_rates(db: Session, i: Instrument, specs: list[cf.VersionSpec]) -> None:
    existing = {r.id: r for r in i.rates}
    keep = {s.id for s in specs if s.id is not None}
    for rid, r in existing.items():
        if rid not in keep:
            i.rates.remove(r)
    for s in specs:
        if s.id is not None:
            r = existing[s.id]
            r.amount, r.valid_from, r.valid_to = s.amount, s.valid_from, s.valid_to
        else:
            i.rates.append(
                SavingsRate(amount=s.amount, valid_from=s.valid_from, valid_to=s.valid_to)
            )
    db.flush()


def _rates_snapshot(i: Instrument) -> list[dict[str, Any]]:
    return [
        {
            "amount": str(r.amount),
            "from": format_month(r.valid_from),
            "to": format_month(r.valid_to) if r.valid_to else None,
        }
        for r in i.rates
    ]


# --------------------------------------------------------------------------------------
# instruments
# --------------------------------------------------------------------------------------


PersonParam = Annotated[
    int | None, Query(description="Only this person's positions; all positions when left out")
]


def _scope(db: Session, user: CurrentUser, person: int | None) -> int | None:
    if person is None:
        return None
    return get_person(db, user.household_id, person).id


@router.get("", response_model=DepotOut)
def depot(user: CurrentUser, db: DbSession, person: PersonParam = None) -> DepotOut:
    scope = _scope(db, user, person)
    instruments = [_summary(i) for i in load_instruments(db, user.household_id, scope)]
    return DepotOut(
        base_rate=sum(i.current_rate for i in instruments),
        planned_value=sum(i.planned_value for i in instruments),
        paid_in=sum(i.paid_in for i in instruments),
        instruments=instruments,
    )


@router.post("/instruments", response_model=InstrumentDetailOut, status_code=201)
def create_instrument(body: InstrumentIn, user: CurrentUser, db: DbSession) -> InstrumentDetailOut:
    owner = (
        get_person(db, user.household_id, body.person_id)
        if body.person_id is not None
        else own_person(db, user)
    )
    i = Instrument(
        household_id=user.household_id,
        person_id=owner.id,
        kind=InstrumentKind(body.kind),
        name=body.name.strip(),
        isin=body.isin.upper() if body.isin else None,
        expected_return_percent=body.expected_return_percent,
        cost_percent=body.cost_percent,
        entry_fee_percent=body.entry_fee_percent,
        tax_exempt_percent=_default_exempt(body),
        start=body.start,
        start_value=body.start_value,
    )
    i.rates.append(SavingsRate(amount=body.monthly_rate, valid_from=body.start, valid_to=None))
    db.add(i)
    db.flush()
    db.refresh(i)
    audit(
        db,
        user,
        "backfill" if body.start < current_month() else "create",
        "instrument",
        i.id,
        after={**_snapshot(i), "rates": _rates_snapshot(i)},
    )
    return _detail(i)


@router.put("/instruments/{instrument_id}/person", response_model=InstrumentDetailOut)
def change_owner(
    instrument_id: int, body: OwnerChange, user: CurrentUser, db: DbSession
) -> InstrumentDetailOut:
    """Hand a position to another person, for example when it was entered for the wrong one."""
    i = _get(db, user, instrument_id)
    owner = get_person(db, user.household_id, body.person_id)
    before = {"person_id": i.person_id}
    i.person_id = owner.id
    db.flush()
    audit(
        db, user, "owner_change", "instrument", i.id, before=before, after={"person_id": owner.id}
    )
    return _detail(i)


@router.get("/instruments/{instrument_id}", response_model=InstrumentDetailOut)
def get_instrument(instrument_id: int, user: CurrentUser, db: DbSession) -> InstrumentDetailOut:
    return _detail(_get(db, user, instrument_id))


@router.put("/instruments/{instrument_id}", response_model=InstrumentDetailOut)
def update_assumptions(
    instrument_id: int, body: Assumptions, user: CurrentUser, db: DbSession
) -> InstrumentDetailOut:
    """Name, expected return and costs are assumptions, not history, so no reason is needed."""
    i = _get(db, user, instrument_id)
    before = _snapshot(i)
    i.name = body.name.strip()
    i.isin = body.isin.upper() if body.isin else None
    i.expected_return_percent = body.expected_return_percent
    i.cost_percent = body.cost_percent
    i.entry_fee_percent = body.entry_fee_percent
    if body.tax_exempt_percent is not None:
        i.tax_exempt_percent = body.tax_exempt_percent
    db.flush()
    db.refresh(i)
    _check(i)
    audit(db, user, "update", "instrument", i.id, before=before, after=_snapshot(i))
    return _detail(i)


@router.delete("/instruments/{instrument_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_instrument(instrument_id: int, user: CurrentUser, db: DbSession) -> None:
    """Remove a position with its plan data and actual values. Transactions are kept, unlinked."""
    i = _get(db, user, instrument_id)
    audit(
        db,
        user,
        "delete",
        "instrument",
        i.id,
        before={**_snapshot(i), "rates": _rates_snapshot(i)},
    )
    db.execute(delete(ActualValue).where(ActualValue.instrument_id == i.id))
    db.execute(
        update(DepotTransaction)
        .where(DepotTransaction.instrument_id == i.id)
        .values(instrument_id=None)
    )
    db.delete(i)


@router.post("/instruments/{instrument_id}/correct", response_model=InstrumentDetailOut)
def correct_instrument(
    instrument_id: int, body: InstrumentCorrection, user: CurrentUser, db: DbSession
) -> InstrumentDetailOut:
    """Fix start month and start value. Rewrites the plan's base, so a reason is required."""
    i = _get(db, user, instrument_id)
    if any(o.month < body.start for o in i.one_offs):
        raise HTTPException(422, "Es gibt Einmalzahlungen vor dem neuen Startmonat.")
    before = {**_snapshot(i), "rates": _rates_snapshot(i)}
    specs = [s for s in rate_specs(i) if s.valid_to is None or s.valid_to > body.start]
    if specs:
        first = min(specs, key=lambda s: s.valid_from)
        specs = [
            cf.VersionSpec(s.amount, s.frequency, body.start, s.valid_to, s.id) if s is first else s
            for s in specs
        ]
    i.start, i.start_value = body.start, body.start_value
    _sync_rates(db, i, specs)
    db.refresh(i)
    _check(i)
    audit(
        db,
        user,
        "correction",
        "instrument",
        i.id,
        reason=body.reason.strip(),
        before=before,
        after={**_snapshot(i), "rates": _rates_snapshot(i)},
    )
    return _detail(i)


# --------------------------------------------------------------------------------------
# savings rates and one-off payments
# --------------------------------------------------------------------------------------


@router.post("/instruments/{instrument_id}/rate", response_model=InstrumentDetailOut)
def change_rate(
    instrument_id: int, body: RateChange, user: CurrentUser, db: DbSession
) -> InstrumentDetailOut:
    """New monthly savings rate from a month on (0 pauses saving). Later changes are kept."""
    if body.effective_from < current_month():
        raise HTTPException(status.HTTP_409_CONFLICT, LOCKED_MESSAGE)
    i = _get(db, user, instrument_id)
    before = _rates_snapshot(i)
    try:
        specs = cf.apply_change(rate_specs(i), body.effective_from, body.amount, "monthly")
    except ValueError:
        raise HTTPException(422, "Die Änderung liegt vor dem Start der Position.") from None
    _sync_rates(db, i, specs)
    db.refresh(i)
    audit(
        db,
        user,
        "rate_change",
        "instrument",
        i.id,
        before={"rates": before},
        after={"rates": _rates_snapshot(i)},
    )
    return _detail(i)


@router.post("/instruments/{instrument_id}/one-offs", response_model=InstrumentDetailOut)
def add_one_off(
    instrument_id: int, body: OneOffIn, user: CurrentUser, db: DbSession
) -> InstrumentDetailOut:
    if body.amount == 0:
        raise HTTPException(422, "Der Betrag darf nicht 0 sein.")
    if body.month < current_month():
        raise HTTPException(status.HTTP_409_CONFLICT, LOCKED_MESSAGE)
    i = _get(db, user, instrument_id)
    if body.month < i.start:
        raise HTTPException(422, "Die Zahlung liegt vor dem Start der Position.")
    i.one_offs.append(OneOffPayment(month=body.month, amount=body.amount, note=body.note))
    db.flush()
    _check(i)
    audit(
        db,
        user,
        "oneoff_add",
        "instrument",
        i.id,
        after={"month": format_month(body.month), "amount": str(body.amount), "note": body.note},
    )
    db.refresh(i)
    return _detail(i)


@router.delete(
    "/instruments/{instrument_id}/one-offs/{one_off_id}", response_model=InstrumentDetailOut
)
def remove_one_off(
    instrument_id: int, one_off_id: int, user: CurrentUser, db: DbSession
) -> InstrumentDetailOut:
    i = _get(db, user, instrument_id)
    o = next((x for x in i.one_offs if x.id == one_off_id), None)
    if o is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Einmalzahlung nicht gefunden")
    if o.month < current_month():
        raise HTTPException(status.HTTP_409_CONFLICT, LOCKED_MESSAGE)
    snapshot = {"month": format_month(o.month), "amount": str(o.amount), "note": o.note}
    i.one_offs.remove(o)
    db.flush()
    _check(i)
    audit(db, user, "oneoff_remove", "instrument", i.id, before=snapshot)
    db.refresh(i)
    return _detail(i)


# --------------------------------------------------------------------------------------
# projection
# --------------------------------------------------------------------------------------


@router.get("/projection", response_model=ProjectionOut)
def projection(
    user: CurrentUser,
    db: DbSession,
    years: Annotated[
        int, Query(ge=1, le=MAX_YEARS, description="Years after the current month")
    ] = 30,
    start: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")] = None,
    return_shift: Annotated[
        Decimal, Query(ge=-15, le=15, description="Percentage points")
    ] = Decimal(0),
    inflation: Annotated[Decimal, Query(ge=0, le=20, description="Percent per year")] = Decimal(0),
    person: PersonParam = None,
) -> ProjectionOut:
    """Planned development of the depot, from the earliest start (history) into the future."""
    today = current_month()
    scope = _scope(db, user, person)
    instruments = load_instruments(db, user.household_id, scope)
    positions = [to_position(i) for i in instruments]

    earliest = min((p.start for p in positions), default=today)
    first = date(int(start[:4]), int(start[5:]), 1) if start else earliest
    last = add_months(today, years * 12)
    if first > last:
        raise HTTPException(422, "Der Start liegt nach dem Ende der Prognose.")

    shift = return_shift / 100
    try:
        months = dom.project_depot(positions, first, last, shift)
    except dom.DepotError as e:
        raise HTTPException(422, str(e)) from e

    infl = inflation / 100
    # Allowance and church tax are personal, so every owner is taxed with their own settings.
    by_owner: dict[int, list[dom.Position]] = defaultdict(list)
    for i, pos in zip(instruments, positions, strict=True):
        by_owner[i.person_id].append(pos)
    taxes: dict[date, tax_dom.TaxMonth] = {}
    try:
        for owner_id, group in by_owner.items():
            for t in tax_dom.project_tax(group, first, last, tax_config(db, owner_id), shift):
                known = taxes.get(t.month)
                taxes[t.month] = (
                    t
                    if known is None
                    else tax_dom.TaxMonth(
                        t.month, known.vorab_paid + t.vorab_paid, known.sale_tax + t.sale_tax
                    )
                )
    except dom.DepotError as e:
        raise HTTPException(422, str(e)) from e
    shown = scope if scope is not None else own_person(db, user).id
    config = tax_config(db, shown)
    for m in months:  # months without any position still need a (zero) tax row
        taxes.setdefault(m.month, tax_dom.TaxMonth(m.month, Decimal(0), Decimal(0)))

    def real(value: Decimal, month: date) -> float:
        # Today's purchasing power: later months are deflated, past months stay as they are.
        ahead = (month.year - today.year) * 12 + month.month - today.month
        return float(cf.cents(dom.deflate(value, infl, ahead)))

    points = [
        ProjectionPoint(
            month=m.month,
            value=real(m.value, m.month),
            paid_in=float(cf.cents(m.paid_in)),
            deposit=float(cf.cents(m.deposit)),
            fees=float(cf.cents(m.fees)),
            balances=[real(m.balances[p.id], m.month) for p in positions],
            tax_paid=real(taxes[m.month].vorab_paid, m.month),
            tax_on_sale=real(taxes[m.month].sale_tax, m.month),
            net_value=real(m.value - taxes[m.month].total, m.month),
        )
        for m in months
    ]
    return ProjectionOut(
        first=first,
        last=last,
        return_shift_percent=float(return_shift),
        inflation_percent=float(inflation),
        tax_rate_percent=round(float(tax_dom.tax_rate(config.church_tax)) * 100, 3),
        base_rate=float(dom.base_rate(positions, today)),
        instruments=[
            ProjectionInstrument(id=i.id, name=i.name, kind=i.kind.value) for i in instruments
        ],
        points=points,
    )
