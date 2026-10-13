"""Tests for WAPDA outage calendar events."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from custom_components.wapda_monitor import calendar as calendar_platform
from custom_components.wapda_monitor.calendar import (
    WapdaOutageCalendar,
    _actual_outage_events,
    _overlaps_range,
    _parse_portal_datetime,
    _scheduled_outage_events,
)

PKT = ZoneInfo("Asia/Karachi")


def _hours(*on: int) -> list[int]:
    return [int(hour in on) for hour in range(24)]


def test_scheduled_outages_are_calendar_events_in_portal_timezone() -> None:
    now = datetime(2026, 10, 13, 10, 0, tzinfo=PKT)
    schedule = {
        "maintenance_data": {
            "dt_20261013": _hours(17),
            "dt_20261014": _hours(2, 3),
        },
        "maintenance_sch": [0] * 24,
    }

    events = _scheduled_outage_events(schedule, now)

    assert len(events) == 2
    assert events[0].summary == "Scheduled outage"
    assert events[0].start == datetime(2026, 10, 13, 17, 0, tzinfo=PKT)
    assert events[0].end == datetime(2026, 10, 13, 18, 0, tzinfo=PKT)
    assert events[1].start == datetime(2026, 10, 14, 2, 0, tzinfo=PKT)
    assert events[1].end == datetime(2026, 10, 14, 4, 0, tzinfo=PKT)


def test_actual_outages_pair_off_and_on_transitions() -> None:
    now = datetime(2026, 10, 13, 13, 0, tzinfo=PKT)
    load = {
        # The portal may return oldest-first; the parser sorts defensively.
        "event_logs": [
            {"event": "OFF", "event_time": "2026-10-13 12:00:00"},
            {"event": "ON", "event_time": "2026-10-13 11:00:00"},
            {"event": "ON", "event_time": "2026-10-13 09:30:00"},
            {"event": "OFF", "event_time": "2026-10-13 09:00:00"},
        ],
        "current_status": "OFF",
        "current_status_time": "2026-10-13 12:00:00",
    }

    events = _actual_outage_events(load, now)

    assert len(events) == 2
    assert events[0].summary == "Actual outage"
    assert events[0].start == datetime(2026, 10, 13, 9, 0, tzinfo=PKT)
    assert events[0].end == datetime(2026, 10, 13, 9, 30, tzinfo=PKT)
    assert events[1].summary == "Actual outage (ongoing)"
    assert events[1].start == datetime(2026, 10, 13, 12, 0, tzinfo=PKT)
    assert events[1].end == now


def test_actual_outage_uses_status_time_when_off_transition_is_missing() -> None:
    now = datetime(2026, 10, 13, 13, 0, tzinfo=PKT)
    load = {
        "event_logs": [],
        "current_status": "OFF",
        "current_status_time": "2026-10-13 12:15:00",
    }

    events = _actual_outage_events(load, now)

    assert len(events) == 1
    assert events[0].start == datetime(2026, 10, 13, 12, 15, tzinfo=PKT)
    assert events[0].end == now


def test_actual_calendar_exposes_current_outage_as_active_event(
    monkeypatch,
) -> None:
    now = datetime(2026, 10, 13, 13, 0, tzinfo=PKT)
    monkeypatch.setattr(calendar_platform.dt_util, "now", lambda: now)
    coordinator = MagicMock()
    coordinator.data = {
        "load": {
            "event_logs": [],
            "current_status": "OFF",
            "current_status_time": "2026-10-13 12:15:00",
        }
    }
    coordinator.update_interval = timedelta(minutes=5)

    entity = WapdaOutageCalendar(coordinator, "01234567890123", scheduled=False)

    assert entity.event is not None
    assert entity.event.summary == "Actual outage (ongoing)"
    assert entity.event.start == datetime(2026, 10, 13, 12, 15, tzinfo=PKT)
    assert entity.event.end == now + timedelta(minutes=5)


def test_unpaired_historical_off_is_not_reported_as_actual_outage() -> None:
    now = datetime(2026, 10, 13, 13, 0, tzinfo=PKT)
    load = {
        "event_logs": [{"event": "OFF", "event_time": "2026-10-13 12:00:00"}],
        "current_status": "ON",
    }

    assert _actual_outage_events(load, now) == []


def test_portal_timestamps_are_interpreted_as_pakistan_time() -> None:
    naive = _parse_portal_datetime("2026-10-13 12:00:00")
    aware = _parse_portal_datetime("2026-10-13T07:00:00+00:00")

    assert naive == datetime(2026, 10, 13, 12, 0, tzinfo=PKT)
    assert aware == naive
    assert _parse_portal_datetime("not a timestamp") is None


def test_calendar_range_includes_overlapping_events() -> None:
    start = datetime(2026, 10, 13, 9, 30, tzinfo=PKT)
    end = start + timedelta(hours=1)
    event = _scheduled_outage_events(
        {"maintenance_data": {"dt_20261013": _hours(9)}},
        datetime(2026, 10, 13, 8, 0, tzinfo=PKT),
    )[0]

    assert _overlaps_range(event, start, end)
    assert not _overlaps_range(
        event,
        datetime(2026, 10, 13, 10, 0, tzinfo=UTC),
        datetime(2026, 10, 13, 11, 0, tzinfo=UTC),
    )
