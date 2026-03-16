"""Tests for the WAPDA Monitor data coordinator."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.wapda_monitor.api import WapdaApiError, WapdaConnectionError
from custom_components.wapda_monitor.const import (
    DATA_BILL,
    DATA_LOAD,
    DATA_SCHEDULE,
    DATA_USER,
    DEFAULT_SCAN_INTERVAL_LOAD,
)
from custom_components.wapda_monitor.coordinator import WapdaDataCoordinator

from .const import (
    MOCK_BILL_DATA,
    MOCK_LOAD_DATA,
    MOCK_REFERENCE,
    MOCK_SCHEDULE_DATA,
    MOCK_USER_DATA,
)


@pytest.fixture
def coordinator(
    hass: HomeAssistant,
    mock_config_entry,
    mock_wapda_client: MagicMock,
) -> WapdaDataCoordinator:
    """Create a WapdaDataCoordinator for testing."""
    mock_config_entry.add_to_hass(hass)
    return WapdaDataCoordinator(hass, mock_config_entry, mock_wapda_client)


class TestCoordinatorInit:
    """Tests for coordinator initialization."""

    def test_reference(self, coordinator: WapdaDataCoordinator) -> None:
        """Test coordinator stores reference."""
        assert coordinator.reference == MOCK_REFERENCE

    def test_update_interval(self, coordinator: WapdaDataCoordinator) -> None:
        """Test coordinator uses default update interval."""
        assert coordinator.update_interval == timedelta(
            seconds=DEFAULT_SCAN_INTERVAL_LOAD
        )

    def test_initial_caches_empty(self, coordinator: WapdaDataCoordinator) -> None:
        """Test caches are initially empty."""
        assert coordinator._cached_user is None
        assert coordinator._cached_bill is None
        assert coordinator._cached_schedule is None


class TestCoordinatorUpdate:
    """Tests for _async_update_data."""

    async def test_full_update(
        self,
        hass: HomeAssistant,
        coordinator: WapdaDataCoordinator,
        mock_wapda_client: MagicMock,
    ) -> None:
        """Test a full update cycle returns all data."""
        data = await coordinator._async_update_data()

        assert DATA_LOAD in data
        assert DATA_USER in data
        assert DATA_BILL in data
        assert DATA_SCHEDULE in data
        assert data[DATA_LOAD] == MOCK_LOAD_DATA
        assert data[DATA_USER] == MOCK_USER_DATA

    async def test_load_connection_error_no_cache(
        self,
        hass: HomeAssistant,
        coordinator: WapdaDataCoordinator,
        mock_wapda_client: MagicMock,
    ) -> None:
        """Test UpdateFailed raised when load fails with no cached data."""
        mock_wapda_client.get_load_info.side_effect = WapdaConnectionError(
            "Cannot connect"
        )

        with pytest.raises(UpdateFailed, match="Cannot reach CCMS"):
            await coordinator._async_update_data()

    async def test_load_connection_error_with_cache(
        self,
        hass: HomeAssistant,
        coordinator: WapdaDataCoordinator,
        mock_wapda_client: MagicMock,
    ) -> None:
        """Test load error returns None when cached data exists."""
        # First populate the cache
        coordinator._cached_user = MOCK_USER_DATA

        mock_wapda_client.get_load_info.side_effect = WapdaConnectionError(
            "Cannot connect"
        )

        data = await coordinator._async_update_data()
        assert data[DATA_LOAD] is None
        assert data[DATA_USER] == MOCK_USER_DATA

    async def test_load_api_error(
        self,
        hass: HomeAssistant,
        coordinator: WapdaDataCoordinator,
        mock_wapda_client: MagicMock,
    ) -> None:
        """Test load API error sets load to None."""
        mock_wapda_client.get_load_info.side_effect = WapdaApiError("Bad data")

        data = await coordinator._async_update_data()
        assert data[DATA_LOAD] is None

    async def test_user_cached_after_first_fetch(
        self,
        hass: HomeAssistant,
        coordinator: WapdaDataCoordinator,
        mock_wapda_client: MagicMock,
    ) -> None:
        """Test user data is fetched once then cached."""
        await coordinator._async_update_data()
        assert coordinator._cached_user == MOCK_USER_DATA

        # Second call should not refetch user
        mock_wapda_client.get_user_details.reset_mock()
        await coordinator._async_update_data()
        mock_wapda_client.get_user_details.assert_not_called()

    async def test_user_fetch_failure(
        self,
        hass: HomeAssistant,
        coordinator: WapdaDataCoordinator,
        mock_wapda_client: MagicMock,
    ) -> None:
        """Test user fetch failure is handled gracefully."""
        mock_wapda_client.get_user_details.side_effect = WapdaApiError("No user")

        data = await coordinator._async_update_data()
        assert data[DATA_USER] is None
        assert coordinator._cached_user is None


class TestResolveFeederCode:
    """Tests for _resolve_feeder_code static method."""

    def test_from_load_info(self) -> None:
        """Test feeder code from load info."""
        data = {DATA_LOAD: {"feeder_code": "FDR001"}, DATA_USER: None}
        assert WapdaDataCoordinator._resolve_feeder_code(data) == "FDR001"

    def test_from_user_details(self) -> None:
        """Test feeder code falls back to user details."""
        data = {
            DATA_LOAD: None,
            DATA_USER: {"FEEDERCD": "FDR002"},
        }
        assert WapdaDataCoordinator._resolve_feeder_code(data) == "FDR002"

    def test_none_when_missing(self) -> None:
        """Test None when feeder code unavailable."""
        data = {DATA_LOAD: None, DATA_USER: None}
        assert WapdaDataCoordinator._resolve_feeder_code(data) is None

    def test_empty_feeder_code(self) -> None:
        """Test empty string feeder code returns None."""
        data = {
            DATA_LOAD: {"feeder_code": ""},
            DATA_USER: {"FEEDERCD": "  "},
        }
        assert WapdaDataCoordinator._resolve_feeder_code(data) is None
