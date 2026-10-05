from datetime import date
from decimal import Decimal

from kontor.domain.cashflow import VersionSpec
from kontor.domain.depot import Position, project_position
from kontor.domain.tax import TaxConfig, base_interest, project_tax, tax_rate, vorabpauschale

D = Decimal


def _position(
    start: date = date(2024, 1, 1),
    start_value: str = "10000",
    rate: str = "0",
    exempt: str = "0.3",
    annual_return: str = "0.07",
) -> Position:
    return Position(
        id=1,
        name="X",
        kind="etf",
        annual_return=D(annual_return),
        annual_cost=D(0),
        entry_fee=D(0),
        start=start,
        start_value=D(start_value),
        rates=[VersionSpec(D(rate), "monthly", start, None, 1)],
        tax_exempt=D(exempt),
    )


def test_tax_rate_without_and_with_church_tax() -> None:
    assert round(tax_rate(D(0)), 5) == D("0.26375")
    assert round(tax_rate(D("0.09")), 4) == D("0.28")
    assert round(tax_rate(D("0.08")), 4) == D("0.2782")


def test_base_interest_uses_published_values_then_assumption() -> None:
    cfg = TaxConfig(future_base_interest=D("0.025"))
    assert base_interest(2026, cfg) == D("0.032")
    assert base_interest(2030, cfg) == D("0.025")
    assert base_interest(2020, cfg) == 0


def test_vorabpauschale_is_70_percent_of_base_yield_for_a_full_year() -> None:
    p = _position()
    rows = project_position(p, date(2025, 12, 1))
    vorab = vorabpauschale(p, rows, TaxConfig())
    opening = next(r.balance for r in rows if r.month == date(2024, 12, 1))
    assert vorab[2025] == opening * D("0.0253") * D("0.7")
    assert vorab[2024] == D(10000) * D("0.0229") * D("0.7")


def test_vorabpauschale_is_capped_by_the_actual_gain() -> None:
    p = _position(annual_return="0.01")  # gain 1 % < basisertrag 1.6 % of 10 000
    rows = project_position(p, date(2024, 12, 1))
    gain = rows[-1].balance - D(10000)
    assert vorabpauschale(p, rows, TaxConfig())[2024] == gain


def test_no_vorabpauschale_on_a_loss() -> None:
    p = _position(annual_return="-0.10")
    rows = project_position(p, date(2024, 12, 1))
    assert vorabpauschale(p, rows, TaxConfig())[2024] == 0


def test_purchases_count_only_for_the_months_held() -> None:
    p = _position(start=date(2024, 7, 1))  # July: 6 of 12 months
    rows = project_position(p, date(2024, 12, 1))
    vorab = vorabpauschale(p, rows, TaxConfig())[2024]
    assert vorab == D(10000) * D(6) / 12 * D("0.0229") * D("0.7")


def test_sale_tax_applies_teilfreistellung_and_allowance() -> None:
    p = _position(start=date(2026, 1, 1))
    months = project_tax([p], date(2026, 12, 1), date(2026, 12, 1), TaxConfig())
    rows = project_position(p, date(2026, 12, 1))
    gain = rows[-1].balance - D(10000)
    expected = max(D(0), gain * D("0.7") - 1000) * tax_rate(D(0))
    assert months[0].sale_tax == expected
    assert months[0].vorab_paid == 0  # the 2026 Vorabpauschale is taxed in January 2027


def test_vorabpauschale_is_credited_at_sale_and_taxed_once() -> None:
    p = _position(start=date(2026, 1, 1), start_value="200000", exempt="0")
    cfg = TaxConfig(allowance=D(0))
    jan = project_tax([p], date(2027, 1, 1), date(2027, 1, 1), cfg)[0]
    rows = project_position(p, date(2027, 1, 1))
    vorab = vorabpauschale(p, rows, cfg)[2026]
    assert vorab > 0
    assert jan.vorab_paid == vorab * tax_rate(D(0))
    gain = rows[-1].balance - rows[-1].paid_in
    assert jan.sale_tax == (gain - vorab) * tax_rate(D(0))


def test_allowance_covers_small_depots_completely() -> None:
    p = _position(start_value="2000")
    months = project_tax([p], date(2024, 1, 1), date(2026, 1, 1), TaxConfig())
    assert all(m.vorab_paid == 0 for m in months)
    assert months[0].sale_tax == 0


def test_church_tax_raises_the_tax() -> None:
    p = _position(start_value="100000")
    plain = project_tax([p], date(2030, 1, 1), date(2030, 1, 1), TaxConfig())[0]
    church = project_tax([p], date(2030, 1, 1), date(2030, 1, 1), TaxConfig(church_tax=D("0.09")))[
        0
    ]
    assert church.total > plain.total


def test_losses_are_netted_across_positions() -> None:
    win = _position()
    loss = Position(**{**win.__dict__, "id": 2, "annual_return": D("-0.2")})
    both = project_tax([win, loss], date(2025, 12, 1), date(2025, 12, 1), TaxConfig(allowance=D(0)))
    alone = project_tax([win], date(2025, 12, 1), date(2025, 12, 1), TaxConfig(allowance=D(0)))
    assert both[0].sale_tax < alone[0].sale_tax
