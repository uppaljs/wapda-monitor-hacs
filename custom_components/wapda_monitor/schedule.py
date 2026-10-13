"""Pure helpers that turn the CCMS schedule payload into outage windows.

The ``/api/schedule_api`` payload carries per-day, per-hour arrays:

* ``maintenance_data["dt_YYYYMMDD"]`` — 24 flags for today and tomorrow
  (the DISCO's published shutdown/load-management plan for that day).
* ``maintenance_sch`` — 24 values for the current day (older field; often all
  zeros even when ``maintenance_data`` has slots, so both are merged).

Hour ``h`` of a day covers ``[h:00, h+1:00)`` in Pakistan local time (the
caller passes timezone-aware datetimes; HA's configured timezone is used).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any


def _flags(value: Any) -> list[bool]:
    """Normalise an hourly array to 24 booleans (True = outage)."""
    out = [False] * 24
    if isinstance(value, list):
        for i, v in enumerate(value[:24]):
            if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
                out[i] = True
    return out


def day_slots(schedule: dict[str, Any] | None, day: date, today: date) -> list[bool] | None:
    """Return 24 outage flags for ``day`` or None if the feed has no data for it."""
    if not schedule:
        return None
    key = f"dt_{day:%Y%m%d}"
    data = schedule.get("maintenance_data")
    has_day = isinstance(data, dict) and key in data
    flags = _flags(data[key]) if has_day else [False] * 24
    has_sch = False
    if day == today and isinstance(schedule.get("maintenance_sch"), list):
        has_sch = True
        flags = [a or b for a, b in zip(flags, _flags(schedule["maintenance_sch"]))]
    if not has_day and not has_sch:
        return None
    return flags


def outage_windows(
    schedule: dict[str, Any] | None, now: datetime, days: int = 2
) -> list[tuple[datetime, datetime]]:
    """Contiguous outage windows from today's 00:00 across ``days`` days.

    Windows already finished before ``now`` are included (callers filter), so
    "scheduled outage today" can still count slots that passed.
    """
    today = now.date()
    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    windows: list[tuple[datetime, datetime]] = []
    cur_start: datetime | None = None
    last_end: datetime | None = None
    for d in range(days):
        day = today + timedelta(days=d)
        flags = day_slots(schedule, day, today)
        if flags is None:
            flags = [False] * 24
        for h, on in enumerate(flags):
            slot_start = start_of_today + timedelta(days=d, hours=h)
            slot_end = slot_start + timedelta(hours=1)
            if on:
                if cur_start is not None and last_end == slot_start:
                    last_end = slot_end
                else:
                    if cur_start is not None and last_end is not None:
                        windows.append((cur_start, last_end))
                    cur_start, last_end = slot_start, slot_end
    if cur_start is not None and last_end is not None:
        windows.append((cur_start, last_end))
    return windows


def scheduled_hours_today(schedule: dict[str, Any] | None, now: datetime) -> float | None:
    """Number of scheduled outage hours in the current day (None if no data)."""
    flags = day_slots(schedule, now.date(), now.date())
    if flags is None:
        return None
    return float(sum(flags))


def is_outage_now(schedule: dict[str, Any] | None, now: datetime) -> bool | None:
    flags = day_slots(schedule, now.date(), now.date())
    if flags is None:
        return None
    return flags[now.hour]


def next_window(
    schedule: dict[str, Any] | None, now: datetime
) -> tuple[datetime, datetime] | None:
    """First window that starts after ``now`` (excludes the one in progress)."""
    for start, end in outage_windows(schedule, now):
        if start > now:
            return start, end
    return None


def current_window(
    schedule: dict[str, Any] | None, now: datetime
) -> tuple[datetime, datetime] | None:
    for start, end in outage_windows(schedule, now):
        if start <= now < end:
            return start, end
    return None
