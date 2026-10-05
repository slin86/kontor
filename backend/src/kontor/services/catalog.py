"""Seeds the built-in instrument catalog from the bundled reference data."""

import json
import threading
from decimal import Decimal
from importlib import resources

from sqlalchemy import select
from sqlalchemy.orm import Session

from kontor.models import CatalogEntry

_seed_lock = threading.Lock()


def seed_if_needed(db: Session) -> None:
    """Insert the bundled ETF reference data once.

    Several requests may arrive at the same time right after the first start. The seeding therefore
    runs under a lock in its own short transaction, and only inserts ISINs that are still missing.
    """
    with _seed_lock, Session(bind=db.get_bind(), expire_on_commit=False) as own:
        existing = set(
            own.scalars(select(CatalogEntry.isin).where(CatalogEntry.household_id.is_(None)))
        )
        if existing:
            return
        raw = (
            resources.files("kontor.data").joinpath("etf_catalog.json").read_text(encoding="utf-8")
        )
        doc = json.loads(raw)
        for e in doc["entries"]:
            if e["isin"] in existing:
                continue
            own.add(
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
        own.commit()
