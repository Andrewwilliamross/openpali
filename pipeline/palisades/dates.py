"""Date parsing for the various upstream formats.

ArcGIS layers return epoch milliseconds; USACE ROE timestamps are Oracle strings
like '22-MAR-25 09.37.30.000000 PM'; Socrata uses ISO calendar dates.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

_ORACLE_MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}


def from_epoch_ms(v: object) -> date | None:
    """Epoch milliseconds (int/float/str) → UTC date. 0 and None → None."""
    if v in (None, "", 0, "0"):
        return None
    try:
        ms = int(v)
    except (TypeError, ValueError):
        return None
    if ms <= 0:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date()
    except (OverflowError, OSError, ValueError):
        return None


def from_oracle(s: object) -> date | None:
    """'22-MAR-25 09.37.30.000000 PM' → date(2025, 3, 22)."""
    if not s or not isinstance(s, str):
        return None
    head = s.strip().split(" ")[0]  # '22-MAR-25'
    parts = head.split("-")
    if len(parts) != 3:
        return None
    try:
        day = int(parts[0])
        mon = _ORACLE_MONTHS.get(parts[1].upper())
        yy = int(parts[2])
        if mon is None:
            return None
        year = 2000 + yy if yy < 70 else 1900 + yy
        return date(year, mon, day)
    except ValueError:
        return None


def from_iso(s: object) -> date | None:
    """ISO date or datetime string → date."""
    if not s or not isinstance(s, str):
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(s[:10])
        except ValueError:
            return None
