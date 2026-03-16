"""Tests for the WAPDA Monitor async API client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from custom_components.wapda_monitor.api import (
    WapdaApiError,
    WapdaClient,
    WapdaConnectionError,
)


@pytest.fixture
def mock_session() -> MagicMock:
    """Create a mock aiohttp.ClientSession."""
    return MagicMock(spec=aiohttp.ClientSession)


@pytest.fixture
def client(mock_session: MagicMock) -> WapdaClient:
    """Create a WapdaClient with a mock session."""
    return WapdaClient(mock_session, timeout=5)


def _make_response(status: int = 200, json_data: dict | None = None) -> MagicMock:
    """Create a mock aiohttp response as an async context manager."""
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data or {})
    resp.read = AsyncMock(return_value=b"")

    # Make it work as async context manager for session.request / session.get
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


class TestWapdaClientInit:
    """Tests for WapdaClient initialization."""

    def test_not_initialized_by_default(self, client: WapdaClient) -> None:
        """Test client starts uninitialized."""
        assert client._initialized is False

    def test_default_timeout(self, mock_session: MagicMock) -> None:
        """Test default timeout value."""
        c = WapdaClient(mock_session)
        assert c._timeout.total == 30

    def test_custom_timeout(self, mock_session: MagicMock) -> None:
        """Test custom timeout value."""
        c = WapdaClient(mock_session, timeout=10)
        assert c._timeout.total == 10


class TestEnsureSession:
    """Tests for session initialization."""

    async def test_ensure_session_success(
        self, client: WapdaClient, mock_session: MagicMock
    ) -> None:
        """Test successful session initialization."""
        mock_session.get = MagicMock(return_value=_make_response(200))
        await client._ensure_session()
        assert client._initialized is True

    async def test_ensure_session_already_initialized(
        self, client: WapdaClient, mock_session: MagicMock
    ) -> None:
        """Test session not re-initialized."""
        client._initialized = True
        await client._ensure_session()
        mock_session.get.assert_not_called()

    async def test_ensure_session_connection_error(
        self, client: WapdaClient, mock_session: MagicMock
    ) -> None:
        """Test session init raises on connection error."""
        mock_session.get = MagicMock(
            side_effect=aiohttp.ClientError("Cannot connect")
        )
        with pytest.raises(WapdaConnectionError, match="Cannot reach"):
            await client._ensure_session()


class TestRequest:
    """Tests for the _request helper."""

    async def test_connection_error(
        self, client: WapdaClient, mock_session: MagicMock
    ) -> None:
        """Test _request wraps ClientConnectorError."""
        mock_session.request = MagicMock(
            side_effect=aiohttp.ClientConnectorError(
                connection_key=MagicMock(), os_error=OSError("Connection refused")
            )
        )
        with pytest.raises(WapdaConnectionError, match="Connection failed"):
            await client._request("GET", "http://example.com")

    async def test_timeout_error(
        self, client: WapdaClient, mock_session: MagicMock
    ) -> None:
        """Test _request wraps ServerTimeoutError."""
        mock_session.request = MagicMock(
            side_effect=aiohttp.ServerTimeoutError("Timeout")
        )
        with pytest.raises(WapdaConnectionError, match="timed out"):
            await client._request("GET", "http://example.com")

    async def test_ssl_error(
        self, client: WapdaClient, mock_session: MagicMock
    ) -> None:
        """Test _request wraps ClientSSLError."""
        mock_session.request = MagicMock(
            side_effect=aiohttp.ClientSSLError(
                connection_key=MagicMock(), os_error=OSError("SSL error")
            )
        )
        with pytest.raises(WapdaConnectionError, match="SSL/TLS error"):
            await client._request("GET", "http://example.com")

    async def test_http_429(
        self, client: WapdaClient, mock_session: MagicMock
    ) -> None:
        """Test _request raises on 429."""
        mock_session.request = MagicMock(return_value=_make_response(429))
        with pytest.raises(WapdaApiError, match="Rate limited"):
            await client._request("GET", "http://example.com/test")

    async def test_http_500(
        self, client: WapdaClient, mock_session: MagicMock
    ) -> None:
        """Test _request raises on 500."""
        mock_session.request = MagicMock(return_value=_make_response(500))
        with pytest.raises(WapdaApiError, match="Server error"):
            await client._request("GET", "http://example.com/test")

    async def test_success(
        self, client: WapdaClient, mock_session: MagicMock
    ) -> None:
        """Test _request returns parsed JSON on success."""
        mock_session.request = MagicMock(
            return_value=_make_response(200, {"key": "value"})
        )
        result = await client._request("GET", "http://example.com")
        assert result == {"key": "value"}

    async def test_invalid_json(
        self, client: WapdaClient, mock_session: MagicMock
    ) -> None:
        """Test _request raises on invalid JSON."""
        resp = AsyncMock()
        resp.status = 200
        resp.json = AsyncMock(side_effect=ValueError("No JSON"))
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=resp)
        ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session.request = MagicMock(return_value=ctx)
        with pytest.raises(WapdaApiError, match="Invalid JSON"):
            await client._request("GET", "http://example.com/test")


class TestGetLoadInfo:
    """Tests for get_load_info."""

    async def test_success(
        self, client: WapdaClient, mock_session: MagicMock
    ) -> None:
        """Test successful load info retrieval."""
        client._initialized = True
        json_data = {
            "message": "Success",
            "load": [
                {
                    "statusCode": 1,
                    "response": {
                        "data": [
                            {
                                "feeder_code": "FDR001",
                                "current_status": "ON",
                            }
                        ]
                    },
                }
            ],
        }
        mock_session.request = MagicMock(
            return_value=_make_response(200, json_data)
        )
        result = await client.get_load_info("01234567890123")
        assert result["feeder_code"] == "FDR001"
        assert result["current_status"] == "ON"

    async def test_api_error_message(
        self, client: WapdaClient, mock_session: MagicMock
    ) -> None:
        """Test load info raises on non-success message."""
        client._initialized = True
        mock_session.request = MagicMock(
            return_value=_make_response(200, {"message": "Error"})
        )
        with pytest.raises(WapdaApiError, match="API error"):
            await client.get_load_info("01234567890123")


class TestGetUserDetails:
    """Tests for get_user_details."""

    async def test_success(
        self, client: WapdaClient, mock_session: MagicMock
    ) -> None:
        """Test successful user details retrieval."""
        client._initialized = True
        mock_session.request = MagicMock(
            return_value=_make_response(
                200, {"user": {"NAME": "Test User", "TARIFF": "A1"}}
            )
        )
        result = await client.get_user_details("01234567890123")
        assert result["NAME"] == "Test User"

    async def test_no_user(
        self, client: WapdaClient, mock_session: MagicMock
    ) -> None:
        """Test user details raises when no user found."""
        client._initialized = True
        mock_session.request = MagicMock(
            return_value=_make_response(200, {"user": None})
        )
        with pytest.raises(WapdaApiError, match="No user found"):
            await client.get_user_details("01234567890123")


class TestGetBillDetails:
    """Tests for get_bill_details."""

    async def test_success(
        self, client: WapdaClient, mock_session: MagicMock
    ) -> None:
        """Test successful bill retrieval."""
        client._initialized = True
        mock_session.request = MagicMock(
            return_value=_make_response(
                200, {"bill": {"NETAMT": "5000", "DUEDATE": "2025-02-15"}}
            )
        )
        result = await client.get_bill_details("01234567890123")
        assert result["NETAMT"] == "5000"

    async def test_no_bill(
        self, client: WapdaClient, mock_session: MagicMock
    ) -> None:
        """Test bill details raises when no billing data."""
        client._initialized = True
        mock_session.request = MagicMock(
            return_value=_make_response(200, {"bill": None})
        )
        with pytest.raises(WapdaApiError, match="No billing data"):
            await client.get_bill_details("01234567890123")


class TestGetSchedule:
    """Tests for get_schedule."""

    async def test_success(
        self, client: WapdaClient, mock_session: MagicMock
    ) -> None:
        """Test successful schedule retrieval."""
        client._initialized = True
        mock_session.request = MagicMock(
            return_value=_make_response(
                200,
                {"loaddata": [{"maintenance_sch": {str(i): 0 for i in range(24)}}]},
            )
        )
        result = await client.get_schedule("FDR001", "01000")
        assert "maintenance_sch" in result

    async def test_no_schedule(
        self, client: WapdaClient, mock_session: MagicMock
    ) -> None:
        """Test schedule raises when no data."""
        client._initialized = True
        mock_session.request = MagicMock(
            return_value=_make_response(200, {"loaddata": []})
        )
        with pytest.raises(WapdaApiError, match="No schedule data"):
            await client.get_schedule("FDR001", "01000")


class TestValidateReference:
    """Tests for validate_reference."""

    async def test_valid_reference(
        self, client: WapdaClient, mock_session: MagicMock
    ) -> None:
        """Test valid reference returns name."""
        client._initialized = True
        mock_session.request = MagicMock(
            return_value=_make_response(
                200, {"user": {"NAME": "Test Consumer"}}
            )
        )
        result = await client.validate_reference("01234567890123")
        assert result == "Test Consumer"

    async def test_invalid_format(self, client: WapdaClient) -> None:
        """Test invalid reference format raises."""
        with pytest.raises(WapdaApiError, match="14 digits"):
            await client.validate_reference("12345")

    async def test_empty_name(
        self, client: WapdaClient, mock_session: MagicMock
    ) -> None:
        """Test reference with empty name returns None."""
        client._initialized = True
        mock_session.request = MagicMock(
            return_value=_make_response(200, {"user": {"NAME": "  "}})
        )
        result = await client.validate_reference("01234567890123")
        assert result is None
