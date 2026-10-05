"""Tolerant parser for broker CSV exports (built against Trade Republic's transaction export).

The real export format is not publicly specified and has changed over time, so the parser works
on normalised header names and a few known layouts instead of fixed column positions::

    datetime,date,account_type,category,type,asset_class,name,symbol,shares,price,amount,fee,tax,...
    Date,Type,Ticker,ISIN,Shares,Price,Amount,Currency,Fee,Tax

Only securities orders (buy, sell, savings plan) and dividends are imported. Everything else
(card payments, deposits, interest, corporate actions, ...) is counted and reported, never guessed.
"""

import csv
import hashlib
import io
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

ISIN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
MAX_ROWS = 20000

ALIASES: dict[str, tuple[str, ...]] = {
    "day": ("date", "datum", "datetime", "buchungsdatum", "timestamp"),
    "category": ("category", "kategorie"),
    "type": ("type", "typ", "transaction_type", "transaktionstyp"),
    "name": ("name", "security_name", "bezeichnung", "asset_name"),
    "symbol": ("symbol", "ticker"),
    "isin": ("isin",),
    "shares": ("shares", "quantity", "stuecke", "stücke", "anzahl"),
    "price": ("price", "kurs", "preis"),
    "amount": ("amount", "betrag", "net_value", "gross_value", "value"),
    "fee": ("fee", "gebuehr", "gebühr", "gebuehren", "gebühren"),
    "description": ("description", "beschreibung"),
    "external_id": ("transaction_id", "id", "order_id"),
}


class CsvError(ValueError):
    """The file cannot be read as a transaction export."""


@dataclass(frozen=True)
class ParsedTransaction:
    day: date
    kind: str  # "buy" | "sell" | "dividend"
    amount: Decimal  # money moved, always positive for buy and sell
    fee: Decimal
    shares: Decimal | None
    isin: str | None
    name: str | None
    external_id: str
    line: int


@dataclass
class ParseResult:
    rows: list[ParsedTransaction] = field(default_factory=list)
    skipped: dict[str, int] = field(default_factory=dict)  # reason -> count
    errors: list[str] = field(default_factory=list)  # unreadable data rows


def parse_number(raw: str | None) -> Decimal | None:
    """Accepts ``1234.56``, ``1.234,56``, ``1,234.56`` and ``12,5``; empty means no value."""
    text = re.sub(r"\s+", "", raw or "")
    if not text or text in {"-", "—"}:
        return None
    text = text.replace("€", "").replace("$", "")
    if "," in text and "." in text:
        decimal_sep = "," if text.rfind(",") > text.rfind(".") else "."
        group_sep = "." if decimal_sep == "," else ","
        text = text.replace(group_sep, "").replace(decimal_sep, ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation:
        raise ValueError(f"keine Zahl: {raw!r}") from None


def parse_day(raw: str | None) -> date:
    text = re.sub(r"\s+", "", raw or "")
    if re.match(r"^\d{4}-\d{2}-\d{2}", text):
        return date.fromisoformat(text[:10])
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    raise ValueError(f"kein Datum: {raw!r}")


def _normalise(header: str) -> str:
    return header.strip().strip("﻿").lower().replace(" ", "_")


def _column_map(headers: list[str]) -> dict[str, int]:
    normalised = [_normalise(h) for h in headers]
    found: dict[str, int] = {}
    for key, names in ALIASES.items():
        for name in names:
            if name in normalised:
                found[key] = normalised.index(name)
                break
    # "datetime" and "date" both exist in Trade Republic exports; prefer the plain date
    if "date" in normalised:
        found["day"] = normalised.index("date")
    return found


def _kind(category: str, type_: str, description: str) -> str | None:
    text = f"{category} {type_}".upper()
    if "DIVIDEND" in text:
        return "dividend"
    if category and category.upper() not in {"TRADING", ""}:
        return None  # e.g. CASH/CUSTOMER_INBOUND, CORPORATE_ACTION/...
    if re.search(r"BUY|KAUF|SAVINGS|SPARPLAN", text):
        return "buy"
    if re.search(r"SELL|VERKAUF", text):
        return "sell"
    return None


def parse_broker_csv(text: str) -> ParseResult:
    sample = text[:4096]
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
    except csv.Error:
        delimiter = ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    try:
        headers = next(reader)
    except StopIteration:
        raise CsvError("Die Datei ist leer.") from None

    cols = _column_map(headers)
    missing = [k for k in ("day", "amount") if k not in cols]
    if missing or ("type" not in cols and "category" not in cols):
        raise CsvError(
            "Das sieht nicht nach einem Transaktionsexport aus. "
            f"Erkannte Spalten: {', '.join(h.strip() for h in headers[:12])}"
        )

    def cell(row: list[str], key: str) -> str:
        i = cols.get(key)
        return row[i].strip() if i is not None and i < len(row) else ""

    result = ParseResult()
    skipped: Counter[str] = Counter()
    seen: Counter[str] = Counter()
    for line, row in enumerate(reader, start=2):
        if not any(c.strip() for c in row):
            continue
        if line > MAX_ROWS:
            raise CsvError(f"Die Datei hat mehr als {MAX_ROWS} Zeilen.")
        category, type_ = cell(row, "category"), cell(row, "type")
        kind = _kind(category, type_, cell(row, "description"))
        if kind is None:
            label = "/".join(x for x in (category, type_) if x) or "ohne Typ"
            skipped[label] += 1
            continue
        try:
            amount = parse_number(cell(row, "amount"))
            if amount is None:
                raise ValueError("Betrag fehlt")
            shares = parse_number(cell(row, "shares"))
            fee = abs(parse_number(cell(row, "fee")) or Decimal(0))
            day = parse_day(cell(row, "day") or cell(row, "date"))
        except ValueError as e:
            result.errors.append(f"Zeile {line}: {e}")
            continue

        symbol = cell(row, "symbol").upper()
        isin = cell(row, "isin").upper() or (symbol if ISIN.match(symbol) else "")
        isin_value = isin if ISIN.match(isin) else None
        money = amount if kind == "dividend" else abs(amount)
        external = cell(row, "external_id")
        if not external:
            basis = f"{day}|{kind}|{isin_value}|{money}|{shares}"
            seen[basis] += 1  # identical rows on one day stay distinct, but stable across imports
            external = "h-" + hashlib.sha1(f"{basis}|{seen[basis]}".encode()).hexdigest()[:20]
        result.rows.append(
            ParsedTransaction(
                day=day,
                kind=kind,
                amount=money,
                fee=fee,
                shares=abs(shares) if shares is not None else None,
                isin=isin_value,
                name=cell(row, "name") or None,
                external_id=external[:64],
                line=line,
            )
        )
    result.skipped = dict(skipped)
    return result
