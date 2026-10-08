"""Financings: loans and building-society contracts with dated events and audited corrections."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy.orm import Session

from kontor.api.deps import CurrentUser, DbSession
from kontor.core.clock import current_month, format_month, parse_month
from kontor.domain.financing import FinancingError, Schedule
from kontor.models import Financing, FinancingEvent, FinancingKind
from kontor.schemas.financing import (
    BausparIn,
    CreditLineIn,
    EventIn,
    EventOut,
    FinancingCorrection,
    FinancingDetailOut,
    FinancingIn,
    FinancingOut,
    LoanIn,
    ScheduleRowOut,
)
from kontor.services.audit import record as audit
from kontor.services.financing_book import (
    all_payouts,
    load_financings,
    schedule_for,
    to_params,
    validate,
)
from kontor.services.people import get_person, own_person

router = APIRouter(prefix="/api/financings", tags=["financings"])

PERCENT = Decimal(100)

LOCKED_EVENT_MESSAGE = (
    "Dieser Monat ist abgeschlossen. Ereignisse in der Vergangenheit lassen sich nicht ändern; "
    "korrigiere stattdessen die Vertragsdaten mit einer Begründung."
)


def _get(db: Session, user: CurrentUser, financing_id: int) -> Financing:
    f = db.get(Financing, financing_id)
    if f is None or f.household_id != user.household_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Finanzierung nicht gefunden")
    return f


def _schedule(f: Financing) -> Schedule:
    try:
        return schedule_for(f)
    except FinancingError as e:
        raise HTTPException(422, str(e)) from e


def _loan_start(f: Financing) -> str:
    """First month in which events make sense: loan start, or Bauspar allocation."""
    key = "allocation" if f.kind == FinancingKind.BUILDING_SAVINGS else "start"
    return str(f.params[key])


def _summary(f: Financing, schedule: Schedule) -> FinancingOut:
    today = current_month()
    rows = schedule.rows
    this = schedule.at(today)
    before = [r for r in rows if r.month < today]
    loan_rows = [r for r in rows if r.phase == "loan"]

    if today < schedule.first_month:
        phase = "not_started"
    elif today >= schedule.end_month:
        phase = "finished"
    else:
        phase = this.phase if this else "loan"

    remaining_debt: float | None = None
    if loan_rows:
        paid_before = [r for r in loan_rows if r.month < today]
        if paid_before:
            remaining_debt = float(paid_before[-1].balance)
        else:
            first = loan_rows[0]
            remaining_debt = float(first.balance + first.principal - first.drawn)
    prefinanced = f.kind == FinancingKind.BUILDING_SAVINGS and (
        f.params.get("prefinance_rate_percent") is not None
    )
    if f.kind == FinancingKind.BUILDING_SAVINGS and phase in ("not_started", "saving"):
        # the Bauspar loan only exists after allocation; an advance loan is paid out on day 1
        paid_out = (
            sum((a for m, a in all_payouts(f) if m <= today), Decimal(0))
            if f.params.get("payouts")
            else Decimal(f.params["contract_sum"])
        )
        remaining_debt = float(paid_out) if prefinanced and phase == "saving" else None

    saved: float | None = None
    if f.kind == FinancingKind.BUILDING_SAVINGS:
        saving_rows = [r for r in before if r.phase == "saving"]
        saved = float(saving_rows[-1].balance) if saving_rows else 0.0

    credit_limit: float | None = None
    available: float | None = None
    if f.kind == FinancingKind.CREDIT_LINE:
        credit_limit = float(Decimal(f.params["limit"]))
        used = remaining_debt if remaining_debt is not None else 0.0
        available = max(credit_limit - used, 0.0)

    return FinancingOut(
        id=f.id,
        person_id=f.person_id,
        kind=f.kind.value,
        name=f.name,
        purpose=f.purpose,
        start=schedule.first_month,
        end_month=schedule.end_month,
        regular_payment=float(schedule.regular_payment),
        payment_this_month=float(this.outflow) if this else 0.0,
        phase=phase,
        remaining_debt=remaining_debt,
        saved=saved,
        prefinanced=prefinanced,
        total_interest=float(sum(r.interest for r in rows)),
        remaining_interest=float(sum(r.interest for r in rows if r.month >= today)),
        credit_limit=credit_limit,
        available=available,
    )


def _event_out(e: FinancingEvent) -> EventOut:
    value = Decimal(e.value) * PERCENT if e.kind == "rate_change" else Decimal(e.value)
    return EventOut(
        id=e.id,
        month=e.month,
        kind=e.kind,
        value=float(value),
        locked=e.month < current_month(),
    )


def _detail(f: Financing) -> FinancingDetailOut:
    schedule = _schedule(f)
    base = _summary(f, schedule)
    return FinancingDetailOut(
        **base.model_dump(),
        input={"kind": f.kind.value, "name": f.name, "purpose": f.purpose, **f.params},
        events=[_event_out(e) for e in f.events],
        schedule=[
            ScheduleRowOut(
                month=r.month,
                interest=float(r.interest),
                principal=float(r.principal),
                saving=float(r.saving),
                fee=float(r.fee),
                balance=float(r.balance),
                phase=r.phase,
                special=float(r.special),
                drawn=float(r.drawn),
            )
            for r in schedule.rows
        ],
    )


def _snapshot(f: Financing) -> dict[str, Any]:
    return {"name": f.name, "purpose": f.purpose, **f.params}


def _validated(body: LoanIn | BausparIn | CreditLineIn) -> None:
    try:
        validate(body)
    except FinancingError as e:
        raise HTTPException(422, str(e)) from e


PersonParam = Annotated[
    int | None, Query(description="Only this person's financings; all when left out")
]


@router.get("", response_model=list[FinancingOut])
def list_financings(
    user: CurrentUser, db: DbSession, person: PersonParam = None
) -> list[FinancingOut]:
    scope = get_person(db, user.household_id, person).id if person is not None else None
    out: list[FinancingOut] = []
    for f in load_financings(db, user.household_id, scope):
        out.append(_summary(f, _schedule(f)))
    return out


@router.post("", response_model=FinancingDetailOut, status_code=status.HTTP_201_CREATED)
def create_financing(
    body: FinancingIn, user: CurrentUser, db: DbSession, person: PersonParam = None
) -> FinancingDetailOut:
    _validated(body)
    owner = (
        get_person(db, user.household_id, person) if person is not None else own_person(db, user)
    )
    f = Financing(
        household_id=user.household_id,
        person_id=owner.id,
        kind=FinancingKind(body.kind),
        name=body.name.strip(),
        purpose=body.purpose if isinstance(body, LoanIn) else None,
        params=to_params(body),
    )
    db.add(f)
    db.flush()
    db.refresh(f)
    audit(
        db,
        user,
        "backfill" if body.start < current_month() else "create",
        "financing",
        f.id,
        after=_snapshot(f),
    )
    return _detail(f)


@router.get("/{financing_id}", response_model=FinancingDetailOut)
def get_financing(financing_id: int, user: CurrentUser, db: DbSession) -> FinancingDetailOut:
    return _detail(_get(db, user, financing_id))


@router.put("/{financing_id}/person", response_model=FinancingDetailOut)
def change_owner(
    financing_id: int, person: Annotated[int, Query()], user: CurrentUser, db: DbSession
) -> FinancingDetailOut:
    f = _get(db, user, financing_id)
    owner = get_person(db, user.household_id, person)
    before = f.person_id
    f.person_id = owner.id
    audit(
        db,
        user,
        "update",
        "financing",
        f.id,
        before={"person_id": before},
        after={"person_id": owner.id},
    )
    return _detail(f)


@router.delete("/{financing_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_financing(financing_id: int, user: CurrentUser, db: DbSession) -> None:
    """Remove a contract entered by mistake. The audit log keeps its last state."""
    f = _get(db, user, financing_id)
    audit(db, user, "delete", "financing", f.id, before=_snapshot(f))
    db.delete(f)


@router.post("/{financing_id}/correct", response_model=FinancingDetailOut)
def correct_financing(
    financing_id: int, body: FinancingCorrection, user: CurrentUser, db: DbSession
) -> FinancingDetailOut:
    """Replace the contract data. Changes the whole schedule, so a reason is required."""
    f = _get(db, user, financing_id)
    if body.data.kind != f.kind.value:
        raise HTTPException(422, "Die Art der Finanzierung lässt sich nicht ändern.")
    before = _snapshot(f)
    f.name = body.data.name.strip()
    f.purpose = body.data.purpose if isinstance(body.data, LoanIn) else None
    f.params = to_params(body.data)
    db.flush()
    db.refresh(f)
    _schedule(f)  # rejects data that no longer works together with the existing events
    audit(
        db,
        user,
        "correction",
        "financing",
        f.id,
        reason=body.reason.strip(),
        before=before,
        after=_snapshot(f),
    )
    return _detail(f)


def _check_payout(f: Financing, month: date, amount: Decimal) -> None:
    """A further payout of the advance loan has to fit between contract start and allocation."""
    if f.kind != FinancingKind.BUILDING_SAVINGS or f.params.get("prefinance_rate_percent") is None:
        raise HTTPException(422, "Auszahlungen gibt es nur bei einer Bausparfinanzierung.")
    if not f.params.get("payouts"):
        raise HTTPException(
            422,
            "Dieser Vertrag zahlt die ganze Summe am ersten Tag aus. Trage die einzelnen "
            "Auszahlungen unter „Vertragsdaten korrigieren“ ein.",
        )
    if month < parse_month(str(f.params["start"])) or month >= parse_month(
        str(f.params["allocation"])
    ):
        raise HTTPException(
            422, "Die Auszahlung muss zwischen Vertragsbeginn und Zuteilung liegen."
        )
    total = sum((a for _, a in all_payouts(f)), Decimal(0))
    if total + amount > Decimal(f.params["contract_sum"]):
        raise HTTPException(422, "Die Auszahlungen dürfen die Darlehenssumme nicht übersteigen.")


@router.post("/{financing_id}/events", response_model=FinancingDetailOut)
def add_event(
    financing_id: int, body: EventIn, user: CurrentUser, db: DbSession
) -> FinancingDetailOut:
    if body.month < current_month():
        raise HTTPException(status.HTTP_409_CONFLICT, LOCKED_EVENT_MESSAGE)
    f = _get(db, user, financing_id)
    if body.kind == "payout":
        _check_payout(f, body.month, body.value)
    elif body.month < parse_month(_loan_start(f)):
        raise HTTPException(422, "Das Ereignis liegt vor dem Beginn der Darlehensphase.")
    if body.kind == "rate_change" and body.value > 30:
        raise HTTPException(422, "Der Zins darf höchstens 30 % betragen.")

    value = body.value / PERCENT if body.kind == "rate_change" else body.value
    event = FinancingEvent(month=body.month, kind=body.kind, value=value)
    f.events.append(event)
    db.flush()
    schedule = _schedule(f)
    if body.kind != "payout" and body.month >= schedule.end_month:
        raise HTTPException(422, "Die Finanzierung ist zu diesem Zeitpunkt bereits abbezahlt.")
    audit(
        db,
        user,
        "event_add",
        "financing",
        f.id,
        after={"month": format_month(body.month), "kind": body.kind, "value": str(body.value)},
    )
    db.refresh(f)
    return _detail(f)


@router.delete("/{financing_id}/events/{event_id}", response_model=FinancingDetailOut)
def remove_event(
    financing_id: int, event_id: int, user: CurrentUser, db: DbSession
) -> FinancingDetailOut:
    f = _get(db, user, financing_id)
    event = next((e for e in f.events if e.id == event_id), None)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ereignis nicht gefunden")
    if event.month < current_month():
        raise HTTPException(status.HTTP_409_CONFLICT, LOCKED_EVENT_MESSAGE)
    snapshot = {"month": format_month(event.month), "kind": event.kind, "value": str(event.value)}
    f.events.remove(event)
    db.flush()
    _schedule(f)
    audit(db, user, "event_remove", "financing", f.id, before=snapshot)
    db.refresh(f)
    return _detail(f)
