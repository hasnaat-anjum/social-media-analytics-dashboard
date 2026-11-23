"""Parsing helpers: numbers and dates from messy platform exports.

Exports come in many shapes: "1,234", "1.2k", "1,2k", "12 Nov 2026",
"11/12/2026", "2026-11-12 19:30".  These helpers accept all of them
and fail cleanly (returning None / 0) instead of crashing the import.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

_NUMBER_RE = re.compile(r"^\s*([+-]?[\d.,]+)\s*([kKmM]?)\s*$")

# Date formats tried in order.  ISO first (unambiguous), then the
# common day-first export formats, then month-first, then written out.
_DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%m/%d/%Y %H:%M",
    "%m/%d/%Y",
    "%d %b %Y %H:%M",
    "%d %b %Y",
    "%d %B %Y",
    "%b %d, %Y %H:%M",
    "%b %d, %Y",
    "%B %d, %Y",
    "%Y/%m/%d",
)


def parse_number(raw) -> int:
    """Parse an export number: ints, floats, commas, k/m suffixes.

    "1,234" -> 1234, "1.2k" -> 1200, "2.5m" -> 2500000, "" -> 0.
    Anything unparseable is 0, never an exception.
    """
    if raw is None:
        return 0
    if isinstance(raw, (int, float)):
        return int(raw)
    text = str(raw).strip()
    if not text or text.lower() in ("n/a", "na", "-", "--", "null", "none"):
        return 0
    # European-style "1.234,5" is rare in exports; treat a trailing
    # comma-group as a decimal separator only when it looks like one.
    match = _NUMBER_RE.match(text.replace(",", "") if text.count(",") > 1 else text)
    if not match:
        # Try again after removing thousands separators.
        match = _NUMBER_RE.match(text.replace(",", "").replace(" ", ""))
    if not match:
        return 0
    number = float(match.group(1).replace(",", ""))
    suffix = match.group(2).lower()
    if suffix == "k":
        number *= 1_000
    elif suffix == "m":
        number *= 1_000_000
    return int(number)


def parse_date(raw) -> Optional[datetime]:
    """Parse a date from an export cell.  Returns None if unparseable."""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw
    text = str(raw).strip()
    if not text:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    # ISO with a T separator, e.g. 2026-11-12T19:30:00
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def normalise_header(header: str) -> str:
    """Lowercase a CSV header and strip everything but letters/digits."""
    return re.sub(r"[^a-z0-9]", "", header.strip().lower())


def format_number(value: int) -> str:
    """Human-friendly number: 1234 -> '1,234'."""
    return f"{value:,}"


def format_pct(value: Optional[float]) -> str:
    """Percentage with two decimals, or an em dash when unknown."""
    if value is None:
        return "—"
    return f"{value:.2f}%"
