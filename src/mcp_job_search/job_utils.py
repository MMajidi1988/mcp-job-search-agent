"""Shared helpers for job listings (deadlines, NAV token parsing)."""

from __future__ import annotations

import re
from datetime import UTC, datetime

_JWT_RE = re.compile(r"(eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)")


def extract_jwt_from_text(text: str) -> str:
    """NAV publicToken may return a JWT alone or explanatory text plus JWT."""
    text = text.strip().strip('"')
    m = _JWT_RE.search(text)
    if m:
        return m.group(1)
    return text


def parse_datetime_loose(value: str) -> datetime | None:
    """Parse ISO-ish datetime strings from APIs (NAV, Finn)."""
    if not value or not value.strip():
        return None
    s = value.strip()
    if s.lower() in ("snarest", "asap", "fortløpende", "continuous"):
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except ValueError:
        pass
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        return None


def deadline_is_still_open(deadline_str: str, now: datetime | None = None) -> bool:
    """True if deadline is missing, ASAP-style, or not before today (UTC date)."""
    now = now or datetime.now(UTC)
    if not deadline_str or not deadline_str.strip():
        return True
    low = deadline_str.strip().lower()
    if low in ("snarest", "asap", "fortløpende", "continuous"):
        return True
    dt = parse_datetime_loose(deadline_str)
    if dt is None:
        return True
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.date() >= now.astimezone(dt.tzinfo).date()
