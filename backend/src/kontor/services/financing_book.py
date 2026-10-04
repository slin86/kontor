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
    FinancingError,
    LoanEvent,
    LoanParams,
    Schedule,
    bauspar_schedule,
    initial_payment,
    loan_schedule,
)
from kontor.models import Financing, FinancingKind
from kontor.schemas.financing import BausparIn, LoanIn

PERCENT = Decimal(100)
log = logging.getLogger(__name__)


def to_params(body: LoanIn | BausparIn) -> dict[str, Any]:
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
    return {
        "contract_sum": str(body.contract_sum),
        "monthly_saving": str(body.monthly_saving),
        "start": format_month(body.start),
        "allocation": format_month(body.allocation),
        "fee_percent": str(body.fee_percent),
        "deposit_rate_percent": str(body.deposit_rate_percent),
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
    return bauspar_schedule(
        BausparParams(
            contract_sum=Decimal(p["contract_sum"]),
            monthly_saving=Decimal(p["monthly_saving"]),
            start=parse_month(p["start"]),
            allocation=parse_month(p["allocation"]),
            fee_percent=Decimal(p["fee_percent"]) / PERCENT,
            deposit_rate=Decimal(p["deposit_rate_percent"]) / PERCENT,
            loan_rate=Decimal(p["loan_rate_percent"]) / PERCENT,
            loan_payment=Decimal(p["loan_payment"]),
        ),
        events,
    )


def validate(body: LoanIn | BausparIn) -> None:
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

    def flows_at(self, month: date) -> list[FinancingFlow]:
        out: list[FinancingFlow] = []
        for f, schedule in self.items:
            row = schedule.at(month)
            if row is not None:
                out.append(
                    FinancingFlow(f.id, f.name, row.interest, row.principal, row.saving, row.fee)
                )
        return out


def load_financings(db: Session, household_id: int) -> list[Financing]:
    return list(
        db.scalars(
            select(Financing)
            .where(Financing.household_id == household_id)
            .options(selectinload(Financing.events))
            .order_by(Financing.name, Financing.id)
        )
    )


def load_book(db: Session, household_id: int) -> FinancingBook:
    items: list[tuple[Financing, Schedule]] = []
    for f in load_financings(db, household_id):
        try:
            items.append((f, schedule_for(f)))
        except FinancingError:
            # A contract that no longer yields a schedule must not break every other view.
            log.warning("Financing %s has no valid schedule and is skipped", f.id)
            continue
    return FinancingBook(items)
