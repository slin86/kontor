"""Bank statements: parse the common export formats and find payments that come back regularly.

Nothing in here touches the database or the network. Parsers return ``BankLine`` rows where an
expense has a negative amount. ``find_recurring`` groups lines by counterparty and looks at the
rhythm and the amounts: that is plain arithmetic and more reliable than asking a language model.
"""

import csv
import io
import re
import statistics
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from itertools import pairwise

MAX_LINES = 20000
AMOUNT_TOLERANCE = Decimal("0.10")  # recurring payments may vary by this share (utilities)

# (min gap in days, max gap in days, months)
RHYTHMS: tuple[tuple[int, int, int], ...] = (
    (25, 36, 1),
    (80, 100, 3),
    (170, 196, 6),
    (350, 380, 12),
)


class StatementError(ValueError):
    """The file cannot be read as a bank statement."""


@dataclass(frozen=True)
class BankLine:
    day: date
    amount: Decimal  # negative for money that left the account
    counterparty: str
    purpose: str


@dataclass(frozen=True)
class Recurring:
    key: str
    name: str  # most common spelling of the counterparty
    amount: Decimal  # positive; the most recent amount
    income: bool
    months: int  # 1, 3, 6 or 12
    count: int
    first: date
    last: date
    purpose: str


# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------


def parse_amount(raw: str) -> Decimal:
    """German ("1.234,56") and plain ("1234.56") notation, optional sign or trailing minus."""
    text = raw.replace("\u00a0", "").replace(" ", "").replace("€", "").replace("EUR", "")
    if not text:
        raise StatementError("Betrag fehlt")
    negative = text.startswith("-") or text.endswith("-") or text.startswith("(")
    text = text.strip("-+()")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise StatementError(f"Betrag nicht lesbar: {raw!r}") from exc
    return -value if negative else value


def parse_day(raw: str) -> date:
    text = raw.strip()
    for pattern, order in (
        (r"^(\d{4})-(\d{2})-(\d{2})", "ymd"),
        (r"^(\d{2})\.(\d{2})\.(\d{4})", "dmy"),
        (r"^(\d{2})\.(\d{2})\.(\d{2})$", "dmy2"),
        (r"^(\d{2})/(\d{2})/(\d{4})", "dmy"),
    ):
        m = re.match(pattern, text)
        if not m:
            continue
        a, b, c = (int(x) for x in m.groups())
        try:
            if order == "ymd":
                return date(a, b, c)
            if order == "dmy2":
                return date(2000 + c, b, a)
            return date(c, b, a)
        except ValueError as exc:
            raise StatementError(f"Datum nicht lesbar: {raw!r}") from exc
    raise StatementError(f"Datum nicht lesbar: {raw!r}")


def _norm(header: str) -> str:
    return re.sub(r"[^a-zäöüß0-9]", "", header.lower())


# --------------------------------------------------------------------------------------
# CSV
# --------------------------------------------------------------------------------------

_DAY = ("buchungstag", "buchungsdatum", "buchung", "datum", "date", "valuta", "wertstellung")
_AMOUNT = ("betrag", "betrageur", "umsatz", "amount", "betragineur")
_PARTY = (
    "zahlungsempfänger",
    "beguenstigter",
    "begünstigter",
    "beguenstigterzahlungspflichtiger",
    "begünstigterzahlungspflichtiger",
    "name",
    "auftraggeberempfänger",
    "empfänger",
    "auftraggeber",
    "partnername",
    "counterparty",
    "zahlungspflichtiger",
)
_PURPOSE = ("verwendungszweck", "buchungstext", "beschreibung", "text", "purpose", "details")
_DEBIT = ("soll", "belastung")
_CREDIT = ("haben", "gutschrift")


def _pick(headers: dict[str, int], names: tuple[str, ...], *, fuzzy: bool = False) -> int | None:
    for n in names:
        if _norm(n) in headers:
            return headers[_norm(n)]
    if fuzzy:  # "Name Zahlungsbeteiligter", "Verwendungszweck (Text)" and the like
        for n in names:
            for header, i in headers.items():
                if _norm(n) in header:
                    return i
    return None


def parse_csv(text: str) -> list[BankLine]:
    text = text.lstrip("﻿")
    rows = list(
        csv.reader(io.StringIO(text), delimiter=";" if text.count(";") > text.count(",") else ",")
    )
    # banks add address or balance rows before the header; the header is the first row with a
    # date column and an amount column
    for header_row, row in enumerate(rows):  # noqa: B007 (used after the loop)
        headers = {_norm(h): i for i, h in enumerate(row) if h.strip()}
        day_i, amount_i = _pick(headers, _DAY), _pick(headers, _AMOUNT)
        debit_i, credit_i = _pick(headers, _DEBIT), _pick(headers, _CREDIT)
        if day_i is not None and (
            amount_i is not None or (debit_i is not None and credit_i is not None)
        ):
            break
    else:
        raise StatementError("In der CSV-Datei fehlen Datum und Betrag.")
    party_i = _pick(headers, _PARTY, fuzzy=True)
    purpose_i = _pick(headers, _PURPOSE, fuzzy=True)

    def cell(row: list[str], i: int | None) -> str:
        return row[i].strip() if i is not None and i < len(row) else ""

    lines: list[BankLine] = []
    for row in rows[header_row + 1 :]:
        if not any(c.strip() for c in row):
            continue
        try:
            day = parse_day(cell(row, day_i))
            if amount_i is not None:
                amount = parse_amount(cell(row, amount_i))
            else:
                debit, credit = cell(row, debit_i), cell(row, credit_i)
                amount = parse_amount(credit) if credit else -abs(parse_amount(debit))
        except StatementError:
            continue  # summary and balance rows
        lines.append(BankLine(day, amount, cell(row, party_i), cell(row, purpose_i)))
        if len(lines) > MAX_LINES:
            raise StatementError("Die Datei hat zu viele Zeilen.")
    if not lines:
        raise StatementError("In der CSV-Datei wurden keine Buchungen gefunden.")
    return lines


# --------------------------------------------------------------------------------------
# CAMT.053 (XML)
# --------------------------------------------------------------------------------------


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_camt(text: str) -> list[BankLine]:
    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise StatementError("Die XML-Datei enthält unzulässige Definitionen.")
    try:
        root = ET.fromstring(text.lstrip("﻿").encode())
    except ET.ParseError as exc:
        raise StatementError("Die XML-Datei ist nicht lesbar.") from exc
    lines: list[BankLine] = []
    for entry in (e for e in root.iter() if _local(e.tag) == "Ntry"):
        fields: dict[str, str] = {}
        credit = True
        for el in entry.iter():
            name = _local(el.tag)
            if name == "CdtDbtInd" and el.text and "cdtdbt" not in fields:
                credit = el.text.strip() == "CRDT"
                fields["cdtdbt"] = "x"
            elif name == "Amt" and "amt" not in fields and el.text:
                fields["amt"] = el.text.strip()
            elif name == "BookgDt" and "day" not in fields:
                fields["day"] = next(
                    (c.text or "" for c in el if _local(c.tag) in ("Dt", "DtTm")), ""
                )
        # the other party is the creditor for money that left, the debtor for money that arrived
        party_tag = "Dbtr" if credit else "Cdtr"
        party = ""
        for el in entry.iter():
            if _local(el.tag) == party_tag:
                party = next((c.text or "" for c in el.iter() if _local(c.tag) == "Nm"), "")
                break
        purpose = " ".join(
            (el.text or "").strip() for el in entry.iter() if _local(el.tag) == "Ustrd" and el.text
        )
        if "amt" not in fields or "day" not in fields:
            continue
        amount = parse_amount(fields["amt"])
        lines.append(
            BankLine(
                parse_day(fields["day"]), amount if credit else -amount, party.strip(), purpose
            )
        )
    if not lines:
        raise StatementError("In der XML-Datei wurden keine Buchungen gefunden.")
    return lines


# --------------------------------------------------------------------------------------
# MT940
# --------------------------------------------------------------------------------------

_MT_61 = re.compile(r"^:61:(\d{6})(?:\d{4})?(R?[CD])R?(\d+,\d*)")


def parse_mt940(text: str) -> list[BankLine]:
    lines: list[BankLine] = []
    current: dict[str, str] | None = None
    in_86 = False

    def flush() -> None:
        if current and "day" in current:
            lines.append(
                BankLine(
                    parse_day(current["day"]),
                    parse_amount(current["amount"]) * (1 if current["sign"] == "C" else -1),
                    current.get("party", ""),
                    current.get("purpose", "").strip(),
                )
            )

    for raw in text.splitlines():
        line = raw.rstrip()
        m = _MT_61.match(line)
        if m:
            flush()
            yymmdd, sign, amount = m.groups()
            current = {
                "day": f"{yymmdd[4:6]}.{yymmdd[2:4]}.{yymmdd[0:2]}",
                "sign": sign[-1],
                "amount": amount,
            }
            in_86 = False
        elif line.startswith(":86:") and current is not None:
            in_86 = True
            _mt_86(current, line[4:])
        elif line.startswith(":") and not line.startswith(":86:"):
            in_86 = False
        elif in_86 and current is not None:
            _mt_86(current, line)
    flush()
    if not lines:
        raise StatementError("In der MT940-Datei wurden keine Buchungen gefunden.")
    return lines


def _mt_86(current: dict[str, str], chunk: str) -> None:
    # structured field: ?20..?29 purpose, ?32/?33 name of the other party
    for code, value in re.findall(r"\?(\d{2})([^?]*)", chunk):
        if code in ("32", "33"):
            current["party"] = (current.get("party", "") + value).strip()
        elif code.startswith("2") or code in ("60", "61", "62", "63"):
            current["purpose"] = current.get("purpose", "") + " " + value
    if "?" not in chunk:
        current["purpose"] = current.get("purpose", "") + " " + chunk


# --------------------------------------------------------------------------------------
# recurring payments
# --------------------------------------------------------------------------------------

_NOISE = re.compile(
    r"\b(sepa|lastschrift|dauerauftrag|gutschrift|ueberweisung|überweisung|kartenzahlung|visa|girocard|mandat\w*|ref\w*|gmbh|ag|kg|se|e\.?v\.?)\b"
)


def counterparty_key(name: str, purpose: str = "") -> str:
    """Stable key for "the same payee": lower case, no reference numbers, dates or legal forms."""
    text = (name or purpose).lower()
    text = _NOISE.sub(" ", text)
    text = re.sub(r"[0-9]+", " ", text)
    text = re.sub(r"[^a-zäöüß ]", " ", text)
    return " ".join(text.split())[:60]


def _months_for(gaps: list[int]) -> int | None:
    median = statistics.median(gaps)
    for low, high, months in RHYTHMS:
        if low <= median <= high:
            return months
    return None


def find_recurring(lines: list[BankLine]) -> tuple[list[Recurring], list[BankLine]]:
    """Payments that repeat in a fixed rhythm, plus the lines that could not be matched."""
    groups: dict[tuple[str, bool], list[BankLine]] = defaultdict(list)
    for line in lines:
        key = counterparty_key(line.counterparty, line.purpose)
        if key:
            groups[(key, line.amount > 0)].append(line)

    found: list[Recurring] = []
    matched: set[int] = set()
    for (key, income), group in groups.items():
        group.sort(key=lambda x: x.day)
        # split by amount level: a payee may have a rent and a one-off payment
        level = statistics.median(abs(x.amount) for x in group)
        close = [
            x
            for x in group
            if abs(abs(x.amount) - level) <= level * AMOUNT_TOLERANCE + Decimal("0.5")
        ]
        days = sorted({x.day for x in close})
        if len(days) < 2:
            continue
        gaps = [(b - a).days for a, b in pairwise(days)]
        months = _months_for(gaps)
        if months is None:
            continue
        name = Counter(x.counterparty or x.purpose for x in close).most_common(1)[0][0]
        found.append(
            Recurring(
                key=key,
                name=name.strip()[:120],
                amount=abs(close[-1].amount),
                income=income,
                months=months,
                count=len(close),
                first=close[0].day,
                last=close[-1].day,
                purpose=close[-1].purpose.strip()[:200],
            )
        )
        matched.update(id(x) for x in close)
    found.sort(key=lambda r: (r.income, -r.amount))
    return found, [x for x in lines if id(x) not in matched]
