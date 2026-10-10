"""AI helper: category and rhythm suggestions for items, and bank statement analysis.

Statements and anything derived from them only ever go to the local AI server. The optional cloud
key is used for a single item name typed into the form, nothing else.
"""

import base64
import binascii
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from kontor.api.deps import CurrentUser, DbSession
from kontor.domain import statements as st
from kontor.models import CashflowItem, Category
from kontor.services import ai
from kontor.services import documents as docs
from kontor.services.documents import DocumentError, decode_text, pdf_pages

router = APIRouter(prefix="/api/ai", tags=["ai"])

MONTHS_TO_FREQUENCY = {1: "monthly", 3: "quarterly", 6: "semiannual", 12: "yearly"}
MAX_UPLOAD_CHARS = 14_000_000  # base64, about 10 MB
CLASSIFY_BATCH = 30
MAX_SINGLES = 60
UNAVAILABLE = "Der KI-Server ist nicht erreichbar. Starte den Rechner und versuche es erneut."


class StatusOut(BaseModel):
    local_configured: bool
    local_reachable: bool
    local_model: str | None
    cloud_configured: bool


@router.get("/status", response_model=StatusOut)
def get_status(user: CurrentUser) -> StatusOut:
    s = ai.status()
    return StatusOut(
        local_configured=s.local_configured,
        local_reachable=s.local_reachable,
        local_model=s.local_model,
        cloud_configured=s.cloud_configured,
    )


# --------------------------------------------------------------------------------------
# shared helpers
# --------------------------------------------------------------------------------------


def categories(db: DbSession, household_id: int) -> tuple[list[Category], dict[int, str]]:
    cats = list(
        db.scalars(
            select(Category)
            .where(Category.household_id == household_id)
            .order_by(Category.sort_order, Category.id)
        )
    )
    by_id = {c.id: c for c in cats}
    label = {
        c.id: f"{by_id[c.parent_id].name} / {c.name}" if c.parent_id in by_id else c.name
        for c in cats
    }
    return cats, label


def category_lines(cats: list[Category], label: dict[int, str], income: bool | None) -> str:
    """Categories that can hold an item; a group with children is not offered itself."""
    parents = {c.parent_id for c in cats if c.parent_id}
    return "\n".join(
        f"{c.id}: {label[c.id]}"
        for c in cats
        if c.id not in parents and (income is None or (c.kind.value == "income") == income)
    )


def allowed_ids(cats: list[Category], income: bool | None) -> set[int]:
    parents = {c.parent_id for c in cats if c.parent_id}
    return {
        c.id
        for c in cats
        if c.id not in parents and (income is None or (c.kind.value == "income") == income)
    }


def existing_items(db: DbSession, household_id: int) -> list[CashflowItem]:
    return list(
        db.scalars(
            select(CashflowItem)
            .where(CashflowItem.household_id == household_id)
            .options(selectinload(CashflowItem.versions))
            .order_by(CashflowItem.name)
        )
    )


def match_item(key: str, items: list[CashflowItem]) -> CashflowItem | None:
    if len(key) < 3:
        return None
    for item in items:
        ik = st.counterparty_key(item.name)
        if ik and (ik == key or (len(ik) >= 4 and (ik in key or key in ik))):
            return item
    return None


# --------------------------------------------------------------------------------------
# suggestion for one item name
# --------------------------------------------------------------------------------------


class SuggestIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    income: bool | None = None  # known from the form when the amount was entered first


class SuggestOut(BaseModel):
    category_id: int | None
    recurring: bool | None
    frequency: Literal["monthly", "quarterly", "semiannual", "yearly"] | None
    reason: str | None
    source: Literal["existing", "local", "cloud", "none"]


SUGGEST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "category_id": {"type": ["integer", "null"]},
        "recurring": {"type": "boolean"},
        "months": {"type": "integer", "enum": [0, 1, 3, 6, 12]},
        "reason": {"type": "string"},
    },
    "required": ["category_id", "recurring", "months", "reason"],
    "additionalProperties": False,
}


@router.post("/suggest", response_model=SuggestOut)
def suggest(body: SuggestIn, user: CurrentUser, db: DbSession) -> SuggestOut:
    """Category and rhythm for an item name: from the household's own items first, then the AI."""
    name = body.name.strip()
    items = existing_items(db, user.household_id)
    same = next((i for i in items if i.name.strip().lower() == name.lower()), None)
    if same is not None and same.versions:
        latest = same.versions[-1]
        return SuggestOut(
            category_id=same.category_id,
            recurring=True,
            frequency=latest.frequency.value,
            reason="Einen Posten mit diesem Namen gibt es schon.",
            source="existing",
        )

    cats, label = categories(db, user.household_id)
    allowed = allowed_ids(cats, body.income)
    if not allowed:
        return SuggestOut(
            category_id=None, recurring=None, frequency=None, reason=None, source="none"
        )
    examples = "\n".join(
        f"- {i.name} → {label.get(i.category_id, '?')}"
        for i in items[:25]
        if i.category_id in allowed
    )
    system = (
        "Du hilfst bei einer Haushaltsfinanz-App. Ordne einen Posten einer Kategorie zu und schätze, "  # noqa: E501
        "ob er regelmäßig wiederkehrt (monatlich=1, vierteljährlich=3, halbjährlich=6, jährlich=12, "  # noqa: E501
        "einmalig oder unklar=0). Wähle category_id ausschließlich aus der Liste, sonst null. "
        "Antworte knapp auf Deutsch; reason ist ein kurzer Satz."
    )
    prompt = f"Kategorien:\n{category_lines(cats, label, body.income)}\n\n"
    if examples:
        prompt += f"Bisherige Zuordnungen des Nutzers:\n{examples}\n\n"
    prompt += f"Posten: {name}"
    try:
        answer = ai.complete_json(system, prompt, SUGGEST_SCHEMA, allow_cloud=True)
    except ai.AiUnavailable:
        return SuggestOut(
            category_id=None, recurring=None, frequency=None, reason=None, source="none"
        )
    data = answer.data
    category_id = data.get("category_id")
    months = data.get("months")
    return SuggestOut(
        category_id=category_id if category_id in allowed else None,
        recurring=bool(data.get("recurring")) and months in MONTHS_TO_FREQUENCY,
        frequency=MONTHS_TO_FREQUENCY.get(months) if isinstance(months, int) else None,
        reason=str(data.get("reason") or "")[:300] or None,
        source=answer.via,
    )


# --------------------------------------------------------------------------------------
# bank statement analysis
# --------------------------------------------------------------------------------------


class AnalyzeIn(BaseModel):
    filename: str = Field(max_length=200)
    content_base64: str = Field(max_length=MAX_UPLOAD_CHARS)


class Candidate(BaseModel):
    name: str
    amount: float
    income: bool
    frequency: Literal["monthly", "quarterly", "semiannual", "yearly"]
    category_id: int | None
    reason: str | None
    occurrences: int
    first: date
    last: date
    source: Literal["pattern", "ai", "document"]
    check: str | None = None  # why the user should look at this row twice
    existing_item_id: int | None
    existing_item_name: str | None


class AiNote(BaseModel):
    used: bool
    note: str | None


class AnalyzeOut(BaseModel):
    format: Literal["csv", "camt", "mt940", "pdf"]
    lines: int
    period_from: date
    period_to: date
    candidates: list[Candidate]
    unrated: int  # single payments nobody judged because the AI was off
    ai: AiNote


EXTRACT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "date": {"type": "string"},
                    "amount": {"type": "number"},
                    "counterparty": {"type": "string"},
                    "purpose": {"type": "string"},
                },
                "required": ["date", "amount", "counterparty", "purpose"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["lines"],
    "additionalProperties": False,
}

CLASSIFY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "category_id": {"type": ["integer", "null"]},
                    "recurring": {"type": "boolean"},
                    "months": {"type": "integer", "enum": [0, 1, 3, 6, 12]},
                    "reason": {"type": "string"},
                },
                "required": ["index", "category_id", "recurring", "months", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


def _extract_from_pdf(pages: list[str]) -> list[st.BankLine]:
    text = "\n".join(pages)
    docs.require_kind(text, {"bank_statement"})
    chunks = docs.chunks(text)

    system = (
        "Du liest den Text eines deutschen Kontoauszugs. Gib jede einzelne Buchung zurück: Datum "
        "als YYYY-MM-DD, Betrag als Zahl (Abbuchungen negativ, Gutschriften positiv), Name der "
        "Gegenseite und Verwendungszweck. Lass Salden, Zwischensummen und Kopfzeilen weg. "
        "Erfinde nichts; was nicht im Text steht, bleibt ein leerer String."
    )
    lines: list[st.BankLine] = []
    for chunk in chunks:
        answer = ai.complete_json(system, chunk, EXTRACT_SCHEMA, allow_cloud=False)
        for row in answer.data.get("lines", []):
            try:
                lines.append(
                    st.BankLine(
                        st.parse_day(str(row["date"])),
                        Decimal(str(round(float(row["amount"]), 2))),
                        str(row.get("counterparty", "")).strip(),
                        str(row.get("purpose", "")).strip(),
                    )
                )
            except (st.StatementError, KeyError, ValueError, InvalidOperation):
                continue  # a row the model got wrong is better skipped than guessed
    return lines


COLUMNS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "header_row": {"type": "integer"},
        "date": {"type": "integer"},
        "amount": {"type": ["integer", "null"]},
        "debit": {"type": ["integer", "null"]},
        "credit": {"type": ["integer", "null"]},
        "counterparty": {"type": ["integer", "null"]},
        "purpose": {"type": ["integer", "null"]},
    },
    "required": ["header_row", "date", "amount", "debit", "credit", "counterparty", "purpose"],
    "additionalProperties": False,
}


def _map_csv(text: str) -> st.CsvColumns:
    """A CSV with headers nobody has seen: the AI only says which column is which."""
    rows = st.csv_rows(text)
    sample = rows[:12]
    width = max((len(r) for r in sample), default=0)
    system = (
        "Du bekommst die ersten Zeilen einer CSV-Datei einer Bank oder eines Kreditkarten-"
        "Anbieters (Zeilen und Spalten ab 0 nummeriert). Gib an, in welcher Zeile die "
        "Spaltenüberschriften stehen und in welcher Spalte Buchungsdatum, Betrag (mit Vorzeichen) "
        "oder getrennt Soll/Haben, Name der Gegenseite und Verwendungszweck stehen. Spalten, die "
        "es nicht gibt, sind null. Rate nichts."
    )
    prompt = "\n".join(
        f"{i}: " + " | ".join(f"[{j}] {c}" for j, c in enumerate(r)) for i, r in enumerate(sample)
    )
    answer = ai.complete_json(system, prompt, COLUMNS_SCHEMA, allow_cloud=False)
    d = answer.data

    def col(key: str) -> int | None:
        v = d.get(key)
        return v if isinstance(v, int) and 0 <= v < width else None

    day, amount = col("date"), col("amount")
    debit, credit = col("debit"), col("credit")
    header = d.get("header_row")
    if day is None or not isinstance(header, int) or not 0 <= header < len(sample):
        raise st.StatementError("Die Spalten dieser CSV-Datei konnten nicht erkannt werden.")
    if amount is None and (debit is None or credit is None):
        raise st.StatementError("Die Spalten dieser CSV-Datei konnten nicht erkannt werden.")
    cols = st.CsvColumns(header, day, amount, debit, credit, col("counterparty"), col("purpose"))
    if not st.read_csv(rows, cols):
        raise st.StatementError("Die Spalten dieser CSV-Datei konnten nicht erkannt werden.")
    return cols


def _read_lines(raw: bytes) -> tuple[Literal["csv", "camt", "mt940", "pdf"], list[st.BankLine]]:
    if raw[:5] == b"%PDF-":
        return "pdf", _extract_from_pdf(pdf_pages(raw))
    text = decode_text(raw)
    head = text[:2000]
    if "<Document" in head or "camt.053" in head or head.lstrip().startswith("<?xml"):
        return "camt", st.parse_camt(text)
    if ":20:" in head and ":61:" in text:
        return "mt940", st.parse_mt940(text)
    try:
        return "csv", st.parse_csv(text)
    except st.UnknownCsv:
        return "csv", st.read_csv(st.csv_rows(text), _map_csv(text))


def _classify(
    entries: list[dict[str, Any]], cats: list[Category], label: dict[int, str]
) -> dict[int, dict[str, Any]] | None:
    """Category and "does it come back?" for payees, in batches. ``None`` when the AI is off."""
    results: dict[int, dict[str, Any]] = {}
    system = (
        "Du hilfst bei einer Haushaltsfinanz-App. Zu jeder Zahlung aus einem Kontoauszug: wähle die "  # noqa: E501
        "passende Kategorie (category_id nur aus der Liste, sonst null) und schätze, ob sie "
        "regelmäßig wiederkehrt (monatlich=1, vierteljährlich=3, halbjährlich=6, jährlich=12, "
        "einmalig=0). Tankstellen, Supermärkte und Restaurants sind einmalig. Verträge, Abos, "
        "Versicherungen, Miete, Gehalt wiederkehrend. Gib für jede index genau einen Eintrag "
        "zurück; reason ist ein kurzer deutscher Satz."
    )
    for start in range(0, len(entries), CLASSIFY_BATCH):
        batch = entries[start : start + CLASSIFY_BATCH]
        by_kind = {
            True: category_lines(cats, label, True),
            False: category_lines(cats, label, False),
        }
        prompt = (
            f"Einnahmen-Kategorien:\n{by_kind[True]}\n\nAusgaben-Kategorien:\n{by_kind[False]}\n\n"
        )
        prompt += "Zahlungen:\n" + "\n".join(
            f"{e['index']}: {'Einnahme' if e['income'] else 'Ausgabe'} {e['amount']} EUR, "
            f"{e['name']}, {e['purpose']}"
            + (f" (kommt {e['count']}x vor)" if e["count"] > 1 else "")
            for e in batch
        )
        try:
            answer = ai.complete_json(system, prompt, CLASSIFY_SCHEMA, allow_cloud=False)
        except ai.AiUnavailable:
            return None
        for row in answer.data.get("items", []):
            if isinstance(row, dict) and isinstance(row.get("index"), int):
                results[row["index"]] = row
    return results


@router.post("/statements/analyze", response_model=AnalyzeOut)
def analyze_statement(body: AnalyzeIn, user: CurrentUser, db: DbSession) -> AnalyzeOut:
    """Read a statement (CSV, CAMT.053, MT940 or a PDF with text) and propose recurring items."""
    try:
        raw = base64.b64decode(body.content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Die Datei ist beschädigt."
        ) from exc
    try:
        fmt, lines = _read_lines(raw)
    except (st.StatementError, DocumentError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except ai.AiUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, UNAVAILABLE) from exc
    if not lines:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Es wurden keine Buchungen gefunden."
        )

    recurring, rest = st.find_recurring(lines)
    cats, label = categories(db, user.household_id)
    items = existing_items(db, user.household_id)

    # single payments: one entry per payee, the AI decides whether any of them is a regular one
    singles: dict[str, st.BankLine] = {}
    for line in rest:
        key = st.counterparty_key(line.counterparty, line.purpose)
        if key and key not in singles:
            singles[key] = line
    single_keys = sorted(singles, key=lambda k: -abs(singles[k].amount))[:MAX_SINGLES]

    entries: list[dict[str, Any]] = []
    for r in recurring:
        entries.append(
            {
                "index": len(entries),
                "income": r.income,
                "amount": str(r.amount),
                "name": r.name,
                "purpose": r.purpose,
                "count": r.count,
            }
        )
    for key in single_keys:
        line = singles[key]
        entries.append(
            {
                "index": len(entries),
                "income": line.amount > 0,
                "amount": str(abs(line.amount)),
                "name": line.counterparty or line.purpose,
                "purpose": line.purpose,
                "count": 1,
            }
        )
    judged = _classify(entries, cats, label) if entries else {}

    candidates: list[Candidate] = []

    def add(
        index: int,
        *,
        name: str,
        amount: Decimal,
        income: bool,
        months: int,
        count: int,
        first: date,
        last: date,
        source: Literal["pattern", "ai"],
        key: str,
    ) -> None:
        verdict = (judged or {}).get(index, {})
        item = match_item(key, items)
        category_id = item.category_id if item else verdict.get("category_id")
        if category_id not in allowed_ids(cats, income):
            category_id = None
        candidates.append(
            Candidate(
                name=name,
                amount=float(amount),
                income=income,
                frequency=MONTHS_TO_FREQUENCY[months],
                category_id=category_id,
                reason=(str(verdict.get("reason") or "")[:300] or None) if verdict else None,
                occurrences=count,
                first=first,
                last=last,
                source=source,
                existing_item_id=item.id if item else None,
                existing_item_name=item.name if item else None,
            )
        )

    for index, r in enumerate(recurring):
        add(
            index,
            name=r.name,
            amount=r.amount,
            income=r.income,
            months=r.months,
            count=r.count,
            first=r.first,
            last=r.last,
            source="pattern",
            key=r.key,
        )
    unrated = 0
    for offset, key in enumerate(single_keys):
        index = len(recurring) + offset
        line = singles[key]
        verdict = (judged or {}).get(index)
        if judged is None:
            unrated += 1
        elif verdict and verdict.get("recurring") and verdict.get("months") in MONTHS_TO_FREQUENCY:
            add(
                index,
                name=(line.counterparty or line.purpose)[:120],
                amount=abs(line.amount),
                income=line.amount > 0,
                months=int(verdict["months"]),
                count=1,
                first=line.day,
                last=line.day,
                source="ai",
                key=key,
            )

    days = [x.day for x in lines]
    note = (
        None
        if judged is not None
        else (
            "Der KI-Server war nicht erreichbar. Kategorien und einzelne Buchungen wurden nicht bewertet."  # noqa: E501
        )
    )
    return AnalyzeOut(
        format=fmt,
        lines=len(lines),
        period_from=min(days),
        period_to=max(days),
        candidates=candidates,
        unrated=unrated if judged is None else 0,
        ai=AiNote(used=judged is not None, note=note),
    )
