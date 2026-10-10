"""Checks for what a language model claims to have read in a document.

A model can invent a number that looks right. Everything it extracts is therefore compared with
the document text: an amount or ISIN that does not appear in the text is flagged for the user,
never silently accepted.
"""

import re
from datetime import date
from decimal import Decimal

_ISIN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


def isin_valid(isin: str) -> bool:
    """Format and Luhn check digit of an ISIN."""
    isin = isin.strip().upper()
    if not _ISIN.match(isin):
        return False
    digits = "".join(str(int(c, 36)) for c in isin)
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            n = n - 9 if n > 9 else n
        total += n
    return total % 10 == 0


def _group(whole: str, sep: str) -> str:
    out: list[str] = []
    while len(whole) > 3:
        out.insert(0, whole[-3:])
        whole = whole[:-3]
    out.insert(0, whole)
    return sep.join(out)


def number_variants(value: Decimal | float | str) -> set[str]:
    """The spellings a document may use for a number: 1.234,50 / 1234,50 / 1,234.50 / 1234.5."""
    d = abs(Decimal(str(value))).quantize(Decimal("0.01"))
    whole, frac = f"{d:.2f}".split(".")
    out: set[str] = set()
    for sep_thousand, sep_dec in (
        (".", ","),
        (",", "."),
        (" ", ","),
        ("", ","),
        ("", "."),
        ("'", "."),
    ):
        grouped = _group(whole, sep_thousand) if sep_thousand else whole
        out.add(f"{grouped}{sep_dec}{frac}")
        if frac == "00":
            out.add(grouped)
        elif frac.endswith("0"):
            out.add(f"{grouped}{sep_dec}{frac[0]}")
    return out


def amount_in_text(text: str, value: Decimal | float | str) -> bool:
    """Whether the amount is written somewhere in the text, as a whole number token."""
    for variant in number_variants(value):
        if re.search(rf"(?<![\d.,]){re.escape(variant)}(?![\d]|[.,]\d)", text):
            return True
    return False


def isin_in_text(text: str, isin: str) -> bool:
    return isin.upper() in text.upper().replace(" ", "")


def quantity_in_text(text: str, value: Decimal | float | str) -> bool:
    """A share count such as 0,3456 or 12.5 as it may be written: comma or dot, any length."""
    d = Decimal(str(value)).normalize()
    plain = format(d, "f")
    for variant in {plain, plain.replace(".", ",")}:
        if re.search(rf"(?<![\d.,]){re.escape(variant)}(?!\d|[.,]\d)", text):
            return True
    return False


def date_in_text(text: str, day: date) -> bool:
    """A date in the usual German and ISO spellings."""
    options = {
        day.isoformat(),
        f"{day.day:02d}.{day.month:02d}.{day.year}",
        f"{day.day}.{day.month}.{day.year}",
        f"{day.day:02d}.{day.month:02d}.{day.year % 100:02d}",
        f"{day.day:02d}/{day.month:02d}/{day.year}",
    }
    return any(o in text for o in options)
