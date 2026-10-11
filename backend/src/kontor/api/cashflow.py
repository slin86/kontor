"""Categories and cashflow: items with effective-dated versions, summaries, Sankey, audit log."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session, selectinload

from kontor.api.deps import CurrentUser, DbSession
from kontor.core.clock import current_month, month_range, parse_month
from kontor.domain import cashflow as dom
from kontor.models import (
    AuditLog,
    CashflowItem,
    CashflowVersion,
    Category,
    CategoryKind,
    Person,
    User,
)
from kontor.schemas.cashflow import (
    AuditOut,
    CategoryIn,
    CategoryMove,
    CategoryOut,
    CategoryUpdate,
    FinancingFlowOut,
    GroupOut,
    ItemChange,
    ItemCreate,
    ItemEnd,
    ItemOut,
    ItemRename,
    ItemStart,
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
from kontor.services.people import get_person, list_people, own_person

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


def _items(db: Session, household_id: int, person_id: int | None = None) -> list[CashflowItem]:
    """The household's items; for one person also the transfers they receive."""
    stmt = select(CashflowItem).where(CashflowItem.household_id == household_id)
    if person_id is not None:
        stmt = stmt.where(
            or_(CashflowItem.person_id == person_id, CashflowItem.transfer_to_id == person_id)
        )
    return list(
        db.scalars(
            stmt.options(
                selectinload(CashflowItem.versions), selectinload(CashflowItem.category)
            ).order_by(CashflowItem.name)
        )
    )


SAME_PERSON = "Absender und Empfänger eines Übertrags müssen verschieden sein"
TRANSFER_OUT = "Übertrag an andere Person"
TRANSFER_IN = "Übertrag erhalten"


def _transfer_category(
    db: Session, household_id: int, kind: CategoryKind, *, create: bool = False
) -> Category | None:
    """The category transfers are booked on (sender: expense, receiver: income)."""
    name = TRANSFER_OUT if kind == CategoryKind.EXPENSE else TRANSFER_IN
    cat = db.scalar(
        select(Category).where(
            Category.household_id == household_id,
            Category.name == name,
            Category.kind == kind,
            Category.parent_id.is_(None),
        )
    )
    if cat is None and create:
        last = max((c.sort_order for c in _categories(db, household_id)), default=0)
        cat = Category(household_id=household_id, name=name, kind=kind, sort_order=last + 1)
        db.add(cat)
        db.flush()
    return cat


@dataclass
class Scope:
    """Whose books a request looks at: one person, or the whole household (``person`` None)."""

    person: int | None
    names: dict[int, str]
    income_category: int  # where received transfers show up

    def incoming(self, item: CashflowItem) -> bool:
        return (
            self.person is not None
            and item.transfer_to_id == self.person
            and item.person_id != self.person
        )


def _scope(db: Session, user: User, person: int | None) -> Scope:
    if person is not None:
        person = get_person(db, user.household_id, person).id
    names = {p.id: p.name for p in list_people(db, user.household_id)}
    cat = _transfer_category(db, user.household_id, CategoryKind.INCOME)
    return Scope(person, names, cat.id if cat else -1)


PersonParam = Annotated[
    int | None, Query(description="Only this person's books; the whole household when left out")
]


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


def _item_out(item: CashflowItem, month: date, scope: Scope) -> ItemOut:
    active = next(
        (
            v
            for v in item.versions
            if v.valid_from <= month and (v.valid_to is None or month < v.valid_to)
        ),
        None,
    )
    specs = _specs(item)
    spec = dom.active_version(specs, month)
    booked = (
        dom.booked_amount(spec, dom.anchor_month(specs, spec), month, item.spread)
        if spec
        else Decimal(0)
    )
    incoming = scope.incoming(item)
    sender = scope.names.get(item.person_id, "")
    return ItemOut(
        id=item.id,
        name=f"Übertrag von {sender}" if incoming else item.name,
        category_id=scope.income_category if incoming else item.category_id,
        category_name=TRANSFER_IN if incoming else item.category.name,
        kind=CategoryKind.INCOME if incoming else item.category.kind,
        person_id=item.person_id,
        transfer_to_id=item.transfer_to_id,
        transfer_to_name=scope.names.get(item.transfer_to_id) if item.transfer_to_id else None,
        incoming=incoming,
        spread=item.spread,
        due_now=booked > 0,
        booked=float(dom.cents(booked)),
        active=_version_out(active) if active else None,
        versions=[_version_out(v) for v in item.versions],
    )


def _active_items(
    items: list[CashflowItem], month: date, scope: Scope, averaged: bool = False
) -> list[dom.ActiveItem]:
    """Items booked in a month. Transfers net out in the household view and are income for
    the receiver, expense for the sender. ``averaged`` ignores the due month and spreads every
    periodic item over the year, which is what long-range views want."""
    out: list[dom.ActiveItem] = []
    for item in items:
        if item.transfer_to_id is not None and scope.person is None:
            continue
        specs = _specs(item)
        spec = dom.active_version(specs, month)
        if spec is None:
            continue
        incoming = scope.incoming(item)
        out.append(
            dom.ActiveItem(
                item.id,
                f"Übertrag von {scope.names.get(item.person_id, '')}" if incoming else item.name,
                scope.income_category if incoming else item.category_id,
                dom.booked_amount(
                    spec, dom.anchor_month(specs, spec), month, item.spread or averaged
                ),
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


def _category_out(c: Category, item_count: int = 0) -> CategoryOut:
    return CategoryOut(
        id=c.id,
        name=c.name,
        kind=c.kind,
        parent_id=c.parent_id,
        item_count=item_count,
        sort_order=c.sort_order,
    )


def _check_parent(
    db: Session, household_id: int, cat: Category | None, kind: CategoryKind, parent_id: int | None
) -> None:
    """A category sits at most two levels deep and under a group of the same kind."""
    if parent_id is None:
        return
    parent = _category_or_422(db, household_id, parent_id)
    if parent.parent_id is not None:
        raise HTTPException(422, "Kategorien haben höchstens zwei Ebenen")
    if parent.kind != kind:
        raise HTTPException(422, "Unterkategorie und Oberkategorie müssen dieselbe Art haben")
    if cat is not None:
        if parent.id == cat.id:
            raise HTTPException(422, "Eine Kategorie kann nicht ihre eigene Oberkategorie sein")
        has_children = db.scalar(
            select(func.count(Category.id)).where(Category.parent_id == cat.id)
        )
        if has_children:
            raise HTTPException(
                422, "Eine Gruppe mit Unterkategorien kann nicht selbst Unterkategorie werden"
            )


def _siblings(db: Session, cat: Category) -> list[Category]:
    return [
        c
        for c in _categories(db, cat.household_id)
        if c.parent_id == cat.parent_id and c.kind == cat.kind
    ]


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(user: CurrentUser, db: DbSession) -> list[CategoryOut]:
    rows = db.execute(
        select(CashflowItem.category_id, func.count(CashflowItem.id))
        .where(CashflowItem.household_id == user.household_id)
        .group_by(CashflowItem.category_id)
    ).all()
    counts = {category_id: n for category_id, n in rows}
    return [_category_out(c, counts.get(c.id, 0)) for c in _categories(db, user.household_id)]


@router.post("/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(body: CategoryIn, user: CurrentUser, db: DbSession) -> CategoryOut:
    _check_parent(db, user.household_id, None, body.kind, body.parent_id)
    last = max((c.sort_order for c in _categories(db, user.household_id)), default=0)
    cat = Category(
        household_id=user.household_id,
        parent_id=body.parent_id,
        name=body.name.strip(),
        kind=body.kind,
        sort_order=last + 1,
    )
    db.add(cat)
    db.flush()
    _audit(db, user, "create", "category", cat.id, after={"name": cat.name})
    return _category_out(cat)


@router.put("/categories/{category_id}", response_model=CategoryOut)
def update_category(
    category_id: int, body: CategoryUpdate, user: CurrentUser, db: DbSession
) -> CategoryOut:
    """Rename a category or move it under another group (or back to the top level)."""
    cat = _category_or_422(db, user.household_id, category_id)
    _check_parent(db, user.household_id, cat, cat.kind, body.parent_id)
    before = {"name": cat.name, "parent_id": cat.parent_id}
    cat.name = body.name.strip()
    cat.parent_id = body.parent_id
    if before["parent_id"] != body.parent_id:
        cat.sort_order = (
            max((c.sort_order for c in _categories(db, user.household_id)), default=0) + 1
        )
    db.flush()
    _audit(
        db,
        user,
        "update",
        "category",
        cat.id,
        before=before,
        after={"name": cat.name, "parent_id": cat.parent_id},
    )
    return _category_out(cat)


@router.post("/categories/{category_id}/move", response_model=list[CategoryOut])
def move_category(
    category_id: int, body: CategoryMove, user: CurrentUser, db: DbSession
) -> list[CategoryOut]:
    """Swap the position with the neighbouring category of the same level and kind."""
    cat = _category_or_422(db, user.household_id, category_id)
    siblings = _siblings(db, cat)
    index = next(i for i, c in enumerate(siblings) if c.id == cat.id)
    other = index - 1 if body.direction == "up" else index + 1
    if 0 <= other < len(siblings):
        slots = sorted(c.sort_order for c in siblings)
        if len(set(slots)) != len(slots):  # ties from older data: number the siblings afresh
            slots = list(range(len(slots)))
        siblings[index], siblings[other] = siblings[other], siblings[index]
        for slot, c in zip(slots, siblings, strict=True):
            c.sort_order = slot
        db.flush()
        _audit(db, user, "move", "category", cat.id, after={"direction": body.direction})
    return list_categories(user, db)


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    category_id: int,
    user: CurrentUser,
    db: DbSession,
    move_to: Annotated[int | None, Query(description="Category that takes over the items")] = None,
) -> None:
    """Delete an empty category, or hand its items to ``move_to`` first."""
    cat = _category_or_422(db, user.household_id, category_id)
    if db.scalar(select(func.count(Category.id)).where(Category.parent_id == cat.id)):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Die Kategorie hat Unterkategorien. Verschiebe oder lösche sie zuerst.",
        )
    items = list(db.scalars(select(CashflowItem.id).where(CashflowItem.category_id == cat.id)))
    if items:
        if move_to is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Es hängen noch {len(items)} Posten an der Kategorie. Wähle eine Zielkategorie.",
            )
        target = _category_or_422(db, user.household_id, move_to)
        if target.id == cat.id or target.kind != cat.kind:
            raise HTTPException(422, "Die Zielkategorie muss eine andere derselben Art sein.")
        db.execute(
            update(CashflowItem).where(CashflowItem.id.in_(items)).values(category_id=target.id)
        )
    _audit(
        db,
        user,
        "delete",
        "category",
        cat.id,
        before={"name": cat.name, "parent_id": cat.parent_id},
        after={"moved_items": len(items), "move_to": move_to} if items else None,
    )
    db.delete(cat)


# --------------------------------------------------------------------------------------
# items
# --------------------------------------------------------------------------------------


@router.get("/cashflow/items", response_model=list[ItemOut])
def list_items(
    user: CurrentUser,
    db: DbSession,
    month: MonthParam = None,
    include_inactive: bool = False,
    person: PersonParam = None,
) -> list[ItemOut]:
    m = _month_query(month)
    scope = _scope(db, user, person)
    out = [_item_out(i, m, scope) for i in _items(db, user.household_id, scope.person)]
    return out if include_inactive else [i for i in out if i.active is not None]


@router.post("/cashflow/items", response_model=ItemOut, status_code=status.HTTP_201_CREATED)
def create_item(body: ItemCreate, user: CurrentUser, db: DbSession) -> ItemOut:
    owner = (
        get_person(db, user.household_id, body.person_id)
        if body.person_id is not None
        else own_person(db, user)
    )
    transfer_to: Person | None = None
    if body.transfer_to_id is not None:
        transfer_to = get_person(db, user.household_id, body.transfer_to_id)
        if transfer_to.id == owner.id:
            raise HTTPException(
                422, "Absender und Empfänger eines Übertrags müssen verschieden sein"
            )
        category = _transfer_category(db, user.household_id, CategoryKind.EXPENSE, create=True)
        _transfer_category(db, user.household_id, CategoryKind.INCOME, create=True)
        assert category is not None
        category_id = category.id
    else:
        if body.category_id is None:
            raise HTTPException(422, "Wähle eine Kategorie")
        category_id = _category_or_422(db, user.household_id, body.category_id).id
    item = CashflowItem(
        household_id=user.household_id,
        category_id=category_id,
        person_id=owner.id,
        transfer_to_id=transfer_to.id if transfer_to else None,
        name=body.name.strip(),
        spread=body.spread,
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
    return _item_out(item, body.valid_from, _scope(db, user, None))


@router.patch("/cashflow/items/{item_id}", response_model=ItemOut)
def rename_item(item_id: int, body: ItemRename, user: CurrentUser, db: DbSession) -> ItemOut:
    item = _item_or_404(db, user, item_id)
    before = {
        "name": item.name,
        "category_id": item.category_id,
        "person_id": item.person_id,
        "spread": item.spread,
    }
    if body.spread is not None:
        item.spread = body.spread
    if body.category_id is not None:
        if item.transfer_to_id is not None:
            raise HTTPException(422, "Übertragungen haben eine feste Kategorie")
        _category_or_422(db, user.household_id, body.category_id)
        item.category_id = body.category_id
    if body.person_id is not None:
        owner = get_person(db, user.household_id, body.person_id)
        if owner.id == item.transfer_to_id:
            raise HTTPException(
                422, "Absender und Empfänger eines Übertrags müssen verschieden sein"
            )
        item.person_id = owner.id
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
        after={
            "name": item.name,
            "category_id": item.category_id,
            "person_id": item.person_id,
            "spread": item.spread,
        },
    )
    return _item_out(item, current_month(), _scope(db, user, None))


@router.delete("/cashflow/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: int, user: CurrentUser, db: DbSession) -> None:
    """Remove an item with all its versions, for example one that was entered twice.

    Unlike ``end`` this also removes the months already booked. The audit log keeps what was there.
    """
    item = _item_or_404(db, user, item_id)
    _audit(
        db,
        user,
        "delete",
        "cashflow_item",
        item.id,
        before={
            "name": item.name,
            "category_id": item.category_id,
            "person_id": item.person_id,
            "versions": [_version_snapshot(v) for v in item.versions],
        },
    )
    db.delete(item)


@router.delete("/cashflow/items", status_code=status.HTTP_204_NO_CONTENT)
def delete_all_items(
    user: CurrentUser,
    db: DbSession,
    confirm: Annotated[str, Query()] = "",
) -> None:
    """Developer tool: remove every item of the household. Needs ``?confirm=all``."""
    if confirm != "all":
        raise HTTPException(422, "Zum Löschen aller Posten fehlt die Bestätigung.")
    items = list(
        db.scalars(select(CashflowItem).where(CashflowItem.household_id == user.household_id))
    )
    _audit(
        db,
        user,
        "delete_all",
        "cashflow_item",
        0,
        before={"count": len(items), "names": sorted(i.name for i in items)[:200]},
    )
    for item in items:
        db.delete(item)


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
    return _item_out(item, body.effective_from, _scope(db, user, None))


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
    return _item_out(item, body.end_from, _scope(db, user, None))


@router.post("/cashflow/items/{item_id}/start", response_model=ItemOut)
def start_item_earlier(item_id: int, body: ItemStart, user: CurrentUser, db: DbSession) -> ItemOut:
    """Backfill: let an item begin in an earlier month. Needs a reason when that month is closed."""
    item = _item_or_404(db, user, item_id)
    first = min(item.versions, key=lambda v: v.valid_from)
    if body.start_from >= first.valid_from:
        raise HTTPException(422, "Der neue Beginn muss vor dem bisherigen Beginn liegen")
    if body.start_from < current_month() and not body.reason:
        raise HTTPException(422, "Für abgeschlossene Monate ist eine Begründung nötig")
    before = _version_snapshot(first)
    first.valid_from = body.start_from
    db.flush()
    _audit(
        db,
        user,
        "backfill" if body.start_from < current_month() else "update",
        "cashflow_version",
        first.id,
        reason=body.reason.strip() if body.reason else None,
        before=before,
        after=_version_snapshot(first),
    )
    db.refresh(item)
    return _item_out(item, body.start_from, _scope(db, user, None))


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
    return _item_out(item, version.valid_from, _scope(db, user, None))


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
        direct=g.direct,
    )


@router.get("/cashflow/summary", response_model=SummaryOut)
def summary(
    user: CurrentUser, db: DbSession, month: MonthParam = None, person: PersonParam = None
) -> SummaryOut:
    m = _month_query(month)
    scope = _scope(db, user, person)
    s = dom.summarize(
        _category_infos(_categories(db, user.household_id)),
        _active_items(_items(db, user.household_id, scope.person), m, scope),
        load_book(db, user.household_id, scope.person).flows_at(m),
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
def sankey(
    user: CurrentUser, db: DbSession, month: MonthParam = None, person: PersonParam = None
) -> SankeyOut:
    m = _month_query(month)
    scope = _scope(db, user, person)
    s = dom.build_sankey(
        _category_infos(_categories(db, user.household_id)),
        _active_items(_items(db, user.household_id, scope.person), m, scope),
        load_book(db, user.household_id, scope.person).flows_at(m),
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
    person: PersonParam = None,
) -> list[SeriesPoint]:
    first, last = parse_month(start), parse_month(end)
    if last < first:
        raise HTTPException(422, "'to' darf nicht vor 'from' liegen")
    months = month_range(first, last)
    if len(months) > 240:
        raise HTTPException(422, "Höchstens 240 Monate pro Abfrage")
    cats = _category_infos(_categories(db, user.household_id))
    scope = _scope(db, user, person)
    items = _items(db, user.household_id, scope.person)
    book = load_book(db, user.household_id, scope.person)
    out: list[SeriesPoint] = []
    for m in months:
        s = dom.summarize(cats, _active_items(items, m, scope), book.flows_at(m))
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
            if a.action == "delete_all":
                return f"Alle Posten ({(a.before or {}).get('count', 0)})"
            return item_names.get(a.entity_id) or (a.before or {}).get("name")
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
