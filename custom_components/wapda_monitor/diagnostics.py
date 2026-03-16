"""Diagnostics support for WAPDA Monitor."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_REFERENCE,
    DOMAIN,
)

# Keys to redact from config entry data and coordinator data
TO_REDACT_CONFIG = {CONF_REFERENCE}
TO_REDACT_DATA = {
    "reference",
    "CONSNAME",       # consumer name
    "CONSUMERNAME",
    "CONSADDRESS",    # consumer address
    "ADDRESS",
    "CNIC",           # national ID
    "MOBILE",         # phone number
    "PHONE",
    "EMAIL",
    "consumer_name",
    "consumer_address",
    "name",
    "address",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data or {}

    return {
        "config_entry": {
            "title": entry.title,
            "data": async_redact_data(dict(entry.data), TO_REDACT_CONFIG),
            "options": dict(entry.options),
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval_seconds": (
                coordinator.update_interval.total_seconds()
                if coordinator.update_interval
                else None
            ),
        },
        "data": {
            "load": _redact_dict(data.get("load")),
            "user": _redact_dict(data.get("user")),
            "bill": _redact_dict(data.get("bill")),
            "schedule": data.get("schedule"),
        },
    }


def _redact_dict(data: dict | None) -> dict | None:
    """Redact sensitive keys from a data dictionary."""
    if data is None:
        return None
    return async_redact_data(data, TO_REDACT_DATA)
