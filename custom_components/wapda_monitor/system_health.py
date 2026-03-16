"""Provide system health information for WAPDA Monitor."""

from __future__ import annotations

from typing import Any

from homeassistant.components import system_health
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN

CCMS_PORTAL_URL = "https://ccms.pitc.com.pk"
ROSHAN_PORTAL_URL = "https://roshanpakistan.pk"


@callback
def async_register(
    hass: HomeAssistant,
    register: system_health.SystemHealthRegistration,
) -> None:
    """Register system health callbacks."""
    register.async_register_info(system_health_info)


async def system_health_info(hass: HomeAssistant) -> dict[str, Any]:
    """Get info for the info page."""
    entries = hass.config_entries.async_entries(DOMAIN)
    configured_accounts = len(entries)

    # Collect reference numbers (masked for privacy)
    references = []
    for entry in entries:
        ref = entry.data.get("reference", "")
        if len(ref) >= 6:
            references.append(f"{ref[:3]}...{ref[-3:]}")
        else:
            references.append(ref)

    return {
        "can_reach_server": system_health.async_check_can_reach_url(
            hass, CCMS_PORTAL_URL
        ),
        "can_reach_portal": system_health.async_check_can_reach_url(
            hass, ROSHAN_PORTAL_URL
        ),
        "configured_accounts": configured_accounts,
        "reference_numbers": ", ".join(references) if references else "None",
    }
