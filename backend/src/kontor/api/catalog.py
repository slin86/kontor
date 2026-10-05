"""Instrument search, own catalog entries and cost comparison."""

from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import Select, or_, select

from kontor.api.deps import CurrentUser, DbSession
from kontor.core.clock import add_months, current_month
from kontor.domain import cashflow as cf
from kontor.domain import depot as dom
from kontor.models import CatalogEntry
from kontor.schemas.catalog import (
    CatalogIn,
    CatalogOut,
    CompareOut,
    CostResult,
    Facets,
    SearchOut,
)
from kontor.services.catalog import seed_if_needed

router = APIRouter(prefix="/api/catalog", tags=["catalog"])

MAX_COMPARE = 6


def _visible(user: CurrentUser) -> Select[CatalogEntry]:
    return select(CatalogEntry).where(
        or_(CatalogEntry.household_id.is_(None), CatalogEntry.household_id == user.household_id)
    )


def _out(e: CatalogEntry) -> CatalogOut:
    return CatalogOut(
        id=e.id,
        kind=e.kind,
        isin=e.isin,
        name=e.name,
        index_name=e.index_name,
        ter_percent=float(e.ter_percent),
        distribution=e.distribution,
        replication=e.replication,
        domicile=e.domicile,
        fund_size_m_eur=e.fund_size_m_eur,
        builtin=e.household_id is None,
        source=e.source,
        as_of=e.as_of,
    )


@router.get("", response_model=SearchOut)
def search(
    user: CurrentUser,
    db: DbSession,
    q: Annotated[str | None, Query(max_length=100)] = None,
    index: Annotated[str | None, Query(max_length=80)] = None,
    kind: Literal["etf", "private_equity"] | None = None,
    distribution: Literal["accumulating", "distributing"] | None = None,
    replication: Annotated[str | None, Query(max_length=32)] = None,
    max_ter: Annotated[Decimal | None, Query(ge=0, le=15)] = None,
    sort: Literal["size", "ter", "name"] = "size",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SearchOut:
    """Search by name, ISIN or index; every word of ``q`` has to match somewhere."""
    seed_if_needed(db)
    stmt = _visible(user)
    for word in (q or "").split():
        like = f"%{word}%"
        stmt = stmt.where(
            or_(
                CatalogEntry.name.ilike(like),
                CatalogEntry.isin.ilike(like),
                CatalogEntry.index_name.ilike(like),
            )
        )
    if index:
        stmt = stmt.where(CatalogEntry.index_name == index)
    if kind:
        stmt = stmt.where(CatalogEntry.kind == kind)
    if distribution:
        stmt = stmt.where(CatalogEntry.distribution == distribution)
    if replication:
        stmt = stmt.where(CatalogEntry.replication == replication)
    if max_ter is not None:
        stmt = stmt.where(CatalogEntry.ter_percent <= max_ter)

    rows = list(db.scalars(stmt))
    if sort == "ter":
        rows.sort(key=lambda e: (e.ter_percent, -(e.fund_size_m_eur or 0), e.name))
    elif sort == "name":
        rows.sort(key=lambda e: e.name.lower())
    else:
        rows.sort(key=lambda e: (-(e.fund_size_m_eur or 0), e.ter_percent, e.name))

    everything = list(db.scalars(_visible(user)))
    facets = Facets(
        indexes=sorted({e.index_name for e in everything if e.index_name}),
        distributions=sorted({e.distribution for e in everything if e.distribution}),
        replications=sorted({e.replication for e in everything if e.replication}),
    )
    return SearchOut(
        total=len(rows), items=[_out(e) for e in rows[offset : offset + limit]], facets=facets
    )


@router.post("", response_model=CatalogOut, status_code=status.HTTP_201_CREATED)
def create_entry(body: CatalogIn, user: CurrentUser, db: DbSession) -> CatalogOut:
    """Own entry, e.g. a private-equity fund or an ETF missing from the reference data."""
    e = CatalogEntry(
        household_id=user.household_id,
        kind=body.kind,
        isin=body.isin.upper() if body.isin else None,
        name=body.name.strip(),
        index_name=body.index_name.strip() if body.index_name else None,
        ter_percent=body.ter_percent,
        distribution=body.distribution,
        replication=body.replication,
        domicile=body.domicile,
        fund_size_m_eur=body.fund_size_m_eur,
        source="Eigener Eintrag",
        as_of=current_month().strftime("%Y-%m"),
    )
    db.add(e)
    db.flush()
    return _out(e)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(entry_id: int, user: CurrentUser, db: DbSession) -> None:
    e = db.get(CatalogEntry, entry_id)
    if e is None or e.household_id != user.household_id:
        # built-in reference data cannot be removed, and foreign entries do not exist for us
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Eintrag nicht gefunden")
    db.delete(e)


def _final_value(
    monthly: Decimal, start_value: Decimal, years: int, annual_return: Decimal, cost: Decimal
) -> Decimal:
    today = current_month()
    position = dom.Position(
        id=0,
        name="",
        kind="etf",
        annual_return=annual_return,
        annual_cost=cost,
        entry_fee=Decimal(0),
        start=today,
        start_value=start_value,
        rates=[cf.VersionSpec(monthly, "monthly", today)],
    )
    last = add_months(today, years * 12 - 1)
    return dom.project_position(position, last)[-1].balance


@router.get("/compare", response_model=CompareOut)
def compare(
    user: CurrentUser,
    db: DbSession,
    ids: Annotated[str, Query(description="Comma-separated catalog ids", max_length=100)],
    monthly: Annotated[Decimal, Query(ge=0, le=1_000_000)] = Decimal(300),
    years: Annotated[int, Query(ge=1, le=60)] = 20,
    expected_return: Annotated[Decimal, Query(ge=-20, le=40)] = Decimal(6),
    start_value: Annotated[Decimal, Query(ge=0, le=100_000_000)] = Decimal(0),
) -> CompareOut:
    """What the running costs (TER) of the selected instruments mean over ``years``.

    All entries get the same gross return, so differences come from costs only.
    """
    try:
        wanted = [int(x) for x in ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(422, "Ungültige Liste von Einträgen.") from None
    if not 1 <= len(wanted) <= MAX_COMPARE:
        raise HTTPException(422, f"Wähle 1 bis {MAX_COMPARE} Einträge aus.")

    found = {e.id: e for e in db.scalars(_visible(user).where(CatalogEntry.id.in_(wanted)))}
    if len(found) != len(set(wanted)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Eintrag nicht gefunden")

    gross = expected_return / 100
    free = _final_value(monthly, start_value, years, gross, Decimal(0))
    rows: list[tuple[CatalogEntry, Decimal]] = []
    for i in dict.fromkeys(wanted):
        e = found[i]
        value = _final_value(monthly, start_value, years, gross, Decimal(e.ter_percent) / 100)
        rows.append((e, value))
    best = max(v for _, v in rows)
    return CompareOut(
        monthly=float(monthly),
        years=years,
        expected_return_percent=float(expected_return),
        start_value=float(start_value),
        paid_in=float(start_value + monthly * years * 12),
        results=[
            CostResult(
                entry=_out(e),
                final_value=float(cf.cents(v)),
                total_costs=float(cf.cents(free - v)),
                extra_vs_cheapest=float(cf.cents(best - v)),
            )
            for e, v in rows
        ],
    )
