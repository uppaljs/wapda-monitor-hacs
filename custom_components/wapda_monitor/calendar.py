"""Calendar entities for scheduled and actual feeder outages."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import WapdaConfigEntry
from . import schedule as sched
from .const import CONF_REFERENCE, DATA_LOAD, DATA_SCHEDULE, DOMAIN, MANUFACTURER
from .coordinator import WapdaDataCoordinator

_PAKISTAN_TZ = ZoneInfo("Asia/Karachi")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WapdaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up scheduled and actual outage calendars."""
    coordinator = entry.runtime_data
    reference = entry.data[CONF_REFERENCE]
    async_add_entities(
        [
            WapdaOutageCalendar(coordinator, reference, scheduled=True),
            WapdaOutageCalendar(coordinator, reference, scheduled=False),
        ]
    )


class WapdaOutageCalendar(CoordinatorEntity[WapdaDataCoordinator], CalendarEntity):
    """Calendar backed by the coordinator's cached WAPDA data."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: WapdaDataCoordinator,
        reference: str,
        *,
        scheduled: bool,
    ) -> None:
        super().__init__(coordinator)
        self._reference = reference
        self._scheduled = scheduled
        self._attr_translation_key = (
            "scheduled_outages" if scheduled else "actual_outages"
        )
        self._attr_unique_id = (
            f"wapda_{reference}_{'scheduled' if scheduled else 'actual'}_outages"
        )
        self._attr_icon = "mdi:calendar-clock" if scheduled else "mdi:calendar-alert"

    @property
    def device_info(self) -> DeviceInfo:
        """Group both calendars with this account's existing device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._reference)},
            name=f"WAPDA Feeder Monitor …{self._reference[-4:]}",
            manufacturer=MANUFACTURER,
            model="WAPDA Feeder Monitor",
        )

    @property
    def event(self) -> CalendarEvent | None:
        """Return the current or next outage for this calendar."""
        now = _now_in_pakistan()
        for event in self._events(now, extend_current=True):
            if event.end > now:
                return event
        return None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return known outage events overlapping the requested time range."""
        if end_date <= start_date:
            return []
        now = _now_in_pakistan()
        return [
            event
            for event in self._events(now)
            if _overlaps_range(event, start_date, end_date)
        ]

    def _events(
        self, now: datetime, *, extend_current: bool = False
    ) -> list[CalendarEvent]:
        """Build events from cached data without making additional requests."""
        data = self.coordinator.data or {}
        if self._scheduled:
            events = _scheduled_outage_events(data.get(DATA_SCHEDULE), now)
        else:
            current_end = None
            if extend_current:
                current_end = now + (
                    self.coordinator.update_interval or timedelta(minutes=5)
                )
            events = _actual_outage_events(
                data.get(DATA_LOAD), now, current_end=current_end
            )
        return sorted(events, key=lambda item: (item.start, item.end))


def _now_in_pakistan() -> datetime:
    """Use Pakistan time for the portal's local schedule/event timestamps."""
    return dt_util.now().astimezone(_PAKISTAN_TZ)


def _scheduled_outage_events(
    schedule: dict[str, Any] | None, now: datetime
) -> list[CalendarEvent]:
    """Convert the portal's today/tomorrow schedule into calendar events."""
    local_now = _as_pakistan_time(now)
    return [
        CalendarEvent(
            summary="Scheduled outage",
            start=start,
            end=end,
            description="Forecast outage from the published CCMS schedule.",
        )
        for start, end in sched.outage_windows(schedule, local_now)
    ]


def _overlaps_range(
    event: CalendarEvent, start_date: datetime, end_date: datetime
) -> bool:
    """Return whether an event overlaps the requested calendar range."""
    return event.start < end_date and event.end > start_date


def _actual_outage_events(
    load: dict[str, Any] | None,
    now: datetime,
    *,
    current_end: datetime | None = None,
) -> list[CalendarEvent]:
    """Pair observed OFF/ON transitions into actual outage events.

    Incomplete historical pairs are ignored. If the feeder is currently OFF,
    the open outage is included through ``now`` (or ``current_end`` for the
    calendar entity's next-event state) using the latest OFF transition or the
    portal's current-status timestamp.
    """
    if not isinstance(load, dict):
        return []

    local_now = _as_pakistan_time(now)
    local_end = _as_pakistan_time(current_end) if current_end else local_now
    transitions: list[tuple[datetime, str]] = []
    raw_events = load.get("event_logs")
    if isinstance(raw_events, list):
        for item in raw_events:
            if not isinstance(item, dict):
                continue
            timestamp = _parse_portal_datetime(item.get("event_time"))
            status = str(item.get("event", "")).strip().upper()
            if (
                timestamp is not None
                and timestamp <= local_now
                and status in {"ON", "OFF"}
            ):
                transitions.append((timestamp, status))
    transitions.sort(key=lambda item: item[0])

    outages: list[CalendarEvent] = []
    open_start: datetime | None = None
    for timestamp, status in transitions:
        if status == "OFF":
            if open_start is None:
                open_start = timestamp
        elif open_start is not None:
            if timestamp > open_start:
                outages.append(
                    CalendarEvent(
                        summary="Actual outage",
                        start=open_start,
                        end=timestamp,
                        description="Observed feeder OFF-to-ON transition.",
                    )
                )
            open_start = None

    if str(load.get("current_status", "")).strip().upper() == "OFF":
        current_status_time = _parse_portal_datetime(load.get("current_status_time"))
        start = open_start or current_status_time
        if start is not None and start < local_now:
            outages.append(
                CalendarEvent(
                    summary="Actual outage (ongoing)",
                    start=start,
                    end=local_end,
                    description="The feeder is currently reported OFF.",
                )
            )

    return outages


def _parse_portal_datetime(value: Any) -> datetime | None:
    """Parse a portal timestamp, interpreting naive values as Pakistan time."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        raw_value = value.strip()
        if raw_value.endswith("Z"):
            raw_value = f"{raw_value[:-1]}+00:00"
        parsed = datetime.fromisoformat(raw_value)
    except ValueError:
        parsed = None
        for fmt in ("%d-%m-%Y %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
            try:
                parsed = datetime.strptime(value.strip(), fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    return _as_pakistan_time(parsed)


def _as_pakistan_time(value: datetime) -> datetime:
    """Attach or convert a datetime to the portal's timezone."""
    if value.tzinfo is None:
        return value.replace(tzinfo=_PAKISTAN_TZ)
    return value.astimezone(_PAKISTAN_TZ)
