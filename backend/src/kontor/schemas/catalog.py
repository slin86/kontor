"""Schemas for the instrument catalog: search, own entries, cost comparison."""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from kontor.schemas.depot import CostPercent, Isin

Kind = Literal["etf", "private_equity"]


class CatalogIn(BaseModel):
    kind: Kind
    name: str = Field(min_length=1, max_length=160)
    isin: Isin | None = None
    index_name: str | None = Field(default=None, max_length=80)
    ter_percent: CostPercent
    distribution: Literal["accumulating", "distributing"] | None = None
    replication: str | None = Field(default=None, max_length=32)
    domicile: str | None = Field(default=None, max_length=40)
    fund_size_m_eur: Annotated[int | None, Field(ge=0)] = None


class CatalogOut(BaseModel):
    id: int
    kind: Kind
    isin: str | None
    name: str
    index_name: str | None
    ter_percent: float
    distribution: str | None
    replication: str | None
    domicile: str | None
    fund_size_m_eur: int | None
    builtin: bool  # reference data shipped with Kontor, as opposed to the household's own entry
    source: str | None
    as_of: str | None


class Facets(BaseModel):
    indexes: list[str]
    distributions: list[str]
    replications: list[str]


class SearchOut(BaseModel):
    total: int
    items: list[CatalogOut]
    facets: Facets


class CostResult(BaseModel):
    entry: CatalogOut
    final_value: float
    total_costs: float  # what the TER costs over the period compared with a cost-free fund
    extra_vs_cheapest: float  # additional costs compared with the cheapest selected entry


class CompareOut(BaseModel):
    monthly: float
    years: int
    expected_return_percent: float
    start_value: float
    paid_in: float
    results: list[CostResult]


Money = Annotated[Decimal, Field(ge=0)]
