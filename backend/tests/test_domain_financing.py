from datetime import date
from decimal import Decimal

import pytest

from kontor.domain.financing import (
    BausparParams,
    FinancingError,
    LoanEvent,
    LoanParams,
    bauspar_schedule,
    initial_payment,
    loan_schedule,
)

D = Decimal


def m(year: int, month: int) -> date:
    return date(year, month, 1)


def test_initial_payment_follows_german_annuity_convention() -> None:
    # 100.000 EUR, 3,6 % Sollzins, 2 % Anfangstilgung -> 5,6 % p.a. / 12
    assert initial_payment(D("100000"), D("0.036"), D("0.02")) == D("466.67")


def test_first_month_splits_interest_and_principal() -> None:
    p = LoanParams(D("100000"), D("0.036"), D("466.67"), m(2026, 1))
    first = loan_schedule(p).rows[0]
    assert first.interest == D("300.00")  # 100000 * 0.036 / 12
    assert first.principal == D("166.67")
    assert first.balance == D("99833.33")


def test_schedule_repays_exactly_the_principal() -> None:
    p = LoanParams(D("100000"), D("0.036"), D("466.67"), m(2026, 1))
    s = loan_schedule(p)
    assert sum(r.principal for r in s.rows) == D("100000")
    assert s.rows[-1].balance == D("0")
    assert s.rows[-1].principal <= p.monthly_payment  # last payment is the remainder
    assert s.end_month == date(
        s.last_month.year + (s.last_month.month // 12), s.last_month.month % 12 + 1, 1
    )


def test_known_term_for_zero_interest_loan() -> None:
    p = LoanParams(D("12000"), D("0"), D("500"), m(2026, 1))
    s = loan_schedule(p)
    assert len(s.rows) == 24
    assert s.last_month == m(2027, 12)
    assert s.end_month == m(2028, 1)
    assert all(r.interest == 0 for r in s.rows)


def test_special_repayment_shortens_the_term_and_saves_interest() -> None:
    p = LoanParams(D("100000"), D("0.036"), D("466.67"), m(2026, 1))
    plain = loan_schedule(p)
    with_special = loan_schedule(p, [LoanEvent(m(2027, 1), "special_repayment", D("10000"))])
    assert len(with_special.rows) < len(plain.rows)
    assert sum(r.interest for r in with_special.rows) < sum(r.interest for r in plain.rows)
    jan = with_special.at(m(2027, 1))
    assert jan is not None and jan.special == D("10000")
    # earlier months are untouched by a later event
    assert with_special.rows[:12] == plain.rows[:12]


def test_rate_change_applies_from_its_month_only() -> None:
    p = LoanParams(D("100000"), D("0.036"), D("500"), m(2026, 1))
    s = loan_schedule(p, [LoanEvent(m(2027, 1), "rate_change", D("0.05"))])
    dec, jan = s.at(m(2026, 12)), s.at(m(2027, 1))
    assert dec is not None and jan is not None
    prev = s.at(m(2026, 11))
    assert prev is not None
    assert dec.interest == (prev.balance * D("0.036") / 12).quantize(D("0.01"))
    assert jan.interest == (dec.balance * D("0.05") / 12).quantize(D("0.01"))


def test_payment_change_speeds_up_repayment() -> None:
    p = LoanParams(D("50000"), D("0.03"), D("400"), m(2026, 1))
    slow = loan_schedule(p)
    fast = loan_schedule(p, [LoanEvent(m(2026, 7), "payment_change", D("800"))])
    assert len(fast.rows) < len(slow.rows)
    assert fast.at(m(2026, 7)).interest + fast.at(m(2026, 7)).principal == D("800")  # type: ignore[union-attr]


def test_payment_below_interest_is_rejected() -> None:
    with pytest.raises(FinancingError):
        loan_schedule(LoanParams(D("100000"), D("0.06"), D("400"), m(2026, 1)))


def test_non_positive_principal_is_rejected() -> None:
    with pytest.raises(FinancingError):
        loan_schedule(LoanParams(D("0"), D("0.03"), D("400"), m(2026, 1)))


def test_special_repayment_cannot_exceed_remaining_debt() -> None:
    p = LoanParams(D("1000"), D("0"), D("100"), m(2026, 1))
    s = loan_schedule(p, [LoanEvent(m(2026, 2), "special_repayment", D("50000"))])
    assert s.rows[-1].balance == D("0")
    assert sum(r.principal for r in s.rows) == D("1000")


BAUSPAR = BausparParams(
    contract_sum=D("60000"),
    monthly_saving=D("200"),
    start=m(2026, 1),
    allocation=m(2036, 1),
    fee_percent=D("0.01"),
    deposit_rate=D("0"),
    loan_rate=D("0.025"),
    loan_payment=D("300"),
)


def test_bauspar_saving_phase_collects_savings_and_fee() -> None:
    s = bauspar_schedule(BAUSPAR)
    saving_rows = [r for r in s.rows if r.phase == "saving"]
    assert len(saving_rows) == 120
    assert saving_rows[0].fee == D("600.00")
    assert all(r.fee == 0 for r in saving_rows[1:])
    assert saving_rows[-1].balance == D("24000.00")
    assert saving_rows[0].outflow == D("800.00")  # first rate plus fee


def test_bauspar_loan_covers_the_rest_of_the_contract_sum() -> None:
    s = bauspar_schedule(BAUSPAR)
    loan_rows = [r for r in s.rows if r.phase == "loan"]
    assert loan_rows[0].month == m(2036, 1)
    assert loan_rows[0].interest == D("75.00")  # (60000 - 24000) * 0.025 / 12
    assert sum(r.principal for r in loan_rows) == D("36000")
    assert loan_rows[-1].balance == D("0")
    assert s.regular_payment == D("300")


def test_bauspar_deposit_interest_is_credited_in_december() -> None:
    with_interest = BausparParams(**{**BAUSPAR.__dict__, "deposit_rate": D("0.012")})
    s = bauspar_schedule(with_interest)
    nov, dec = s.at(m(2026, 11)), s.at(m(2026, 12))
    assert nov is not None and dec is not None
    assert dec.balance - nov.balance > D("200")  # a regular rate plus credited interest
    assert s.at(m(2035, 12)).balance > D("24000")  # type: ignore[union-attr]


def test_bauspar_validates_dates_and_rates() -> None:
    with pytest.raises(FinancingError):
        bauspar_schedule(BausparParams(**{**BAUSPAR.__dict__, "allocation": m(2026, 1)}))
    with pytest.raises(FinancingError):
        bauspar_schedule(BausparParams(**{**BAUSPAR.__dict__, "loan_payment": D("0")}))


def test_bauspar_saving_more_than_the_contract_sum_is_rejected() -> None:
    too_much = BausparParams(**{**BAUSPAR.__dict__, "monthly_saving": D("600")})
    with pytest.raises(FinancingError, match="angespart"):
        bauspar_schedule(too_much)
