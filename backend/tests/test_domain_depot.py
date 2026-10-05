from datetime import date
from decimal import Decimal

import pytest

from kontor.domain import depot as dom
from kontor.domain.cashflow import VersionSpec

D = Decimal
JAN = date(2026, 1, 1)


def _position(**kw: object) -> dom.Position:
    base: dict[str, object] = {
        "id": 1,
        "name": "ETF",
        "kind": "etf",
        "annual_return": D("0.06"),
        "annual_cost": D(0),
        "entry_fee": D(0),
        "start": JAN,
        "start_value": D(0),
        "rates": [VersionSpec(D(100), "monthly", JAN)],
    }
    return dom.Position(**{**base, **kw})  # type: ignore[arg-type]


def test_twelve_months_compound_to_the_annual_return() -> None:
    p = _position(rates=[VersionSpec(D(0), "monthly", JAN)], start_value=D(1000))
    rows = dom.project_position(p, date(2026, 12, 1))
    assert rows[-1].balance == pytest.approx(D(1060), abs=D("0.01"))


def test_costs_reduce_the_return_and_entry_fee_the_deposit() -> None:
    p = _position(
        rates=[VersionSpec(D(0), "monthly", JAN)],
        start_value=D(1000),
        annual_cost=D("0.002"),
    )
    assert dom.project_position(p, date(2026, 12, 1))[-1].balance == pytest.approx(
        D(1058), abs=D("0.01")
    )
    q = _position(entry_fee=D("0.05"), annual_return=D(0))
    first = dom.project_position(q, JAN)[0]
    assert (first.deposit, first.fee, first.balance) == (D(100), D(5), D(95))


def test_savings_rate_changes_and_one_offs() -> None:
    p = _position(
        annual_return=D(0),
        rates=[
            VersionSpec(D(100), "monthly", JAN, date(2026, 4, 1)),
            VersionSpec(D(300), "monthly", date(2026, 4, 1)),
        ],
        one_offs={date(2026, 2, 1): D(1000), date(2026, 5, 1): D(-200)},
    )
    rows = {r.month.month: r for r in dom.project_position(p, date(2026, 6, 1))}
    assert rows[1].balance == D(100)
    assert rows[2].balance == D(1200)
    assert rows[4].balance == D(1200 + 100 + 300)
    assert rows[5].deposit == D(100)  # 300 rate - 200 withdrawal
    assert rows[6].paid_in == D(100 * 3 + 1000 + 300 * 3 - 200)


def test_withdrawal_larger_than_the_balance_is_rejected() -> None:
    p = _position(one_offs={JAN: D(-500)}, annual_return=D(0))
    with pytest.raises(dom.DepotError):
        dom.project_position(p, JAN)


def test_depot_sums_positions_and_respects_start_months() -> None:
    a = _position(id=1, annual_return=D(0))
    b = _position(id=2, annual_return=D(0), start=date(2026, 3, 1))
    months = dom.project_depot([a, b], JAN, date(2026, 4, 1))
    assert [m.value for m in months] == [D(100), D(200), D(400), D(600)]
    assert months[0].balances == {1: D(100), 2: D(0)}
    assert dom.base_rate([a, b], date(2026, 2, 1)) == D(100)
    assert dom.base_rate([a, b], date(2026, 3, 1)) == D(200)


def test_view_can_start_later_without_changing_values() -> None:
    p = _position()
    full = dom.project_depot([p], JAN, date(2030, 1, 1))
    later = dom.project_depot([p], date(2028, 1, 1), date(2030, 1, 1))
    assert later[0].value == next(m.value for m in full if m.month == date(2028, 1, 1))


def test_scenario_shift_and_deflation() -> None:
    p = _position(rates=[VersionSpec(D(0), "monthly", JAN)], start_value=D(1000))
    up = dom.project_position(p, date(2026, 12, 1), D("0.02"))[-1].balance
    assert up == pytest.approx(D(1080), abs=D("0.01"))
    assert dom.deflate(D(1000), D("0.02"), 12) == pytest.approx(D("980.39"), abs=D("0.01"))
    assert dom.deflate(D(1000), D("0.02"), -5) == D(1000)
