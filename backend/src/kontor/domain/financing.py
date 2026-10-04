"""Pure financing logic: annuity loans and building-society savings contracts (Bausparvertrag).

Months are ``date`` objects on the first day of the month. All amounts are ``Decimal``.
Schedules are computed deterministically from parameters plus dated events, so the past never
changes unless the parameters or past events are corrected.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from kontor.core.clock import add_months
from kontor.domain.cashflow import cents

MAX_MONTHS = 1200  # 100 years; protects against schedules that never end
ZERO = Decimal(0)


class FinancingError(ValueError):
    """Raised for parameter combinations that cannot produce a valid schedule."""


# --------------------------------------------------------------------------------------
# Common output
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class FinancingMonth:
    """What happens in one month of a financing."""

    month: date
    interest: Decimal = ZERO  # paid to the lender (loan phase)
    principal: Decimal = ZERO  # repayment of debt, including special repayments
    saving: Decimal = ZERO  # paid into a Bauspar savings balance
    fee: Decimal = ZERO  # one-off fees such as the Bauspar contract fee
    balance: Decimal = (
        ZERO  # remaining debt after this month (loan phase) or savings (saving phase)
    )
    phase: str = "loan"  # "loan" | "saving"
    special: Decimal = ZERO  # part of ``principal`` that was a special repayment

    @property
    def outflow(self) -> Decimal:
        """Everything that leaves the household's account in this month."""
        return self.interest + self.principal + self.saving + self.fee


@dataclass(frozen=True)
class Schedule:
    rows: list[FinancingMonth]
    regular_payment: Decimal  # the usual monthly payment, used to show what frees up when it ends

    @property
    def first_month(self) -> date:
        return self.rows[0].month

    @property
    def last_month(self) -> date:
        return self.rows[-1].month

    @property
    def end_month(self) -> date:
        """First month without any payment."""
        return add_months(self.last_month, 1)

    def at(self, month: date) -> FinancingMonth | None:
        for r in self.rows:
            if r.month == month:
                return r
        return None


# --------------------------------------------------------------------------------------
# Annuity loan (real-estate financing or consumer loan)
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class LoanEvent:
    """A dated change: extra repayment, new monthly payment or new interest rate."""

    month: date
    kind: str  # "special_repayment" | "payment_change" | "rate_change"
    value: Decimal  # euros for repayments/payments, annual rate (e.g. 0.035) for rate changes


@dataclass(frozen=True)
class LoanParams:
    principal: Decimal
    annual_rate: Decimal  # nominal interest per year, e.g. 0.0375
    monthly_payment: Decimal
    start: date  # month of the first payment


def initial_payment(
    principal: Decimal, annual_rate: Decimal, repayment_percent: Decimal
) -> Decimal:
    """Monthly payment for a given initial repayment rate (German annuity convention)."""
    return cents(principal * (annual_rate + repayment_percent) / 12)


def loan_schedule(params: LoanParams, events: list[LoanEvent] | None = None) -> Schedule:
    """Monthly schedule of an annuity loan.

    Interest is charged monthly on the remaining balance at ``annual_rate / 12``. A rate or payment
    change applies from its month on. The final payment is reduced to what is still owed.
    """
    balance = params.principal
    month = params.start
    rate = params.annual_rate
    payment = params.monthly_payment
    if balance <= 0:
        raise FinancingError("Der Darlehensbetrag muss größer als null sein.")

    by_month: dict[date, list[LoanEvent]] = {}
    for e in events or []:
        by_month.setdefault(e.month, []).append(e)

    rows: list[FinancingMonth] = []
    for _ in range(MAX_MONTHS):
        specials = ZERO
        for e in by_month.get(month, []):
            if e.kind == "rate_change":
                rate = e.value
            elif e.kind == "payment_change":
                payment = e.value
            elif e.kind == "special_repayment":
                specials += e.value

        interest = cents(balance * rate / 12)
        if payment <= interest:
            raise FinancingError(
                f"Die Rate von {payment} € deckt im Monat {month:%m/%Y} "
                f"die Zinsen von {interest} € nicht."
            )
        principal = min(payment - interest, balance)
        special = min(specials, balance - principal)
        balance = balance - principal - special
        rows.append(
            FinancingMonth(
                month=month,
                interest=interest,
                principal=principal + special,
                balance=balance,
                special=special,
            )
        )
        if balance <= 0:
            return Schedule(rows, params.monthly_payment)
        month = add_months(month, 1)
    raise FinancingError("Das Darlehen wird innerhalb von 100 Jahren nicht getilgt.")


# --------------------------------------------------------------------------------------
# Building-society savings contract (Bausparvertrag)
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class BausparParams:
    contract_sum: Decimal  # Bausparsumme
    monthly_saving: Decimal  # Regelsparbeitrag during the saving phase
    start: date
    allocation: date  # month of Zuteilung; the loan phase starts here
    fee_percent: Decimal = Decimal("0.01")  # Abschlussgebühr as share of the contract sum
    deposit_rate: Decimal = ZERO  # interest on savings per year, credited every December
    loan_rate: Decimal = ZERO  # interest of the Bauspardarlehen per year
    loan_payment: Decimal = ZERO  # monthly payment in the loan phase (Tilgungsrate)


def bauspar_schedule(params: BausparParams, events: list[LoanEvent] | None = None) -> Schedule:
    """Saving phase (monthly savings plus year-end interest), then the Bauspardarlehen.

    The contract fee is due in the first month. At allocation the saved balance counts towards the
    contract sum; the remainder is paid out as a loan that runs like an annuity loan.
    """
    p = params
    if p.allocation <= p.start:
        raise FinancingError("Die Zuteilung muss nach dem Vertragsbeginn liegen.")
    if p.monthly_saving <= 0:
        raise FinancingError("Der Sparbeitrag muss größer als null sein.")

    rows: list[FinancingMonth] = []
    balance = ZERO
    accrued = ZERO
    month = p.start
    while month < p.allocation:
        accrued += balance * p.deposit_rate / 12
        balance += p.monthly_saving
        if month.month == 12:
            balance += cents(accrued)
            accrued = ZERO
        rows.append(
            FinancingMonth(
                month=month,
                saving=p.monthly_saving,
                fee=cents(p.contract_sum * p.fee_percent) if month == p.start else ZERO,
                balance=cents(balance),
                phase="saving",
            )
        )
        month = add_months(month, 1)

    saved = cents(balance + accrued)
    loan = p.contract_sum - saved
    if loan <= 0:
        raise FinancingError(
            "Bis zur Zuteilung wäre die Bausparsumme bereits angespart. "
            "Wähle eine frühere Zuteilung oder einen niedrigeren Sparbeitrag."
        )
    if p.loan_payment <= 0:
        raise FinancingError("Für die Darlehensphase fehlt die monatliche Rate.")

    loan_params = LoanParams(loan, p.loan_rate, p.loan_payment, p.allocation)
    loan_part = loan_schedule(loan_params, events)
    return Schedule(rows + loan_part.rows, p.loan_payment)
