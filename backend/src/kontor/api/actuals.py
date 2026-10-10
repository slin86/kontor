"""Actual depot data: month-end values, transactions, broker CSV import and plan vs. actual."""

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from kontor.api.deps import CurrentUser, DbSession
from kontor.core.clock import current_month, format_month, month_range
from kontor.domain import broker_csv
from kontor.domain import cashflow as cf
from kontor.domain import depot as dom
from kontor.models import ActualValue, DepotTransaction, Instrument
from kontor.schemas.actuals import (
    ComparisonOut,
    ComparisonPoint,
    ImportIn,
    ImportPreview,
    ImportResult,
    ImportRow,
    InstrumentComparison,
    TransactionIn,
    TransactionOut,
    UnmatchedIsin,
    ValueIn,
    ValueOut,
)
from kontor.services.audit import record as audit
from kontor.services.depot_book import load_instruments, to_position
from kontor.services.people import get_person, own_person

router = APIRouter(prefix="/api/actuals", tags=["actuals"])


PersonParam = Annotated[
    int | None, Query(description="Only this person's data; the whole household when left out")
]


def _scope(db: Session, user: CurrentUser, person: int | None) -> int | None:
    return get_person(db, user.household_id, person).id if person is not None else None


def _instrument(db: Session, user: CurrentUser, instrument_id: int) -> Instrument:
    i = db.get(Instrument, instrument_id)
    if i is None or i.household_id != user.household_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Position nicht gefunden")
    return i


def _value_out(v: ActualValue) -> ValueOut:
    return ValueOut(id=v.id, instrument_id=v.instrument_id, month=v.month, value=float(v.value))


def _tx_out(t: DepotTransaction) -> TransactionOut:
    return TransactionOut(
        id=t.id,
        instrument_id=t.instrument_id,
        day=t.day.isoformat(),
        kind=t.kind,
        amount=float(t.amount),
        fee=float(t.fee),
        shares=float(t.shares) if t.shares is not None else None,
        isin=t.isin,
        name=t.name,
        source=t.source,
    )


# --------------------------------------------------------------------------------------
# month-end values
# --------------------------------------------------------------------------------------


@router.get("/values", response_model=list[ValueOut])
def list_values(
    user: CurrentUser, db: DbSession, instrument_id: int | None = None, person: PersonParam = None
) -> list[ValueOut]:
    scope = _scope(db, user, person)
    stmt = (
        select(ActualValue)
        .join(Instrument, Instrument.id == ActualValue.instrument_id)
        .where(Instrument.household_id == user.household_id)
        .order_by(ActualValue.month.desc())
    )
    if scope is not None:
        stmt = stmt.where(Instrument.person_id == scope)
    if instrument_id is not None:
        stmt = stmt.where(ActualValue.instrument_id == instrument_id)
    return [_value_out(v) for v in db.scalars(stmt)]


@router.put("/values", response_model=ValueOut)
def set_value(body: ValueIn, user: CurrentUser, db: DbSession) -> ValueOut:
    """Record what a position was worth at the end of a month.

    Overwriting a value of a closed month is a correction and needs a reason.
    """
    today = current_month()
    if body.month > today:
        raise HTTPException(422, "Ist-Werte gibt es nur bis zum aktuellen Monat.")
    i = _instrument(db, user, body.instrument_id)
    if body.month < i.start:
        raise HTTPException(422, "Der Monat liegt vor dem Start der Position.")
    existing = db.scalar(
        select(ActualValue).where(
            ActualValue.instrument_id == i.id, ActualValue.month == body.month
        )
    )
    if existing is None:
        v = ActualValue(instrument_id=i.id, month=body.month, value=body.value)
        db.add(v)
        db.flush()
        audit(
            db,
            user,
            "actual_set",
            "instrument",
            i.id,
            after={"month": format_month(body.month), "value": str(body.value)},
        )
        return _value_out(v)

    before = {"month": format_month(body.month), "value": str(existing.value)}
    closed = body.month < today
    reason = (body.reason or "").strip()
    if closed and len(reason) < 3:
        raise HTTPException(422, "Für einen abgeschlossenen Monat ist eine Begründung nötig.")
    existing.value = body.value
    db.flush()
    audit(
        db,
        user,
        "correction" if closed else "actual_set",
        "instrument",
        i.id,
        reason=reason or None,
        before=before,
        after={"month": format_month(body.month), "value": str(body.value)},
    )
    return _value_out(existing)


@router.delete("/values/{value_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_value(
    value_id: int,
    user: CurrentUser,
    db: DbSession,
    reason: Annotated[str | None, Query(max_length=500)] = None,
) -> None:
    v = db.get(ActualValue, value_id)
    if v is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Wert nicht gefunden")
    i = _instrument(db, user, v.instrument_id)
    closed = v.month < current_month()
    if closed and len((reason or "").strip()) < 3:
        raise HTTPException(422, "Für einen abgeschlossenen Monat ist eine Begründung nötig.")
    audit(
        db,
        user,
        "actual_remove",
        "instrument",
        i.id,
        reason=(reason or "").strip() or None,
        before={"month": format_month(v.month), "value": str(v.value)},
    )
    db.delete(v)


# --------------------------------------------------------------------------------------
# transactions
# --------------------------------------------------------------------------------------


@router.get("/transactions", response_model=list[TransactionOut])
def list_transactions(
    user: CurrentUser,
    db: DbSession,
    instrument_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    person: PersonParam = None,
) -> list[TransactionOut]:
    scope = _scope(db, user, person)
    stmt = (
        select(DepotTransaction)
        .where(DepotTransaction.household_id == user.household_id)
        .order_by(DepotTransaction.day.desc(), DepotTransaction.id.desc())
        .limit(limit)
    )
    if scope is not None:
        stmt = stmt.join(Instrument, Instrument.id == DepotTransaction.instrument_id).where(
            Instrument.person_id == scope
        )
    if instrument_id is not None:
        stmt = stmt.where(DepotTransaction.instrument_id == instrument_id)
    return [_tx_out(t) for t in db.scalars(stmt)]


@router.post("/transactions", response_model=TransactionOut, status_code=201)
def add_transaction(body: TransactionIn, user: CurrentUser, db: DbSession) -> TransactionOut:
    i = _instrument(db, user, body.instrument_id)
    day = date.fromisoformat(body.day)
    if date(day.year, day.month, 1) > current_month():
        raise HTTPException(422, "Das Datum liegt in der Zukunft.")
    t = DepotTransaction(
        household_id=user.household_id,
        instrument_id=i.id,
        day=day,
        kind=body.kind,
        amount=body.amount,
        fee=body.fee,
        isin=i.isin,
        name=i.name,
        source="manual",
    )
    db.add(t)
    db.flush()
    audit(
        db,
        user,
        "transaction_add",
        "instrument",
        i.id,
        after={"day": body.day, "kind": body.kind, "amount": str(body.amount)},
    )
    return _tx_out(t)


@router.delete("/transactions/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(transaction_id: int, user: CurrentUser, db: DbSession) -> None:
    t = db.get(DepotTransaction, transaction_id)
    if t is None or t.household_id != user.household_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transaktion nicht gefunden")
    audit(
        db,
        user,
        "transaction_remove",
        "instrument",
        t.instrument_id or 0,
        before={"day": t.day.isoformat(), "kind": t.kind, "amount": str(t.amount)},
    )
    db.delete(t)


# --------------------------------------------------------------------------------------
# CSV import
# --------------------------------------------------------------------------------------


def _parse(body: ImportIn) -> broker_csv.ParseResult:
    try:
        return broker_csv.parse_broker_csv(body.csv)
    except broker_csv.CsvError as e:
        raise HTTPException(422, str(e)) from e


def resolve_instruments(
    db: Session, user: CurrentUser, mapping: dict[str, int], person: int | None
) -> tuple[dict[str, int], set[str]]:
    """ISIN -> instrument id: the person's positions, overridden by the user's choice.

    Several people may hold the same fund, so a file is always matched against one person: the
    given one, or the signed-in user's own.
    """
    owner = _scope(db, user, person) or own_person(db, user).id
    positions = load_instruments(db, user.household_id, owner)
    by_isin = {i.isin: i.id for i in positions if i.isin is not None}
    own = {i.id for i in positions}
    for isin, instrument_id in mapping.items():
        if instrument_id not in own:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Position nicht gefunden")
        by_isin[isin.upper()] = instrument_id
    existing = set(
        db.scalars(
            select(DepotTransaction.external_id).where(
                DepotTransaction.household_id == user.household_id,
                DepotTransaction.external_id.is_not(None),
            )
        )
    )
    return by_isin, {e for e in existing if e}


@router.post("/import/preview", response_model=ImportPreview)
def import_preview(body: ImportIn, user: CurrentUser, db: DbSession) -> ImportPreview:
    """Parse the file and show what would happen, without writing anything."""
    parsed = _parse(body)
    by_isin, existing = resolve_instruments(db, user, body.mapping, body.person_id)
    rows: list[ImportRow] = []
    unmatched: dict[str | None, UnmatchedIsin] = {}
    for r in parsed.rows:
        target = by_isin.get(r.isin) if r.isin else None
        rows.append(
            ImportRow(
                line=r.line,
                day=r.day.isoformat(),
                kind=r.kind,
                amount=float(r.amount),
                fee=float(r.fee),
                shares=float(r.shares) if r.shares is not None else None,
                isin=r.isin,
                name=r.name,
                instrument_id=target,
                duplicate=r.external_id in existing,
            )
        )
        if target is None:
            entry = unmatched.setdefault(r.isin, UnmatchedIsin(isin=r.isin, name=r.name, count=0))
            entry.count += 1
    dup = sum(1 for r in rows if r.duplicate)
    return ImportPreview(
        rows=rows,
        skipped=parsed.skipped,
        errors=parsed.errors,
        unmatched=list(unmatched.values()),
        new_count=sum(1 for r in rows if not r.duplicate and r.instrument_id is not None),
        duplicate_count=dup,
    )


@router.post("/import", response_model=ImportResult)
def import_transactions(body: ImportIn, user: CurrentUser, db: DbSession) -> ImportResult:
    """Store the rows that belong to a position. Rows seen before (same id) are skipped."""
    parsed = _parse(body)
    by_isin, existing = resolve_instruments(db, user, body.mapping, body.person_id)
    imported = duplicates = unmatched = 0
    per_instrument: dict[int, int] = defaultdict(int)
    for r in parsed.rows:
        target = by_isin.get(r.isin) if r.isin else None
        if target is None:
            unmatched += 1
            continue
        if r.external_id in existing:
            duplicates += 1
            continue
        existing.add(r.external_id)
        db.add(
            DepotTransaction(
                household_id=user.household_id,
                instrument_id=target,
                day=r.day,
                kind=r.kind,
                amount=r.amount,
                fee=r.fee,
                shares=r.shares,
                isin=r.isin,
                name=r.name,
                source="csv",
                external_id=r.external_id,
            )
        )
        per_instrument[target] += 1
        imported += 1
    db.flush()
    for instrument_id, count in per_instrument.items():
        audit(db, user, "import", "instrument", instrument_id, after={"transactions": count})
    return ImportResult(imported=imported, duplicates=duplicates, unmatched=unmatched)


# --------------------------------------------------------------------------------------
# plan vs. actual
# --------------------------------------------------------------------------------------


@router.get("/compare", response_model=ComparisonOut)
def compare(user: CurrentUser, db: DbSession, person: PersonParam = None) -> ComparisonOut:
    """Plan against reality from the earliest start up to the current month."""
    today = current_month()
    scope = _scope(db, user, person)
    instruments = load_instruments(db, user.household_id, scope)
    shown = {i.id for i in instruments}
    positions = [to_position(i) for i in instruments]
    first = min((p.start for p in positions), default=today)
    months = month_range(first, today)
    planned = {m.month: m for m in dom.project_depot(positions, first, today)}

    values: dict[tuple[int, date], Decimal] = {}
    for v in db.scalars(
        select(ActualValue)
        .join(Instrument, Instrument.id == ActualValue.instrument_id)
        .where(Instrument.household_id == user.household_id)
    ):
        if v.instrument_id in shown:
            values[(v.instrument_id, v.month)] = Decimal(v.value)
    valued = {iid for iid, _ in values}

    net_by_month: dict[tuple[int, date], Decimal] = defaultdict(Decimal)
    traded: set[int] = set()
    for t in db.scalars(
        select(DepotTransaction).where(
            DepotTransaction.household_id == user.household_id,
            DepotTransaction.instrument_id.is_not(None),
            DepotTransaction.kind.in_(("buy", "sell")),
        )
    ):
        assert t.instrument_id is not None
        if t.instrument_id not in shown:
            continue
        traded.add(t.instrument_id)
        sign = 1 if t.kind == "buy" else -1
        net_by_month[(t.instrument_id, date(t.day.year, t.day.month, 1))] += sign * Decimal(
            t.amount
        )

    per_position = {p.id: {r.month: r for r in dom.project_position(p, today)} for p in positions}
    points: list[ComparisonPoint] = []
    for m in months:
        month_plan = planned[m]
        tracked_plan = sum((month_plan.balances[i] for i in valued), Decimal(0))
        complete = bool(valued) and all((i, m) in values for i in valued)
        actual = sum((values[(i, m)] for i in valued), Decimal(0)) if complete else None
        plan_deposit = actual_deposit = None
        if traded:
            plan_deposit = sum(
                (per_position[i][m].deposit for i in traded if m in per_position[i]), Decimal(0)
            )
            actual_deposit = sum((net_by_month.get((i, m), Decimal(0)) for i in traded), Decimal(0))
        points.append(
            ComparisonPoint(
                month=m,
                planned_total=float(cf.cents(month_plan.value)),
                planned_tracked=float(cf.cents(tracked_plan)),
                actual=float(cf.cents(actual)) if actual is not None else None,
                planned_deposit=float(cf.cents(plan_deposit)) if plan_deposit is not None else None,
                actual_deposit=(
                    float(cf.cents(actual_deposit)) if actual_deposit is not None else None
                ),
            )
        )

    rows: list[InstrumentComparison] = []
    for i, p in zip(instruments, positions, strict=True):
        plan_rows = per_position[p.id]
        latest = max((m for (iid, m) in values if iid == i.id), default=None)
        plan_at = plan_rows[latest].balance if latest in plan_rows else Decimal(0)
        actual_value = values[(i.id, latest)] if latest else None
        deviation = actual_value - plan_at if actual_value is not None else None
        percent = (
            float(cf.cents(deviation / plan_at * 100))
            if deviation is not None and plan_at > 0
            else None
        )
        last_plan = plan_rows.get(today)
        shown_plan = plan_at if latest else (last_plan.balance if last_plan else Decimal(0))
        net = sum((v for (iid, _), v in net_by_month.items() if iid == i.id), Decimal(0))
        rows.append(
            InstrumentComparison(
                id=i.id,
                name=i.name,
                planned_value=float(cf.cents(shown_plan)),
                actual_value=float(actual_value) if actual_value is not None else None,
                actual_month=latest,
                deviation=float(cf.cents(deviation)) if deviation is not None else None,
                deviation_percent=percent,
                planned_paid_in=float(last_plan.paid_in) if last_plan else 0.0,
                actual_net_invested=float(net) if i.id in traded else None,
            )
        )
    return ComparisonOut(first=first, last=today, instruments=rows, points=points)
