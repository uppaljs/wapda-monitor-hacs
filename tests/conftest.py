"""Fixtures for WAPDA Monitor tests."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.wapda_monitor.const import DOMAIN

from .const import (
    MOCK_BILL_DATA,
    MOCK_LOAD_DATA,
    MOCK_REFERENCE,
    MOCK_SCHEDULE_DATA,
    MOCK_USER_DATA,
)


@pytest.fixture
def mock_config_entry() -> ConfigEntry:
    """Create a mock config entry."""
    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title=f"WAPDA {MOCK_REFERENCE}",
        data={"reference": MOCK_REFERENCE},
        source="user",
        unique_id=MOCK_REFERENCE,
        options={},
    )
    return entry


@pytest.fixture
def mock_wapda_client() -> Generator[MagicMock, None, None]:
    """Mock the WapdaClient."""
    with patch(
        "custom_components.wapda_monitor.api.WapdaClient",
        autospec=True,
    ) as mock_cls:
        client = mock_cls.return_value
        client.get_load_info.return_value = MOCK_LOAD_DATA
        client.get_user_details.return_value = MOCK_USER_DATA
        client.get_bill_details.return_value = MOCK_BILL_DATA
        client.get_schedule.return_value = MOCK_SCHEDULE_DATA
        client.validate_reference.return_value = "Test Consumer"
        yield client


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock, None, None]:
    """Mock the async_setup_entry function."""
    with patch(
        "custom_components.wapda_monitor.async_setup_entry",
        return_value=True,
    ) as mock_setup:
        yield mock_setup
