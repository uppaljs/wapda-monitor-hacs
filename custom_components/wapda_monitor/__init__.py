"""WAPDA Monitor — Home Assistant Integration.

Polls the Roshan Pakistan / CCMS PITC portal for real-time feeder
status, billing, customer info, and load-shedding schedules.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .api import WapdaClient
from .const import PLATFORMS
from .coordinator import WapdaDataCoordinator

_LOGGER = logging.getLogger(__name__)

type WapdaConfigEntry = ConfigEntry[WapdaDataCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: WapdaConfigEntry) -> bool:
    """Set up WAPDA Monitor from a config entry."""
    client = WapdaClient()
    coordinator = WapdaDataCoordinator(hass, entry, client)

    # Perform the first refresh — if this fails, setup is retried later
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Reload on option changes (polling intervals)
    entry.async_on_unload(entry.add_update_listener(_async_update_options))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: WapdaConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_options(
    hass: HomeAssistant, entry: WapdaConfigEntry
) -> None:
    """Reload the integration when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
