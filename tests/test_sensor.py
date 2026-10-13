"""Tests for sensor value helpers."""

from __future__ import annotations

from custom_components.wapda_monitor.sensor import _last_event_value


def test_last_event_is_newest() -> None:
    """The portal returns event_logs oldest-first; report the newest."""
    load = {
        "event_logs": [
            {"event_time": "2026-10-10 01:14:50", "event": "OFF"},
            {"event_time": "2026-10-12 22:09:15", "event": "ON"},
            {"event_time": "2026-10-11 21:14:10", "event": "OFF"},
        ]
    }
    assert _last_event_value(load) == "ON at 2026-10-12 22:09:15"


def test_last_event_empty() -> None:
    assert _last_event_value(None) is None
    assert _last_event_value({"event_logs": []}) is None
