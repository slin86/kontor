"""Request/response schemas for assets and the net worth development."""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from kontor.schemas.cashflow import Month

AssetKindName = Literal["cash", "property", "vehicle", "other"]
Value = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
Growth = Annotated[Decimal, Field(ge=-30, le=30, max_digits=6, decimal_places=2)]


class AssetIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: AssetKindName
    value: Value
    as_of: Month
    growth_percent: Growth = Decimal(0)
    person_id: int | None = None  # the signed-in user's own person when left out


class AssetOut(BaseModel):
    id: int
    person_id: int
    name: str
    kind: AssetKindName
    value: float
    as_of: Month
    growth_percent: float


class WealthSeries(BaseModel):
    key: str
    name: str
    group: Literal["depot", "bauspar", "asset", "debt"]


class WealthPoint(BaseModel):
    month: Month
    values: list[float]  # aligned with ``series``; debts are positive amounts
    assets: float
    debts: float
    net: float
    net_after_tax: float  # net worth if the depot were sold and taxed that month


class WealthOut(BaseModel):
    first: Month
    last: Month
    today: Month
    inflation_percent: float
    series: list[WealthSeries]
    points: list[WealthPoint]
