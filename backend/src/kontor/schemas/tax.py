"""Schemas for the household's tax settings."""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class TaxSettingsIn(BaseModel):
    church_tax_percent: Literal[0, 8, 9] = 0
    allowance: Annotated[Decimal, Field(ge=0, le=100000, max_digits=10, decimal_places=2)] = (
        Decimal(1000)
    )
    base_interest_percent: Annotated[
        Decimal, Field(ge=0, le=10, max_digits=5, decimal_places=3)
    ] = Decimal("3.2")


class TaxSettingsOut(BaseModel):
    church_tax_percent: int
    allowance: float
    base_interest_percent: float
    tax_rate_percent: float  # effective rate on taxable gains, incl. solidarity surcharge
