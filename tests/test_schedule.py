"""Tests for the pure schedule helpers."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

from custom_components.wapda_monitor import schedule as s

PKT = timezone(timedelta(hours=5))


def _hours(*on: int) -> list[int]:
    return [1 if h in on else 0 for h in range(24)]


# Shape taken from a live schedule_api response (2026-10-13).
SCHED = {
    "maintenance_sch": [0] * 24,
    "maintenance_data": {
        "dt_20261012": [0] * 24,
        "dt_20261013": _hours(17, 21),
        "dt_20261014": _hours(17, 18, 21),
    },
}


def test_merges_sch_and_data() -> None:
    now = datetime(2026, 10, 13, 10, 0, tzinfo=PKT)
    assert s.scheduled_hours_today(SCHED, now) == 2.0
    both = {**SCHED, "maintenance_sch": _hours(3)}
    assert s.scheduled_hours_today(both, now) == 3.0


def test_next_window_and_contiguous_merge() -> None:
    now = datetime(2026, 10, 13, 18, 0, tzinfo=PKT)
    start, end = s.next_window(SCHED, now)  # type: ignore[misc]
    assert (start.hour, end.hour) == (21, 22)
    now = datetime(2026, 10, 13, 22, 30, tzinfo=PKT)
    start, end = s.next_window(SCHED, now)  # type: ignore[misc]
    assert start == datetime(2026, 10, 14, 17, 0, tzinfo=PKT)
    assert end == datetime(2026, 10, 14, 19, 0, tzinfo=PKT)  # 17+18 merged


def test_is_outage_now_and_current_window() -> None:
    assert s.is_outage_now(SCHED, datetime(2026, 10, 13, 17, 30, tzinfo=PKT)) is True
    assert s.is_outage_now(SCHED, datetime(2026, 10, 13, 16, 59, tzinfo=PKT)) is False
    cur = s.current_window(SCHED, datetime(2026, 10, 13, 21, 10, tzinfo=PKT))
    assert cur is not None and cur[1].hour == 22


def test_day_missing_returns_none() -> None:
    now = datetime(2026, 10, 13, 10, 0, tzinfo=PKT)
    assert s.scheduled_hours_today({"maintenance_data": {"dt_20261014": []}}, now) is None
    assert s.scheduled_hours_today(None, now) is None
    assert s.scheduled_hours_today({}, now) is None


def test_garbage_values_are_ignored() -> None:
    bad = {"maintenance_data": {"dt_20261013": ["x", None, True, 2, -1] + [0] * 19}}
    now = datetime(2026, 10, 13, 10, 0, tzinfo=PKT)
    assert s.scheduled_hours_today(bad, now) == 1.0  # only the int 2; bool/neg/str ignored


def test_midnight_spanning_window() -> None:
    sched = {
        "maintenance_data": {
            "dt_20261013": _hours(23),
            "dt_20261014": _hours(0),
        }
    }
    now = datetime(2026, 10, 13, 12, 0, tzinfo=PKT)
    start, end = s.next_window(sched, now)  # type: ignore[misc]
    assert start.hour == 23 and end == datetime(2026, 10, 14, 1, 0, tzinfo=PKT)

