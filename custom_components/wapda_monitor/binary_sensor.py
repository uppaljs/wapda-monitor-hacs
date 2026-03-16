"""Binary sensor platform for WAPDA Monitor."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import WapdaConfigEntry
from .const import CONF_REFERENCE, DATA_LOAD, DATA_SCHEDULE, DOMAIN, MANUFACTURER
from .coordinator import WapdaDataCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WapdaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up WAPDA Monitor binary sensors."""
    coordinator = entry.runtime_data
    reference = entry.data[CONF_REFERENCE]

    entities = [
        WapdaBinarySensor(
            coordinator,
            reference,
            key="feeder_off",
            name="Feeder OFF",
            icon_on="mdi:transmission-tower-off",
            icon_off="mdi:transmission-tower",
            device_class=BinarySensorDeviceClass.PROBLEM,
            category="load",
            value_fn=lambda d: (
                (d.get("current_status") or "").upper() == "OFF"
                if d else None
            ),
            attrs_fn=lambda d: {
                "status_since": d.get("current_status_time"),
                "voltage": d.get("voltage"),
                "remarks": d.get("remarks"),
            } if d else {},
        ),
        WapdaBinarySensor(
            coordinator,
            reference,
            key="scheduled_outage_now",
            name="Scheduled Outage Now",
            icon_on="mdi:calendar-remove",
            icon_off="mdi:calendar-check",
            device_class=BinarySensorDeviceClass.PROBLEM,
            category="schedule",
            value_fn=_is_scheduled_outage_now,
        ),
    ]

    async_add_entities(entities)


def _is_scheduled_outage_now(schedule: dict | None) -> bool | None:
    """Check if there is a scheduled outage for the current hour."""
    if not schedule:
        return None
    maint = schedule.get("maintenance_sch", [])
    if not maint or not isinstance(maint, list):
        return None
    now_hour = datetime.now().hour
    if now_hour < len(maint):
        return maint[now_hour] > 0
    return None


class WapdaBinarySensor(
    CoordinatorEntity[WapdaDataCoordinator], BinarySensorEntity
):
    """Representation of a single WAPDA Monitor binary sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: WapdaDataCoordinator,
        reference: str,
        *,
        key: str,
        name: str,
        icon_on: str,
        icon_off: str,
        device_class: BinarySensorDeviceClass | None = None,
        category: str,
        value_fn,
        attrs_fn=None,
    ) -> None:
        super().__init__(coordinator)
        self._reference = reference
        self._key = key
        self._category = category
        self._value_fn = value_fn
        self._attrs_fn = attrs_fn
        self._icon_on = icon_on
        self._icon_off = icon_off

        self._attr_name = name
        self._attr_unique_id = f"wapda_{reference}_{key}"
        self._attr_device_class = device_class

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._reference)},
            name=f"WAPDA Feeder Monitor {self._reference}",
            manufacturer=MANUFACTURER,
            model="WAPDA Feeder Monitor",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        if not data:
            return None
        category_data = data.get(self._category)
        try:
            return self._value_fn(category_data)
        except Exception:  # noqa: BLE001
            return None

    @property
    def icon(self) -> str:
        return self._icon_on if self.is_on else self._icon_off

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self._attrs_fn is None:
            return None
        data = self.coordinator.data
        if not data:
            return None
        category_data = data.get(self._category)
        try:
            return self._attrs_fn(category_data)
        except Exception:  # noqa: BLE001
            return None

