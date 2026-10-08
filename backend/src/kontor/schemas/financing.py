"""Schemas for financings (loans and building-society contracts) and the budget outlook."""

from decimal import Decimal
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, Field, model_validator

from kontor.schemas.cashflow import Money, Month

Percent = Annotated[Decimal, Field(ge=0, le=30, max_digits=8, decimal_places=4)]


class LoanIn(BaseModel):
    kind: Literal["loan"] = "loan"
    name: str = Field(min_length=1, max_length=120)
    purpose: Literal["real_estate", "consumer", "zero_percent", "other"] = "real_estate"
    principal: Money
    annual_rate_percent: Percent
    monthly_payment: Money | None = None
    initial_repayment_percent: Annotated[Decimal, Field(gt=0, le=30)] | None = None
    start: Month  # month of the first payment

    @model_validator(mode="after")
    def _one_payment_input(self) -> Self:
        if self.purpose == "zero_percent" and self.annual_rate_percent != 0:
            raise ValueError("Eine 0 %-Finanzierung hat keinen Zins.")
        if (self.monthly_payment is None) == (self.initial_repayment_percent is None):
            raise ValueError("Gib entweder die monatliche Rate oder die Anfangstilgung an.")
        return self


class Payout(BaseModel):
    """One payment of the advance loan: from this month on interest runs on the amount."""

    month: Month
    amount: Money


class BausparIn(BaseModel):
    kind: Literal["building_savings"]
    name: str = Field(min_length=1, max_length=120)
    contract_sum: Money
    monthly_saving: Money
    start: Month
    allocation: Month  # month of Zuteilung
    fee_percent: Annotated[Decimal, Field(ge=0, le=5)] = Decimal("1")
    fee_amount: Money | None = None  # the fee in euros; replaces ``fee_percent`` when given
    deposit_rate_percent: Annotated[Decimal, Field(ge=0, le=10)] = Decimal("0")
    # set for a Bausparfinanzierung: interest of the advance loan that is paid out on day 1
    prefinance_rate_percent: Percent | None = None
    # staged payouts of the advance loan; without them the whole sum is paid out on day 1
    payouts: list[Payout] | None = Field(default=None, max_length=24)
    loan_rate_percent: Percent = Decimal("0")
    loan_payment: Money  # monthly payment in the loan phase

    @model_validator(mode="after")
    def _payouts_fit(self) -> Self:
        if not self.payouts:
            return self
        if self.prefinance_rate_percent is None:
            raise ValueError(
                "Auszahlungen gibt es nur bei einer Bausparfinanzierung mit Vorausdarlehen."
            )
        if sum(p.amount for p in self.payouts) > self.contract_sum:
            raise ValueError("Die Auszahlungen übersteigen zusammen die Darlehenssumme.")
        for p in self.payouts:
            if not self.start <= p.month < self.allocation:
                raise ValueError("Jede Auszahlung liegt zwischen Vertragsbeginn und Zuteilung.")
        return self


class CreditLineIn(BaseModel):
    """A revolving credit line: a limit, what is drawn today and a fixed monthly payment."""

    kind: Literal["credit_line"]
    name: str = Field(min_length=1, max_length=120)
    limit: Money
    balance: Money  # amount drawn today
    annual_rate_percent: Percent
    monthly_payment: Money
    start: Month  # month of the first payment

    @model_validator(mode="after")
    def _within_limit(self) -> Self:
        if self.balance > self.limit:
            raise ValueError("Der genutzte Betrag darf den Rahmen nicht übersteigen.")
        return self


FinancingIn = Annotated[LoanIn | BausparIn | CreditLineIn, Field(discriminator="kind")]


class FinancingCorrection(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
    data: FinancingIn


class EventIn(BaseModel):
    month: Month
    kind: Literal["special_repayment", "payment_change", "rate_change", "drawdown"]
    # euros for special_repayment, drawdown and payment_change, percent per year for rate_change
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
    drawn: float


class FinancingOut(BaseModel):
    id: int
    person_id: int
    kind: Literal["loan", "building_savings", "credit_line"]
    name: str
    purpose: str | None
    start: Month
    end_month: Month  # first month without any payment
    regular_payment: float
    payment_this_month: float
    phase: Literal["not_started", "saving", "loan", "finished"]
    remaining_debt: float | None  # None while a Bauspar contract is still saving
    saved: float | None  # savings balance of a Bauspar contract
    prefinanced: bool = False  # Bausparfinanzierung: advance loan runs next to the savings phase
    total_interest: float
    remaining_interest: float
    credit_limit: float | None = None  # credit line only
    available: float | None = None  # credit line only: what can still be drawn


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
