"""APN (Assessor Parcel Number) normalization.

LA County APNs are 10 digits (book/page/parcel: 4423-016-021). Sources format them
inconsistently: with dashes, without, as separate book/page/parcel columns, or with
trailing check characters. Everything joins on the canonical 10-digit string.
"""

from __future__ import annotations

import re

_DIGITS = re.compile(r"\d")


def normalize_apn(raw: str | None) -> str | None:
    """Return canonical 10-digit APN, or None if unparseable."""
    if not raw:
        return None
    digits = "".join(_DIGITS.findall(str(raw)))
    if len(digits) >= 10:
        return digits[:10]
    return None


def apn_from_parts(book: str | None, page: str | None, parcel: str | None) -> str | None:
    """Build an APN from book/page/parcel columns (LADBS style)."""
    if not (book and page and parcel):
        return None
    b = "".join(_DIGITS.findall(str(book))).zfill(4)
    p = "".join(_DIGITS.findall(str(page))).zfill(3)
    c = "".join(_DIGITS.findall(str(parcel))).zfill(3)
    if len(b) == 4 and len(p) == 3 and len(c) == 3:
        return b + p + c
    return None


def format_apn(apn: str) -> str:
    """4423016021 -> 4423-016-021 for display."""
    return f"{apn[:4]}-{apn[4:7]}-{apn[7:]}" if len(apn) == 10 else apn
