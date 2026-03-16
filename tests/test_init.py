"""Tests for WAPDA Monitor integration setup and unload."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from .const import MOCK_COORDINATOR_DATA, MOCK_REFERENCE

PATCH_CLIENT = "custom_components.wapda_monitor.WapdaClient"
PATCH_SESSION = "custom_components.wapda_monitor.async_get_clientsession"


async def test_setup_entry(
    hass: HomeAssistant,
    mock_config_entry,
    mock_wapda_client: MagicMock,
) -> None:
    """Test successful setup of a config entry."""
    mock_config_entry.add_to_hass(hass)

    with (
        patch(PATCH_SESSION, return_value=MagicMock()),
        patch(PATCH_CLIENT, return_value=mock_wapda_client),
        patch(
            "custom_components.wapda_monitor.coordinator.WapdaDataCoordinator._async_update_data",
            return_value=MOCK_COORDINATOR_DATA,
        ),
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert mock_config_entry.runtime_data is not None


async def test_unload_entry(
    hass: HomeAssistant,
    mock_config_entry,
    mock_wapda_client: MagicMock,
) -> None:
    """Test unloading a config entry."""
    mock_config_entry.add_to_hass(hass)

    with (
        patch(PATCH_SESSION, return_value=MagicMock()),
        patch(PATCH_CLIENT, return_value=mock_wapda_client),
        patch(
            "custom_components.wapda_monitor.coordinator.WapdaDataCoordinator._async_update_data",
            return_value=MOCK_COORDINATOR_DATA,
        ),
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED

    await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_entry_connection_error(
    hass: HomeAssistant,
    mock_config_entry,
) -> None:
    """Test setup fails gracefully when the API is unreachable."""
    from custom_components.wapda_monitor.api import WapdaConnectionError

    mock_config_entry.add_to_hass(hass)

    with (
        patch(PATCH_SESSION, return_value=MagicMock()),
        patch(PATCH_CLIENT),
        patch(
            "custom_components.wapda_monitor.coordinator.WapdaDataCoordinator._async_update_data",
            side_effect=WapdaConnectionError("Cannot connect"),
        ),
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
