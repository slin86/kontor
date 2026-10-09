"""Request/response schemas for properties."""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from kontor.schemas.cashflow import Month

Euro = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
Growth = Annotated[Decimal, Field(ge=-20, le=20, max_digits=6, decimal_places=2)]
Share = Annotated[Decimal, Field(gt=0, le=100, max_digits=5, decimal_places=2)]


class PropertyIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    usage: Literal["owner_occupied", "rented"]
    person_id: int | None = None
    purchase_month: Month
    purchase_price: Euro
    closing_costs: Euro = Decimal(0)
    value: Euro  # current market estimate
    value_as_of: Month
    growth_percent: Growth = Decimal(0)
    share_percent: Share = Decimal(100)
    own_share_entered: bool = False


class WorkIn(BaseModel):
    month: Month
    name: str = Field(min_length=1, max_length=120)
    cost: Euro
    value_gain: Euro = Decimal(0)


class WorkOut(BaseModel):
    id: int
    month: Month
    name: str
    cost: float
    value_gain: float


class LinkedFinancing(BaseModel):
    id: int
    name: str
    remaining_debt: float
    payment_this_month: float
    initial_debt: float | None  # highest debt of the loan phase
    repaid_percent: float | None
    end_month: Month  # first month without any payment


class LinkedItem(BaseModel):
    id: int
    name: str
    kind: Literal["income", "expense"]
    monthly: float


class PropertyOut(BaseModel):
    id: int
    person_id: int
    name: str
    usage: Literal["owner_occupied", "rented"]
    purchase_month: Month
    purchase_price: float
    closing_costs: float
    value: float
    value_as_of: Month
    growth_percent: float
    share_percent: float
    own_share_entered: bool
    works: list[WorkOut]
    # computed for the current month
    current_value: float  # whole property, including modernisations
    my_value: float  # the household's share
    debt: float  # the household's share of the linked financings
    repaid: float  # household's share already paid off
    repaid_percent: float | None  # of all linked debt
    equity: float
    invested: float  # price, closing costs and modernisations
    value_gain: float  # current value minus what was put in, whole property
    income: float  # monthly rent etc. from linked items
    costs: float  # monthly running costs from linked items
    financing_payment: float
    net_cashflow: float  # income - costs - financing payment
    yield_percent: float | None  # (income - costs) * 12 / current value
    financings: list[LinkedFinancing]
    items: list[LinkedItem]


class LinksIn(BaseModel):
    financing_ids: list[int] = []
    item_ids: list[int] = []
