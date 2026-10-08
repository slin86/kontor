"""Turns stored financings into schedules and monthly flows for the cashflow views."""

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from kontor.core.clock import format_month, parse_month
from kontor.domain.cashflow import FinancingFlow
from kontor.domain.financing import (
    BausparParams,
    CreditLineParams,
    FinancingError,
    LoanEvent,
    LoanParams,
    Schedule,
    bauspar_schedule,
    credit_line_schedule,
    initial_payment,
    loan_schedule,
)
from kontor.models import Financing, FinancingKind
from kontor.schemas.financing import BausparIn, CreditLineIn, LoanIn

PERCENT = Decimal(100)
log = logging.getLogger(__name__)


def to_params(body: LoanIn | BausparIn | CreditLineIn) -> dict[str, Any]:
    """Contract data as stored: decimals as strings, months as YYYY-MM, percents as entered."""
    if isinstance(body, LoanIn):
        rate = body.annual_rate_percent / PERCENT
        payment = body.monthly_payment
        if payment is None:
            assert body.initial_repayment_percent is not None
            payment = initial_payment(
                body.principal, rate, body.initial_repayment_percent / PERCENT
            )
        return {
            "principal": str(body.principal),
            "annual_rate_percent": str(body.annual_rate_percent),
            "monthly_payment": str(payment),
            "initial_repayment_percent": (
                str(body.initial_repayment_percent) if body.initial_repayment_percent else None
            ),
            "start": format_month(body.start),
        }
    if isinstance(body, CreditLineIn):
        return {
            "limit": str(body.limit),
            "balance": str(body.balance),
            "annual_rate_percent": str(body.annual_rate_percent),
            "monthly_payment": str(body.monthly_payment),
            "start": format_month(body.start),
        }
    return {
        "contract_sum": str(body.contract_sum),
        "monthly_saving": str(body.monthly_saving),
        "start": format_month(body.start),
        "allocation": format_month(body.allocation),
        "fee_percent": str(body.fee_percent),
        "fee_amount": str(body.fee_amount) if body.fee_amount is not None else None,
        "deposit_rate_percent": str(body.deposit_rate_percent),
        "prefinance_rate_percent": (
            str(body.prefinance_rate_percent) if body.prefinance_rate_percent is not None else None
        ),
        "loan_rate_percent": str(body.loan_rate_percent),
        "loan_payment": str(body.loan_payment),
    }


def _events(f: Financing) -> list[LoanEvent]:
    return [LoanEvent(e.month, e.kind, Decimal(e.value)) for e in f.events]


def schedule_for(f: Financing) -> Schedule:
    """Compute the full schedule of a stored financing, including its dated events."""
    p = f.params
    events = _events(f)
    if f.kind == FinancingKind.LOAN:
        return loan_schedule(
            LoanParams(
                principal=Decimal(p["principal"]),
                annual_rate=Decimal(p["annual_rate_percent"]) / PERCENT,
                monthly_payment=Decimal(p["monthly_payment"]),
                start=parse_month(p["start"]),
            ),
            events,
        )
    if f.kind == FinancingKind.CREDIT_LINE:
        return credit_line_schedule(
            CreditLineParams(
                limit=Decimal(p["limit"]),
                balance=Decimal(p["balance"]),
                annual_rate=Decimal(p["annual_rate_percent"]) / PERCENT,
                monthly_payment=Decimal(p["monthly_payment"]),
                start=parse_month(p["start"]),
            ),
            events,
        )
    return bauspar_schedule(
        BausparParams(
            contract_sum=Decimal(p["contract_sum"]),
            monthly_saving=Decimal(p["monthly_saving"]),
            start=parse_month(p["start"]),
            allocation=parse_month(p["allocation"]),
            fee_percent=Decimal(p["fee_percent"]) / PERCENT,
            fee_amount=Decimal(p["fee_amount"]) if p.get("fee_amount") else None,
            deposit_rate=Decimal(p["deposit_rate_percent"]) / PERCENT,
            prefinance_rate=(
                Decimal(p["prefinance_rate_percent"]) / PERCENT
                if p.get("prefinance_rate_percent") is not None
                else None
            ),
            loan_rate=Decimal(p["loan_rate_percent"]) / PERCENT,
            loan_payment=Decimal(p["loan_payment"]),
        ),
        events,
    )


def validate(body: LoanIn | BausparIn | CreditLineIn) -> None:
    """Raise ``FinancingError`` if the contract data cannot produce a schedule."""
    probe = Financing(
        kind=FinancingKind(body.kind),
        name=body.name,
        params=to_params(body),
    )
    probe.events = []
    schedule_for(probe)


@dataclass
class FinancingBook:
    """All financings of a household with their schedules, indexed by month."""

    items: list[tuple[Financing, Schedule]]

    def flows_at(self, month: date, *, regular_only: bool = False) -> list[FinancingFlow]:
        """Flows in a month; ``regular_only`` leaves out one-off special repayments."""
        out: list[FinancingFlow] = []
        for f, schedule in self.items:
            row = schedule.at(month)
            if row is not None:
                out.append(
                    FinancingFlow(
                        f.id,
                        f.name,
                        row.interest,
                        row.principal - (row.special if regular_only else 0),
                        row.saving,
                        row.fee,
                    )
                )
        return out


def load_financings(
    db: Session, household_id: int, person_id: int | None = None
) -> list[Financing]:
    stmt = select(Financing).where(Financing.household_id == household_id)
    if person_id is not None:
        stmt = stmt.where(Financing.person_id == person_id)
    return list(
        db.scalars(
            stmt.options(selectinload(Financing.events)).order_by(Financing.name, Financing.id)
        )
    )


def load_book(db: Session, household_id: int, person_id: int | None = None) -> FinancingBook:
    items: list[tuple[Financing, Schedule]] = []
    for f in load_financings(db, household_id, person_id):
        try:
            items.append((f, schedule_for(f)))
        except FinancingError:
            # A contract that no longer yields a schedule must not break every other view.
            log.warning("Financing %s has no valid schedule and is skipped", f.id)
            continue
    return FinancingBook(items)
