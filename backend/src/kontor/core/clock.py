"""Month handling. Months are represented as the first day of the month (``date``)."""

import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from kontor.core.config import get_settings

_MONTH_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


def current_month() -> date:
    """First day of the current month in the configured time zone."""
    now = datetime.now(ZoneInfo(get_settings().timezone))
    return date(now.year, now.month, 1)


def parse_month(value: str) -> date:
    m = _MONTH_RE.match(value)
    if not m:
        raise ValueError("Month must be formatted as YYYY-MM")
    return date(int(m.group(1)), int(m.group(2)), 1)


def format_month(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def add_months(value: date, delta: int) -> date:
    index = value.year * 12 + (value.month - 1) + delta
    return date(index // 12, index % 12 + 1, 1)


def month_range(start: date, end: date) -> list[date]:
    """All months from ``start`` to ``end`` inclusive."""
    out: list[date] = []
    cur = start
    while cur <= end:
        out.append(cur)
        cur = add_months(cur, 1)
    return out
