"""Pure cashflow logic: versioned periods, monthly normalisation, summaries and Sankey data.

Nothing in here touches the database or HTTP, so it can be tested in isolation.
All amounts are ``Decimal``.
"""

from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
FREQUENCY_MONTHS = {"monthly": 1, "quarterly": 3, "yearly": 12}


def cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def monthly_amount(amount: Decimal, frequency: str) -> Decimal:
    """Monthly equivalent of an amount that is paid once per ``frequency``."""
    return amount / FREQUENCY_MONTHS[frequency]


# --------------------------------------------------------------------------------------
# Effective-dated versions
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class VersionSpec:
    """One version of an item. ``valid_to`` is exclusive; ``None`` means open-ended."""

    amount: Decimal
    frequency: str
    valid_from: date
    valid_to: date | None = None
    id: int | None = None

    def covers(self, month: date) -> bool:
        return self.valid_from <= month and (self.valid_to is None or month < self.valid_to)


def active_version(versions: list[VersionSpec], month: date) -> VersionSpec | None:
    for v in versions:
        if v.covers(month):
            return v
    return None


def apply_change(
    versions: list[VersionSpec], effective_from: date, amount: Decimal, frequency: str
) -> list[VersionSpec]:
    """Change an item from ``effective_from`` onwards.

    The version covering that month is cut off at ``effective_from``; the new version runs until
    the next already planned change (or the end of the cut version). Months before
    ``effective_from`` are never touched.
    """
    ordered = sorted(versions, key=lambda v: v.valid_from)
    if not ordered:
        raise ValueError("Item has no versions")
    if effective_from < ordered[0].valid_from:
        raise ValueError("Change lies before the start of the item")

    kept: list[VersionSpec] = []
    new_valid_to: date | None = None
    boundaries: list[date] = []

    for v in ordered:
        if v.valid_to is not None and v.valid_to <= effective_from:
            kept.append(v)  # entirely before the change
        elif v.valid_from == effective_from:
            # Replaced by the new version, which inherits its end.
            if v.valid_to is not None:
                boundaries.append(v.valid_to)
        elif v.valid_from > effective_from:
            kept.append(v)  # a later, already planned change stays in place
            boundaries.append(v.valid_from)
        else:
            # The version covering ``effective_from`` is cut off there.
            kept.append(replace(v, valid_to=effective_from))
            if v.valid_to is not None:
                boundaries.append(v.valid_to)

    if boundaries:
        new_valid_to = min(boundaries)
    kept.append(VersionSpec(amount, frequency, effective_from, new_valid_to))
    return sorted(kept, key=lambda v: v.valid_from)


def end_item(versions: list[VersionSpec], end_from: date) -> list[VersionSpec]:
    """The item no longer applies from ``end_from`` on (that month is the first one without it)."""
    ordered = sorted(versions, key=lambda v: v.valid_from)
    if not ordered or end_from <= ordered[0].valid_from:
        raise ValueError("End date must lie after the start of the item")
    result: list[VersionSpec] = []
    for v in ordered:
        if v.valid_from >= end_from:
            continue
        if v.valid_to is None or v.valid_to > end_from:
            v = replace(v, valid_to=end_from)
        result.append(v)
    return result


# --------------------------------------------------------------------------------------
# Aggregation
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class CategoryInfo:
    id: int
    name: str
    kind: str  # "income" | "expense"
    parent_id: int | None = None


@dataclass(frozen=True)
class ActiveItem:
    item_id: int
    name: str
    category_id: int
    monthly: Decimal


@dataclass(frozen=True)
class FinancingFlow:
    """What one financing costs in a month, split by purpose (all values >= 0)."""

    financing_id: int
    name: str
    interest: Decimal = Decimal(0)
    principal: Decimal = Decimal(0)
    saving: Decimal = Decimal(0)
    fee: Decimal = Decimal(0)

    @property
    def total(self) -> Decimal:
        return self.interest + self.principal + self.saving + self.fee


@dataclass(frozen=True)
class GroupSummary:
    category_id: int
    name: str
    kind: str
    total: Decimal
    children: list["GroupSummary"]


@dataclass(frozen=True)
class Summary:
    income: Decimal
    expenses: Decimal  # running costs from cashflow items, without financings
    financing: Decimal  # everything paid for financings (interest, repayment, saving, fees)
    balance: Decimal  # income - expenses - financing
    savings_rate: Decimal | None  # balance / income, ``None`` without income
    income_groups: list[GroupSummary]
    expense_groups: list[GroupSummary]
    financing_flows: list[FinancingFlow]


def summarize(
    categories: list[CategoryInfo],
    items: list[ActiveItem],
    financings: list[FinancingFlow] | None = None,
) -> Summary:
    cats = {c.id: c for c in categories}
    totals: dict[int, Decimal] = defaultdict(Decimal)
    for it in items:
        totals[it.category_id] += it.monthly

    def group(top: CategoryInfo) -> GroupSummary:
        child_ids = [c.id for c in categories if c.parent_id == top.id]
        children = [
            GroupSummary(cid, cats[cid].name, top.kind, cents(totals[cid]), [])
            for cid in child_ids
            if totals[cid] != 0
        ]
        total = totals[top.id] + sum((totals[cid] for cid in child_ids), Decimal())
        return GroupSummary(top.id, top.name, top.kind, cents(total), children)

    tops = [c for c in categories if c.parent_id is None]
    groups = [g for g in (group(t) for t in tops) if g.total != 0]
    income_groups = sorted((g for g in groups if g.kind == "income"), key=lambda g: -g.total)
    expense_groups = sorted((g for g in groups if g.kind == "expense"), key=lambda g: -g.total)

    flows = [
        FinancingFlow(
            f.financing_id,
            f.name,
            cents(f.interest),
            cents(f.principal),
            cents(f.saving),
            cents(f.fee),
        )
        for f in (financings or [])
        if f.total != 0
    ]
    income = sum((g.total for g in income_groups), Decimal())
    expenses = sum((g.total for g in expense_groups), Decimal())
    financing = sum((f.total for f in flows), Decimal())
    balance = income - expenses - financing
    rate = (balance / income).quantize(Decimal("0.0001")) if income else None
    return Summary(income, expenses, financing, balance, rate, income_groups, expense_groups, flows)


# --------------------------------------------------------------------------------------
# Sankey
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SankeyNode:
    id: str
    name: str
    kind: str  # income | hub | expense | financing | purpose | surplus | deficit


@dataclass(frozen=True)
class SankeyLink:
    source: str
    target: str
    value: Decimal


@dataclass(frozen=True)
class Sankey:
    nodes: list[SankeyNode]
    links: list[SankeyLink]


HUB_ID = "hub"


def build_sankey(
    categories: list[CategoryInfo],
    items: list[ActiveItem],
    financings: list[FinancingFlow] | None = None,
) -> Sankey:
    """Income sources -> household -> expense groups -> sub-categories, plus surplus/deficit."""
    summary = summarize(categories, items, financings)
    nodes: list[SankeyNode] = [SankeyNode(HUB_ID, "Haushalt", "hub")]
    links: list[SankeyLink] = []

    for g in summary.income_groups:
        nid = f"income:{g.category_id}"
        nodes.append(SankeyNode(nid, g.name, "income"))
        links.append(SankeyLink(nid, HUB_ID, g.total))

    for g in summary.expense_groups:
        nid = f"expense:{g.category_id}"
        nodes.append(SankeyNode(nid, g.name, "expense"))
        links.append(SankeyLink(HUB_ID, nid, g.total))
        for child in g.children:
            cid = f"expense:{child.category_id}"
            nodes.append(SankeyNode(cid, child.name, "expense"))
            links.append(SankeyLink(nid, cid, child.total))

    if summary.financing_flows:
        nodes.append(SankeyNode("financing", "Finanzierungen", "financing"))
        links.append(SankeyLink(HUB_ID, "financing", summary.financing))
        purposes = {
            "interest": "Zinsen",
            "principal": "Tilgung",
            "saving": "Bausparen",
            "fee": "Gebühren",
        }
        used: dict[str, Decimal] = {}
        for f in summary.financing_flows:
            fid = f"financing:{f.financing_id}"
            nodes.append(SankeyNode(fid, f.name, "financing"))
            links.append(SankeyLink("financing", fid, f.total))
            for key in purposes:
                value = getattr(f, key)
                if value > 0:
                    links.append(SankeyLink(fid, f"purpose:{key}", value))
                    used[key] = used.get(key, Decimal(0)) + value
        for key, label in purposes.items():
            if key in used:
                nodes.append(SankeyNode(f"purpose:{key}", label, "purpose"))

    if summary.balance > 0:
        nodes.append(SankeyNode("surplus", "Übrig", "surplus"))
        links.append(SankeyLink(HUB_ID, "surplus", summary.balance))
    elif summary.balance < 0:
        nodes.append(SankeyNode("deficit", "Fehlbetrag", "deficit"))
        links.append(SankeyLink("deficit", HUB_ID, -summary.balance))

    return Sankey(nodes, links)
