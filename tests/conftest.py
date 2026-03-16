"""Fixtures for WAPDA Monitor tests."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wapda_monitor.const import DOMAIN

from .const import (
    MOCK_BILL_DATA,
    MOCK_LOAD_DATA,
    MOCK_REFERENCE,
    MOCK_SCHEDULE_DATA,
    MOCK_USER_DATA,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations,
) -> None:
    """Enable custom integrations for all tests."""
    return


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Create a mock config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=f"WAPDA {MOCK_REFERENCE}",
        data={"reference": MOCK_REFERENCE},
        unique_id=MOCK_REFERENCE,
        version=1,
    )


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
