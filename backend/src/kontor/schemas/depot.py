"""Request/response schemas for the depot plan."""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from kontor.schemas.cashflow import Month

Kind = Literal["etf", "private_equity"]
Percent = Annotated[Decimal, Field(ge=-20, le=40, max_digits=7, decimal_places=3)]
CostPercent = Annotated[Decimal, Field(ge=0, le=15, max_digits=7, decimal_places=3)]
Euro = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
Share = Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]
Isin = Annotated[str, Field(pattern=r"^[A-Za-z]{2}[A-Za-z0-9]{9}[0-9]$")]


class Assumptions(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    isin: Isin | None = None
    expected_return_percent: Percent
    cost_percent: CostPercent = Decimal(0)
    entry_fee_percent: CostPercent = Decimal(0)
    # Teilfreistellung; ``None`` means 30 for new ETFs, 0 for private equity, unchanged on update.
    tax_exempt_percent: Share | None = None


class InstrumentIn(Assumptions):
    # owner of the position; the signed-in user's own person when left out
    person_id: int | None = None
    kind: Kind
    start: Month
    start_value: Euro = Decimal(0)
    monthly_rate: Euro = Decimal(0)


class InstrumentCorrection(BaseModel):
    start: Month
    start_value: Euro
    reason: str = Field(min_length=3, max_length=500)


class RateChange(BaseModel):
    effective_from: Month
    amount: Euro


class OneOffIn(BaseModel):
    month: Month
    amount: Annotated[Decimal, Field(max_digits=14, decimal_places=2)]
    note: str | None = Field(default=None, max_length=200)


class RateOut(BaseModel):
    id: int
    amount: float
    valid_from: Month
    valid_to: Month | None
    locked: bool


class OneOffOut(BaseModel):
    id: int
    month: Month
    amount: float
    note: str | None
    locked: bool


class OwnerChange(BaseModel):
    person_id: int


class InstrumentOut(BaseModel):
    id: int
    person_id: int
    kind: Kind
    name: str
    isin: str | None
    expected_return_percent: float
    cost_percent: float
    entry_fee_percent: float
    tax_exempt_percent: float
    start: Month
    start_value: float
    current_rate: float  # savings rate in the current month
    planned_value: float  # planned balance at the end of the current month
    paid_in: float  # cumulative deposits up to the end of the current month


class InstrumentDetailOut(InstrumentOut):
    rates: list[RateOut]
    one_offs: list[OneOffOut]


class DepotOut(BaseModel):
    base_rate: float  # sum of all current savings rates
    planned_value: float
    paid_in: float
    instruments: list[InstrumentOut]


class ProjectionInstrument(BaseModel):
    id: int
    name: str
    kind: Kind


class ProjectionPoint(BaseModel):
    month: Month
    value: float
    paid_in: float
    deposit: float
    fees: float
    balances: list[float]  # aligned with ``instruments``
    tax_paid: float  # cumulative tax on Vorabpauschalen
    tax_on_sale: float  # tax due if everything were sold at the end of the month
    net_value: float  # value minus both taxes


class ProjectionOut(BaseModel):
    first: Month
    last: Month
    return_shift_percent: float
    inflation_percent: float
    tax_rate_percent: float
    base_rate: float
    instruments: list[ProjectionInstrument]
    points: list[ProjectionPoint]
