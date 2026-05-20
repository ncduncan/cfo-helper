"""Friendly-form ↔ cron translation for the Schedules UI.

The dashboard exposes a human-readable schedule builder (frequency +
time-of-day + day selectors) rather than a raw 5-field cron expression.
The backend still stores a cron string (so APScheduler's CronTrigger keeps
working); this module converts between the two.

build_cron(spec) — produce a 5-field cron from a friendly spec dict.
parse_cron(cron) — best-effort reverse: detect simple Daily/Weekly/Monthly/
    Quarterly/Yearly patterns so the edit form can prefill. Returns None
    when the cron doesn't fit one of those shapes (form falls back to
    Advanced mode).
describe(cron, tz) — short human label for the list view.
"""

from __future__ import annotations

import re
from typing import Optional

DOW_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
MONTH_NAMES = [
    "",
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

# Quarterly day-of-month maps to month list "1,4,7,10".
QUARTERLY_MONTHS = "1,4,7,10"


def _norm_int(v, lo: int, hi: int, default: int) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return default
    return n if lo <= n <= hi else default


def build_cron(spec: dict) -> str:
    """Build a 5-field cron string from the friendly form spec.

    spec keys (all strings, as posted from HTML form):
      frequency: daily | weekly | monthly | quarterly | yearly | custom
      hour, minute: ints
      day_of_week: 0-6 (Sunday=0) — for weekly
      day_of_month: 1-31 — for monthly/quarterly/yearly
      month: 1-12 — for yearly
      cron: raw expression — for custom
    """
    freq = (spec.get("frequency") or "daily").lower()
    if freq == "custom":
        raw = (spec.get("cron") or "").strip()
        return raw

    hour = _norm_int(spec.get("hour"), 0, 23, 9)
    minute = _norm_int(spec.get("minute"), 0, 59, 0)

    if freq == "daily":
        return f"{minute} {hour} * * *"
    if freq == "weekly":
        dow = _norm_int(spec.get("day_of_week"), 0, 6, 1)
        return f"{minute} {hour} * * {dow}"
    if freq == "monthly":
        dom = _norm_int(spec.get("day_of_month"), 1, 31, 1)
        return f"{minute} {hour} {dom} * *"
    if freq == "quarterly":
        dom = _norm_int(spec.get("day_of_month"), 1, 31, 1)
        return f"{minute} {hour} {dom} {QUARTERLY_MONTHS} *"
    if freq == "yearly":
        dom = _norm_int(spec.get("day_of_month"), 1, 31, 1)
        month = _norm_int(spec.get("month"), 1, 12, 1)
        return f"{minute} {hour} {dom} {month} *"

    return f"{minute} {hour} * * *"


_SIMPLE_FIELD = re.compile(r"^\d+$")


def parse_cron(cron: str) -> Optional[dict]:
    """Reverse build_cron for the simple patterns. Returns None on no match.

    Recognized shapes:
      M H * * *           → daily
      M H * * D           → weekly
      M H D * *           → monthly
      M H D 1,4,7,10 *    → quarterly
      M H D M *           → yearly
    """
    parts = (cron or "").split()
    if len(parts) != 5:
        return None
    minute, hour, dom, month, dow = parts
    if not (_SIMPLE_FIELD.match(minute) and _SIMPLE_FIELD.match(hour)):
        return None

    base = {"hour": int(hour), "minute": int(minute)}

    # daily
    if dom == "*" and month == "*" and dow == "*":
        return {**base, "frequency": "daily"}
    # weekly
    if dom == "*" and month == "*" and _SIMPLE_FIELD.match(dow):
        return {**base, "frequency": "weekly", "day_of_week": int(dow)}
    # monthly
    if _SIMPLE_FIELD.match(dom) and month == "*" and dow == "*":
        return {**base, "frequency": "monthly", "day_of_month": int(dom)}
    # quarterly
    if _SIMPLE_FIELD.match(dom) and month == QUARTERLY_MONTHS and dow == "*":
        return {**base, "frequency": "quarterly", "day_of_month": int(dom)}
    # yearly
    if (
        _SIMPLE_FIELD.match(dom)
        and _SIMPLE_FIELD.match(month)
        and dow == "*"
    ):
        return {
            **base,
            "frequency": "yearly",
            "day_of_month": int(dom),
            "month": int(month),
        }
    return None


def _fmt_time(hour: int, minute: int) -> str:
    suffix = "AM" if hour < 12 else "PM"
    h12 = hour % 12 or 12
    return f"{h12}:{minute:02d} {suffix}"


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        s = "th"
    else:
        s = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{s}"


def _tz_label(tz: str) -> str:
    return {
        "America/New_York": "ET",
        "America/Chicago": "CT",
        "America/Denver": "MT",
        "America/Los_Angeles": "PT",
        "UTC": "UTC",
    }.get(tz or "", tz or "")


def describe(cron: str, tz: str = "America/New_York") -> str:
    """Short human label for the list view. Falls back to the raw cron."""
    spec = parse_cron(cron)
    if spec is None:
        return f"cron: {cron}" if cron else "—"
    tzl = _tz_label(tz)
    time_s = _fmt_time(spec["hour"], spec["minute"])
    freq = spec["frequency"]
    if freq == "daily":
        return f"Daily at {time_s} {tzl}"
    if freq == "weekly":
        return f"Weekly on {DOW_NAMES[spec['day_of_week']]} at {time_s} {tzl}"
    if freq == "monthly":
        return f"Monthly on the {_ordinal(spec['day_of_month'])} at {time_s} {tzl}"
    if freq == "quarterly":
        return (
            f"Quarterly on the {_ordinal(spec['day_of_month'])} "
            f"(Jan/Apr/Jul/Oct) at {time_s} {tzl}"
        )
    if freq == "yearly":
        return (
            f"Yearly on {MONTH_NAMES[spec['month']]} "
            f"{_ordinal(spec['day_of_month'])} at {time_s} {tzl}"
        )
    return f"cron: {cron}"
