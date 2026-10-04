"""Schemas for actual values, transactions, CSV import and plan-vs-actual."""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from kontor.schemas.cashflow import Month

Day = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]
Kind = Literal["buy", "sell", "dividend"]
Euro = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]


class ValueIn(BaseModel):
    instrument_id: int
    month: Month
    value: Euro
    reason: str | None = Field(default=None, max_length=500)


class ValueOut(BaseModel):
    id: int
    instrument_id: int
    month: Month
    value: float


class TransactionIn(BaseModel):
    instrument_id: int
    day: Day
    kind: Kind
    amount: Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)]
    fee: Euro = Decimal(0)


class TransactionOut(BaseModel):
    id: int
    instrument_id: int | None
    day: str
    kind: Kind
    amount: float
    fee: float
    shares: float | None
    isin: str | None
    name: str | None
    source: str


class ImportIn(BaseModel):
    csv: str = Field(min_length=1, max_length=8_000_000)
    mapping: dict[str, int] = Field(default_factory=dict)  # ISIN -> instrument id


class ImportRow(BaseModel):
    line: int
    day: str
    kind: Kind
    amount: float
    fee: float
    shares: float | None
    isin: str | None
    name: str | None
    instrument_id: int | None
    duplicate: bool


class UnmatchedIsin(BaseModel):
    isin: str | None
    name: str | None
    count: int


class ImportPreview(BaseModel):
    rows: list[ImportRow]
    skipped: dict[str, int]
    errors: list[str]
    unmatched: list[UnmatchedIsin]
    new_count: int
    duplicate_count: int


class ImportResult(BaseModel):
    imported: int
    duplicates: int
    unmatched: int


class InstrumentComparison(BaseModel):
    id: int
    name: str
    planned_value: float
    actual_value: float | None
    actual_month: Month | None
    deviation: float | None  # actual minus plan
    deviation_percent: float | None
    planned_paid_in: float
    actual_net_invested: float | None  # buys minus sells, only when transactions exist


class ComparisonPoint(BaseModel):
    month: Month
    planned_total: float
    planned_tracked: float  # plan for the positions that have actual values
    actual: float | None  # None unless every tracked position has a value in that month
    planned_deposit: float | None  # plan for the positions with transactions
    actual_deposit: float | None


class ComparisonOut(BaseModel):
    first: Month
    last: Month
    instruments: list[InstrumentComparison]
    points: list[ComparisonPoint]
