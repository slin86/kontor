from datetime import date
from decimal import Decimal

import pytest

from kontor.domain.cashflow import (
    ActiveItem,
    CategoryInfo,
    FinancingFlow,
    VersionSpec,
    active_version,
    apply_change,
    build_sankey,
    end_item,
    monthly_amount,
    summarize,
)

D = Decimal


def m(year: int, month: int) -> date:
    return date(year, month, 1)


def test_monthly_amount_normalises_frequencies() -> None:
    assert monthly_amount(D("120"), "monthly") == D("120")
    assert monthly_amount(D("300"), "quarterly") == D("100")
    assert monthly_amount(D("1200"), "yearly") == D("100")


def test_change_cuts_open_version_and_leaves_history_alone() -> None:
    base = [VersionSpec(D("100"), "monthly", m(2026, 1))]
    result = apply_change(base, m(2026, 11), D("120"), "monthly")
    assert [(v.amount, v.valid_from, v.valid_to) for v in result] == [
        (D("100"), m(2026, 1), m(2026, 11)),
        (D("120"), m(2026, 11), None),
    ]
    assert active_version(result, m(2026, 10)).amount == D("100")  # type: ignore[union-attr]
    assert active_version(result, m(2027, 5)).amount == D("120")  # type: ignore[union-attr]


def test_change_keeps_later_planned_change() -> None:
    base = [
        VersionSpec(D("100"), "monthly", m(2026, 1), m(2027, 1)),
        VersionSpec(D("150"), "monthly", m(2027, 1)),
    ]
    result = apply_change(base, m(2026, 6), D("110"), "monthly")
    assert [(v.amount, v.valid_from, v.valid_to) for v in result] == [
        (D("100"), m(2026, 1), m(2026, 6)),
        (D("110"), m(2026, 6), m(2027, 1)),
        (D("150"), m(2027, 1), None),
    ]


def test_change_on_existing_start_replaces_that_version() -> None:
    base = [
        VersionSpec(D("100"), "monthly", m(2026, 1), m(2027, 1)),
        VersionSpec(D("150"), "monthly", m(2027, 1)),
    ]
    result = apply_change(base, m(2027, 1), D("160"), "monthly")
    assert [(v.amount, v.valid_from, v.valid_to) for v in result] == [
        (D("100"), m(2026, 1), m(2027, 1)),
        (D("160"), m(2027, 1), None),
    ]


def test_change_before_item_start_is_rejected() -> None:
    with pytest.raises(ValueError):
        apply_change([VersionSpec(D("1"), "monthly", m(2026, 5))], m(2026, 1), D("2"), "monthly")


def test_end_item_truncates_and_drops_later_versions() -> None:
    base = [
        VersionSpec(D("100"), "monthly", m(2026, 1), m(2027, 1)),
        VersionSpec(D("150"), "monthly", m(2027, 1)),
    ]
    result = end_item(base, m(2026, 7))
    assert [(v.valid_from, v.valid_to) for v in result] == [(m(2026, 1), m(2026, 7))]
    assert active_version(result, m(2026, 7)) is None


def test_end_item_before_start_is_rejected() -> None:
    with pytest.raises(ValueError):
        end_item([VersionSpec(D("1"), "monthly", m(2026, 5))], m(2026, 5))


CATS = [
    CategoryInfo(1, "Gehalt", "income"),
    CategoryInfo(2, "Wohnen", "expense"),
    CategoryInfo(3, "Miete", "expense", parent_id=2),
    CategoryInfo(4, "Strom", "expense", parent_id=2),
    CategoryInfo(5, "Freizeit", "expense"),
]


def test_summary_rolls_up_children_and_computes_balance() -> None:
    items = [
        ActiveItem(1, "Netto", 1, D("4000")),
        ActiveItem(2, "Miete", 3, D("1200")),
        ActiveItem(3, "Strom", 4, D("80")),
        ActiveItem(4, "Urlaub", 5, D("3000") / 12),
    ]
    s = summarize(CATS, items)
    assert s.income == D("4000.00")
    assert s.expenses == D("1530.00")
    assert s.balance == D("2470.00")
    assert s.savings_rate == D("0.6175")
    wohnen = next(g for g in s.expense_groups if g.name == "Wohnen")
    assert wohnen.total == D("1280.00")
    assert {c.name for c in wohnen.children} == {"Miete", "Strom"}


def test_sankey_surplus_and_deficit() -> None:
    surplus = build_sankey(
        CATS, [ActiveItem(1, "Netto", 1, D("100")), ActiveItem(2, "x", 5, D("40"))]
    )
    assert any(n.id == "surplus" for n in surplus.nodes)
    link = next(link for link in surplus.links if link.target == "surplus")
    assert link.value == D("60.00")

    deficit = build_sankey(
        CATS, [ActiveItem(1, "Netto", 1, D("10")), ActiveItem(2, "x", 5, D("40"))]
    )
    link = next(link for link in deficit.links if link.source == "deficit")
    assert link.value == D("30.00")


def test_sankey_without_data_has_only_the_hub() -> None:
    s = build_sankey(CATS, [])
    assert [n.id for n in s.nodes] == ["hub"]
    assert s.links == []


def test_financings_reduce_the_balance_and_appear_in_the_sankey() -> None:
    items = [ActiveItem(1, "Netto", 1, D("4000")), ActiveItem(2, "Essen", 5, D("500"))]
    flows = [
        FinancingFlow(7, "Haus", interest=D("600"), principal=D("500")),
        FinancingFlow(8, "Bausparer", saving=D("200"), fee=D("50")),
        FinancingFlow(9, "Leer"),  # nothing due this month
    ]
    s = summarize(CATS, items, flows)
    assert s.expenses == D("500.00")
    assert s.financing == D("1350.00")
    assert s.balance == D("2150.00")
    assert [f.name for f in s.financing_flows] == ["Haus", "Bausparer"]

    sk = build_sankey(CATS, items, flows)
    ids = {n.id for n in sk.nodes}
    assert {"financing", "financing:7", "financing:8", "purpose:interest", "purpose:saving"} <= ids
    assert "financing:9" not in ids
    interest = next(link for link in sk.links if link.target == "purpose:interest")
    assert interest.source == "financing:7" and interest.value == D("600.00")
    to_group = next(link for link in sk.links if link.target == "financing")
    assert to_group.value == D("1350.00")
    surplus = next(link for link in sk.links if link.target == "surplus")
    assert surplus.value == D("2150.00")
