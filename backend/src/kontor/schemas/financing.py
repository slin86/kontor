"""Schemas for financings (loans and building-society contracts) and the budget outlook."""

from decimal import Decimal
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, Field, model_validator

from kontor.schemas.cashflow import Money, Month

Percent = Annotated[Decimal, Field(ge=0, le=30, max_digits=8, decimal_places=4)]


class LoanIn(BaseModel):
    kind: Literal["loan"] = "loan"
    name: str = Field(min_length=1, max_length=120)
    purpose: Literal["real_estate", "consumer", "other"] = "real_estate"
    principal: Money
    annual_rate_percent: Percent
    monthly_payment: Money | None = None
    initial_repayment_percent: Annotated[Decimal, Field(gt=0, le=30)] | None = None
    start: Month  # month of the first payment

    @model_validator(mode="after")
    def _one_payment_input(self) -> Self:
        if (self.monthly_payment is None) == (self.initial_repayment_percent is None):
            raise ValueError("Gib entweder die monatliche Rate oder die Anfangstilgung an.")
        return self


class BausparIn(BaseModel):
    kind: Literal["building_savings"]
    name: str = Field(min_length=1, max_length=120)
    contract_sum: Money
    monthly_saving: Money
    start: Month
    allocation: Month  # month of Zuteilung
    fee_percent: Annotated[Decimal, Field(ge=0, le=5)] = Decimal("1")
    deposit_rate_percent: Annotated[Decimal, Field(ge=0, le=10)] = Decimal("0")
    loan_rate_percent: Percent = Decimal("0")
    loan_payment: Money  # monthly payment in the loan phase


FinancingIn = Annotated[LoanIn | BausparIn, Field(discriminator="kind")]


class FinancingCorrection(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
    data: FinancingIn


class EventIn(BaseModel):
    month: Month
    kind: Literal["special_repayment", "payment_change", "rate_change"]
    # euros for special_repayment and payment_change, percent per year for rate_change
    value: Annotated[Decimal, Field(gt=0, le=100_000_000)]


class EventOut(BaseModel):
    id: int
    month: Month
    kind: str
    value: float  # euros, or percent per year for rate changes
    locked: bool  # the month is closed, so the event can no longer be removed


class ScheduleRowOut(BaseModel):
    month: Month
    interest: float
    principal: float
    saving: float
    fee: float
    balance: float
    phase: str
    special: float


class FinancingOut(BaseModel):
    id: int
    kind: Literal["loan", "building_savings"]
    name: str
    purpose: str | None
    start: Month
    end_month: Month  # first month without any payment
    regular_payment: float
    payment_this_month: float
    phase: Literal["not_started", "saving", "loan", "finished"]
    remaining_debt: float | None  # None while a Bauspar contract is still saving
    saved: float | None  # savings balance of a Bauspar contract
    total_interest: float
    remaining_interest: float


class FinancingDetailOut(FinancingOut):
    input: dict[str, Any]  # the contract data as entered, ready to prefill the edit form
    events: list[EventOut]
    schedule: list[ScheduleRowOut]


class OutlookPoint(BaseModel):
    month: Month
    income: float
    expenses: float
    financing: float
    free: float


class OutlookEvent(BaseModel):
    month: Month
    kind: Literal["financing_end", "item_end"]
    label: str
    monthly_change: float  # change of the free monthly budget when this happens


class OutlookOut(BaseModel):
    start: Month
    years: int
    income_growth_percent: float
    expense_growth_percent: float
    points: list[OutlookPoint]
    events: list[OutlookEvent]
