"""Household tax settings (church tax, allowance, assumed Basiszins)."""

from decimal import Decimal

from fastapi import APIRouter

from kontor.api.deps import CurrentUser, DbSession
from kontor.domain import tax as dom
from kontor.models import TaxSettings
from kontor.schemas.tax import TaxSettingsIn, TaxSettingsOut
from kontor.services.audit import record as audit

router = APIRouter(prefix="/api/tax", tags=["tax"])

DEFAULTS = TaxSettingsIn()


def _out(church: Decimal, allowance: Decimal, base_interest: Decimal) -> TaxSettingsOut:
    rate = dom.tax_rate(church / 100)
    return TaxSettingsOut(
        church_tax_percent=int(church),
        allowance=float(allowance),
        base_interest_percent=float(base_interest),
        tax_rate_percent=round(float(rate) * 100, 3),
    )


@router.get("/settings", response_model=TaxSettingsOut)
def get_settings(user: CurrentUser, db: DbSession) -> TaxSettingsOut:
    row = db.get(TaxSettings, user.household_id)
    if row is None:
        return _out(
            Decimal(DEFAULTS.church_tax_percent), DEFAULTS.allowance, DEFAULTS.base_interest_percent
        )
    return _out(row.church_tax_percent, row.allowance, row.base_interest_percent)


@router.put("/settings", response_model=TaxSettingsOut)
def put_settings(body: TaxSettingsIn, user: CurrentUser, db: DbSession) -> TaxSettingsOut:
    row = db.get(TaxSettings, user.household_id)
    before = None
    if row is None:
        row = TaxSettings(household_id=user.household_id)
        db.add(row)
    else:
        before = {
            "church_tax_percent": str(row.church_tax_percent),
            "allowance": str(row.allowance),
            "base_interest_percent": str(row.base_interest_percent),
        }
    row.church_tax_percent = Decimal(body.church_tax_percent)
    row.allowance = body.allowance
    row.base_interest_percent = body.base_interest_percent
    db.flush()
    audit(
        db,
        user,
        "update",
        "tax_settings",
        user.household_id,
        before=before,
        after=body.model_dump(mode="json"),
    )
    return _out(row.church_tax_percent, row.allowance, row.base_interest_percent)
