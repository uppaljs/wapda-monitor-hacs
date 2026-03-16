"""Tests for WAPDA Monitor system health."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from custom_components.wapda_monitor.const import DOMAIN
from custom_components.wapda_monitor.system_health import (
    system_health_info,
)

from .const import MOCK_REFERENCE


async def test_system_health_info(
    hass: HomeAssistant,
    mock_config_entry,
) -> None:
    """Test system health returns expected info."""
    mock_config_entry.add_to_hass(hass)

    info = await system_health_info(hass)

    assert "can_reach_server" in info
    assert "can_reach_portal" in info
    assert info["configured_accounts"] == 1
    # Reference should be masked
    assert "..." in info["reference_numbers"]
    assert info["reference_numbers"] == f"{MOCK_REFERENCE[:3]}...{MOCK_REFERENCE[-3:]}"


async def test_system_health_no_entries(
    hass: HomeAssistant,
) -> None:
    """Test system health with no configured entries."""
    info = await system_health_info(hass)

    assert info["configured_accounts"] == 0
    assert info["reference_numbers"] == "None"


async def test_system_health_multiple_entries(
    hass: HomeAssistant,
    mock_config_entry,
) -> None:
    """Test system health with multiple entries."""
    mock_config_entry.add_to_hass(hass)

    # Add a second entry
    from homeassistant.config_entries import ConfigEntry

    second_ref = "98765432109876"
    second_entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title=f"WAPDA {second_ref}",
        data={"reference": second_ref},
        source="user",
        unique_id=second_ref,
        options={},
    )
    second_entry.add_to_hass(hass)

    info = await system_health_info(hass)

    assert info["configured_accounts"] == 2
    assert "012...123" in info["reference_numbers"]
    assert "987...876" in info["reference_numbers"]
