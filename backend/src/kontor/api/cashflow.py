"""Categories and cashflow: items with effective-dated versions, summaries, Sankey, audit log."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from kontor.api.deps import CurrentUser, DbSession
from kontor.core.clock import current_month, month_range, parse_month
from kontor.domain import cashflow as dom
from kontor.models import (
    AuditLog,
    CashflowItem,
    CashflowVersion,
    Category,
    User,
)
from kontor.schemas.cashflow import (
    AuditOut,
    CategoryIn,
    CategoryOut,
    FinancingFlowOut,
    GroupOut,
    ItemChange,
    ItemCreate,
    ItemEnd,
    ItemOut,
    ItemRename,
    SankeyLinkOut,
    SankeyNodeOut,
    SankeyOut,
    SeriesPoint,
    SummaryOut,
    VersionCorrection,
    VersionOut,
)
from kontor.services.audit import record as audit_record
from kontor.services.depot_book import load_instruments
from kontor.services.financing_book import load_book, load_financings

router = APIRouter(prefix="/api", tags=["cashflow"])

LOCKED_MESSAGE = (
    "Dieser Monat ist abgeschlossen. "
    "Änderungen an der Vergangenheit sind nur als Korrektur mit Begründung möglich."
)


def _month_query(value: str | None) -> date:
    if value is None:
        return current_month()
    try:
        return parse_month(value)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


MonthParam = Annotated[str | None, Query(alias="month", pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]


# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------


_audit = audit_record


def _version_snapshot(v: CashflowVersion) -> dict[str, Any]:
    return {
        "amount": str(dom.cents(v.amount)),
        "frequency": v.frequency.value,
        "valid_from": v.valid_from.isoformat(),
        "valid_to": v.valid_to.isoformat() if v.valid_to else None,
    }


def _categories(db: Session, household_id: int) -> list[Category]:
    return list(
        db.scalars(
            select(Category)
            .where(Category.household_id == household_id)
            .order_by(Category.sort_order, Category.id)
        )
    )


def _category_or_422(db: Session, household_id: int, category_id: int) -> Category:
    cat = db.get(Category, category_id)
    if cat is None or cat.household_id != household_id:
        raise HTTPException(422, "Unbekannte Kategorie")
    return cat


def _items(db: Session, household_id: int) -> list[CashflowItem]:
    return list(
        db.scalars(
            select(CashflowItem)
            .where(CashflowItem.household_id == household_id)
            .options(selectinload(CashflowItem.versions), selectinload(CashflowItem.category))
            .order_by(CashflowItem.name)
        )
    )


def _item_or_404(db: Session, user: User, item_id: int) -> CashflowItem:
    item = db.get(CashflowItem, item_id)
    if item is None or item.household_id != user.household_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Posten nicht gefunden")
    return item


def _specs(item: CashflowItem) -> list[dom.VersionSpec]:
    return [
        dom.VersionSpec(v.amount, v.frequency.value, v.valid_from, v.valid_to, v.id)
        for v in item.versions
    ]


def _sync_versions(db: Session, item: CashflowItem, specs: list[dom.VersionSpec]) -> None:
    """Persist the version list computed by the domain layer."""
    from kontor.models import Frequency

    existing = {v.id: v for v in item.versions}
    keep_ids = {s.id for s in specs if s.id is not None}
    for vid, v in existing.items():
        if vid not in keep_ids:
            item.versions.remove(v)
    for s in specs:
        if s.id is not None:
            v = existing[s.id]
            v.amount, v.frequency = s.amount, Frequency(s.frequency)
            v.valid_from, v.valid_to = s.valid_from, s.valid_to
        else:
            item.versions.append(
                CashflowVersion(
                    amount=s.amount,
                    frequency=Frequency(s.frequency),
                    valid_from=s.valid_from,
                    valid_to=s.valid_to,
                )
            )
    db.flush()


def _version_out(v: CashflowVersion) -> VersionOut:
    return VersionOut(
        id=v.id,
        amount=float(v.amount),
        frequency=v.frequency,
        monthly=float(dom.cents(dom.monthly_amount(v.amount, v.frequency.value))),
        valid_from=v.valid_from,
        valid_to=v.valid_to,
        locked=v.valid_from < current_month(),
    )


def _item_out(item: CashflowItem, month: date) -> ItemOut:
    active = next(
        (
            v
            for v in item.versions
            if v.valid_from <= month and (v.valid_to is None or month < v.valid_to)
        ),
        None,
    )
    return ItemOut(
        id=item.id,
        name=item.name,
        category_id=item.category_id,
        category_name=item.category.name,
        kind=item.category.kind,
        active=_version_out(active) if active else None,
        versions=[_version_out(v) for v in item.versions],
    )


def _active_items(items: list[CashflowItem], month: date) -> list[dom.ActiveItem]:
    out: list[dom.ActiveItem] = []
    for item in items:
        spec = dom.active_version(_specs(item), month)
        if spec is not None:
            out.append(
                dom.ActiveItem(
                    item.id,
                    item.name,
                    item.category_id,
                    dom.monthly_amount(spec.amount, spec.frequency),
                )
            )
    return out


def _category_infos(cats: list[Category]) -> list[dom.CategoryInfo]:
    return [dom.CategoryInfo(c.id, c.name, c.kind.value, c.parent_id) for c in cats]


def _require_open(effective: date) -> None:
    if effective < current_month():
        raise HTTPException(status.HTTP_409_CONFLICT, LOCKED_MESSAGE)


# --------------------------------------------------------------------------------------
# categories
# --------------------------------------------------------------------------------------


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(user: CurrentUser, db: DbSession) -> list[CategoryOut]:
    return [
        CategoryOut(id=c.id, name=c.name, kind=c.kind, parent_id=c.parent_id)
        for c in _categories(db, user.household_id)
    ]


@router.post("/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(body: CategoryIn, user: CurrentUser, db: DbSession) -> CategoryOut:
    if body.parent_id is not None:
        parent = _category_or_422(db, user.household_id, body.parent_id)
        if parent.parent_id is not None:
            raise HTTPException(422, "Kategorien haben höchstens zwei Ebenen")
        if parent.kind != body.kind:
            raise HTTPException(422, "Unterkategorie und Oberkategorie müssen dieselbe Art haben")
    cat = Category(
        household_id=user.household_id,
        parent_id=body.parent_id,
        name=body.name.strip(),
        kind=body.kind,
        sort_order=10_000,
    )
    db.add(cat)
    db.flush()
    _audit(db, user, "create", "category", cat.id, after={"name": cat.name})
    return CategoryOut(id=cat.id, name=cat.name, kind=cat.kind, parent_id=cat.parent_id)


# --------------------------------------------------------------------------------------
# items
# --------------------------------------------------------------------------------------


@router.get("/cashflow/items", response_model=list[ItemOut])
def list_items(
    user: CurrentUser,
    db: DbSession,
    month: MonthParam = None,
    include_inactive: bool = False,
) -> list[ItemOut]:
    m = _month_query(month)
    out = [_item_out(i, m) for i in _items(db, user.household_id)]
    return out if include_inactive else [i for i in out if i.active is not None]


@router.post("/cashflow/items", response_model=ItemOut, status_code=status.HTTP_201_CREATED)
def create_item(body: ItemCreate, user: CurrentUser, db: DbSession) -> ItemOut:
    _category_or_422(db, user.household_id, body.category_id)
    item = CashflowItem(
        household_id=user.household_id, category_id=body.category_id, name=body.name.strip()
    )
    item.versions.append(
        CashflowVersion(amount=body.amount, frequency=body.frequency, valid_from=body.valid_from)
    )
    db.add(item)
    db.flush()
    db.refresh(item)
    _audit(
        db,
        user,
        "backfill" if body.valid_from < current_month() else "create",
        "cashflow_item",
        item.id,
        after={"name": item.name, **_version_snapshot(item.versions[0])},
    )
    return _item_out(item, body.valid_from)


@router.patch("/cashflow/items/{item_id}", response_model=ItemOut)
def rename_item(item_id: int, body: ItemRename, user: CurrentUser, db: DbSession) -> ItemOut:
    item = _item_or_404(db, user, item_id)
    before = {"name": item.name, "category_id": item.category_id}
    if body.category_id is not None:
        _category_or_422(db, user.household_id, body.category_id)
        item.category_id = body.category_id
    if body.name is not None:
        item.name = body.name.strip()
    db.flush()
    db.refresh(item)
    _audit(
        db,
        user,
        "update",
        "cashflow_item",
        item.id,
        before=before,
        after={"name": item.name, "category_id": item.category_id},
    )
    return _item_out(item, current_month())


@router.post("/cashflow/items/{item_id}/change", response_model=ItemOut)
def change_item(item_id: int, body: ItemChange, user: CurrentUser, db: DbSession) -> ItemOut:
    """New amount from ``effective_from`` on. Only the current month or later is allowed."""
    _require_open(body.effective_from)
    item = _item_or_404(db, user, item_id)
    before = [_version_snapshot(v) for v in item.versions]
    try:
        specs = dom.apply_change(
            _specs(item), body.effective_from, body.amount, body.frequency.value
        )
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    _sync_versions(db, item, specs)
    db.refresh(item)
    _audit(
        db,
        user,
        "change",
        "cashflow_item",
        item.id,
        before={"versions": before},
        after={"versions": [_version_snapshot(v) for v in item.versions]},
    )
    return _item_out(item, body.effective_from)


@router.post("/cashflow/items/{item_id}/end", response_model=ItemOut)
def end_item(item_id: int, body: ItemEnd, user: CurrentUser, db: DbSession) -> ItemOut:
    _require_open(body.end_from)
    item = _item_or_404(db, user, item_id)
    before = [_version_snapshot(v) for v in item.versions]
    try:
        specs = dom.end_item(_specs(item), body.end_from)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    _sync_versions(db, item, specs)
    db.refresh(item)
    _audit(
        db,
        user,
        "end",
        "cashflow_item",
        item.id,
        before={"versions": before},
        after={"versions": [_version_snapshot(v) for v in item.versions]},
    )
    return _item_out(item, body.end_from)


@router.post("/cashflow/versions/{version_id}/correct", response_model=ItemOut)
def correct_version(
    version_id: int, body: VersionCorrection, user: CurrentUser, db: DbSession
) -> ItemOut:
    """Fix the amount of a version in place, including locked history. Needs a reason."""
    version = db.get(CashflowVersion, version_id)
    if version is None or version.item.household_id != user.household_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Version nicht gefunden")
    if body.amount is None and body.frequency is None:
        raise HTTPException(422, "Nichts zu korrigieren")
    before = _version_snapshot(version)
    if body.amount is not None:
        version.amount = Decimal(body.amount)
    if body.frequency is not None:
        version.frequency = body.frequency
    db.flush()
    _audit(
        db,
        user,
        "correction",
        "cashflow_version",
        version.id,
        reason=body.reason.strip(),
        before=before,
        after=_version_snapshot(version),
    )
    item = version.item
    db.refresh(item)
    return _item_out(item, version.valid_from)


# --------------------------------------------------------------------------------------
# aggregates
# --------------------------------------------------------------------------------------


def _group_out(g: dom.GroupSummary) -> GroupOut:
    return GroupOut(
        category_id=g.category_id,
        name=g.name,
        kind=g.kind,
        total=float(g.total),
        children=[_group_out(c) for c in g.children],
    )


@router.get("/cashflow/summary", response_model=SummaryOut)
def summary(user: CurrentUser, db: DbSession, month: MonthParam = None) -> SummaryOut:
    m = _month_query(month)
    s = dom.summarize(
        _category_infos(_categories(db, user.household_id)),
        _active_items(_items(db, user.household_id), m),
        load_book(db, user.household_id).flows_at(m),
    )
    return SummaryOut(
        month=m,
        income=float(s.income),
        expenses=float(s.expenses),
        financing=float(s.financing),
        balance=float(s.balance),
        savings_rate=float(s.savings_rate) if s.savings_rate is not None else None,
        income_groups=[_group_out(g) for g in s.income_groups],
        expense_groups=[_group_out(g) for g in s.expense_groups],
        financing_flows=[
            FinancingFlowOut(
                financing_id=f.financing_id,
                name=f.name,
                interest=float(f.interest),
                principal=float(f.principal),
                saving=float(f.saving),
                fee=float(f.fee),
                total=float(f.total),
            )
            for f in s.financing_flows
        ],
    )


@router.get("/cashflow/sankey", response_model=SankeyOut)
def sankey(user: CurrentUser, db: DbSession, month: MonthParam = None) -> SankeyOut:
    m = _month_query(month)
    s = dom.build_sankey(
        _category_infos(_categories(db, user.household_id)),
        _active_items(_items(db, user.household_id), m),
        load_book(db, user.household_id).flows_at(m),
    )
    return SankeyOut(
        month=m,
        nodes=[SankeyNodeOut(id=n.id, name=n.name, kind=n.kind) for n in s.nodes],
        links=[
            SankeyLinkOut(source=link.source, target=link.target, value=float(link.value))
            for link in s.links
        ],
    )


@router.get("/cashflow/series", response_model=list[SeriesPoint])
def series(
    user: CurrentUser,
    db: DbSession,
    start: Annotated[str, Query(alias="from", pattern=r"^\d{4}-(0[1-9]|1[0-2])$")],
    end: Annotated[str, Query(alias="to", pattern=r"^\d{4}-(0[1-9]|1[0-2])$")],
) -> list[SeriesPoint]:
    first, last = parse_month(start), parse_month(end)
    if last < first:
        raise HTTPException(422, "'to' darf nicht vor 'from' liegen")
    months = month_range(first, last)
    if len(months) > 240:
        raise HTTPException(422, "Höchstens 240 Monate pro Abfrage")
    cats = _category_infos(_categories(db, user.household_id))
    items = _items(db, user.household_id)
    book = load_book(db, user.household_id)
    out: list[SeriesPoint] = []
    for m in months:
        s = dom.summarize(cats, _active_items(items, m), book.flows_at(m))
        out.append(
            SeriesPoint(
                month=m,
                income=float(s.income),
                expenses=float(s.expenses),
                financing=float(s.financing),
                balance=float(s.balance),
            )
        )
    return out


@router.get("/audit", response_model=list[AuditOut])
def audit_log(
    user: CurrentUser, db: DbSession, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> list[AuditOut]:
    rows = db.execute(
        select(AuditLog, User.display_name)
        .join(User, User.id == AuditLog.user_id)
        .where(AuditLog.household_id == user.household_id)
        .order_by(AuditLog.id.desc())
        .limit(limit)
    )
    entries = list(rows)
    item_names = {i.id: i.name for i in _items(db, user.household_id)}
    version_rows = db.execute(
        select(CashflowVersion.id, CashflowVersion.item_id)
        .join(CashflowItem, CashflowItem.id == CashflowVersion.item_id)
        .where(CashflowItem.household_id == user.household_id)
    )
    version_items = {version_id: item_id for version_id, item_id in version_rows}
    category_names = {c.id: c.name for c in _categories(db, user.household_id)}
    financing_names = {f.id: f.name for f in load_financings(db, user.household_id)}
    instrument_names = {i.id: i.name for i in load_instruments(db, user.household_id)}

    def subject(a: AuditLog) -> str | None:
        if a.entity == "cashflow_item":
            return item_names.get(a.entity_id)
        if a.entity == "cashflow_version":
            return item_names.get(version_items.get(a.entity_id, -1))
        if a.entity == "category":
            return category_names.get(a.entity_id)
        if a.entity == "financing":
            return financing_names.get(a.entity_id)
        if a.entity == "instrument":
            return instrument_names.get(a.entity_id)
        return None

    return [
        AuditOut(
            id=a.id,
            action=a.action,
            entity=a.entity,
            entity_id=a.entity_id,
            reason=a.reason,
            before=a.before,
            after=a.after,
            created_at=a.created_at.isoformat(),
            user_name=name,
            subject=subject(a),
        )
        for a, name in entries
    ]
