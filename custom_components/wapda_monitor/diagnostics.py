"""Diagnostics support for WAPDA Monitor."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import WapdaConfigEntry
from .const import CONF_REFERENCE

# Keys to redact from config entry data and coordinator data
TO_REDACT_CONFIG = {CONF_REFERENCE}
# Any key containing one of these (case-insensitive) is redacted, at any depth.
# Covers the real CCMS payload: consumerName, consumerAddress1,
# consumerContactNo, owner_cnic, consumerEmail, refNo, ckey, appNo, barCodeMsg,
# the user endpoint's NAME/FNAME/ADDR1/ADDR2/CONTACTNO/NICNO/GPSLATI/GPSLONG,
# and the meter serial numbers.
_REDACT_SUBSTRINGS = (
    "name", "addr", "cnic", "nicno", "contact", "mobile", "phone", "email",
    "refno", "reference", "ckey", "appno", "barcode", "fname", "msn", "mtrno",
    "gps", "lati", "longi",
)
# Feeder/grid names are not personal data and are useful for debugging.
_KEEP_KEYS = {"feedername", "feeder", "grid", "divname", "subdivname"}
REDACTED = "**REDACTED**"


def _should_redact(key: str) -> bool:
    k = key.lower()
    if k in _KEEP_KEYS:
        return False
    return any(sub in k for sub in _REDACT_SUBSTRINGS)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: (REDACTED if _should_redact(str(k)) else _redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: WapdaConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    data = coordinator.data or {}

    return {
        "config_entry": {
            "title": "REDACTED" if entry.title else "",
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
    return _redact(data)
