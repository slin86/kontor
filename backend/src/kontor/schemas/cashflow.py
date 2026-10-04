"""Request/response schemas for categories and cashflow."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, Field, PlainSerializer

from kontor.core.clock import format_month, parse_month
from kontor.models import CategoryKind, Frequency


def _to_month(value: Any) -> date:
    if isinstance(value, date):
        return date(value.year, value.month, 1)
    if isinstance(value, str):
        return parse_month(value)
    raise ValueError("Month must be formatted as YYYY-MM")


# Months travel as "YYYY-MM" strings and are stored as the first day of the month.
Month = Annotated[
    date,
    BeforeValidator(_to_month),
    PlainSerializer(format_month, return_type=str),
]

Money = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: CategoryKind
    parent_id: int | None = None


class CategoryOut(BaseModel):
    id: int
    name: str
    kind: CategoryKind
    parent_id: int | None


class VersionOut(BaseModel):
    id: int
    amount: float
    frequency: Frequency
    monthly: float
    valid_from: Month
    valid_to: Month | None
    locked: bool  # the version starts in a closed month, so edits need a correction


class ItemOut(BaseModel):
    id: int
    name: str
    category_id: int
    category_name: str
    kind: CategoryKind
    active: VersionOut | None  # version valid in the requested month
    versions: list[VersionOut]


class ItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category_id: int
    amount: Money
    frequency: Frequency = Frequency.MONTHLY
    valid_from: Month


class ItemChange(BaseModel):
    effective_from: Month
    amount: Money
    frequency: Frequency


class ItemEnd(BaseModel):
    end_from: Month  # first month in which the item no longer applies


class ItemRename(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    category_id: int | None = None


class VersionCorrection(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
    amount: Money | None = None
    frequency: Frequency | None = None


class GroupOut(BaseModel):
    category_id: int
    name: str
    kind: CategoryKind
    total: float
    children: list["GroupOut"]


class SummaryOut(BaseModel):
    month: Month
    income: float
    expenses: float
    balance: float
    savings_rate: float | None
    income_groups: list[GroupOut]
    expense_groups: list[GroupOut]


class SankeyNodeOut(BaseModel):
    id: str
    name: str
    kind: str


class SankeyLinkOut(BaseModel):
    source: str
    target: str
    value: float


class SankeyOut(BaseModel):
    month: Month
    nodes: list[SankeyNodeOut]
    links: list[SankeyLinkOut]


class SeriesPoint(BaseModel):
    month: Month
    income: float
    expenses: float
    balance: float


class AuditOut(BaseModel):
    id: int
    action: str
    entity: str
    entity_id: int
    reason: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    created_at: str
    user_name: str
    subject: str | None  # name of the item or category the entry is about
