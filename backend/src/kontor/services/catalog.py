"""Seeds the built-in instrument catalog from the bundled reference data."""

import json
from decimal import Decimal
from importlib import resources

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from kontor.models import CatalogEntry


def seed_if_needed(db: Session) -> None:
    """Insert the bundled ETF reference data once. Later releases may ship updated data."""
    count = db.scalar(
        select(func.count()).select_from(CatalogEntry).where(CatalogEntry.household_id.is_(None))
    )
    if count:
        return
    raw = resources.files("kontor.data").joinpath("etf_catalog.json").read_text(encoding="utf-8")
    doc = json.loads(raw)
    for e in doc["entries"]:
        db.add(
            CatalogEntry(
                household_id=None,
                kind="etf",
                isin=e["isin"],
                name=e["name"],
                index_name=e["index"],
                ter_percent=Decimal(str(e["ter_percent"])),
                distribution=e["distribution"],
                replication=e["replication"],
                domicile=e["domicile"],
                fund_size_m_eur=e["fund_size_m_eur"],
                source=doc["source"],
                as_of=doc["as_of"],
            )
        )
    db.flush()
