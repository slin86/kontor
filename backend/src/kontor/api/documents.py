"""AI import of documents: contracts, loan and building savings contracts, broker statements.

The model only reads. Every number it returns is compared with the document text, and whatever
does not appear there is flagged for the user. Nothing is written without a preview, files are not
stored, and the text only goes to the local AI server.
"""

import base64
import binascii
import hashlib
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from kontor.api.actuals import resolve_instruments
from kontor.api.ai import (
    MONTHS_TO_FREQUENCY,
    UNAVAILABLE,
    AiNote,
    AnalyzeIn,
    Candidate,
    allowed_ids,
    categories,
    category_lines,
    existing_items,
    match_item,
)
from kontor.api.deps import CurrentUser, DbSession
from kontor.domain import broker_csv
from kontor.domain import statements as st
from kontor.domain import verify as vf
from kontor.models import DepotTransaction
from kontor.services import ai
from kontor.services import documents as docs
from kontor.services.audit import record as audit
from kontor.services.documents import DocumentError

router = APIRouter(prefix="/api/ai", tags=["ai"])

MAX_CHUNKS = 4  # a contract states its terms near the start; more is mostly small print
MAX_ROWS = 400


def _text(body: AnalyzeIn) -> str:
    try:
        raw = base64.b64decode(body.content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Die Datei ist beschädigt."
        ) from exc
    try:
        return docs.document_text(raw)
    except DocumentError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


def _read(text: str, accepted: set[str]) -> None:
    try:
        docs.require_kind(text, accepted)
    except DocumentError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except ai.AiUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, UNAVAILABLE) from exc


def _ask(system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
    try:
        return ai.complete_json(system, prompt, schema, allow_cloud=False).data
    except ai.AiUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, UNAVAILABLE) from exc


def _number(value: Any) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


# --------------------------------------------------------------------------------------
# contracts with regular payments -> cashflow items
# --------------------------------------------------------------------------------------


class ContractOut(BaseModel):
    candidates: list[Candidate]
    ai: AiNote


CONTRACT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "contracts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "amount": {"type": "number"},
                    "months": {"type": "integer", "enum": [0, 1, 3, 6, 12]},
                    "income": {"type": "boolean"},
                    "category_id": {"type": ["integer", "null"]},
                    "reason": {"type": "string"},
                },
                "required": ["name", "amount", "months", "income", "category_id", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["contracts"],
    "additionalProperties": False,
}


@router.post("/contracts/analyze", response_model=ContractOut)
def analyze_contract(body: AnalyzeIn, user: CurrentUser, db: DbSession) -> ContractOut:
    """A contract, policy or invoice: which regular payment does it cause?"""
    text = _text(body)
    _read(text, {"recurring_contract"})
    cats, label = categories(db, user.household_id)
    items = existing_items(db, user.household_id)
    system = (
        "Du liest den Text eines Vertrags, einer Police oder einer Rechnung (Versicherung, Strom, "
        "Gas, Internet, Mobilfunk, Miete, Kita, Verein, Abo, Gehalt ...). Gib jede Zahlung zurück, "
        "die regelmäßig anfällt: name (Anbieter und Art, kurz), amount (Betrag je Zahlung, "
        "nicht umgerechnet), months (Zahlweise: monatlich=1, vierteljährlich=3, halbjährlich=6, "
        "jährlich=12, einmalig=0), income (nur true bei Geld, das du bekommst), category_id (nur "
        "aus der Liste, sonst null). Nimm Beträge wörtlich aus dem Text. Erfinde nichts. "
        "reason ist ein kurzer deutscher Satz, z. B. mit Laufzeit oder Kündigungsfrist."
    )
    prompt_head = (
        f"Einnahmen-Kategorien:\n{category_lines(cats, label, True)}\n\n"
        f"Ausgaben-Kategorien:\n{category_lines(cats, label, False)}\n\nDokument:\n"
    )
    found: dict[tuple[str, Decimal], dict[str, Any]] = {}
    for chunk in docs.chunks(text)[:MAX_CHUNKS]:
        for row in _ask(system, prompt_head + chunk, CONTRACT_SCHEMA).get("contracts", []):
            amount = _number(row.get("amount")) if isinstance(row, dict) else None
            name = str(row.get("name") or "").strip()[:120] if isinstance(row, dict) else ""
            if amount and amount > 0 and name and row.get("months") in MONTHS_TO_FREQUENCY:
                found.setdefault((name.lower(), amount), row)

    candidates: list[Candidate] = []
    today = date.today()
    for (_, amount), row in found.items():
        income = bool(row.get("income"))
        item = match_item(st.counterparty_key(row["name"]), items)
        category_id = item.category_id if item else row.get("category_id")
        if category_id not in allowed_ids(cats, income):
            category_id = None
        candidates.append(
            Candidate(
                name=str(row["name"]).strip()[:120],
                amount=float(amount),
                income=income,
                frequency=MONTHS_TO_FREQUENCY[row["months"]],
                category_id=category_id,
                reason=str(row.get("reason") or "")[:300] or None,
                occurrences=1,
                first=today,
                last=today,
                source="document",
                check=None if vf.amount_in_text(text, amount) else "Betrag steht nicht im Text",
                existing_item_id=item.id if item else None,
                existing_item_name=item.name if item else None,
            )
        )
    return ContractOut(candidates=candidates, ai=AiNote(used=True, note=None))


# --------------------------------------------------------------------------------------
# loan, building savings and credit line contracts -> prefilled financing form
# --------------------------------------------------------------------------------------

FormKind = Literal["loan", "zero", "credit_line", "building_savings", "prefinanced"]

MONEY_FIELDS = (
    "principal",
    "monthly_payment",
    "contract_sum",
    "monthly_saving",
    "fee_amount",
    "loan_payment",
    "limit",
    "balance",
)
PERCENT_FIELDS = (
    "annual_rate_percent",
    "initial_repayment_percent",
    "fee_percent",
    "deposit_rate_percent",
    "prefinance_rate_percent",
    "loan_rate_percent",
)
MONTH_FIELDS = ("start", "allocation")


def _nullable(kind: str) -> dict[str, Any]:
    return {"type": [kind, "null"]}


FINANCING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "contract": {
            "type": "string",
            "enum": ["loan", "zero_percent_loan", "credit_line", "building_savings"],
        },
        "name": {"type": "string"},
        **{f: _nullable("number") for f in (*MONEY_FIELDS, *PERCENT_FIELDS)},
        **{f: {"type": ["string", "null"]} for f in MONTH_FIELDS},
    },
    "required": [
        "contract",
        "name",
        *MONEY_FIELDS,
        *PERCENT_FIELDS,
        *MONTH_FIELDS,
    ],
    "additionalProperties": False,
}


class FinancingDraft(BaseModel):
    form_kind: FormKind
    fields: dict[str, str]  # form field name -> value as plain text, "." as decimal separator
    unverified: list[str]  # fields whose value is not in the document text
    missing_note: str | None


@router.post("/financings/analyze", response_model=FinancingDraft)
def analyze_financing(body: AnalyzeIn, user: CurrentUser) -> FinancingDraft:
    """Loan, Bauspar or credit line contract: the values for the form, ready to be checked."""
    text = _text(body)
    _read(text, {"loan_contract", "building_savings_contract", "credit_line_contract"})
    system = (
        "Du liest einen Kredit-, Bauspar- oder Rahmenkreditvertrag. Fülle die Felder mit Werten "
        "aus dem Text, Beträge in Euro als Zahl, Zinsen in Prozent (3,45 % = 3.45), Monate als "
        "YYYY-MM. Felder, die nicht im Text stehen, sind null; rechne nichts aus und rate nichts. "
        "principal=Darlehensbetrag, annual_rate_percent=Sollzins p. a., monthly_payment=Rate, "
        "initial_repayment_percent=anfängliche Tilgung, start=Monat der ersten Rate, "
        "contract_sum=Bausparsumme, monthly_saving=Sparrate, allocation=geplante Zuteilung, "
        "fee_amount=Abschlussgebühr in Euro, fee_percent=Abschlussgebühr in Prozent, "
        "deposit_rate_percent=Guthabenzins, prefinance_rate_percent=Zins des Vorausdarlehens, "
        "loan_rate_percent=Darlehenszins, loan_payment=Rate in der Darlehensphase, "
        "limit=Rahmen, balance=aktuell genutzter Betrag."
    )
    merged: dict[str, Any] = {}
    for chunk in docs.chunks(text)[:MAX_CHUNKS]:
        data = _ask(system, chunk, FINANCING_SCHEMA)
        for key, value in data.items():
            if merged.get(key) in (None, "") and value not in (None, ""):
                merged[key] = value

    contract = merged.get("contract")
    form_kind: FormKind
    if contract == "building_savings":
        form_kind = "prefinanced" if merged.get("prefinance_rate_percent") else "building_savings"
    elif contract == "credit_line":
        form_kind = "credit_line"
    elif contract == "zero_percent_loan":
        form_kind = "zero"
    else:
        form_kind = "loan"

    fields: dict[str, str] = {}
    unverified: list[str] = []
    if merged.get("name"):
        fields["name"] = str(merged["name"]).strip()[:120]
    for key in (*MONEY_FIELDS, *PERCENT_FIELDS):
        number = _number(merged.get(key))
        if number is None:
            continue
        fields[key] = format(number.normalize(), "f")
        if not vf.amount_in_text(text, number):
            unverified.append(key)
    for key in MONTH_FIELDS:
        value = str(merged.get(key) or "")
        if len(value) == 7 and value[4] == "-" and value[:4].isdigit() and value[5:].isdigit():
            fields[key] = value
    note = None if len(fields) > 2 else "Aus dem Dokument konnten kaum Werte gelesen werden."
    return FinancingDraft(
        form_kind=form_kind, fields=fields, unverified=unverified, missing_note=note
    )


# --------------------------------------------------------------------------------------
# broker documents -> depot transactions
# --------------------------------------------------------------------------------------


class AiDepotIn(AnalyzeIn):
    mapping: dict[str, int] = Field(default_factory=dict)  # ISIN -> instrument id
    person_id: int | None = None


class AiRow(BaseModel):
    day: str
    kind: Literal["buy", "sell", "dividend"]
    amount: float
    fee: float
    shares: float | None
    isin: str | None
    name: str | None
    external_id: str
    instrument_id: int | None
    duplicate: bool
    check: str | None


class AiUnmatched(BaseModel):
    isin: str | None
    name: str | None
    count: int


class AiDepotPreview(BaseModel):
    rows: list[AiRow]
    unmatched: list[AiUnmatched]
    skipped: int
    method: Literal["csv", "ai"]
    new_count: int
    duplicate_count: int


BROKER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "rows": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "date": {"type": "string"},
                    "kind": {"type": "string", "enum": ["buy", "sell", "dividend", "other"]},
                    "isin": {"type": "string"},
                    "name": {"type": "string"},
                    "shares": {"type": ["number", "null"]},
                    "amount": {"type": "number"},
                    "fee": {"type": ["number", "null"]},
                },
                "required": ["date", "kind", "isin", "name", "shares", "amount", "fee"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["rows"],
    "additionalProperties": False,
}


def external_ids(rows: list[tuple[str, str, str | None, Decimal, Decimal | None]]) -> list[str]:
    """Stable ids for rows read by the AI; identical twins in one document get a counter."""
    seen: Counter[str] = Counter()
    out: list[str] = []
    for day, kind, isin, amount, shares in rows:
        base = f"ai|{day}|{kind}|{isin or ''}|{amount}|{shares if shares is not None else ''}"
        out.append(hashlib.sha1(f"{base}|{seen[base]}".encode(), usedforsecurity=False).hexdigest())
        seen[base] += 1
    return out


def _extract_broker(text: str) -> tuple[list[dict[str, Any]], int]:
    system = (
        "Du liest den Text einer Wertpapier-Abrechnung, eines Depotauszugs oder einer Orderliste. "
        "Gib jede Wertpapier-Transaktion zurück: date (YYYY-MM-DD), kind (buy=Kauf oder "
        "Sparplan-Ausführung, sell=Verkauf, dividend=Dividende oder Ausschüttung, other=alles "
        "andere), isin (12 Zeichen, sonst leerer String), name, shares (Stückzahl), amount (Betrag "
        "in Euro, immer positiv, ohne Gebühren), fee (Gebühren, sonst null). Nimm die Werte "
        "wörtlich aus dem Text, erfinde nichts, lass Salden und Summenzeilen weg."
    )
    rows: list[dict[str, Any]] = []
    skipped = 0
    for chunk in docs.chunks(text):
        for row in _ask(system, chunk, BROKER_SCHEMA).get("rows", []):
            if not isinstance(row, dict) or row.get("kind") == "other":
                skipped += 1
                continue
            rows.append(row)
        if len(rows) > MAX_ROWS:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Das Dokument ist zu groß.")
    return rows, skipped


def _ai_row(text: str, row: dict[str, Any]) -> tuple[Any, ...] | None:
    """Validate one row from the model; ``None`` when it is unusable."""
    try:
        day = date.fromisoformat(str(row["date"]).strip()[:10])
    except (KeyError, ValueError):
        return None
    amount = _number(row.get("amount"))
    if amount is None or amount <= 0 or row.get("kind") not in ("buy", "sell", "dividend"):
        return None
    amount = abs(amount)
    fee = _number(row.get("fee")) or Decimal(0)
    shares = _number_exact(row.get("shares"))
    isin = str(row.get("isin") or "").replace(" ", "").upper() or None
    problems: list[str] = []
    if isin is not None and not (vf.isin_valid(isin) and vf.isin_in_text(text, isin)):
        problems.append("ISIN")
        if not vf.isin_valid(isin):
            isin = None  # a broken ISIN would never match a position
    if not vf.amount_in_text(text, amount):
        problems.append("Betrag")
    if shares is not None and not vf.quantity_in_text(text, shares):
        problems.append("Stückzahl")
    if not vf.date_in_text(text, day):
        problems.append("Datum")
    check = f"Bitte prüfen: {', '.join(problems)} nicht im Text" if problems else None
    name = str(row.get("name") or "").strip()[:160] or None
    return day, row["kind"], isin, amount, abs(fee), shares, name, check


def _number_exact(value: Any) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        d = Decimal(str(value)).normalize()
    except InvalidOperation:
        return None
    return abs(d) if d != 0 else None


@router.post("/depot/analyze", response_model=AiDepotPreview)
def analyze_depot(body: AiDepotIn, user: CurrentUser, db: DbSession) -> AiDepotPreview:
    """Broker CSV (any layout) or PDF: transactions to review before they are stored."""
    try:
        raw = base64.b64decode(body.content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Die Datei ist beschädigt."
        ) from exc
    by_isin, existing = resolve_instruments(db, user, body.mapping, body.person_id)

    parsed: list[tuple[Any, ...]] = []
    skipped = 0
    method: Literal["csv", "ai"] = "ai"
    ids: list[str] = []
    if raw[:5] != b"%PDF-":
        try:
            result = broker_csv.parse_broker_csv(docs.decode_text(raw))
            if result.rows:
                method = "csv"
                skipped = sum(result.skipped.values())
                for r in result.rows:
                    parsed.append((r.day, r.kind, r.isin, r.amount, r.fee, r.shares, r.name, None))
                    ids.append(r.external_id)
        except broker_csv.CsvError:
            pass
    if method == "ai":
        try:
            text = docs.document_text(raw)
        except DocumentError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        _read(text, {"broker_statement"})
        rows, skipped = _extract_broker(text)
        for row in rows:
            item = _ai_row(text, row)
            if item is None:
                skipped += 1
            else:
                parsed.append(item)
        ids = external_ids([(p[0].isoformat(), p[1], p[2], p[3], p[5]) for p in parsed])

    out: list[AiRow] = []
    unmatched: dict[str | None, AiUnmatched] = {}
    for (day, kind, isin, amount, fee, shares, name, check), ext in zip(parsed, ids, strict=True):
        target = by_isin.get(isin) if isin else None
        out.append(
            AiRow(
                day=day.isoformat(),
                kind=kind,
                amount=float(amount),
                fee=float(fee),
                shares=float(shares) if shares is not None else None,
                isin=isin,
                name=name,
                external_id=ext,
                instrument_id=target,
                duplicate=ext in existing,
                check=check,
            )
        )
        if target is None:
            entry = unmatched.setdefault(isin, AiUnmatched(isin=isin, name=name, count=0))
            entry.count += 1
    return AiDepotPreview(
        rows=out,
        unmatched=list(unmatched.values()),
        skipped=skipped,
        method=method,
        new_count=sum(1 for r in out if not r.duplicate and r.instrument_id is not None),
        duplicate_count=sum(1 for r in out if r.duplicate),
    )


class AiRowIn(BaseModel):
    day: date
    kind: Literal["buy", "sell", "dividend"]
    amount: Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)]
    fee: Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=2)] = Decimal(0)
    shares: Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=8)] | None = None
    isin: str | None = Field(default=None, max_length=12)
    name: str | None = Field(default=None, max_length=160)
    external_id: str = Field(min_length=8, max_length=64)


class AiImportIn(BaseModel):
    rows: list[AiRowIn] = Field(max_length=MAX_ROWS)
    mapping: dict[str, int] = Field(default_factory=dict)
    person_id: int | None = None
    source: Literal["csv", "ai"] = "ai"


class AiImportOut(BaseModel):
    imported: int
    duplicates: int
    unmatched: int


@router.post("/depot/import", response_model=AiImportOut)
def import_depot(body: AiImportIn, user: CurrentUser, db: DbSession) -> AiImportOut:
    """Store the rows the user kept. Rows seen before (same id) are skipped."""
    by_isin, existing = resolve_instruments(db, user, body.mapping, body.person_id)
    imported = duplicates = unmatched = 0
    touched: Counter[int] = Counter()
    for r in body.rows:
        target = by_isin.get(r.isin.upper()) if r.isin else None
        if target is None:
            unmatched += 1
            continue
        if r.external_id in existing:
            duplicates += 1
            continue
        existing.add(r.external_id)
        db.add(
            DepotTransaction(
                household_id=user.household_id,
                instrument_id=target,
                day=r.day,
                kind=r.kind,
                amount=r.amount,
                fee=r.fee,
                shares=r.shares,
                isin=r.isin.upper() if r.isin else None,
                name=r.name,
                source=body.source,
                external_id=r.external_id,
            )
        )
        touched[target] += 1
        imported += 1
    db.flush()
    for instrument_id, count in touched.items():
        audit(db, user, "import", "instrument", instrument_id, after={"transactions": count})
    return AiImportOut(imported=imported, duplicates=duplicates, unmatched=unmatched)
