"""Tests for the WAPDA Monitor API client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from custom_components.wapda_monitor.api import (
    BASE_URL,
    WapdaApiError,
    WapdaClient,
    WapdaConnectionError,
)


@pytest.fixture
def client() -> WapdaClient:
    """Create a WapdaClient instance."""
    return WapdaClient(timeout=5)


class TestWapdaClientInit:
    """Tests for WapdaClient initialization."""

    def test_creates_session(self, client: WapdaClient) -> None:
        """Test client creates a requests session."""
        assert client.session is not None
        assert isinstance(client.session, requests.Session)

    def test_not_initialized_by_default(self, client: WapdaClient) -> None:
        """Test client starts uninitialized."""
        assert client._initialized is False

    def test_default_timeout(self) -> None:
        """Test default timeout value."""
        c = WapdaClient()
        assert c.timeout == 30

    def test_custom_timeout(self) -> None:
        """Test custom timeout value."""
        c = WapdaClient(timeout=10)
        assert c.timeout == 10


class TestEnsureSession:
    """Tests for session initialization."""

    def test_ensure_session_success(self, client: WapdaClient) -> None:
        """Test successful session initialization."""
        with patch.object(client.session, "get") as mock_get:
            mock_get.return_value = MagicMock(status_code=200)
            client._ensure_session()
            assert client._initialized is True
            mock_get.assert_called_once()

    def test_ensure_session_already_initialized(self, client: WapdaClient) -> None:
        """Test session not re-initialized."""
        client._initialized = True
        with patch.object(client.session, "get") as mock_get:
            client._ensure_session()
            mock_get.assert_not_called()

    def test_ensure_session_connection_error(self, client: WapdaClient) -> None:
        """Test session init raises on connection error."""
        with patch.object(
            client.session, "get", side_effect=requests.exceptions.ConnectionError()
        ):
            with pytest.raises(WapdaConnectionError, match="Cannot reach"):
                client._ensure_session()


class TestSafeRequest:
    """Tests for the _safe_request helper."""

    def test_connection_error(self, client: WapdaClient) -> None:
        """Test _safe_request wraps ConnectionError."""
        with patch.object(
            client.session,
            "request",
            side_effect=requests.exceptions.ConnectionError(),
        ):
            with pytest.raises(WapdaConnectionError, match="Connection failed"):
                client._safe_request("GET", "http://example.com")

    def test_timeout_error(self, client: WapdaClient) -> None:
        """Test _safe_request wraps Timeout."""
        with patch.object(
            client.session,
            "request",
            side_effect=requests.exceptions.Timeout(),
        ):
            with pytest.raises(WapdaConnectionError, match="timed out"):
                client._safe_request("GET", "http://example.com")

    def test_ssl_error(self, client: WapdaClient) -> None:
        """Test _safe_request wraps SSLError.

        Note: requests.SSLError is a subclass of requests.ConnectionError,
        so it is caught by the ConnectionError handler in _safe_request.
        """
        with patch.object(
            client.session,
            "request",
            side_effect=requests.exceptions.SSLError(),
        ):
            with pytest.raises(WapdaConnectionError, match="Connection failed"):
                client._safe_request("GET", "http://example.com")

    def test_http_429(self, client: WapdaClient) -> None:
        """Test _safe_request raises on 429."""
        mock_resp = MagicMock(status_code=429)
        with patch.object(client.session, "request", return_value=mock_resp):
            with pytest.raises(WapdaApiError, match="Rate limited"):
                client._safe_request("GET", "http://example.com/test")

    def test_http_500(self, client: WapdaClient) -> None:
        """Test _safe_request raises on 500."""
        mock_resp = MagicMock(status_code=500)
        with patch.object(client.session, "request", return_value=mock_resp):
            with pytest.raises(WapdaApiError, match="Server error"):
                client._safe_request("GET", "http://example.com/test")

    def test_success(self, client: WapdaClient) -> None:
        """Test _safe_request returns response on success."""
        mock_resp = MagicMock(status_code=200)
        with patch.object(client.session, "request", return_value=mock_resp):
            resp = client._safe_request("GET", "http://example.com")
            assert resp.status_code == 200


class TestGetLoadInfo:
    """Tests for get_load_info."""

    def test_success(self, client: WapdaClient) -> None:
        """Test successful load info retrieval."""
        client._initialized = True
        mock_json = {
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
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = mock_json

        with patch.object(client.session, "request", return_value=mock_resp):
            result = client.get_load_info("01234567890123")

        assert result["feeder_code"] == "FDR001"
        assert result["current_status"] == "ON"

    def test_api_error_message(self, client: WapdaClient) -> None:
        """Test load info raises on non-success message."""
        client._initialized = True
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"message": "Error"}

        with patch.object(client.session, "request", return_value=mock_resp):
            with pytest.raises(WapdaApiError, match="API error"):
                client.get_load_info("01234567890123")

    def test_invalid_json(self, client: WapdaClient) -> None:
        """Test load info raises on invalid JSON."""
        client._initialized = True
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.side_effect = ValueError("No JSON")

        with patch.object(client.session, "request", return_value=mock_resp):
            with pytest.raises(WapdaApiError, match="invalid JSON"):
                client.get_load_info("01234567890123")


class TestGetUserDetails:
    """Tests for get_user_details."""

    def test_success(self, client: WapdaClient) -> None:
        """Test successful user details retrieval."""
        client._initialized = True
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            "user": {"NAME": "Test User", "TARIFF": "A1"}
        }

        with patch.object(client.session, "request", return_value=mock_resp):
            result = client.get_user_details("01234567890123")

        assert result["NAME"] == "Test User"

    def test_no_user(self, client: WapdaClient) -> None:
        """Test user details raises when no user found."""
        client._initialized = True
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"user": None}

        with patch.object(client.session, "request", return_value=mock_resp):
            with pytest.raises(WapdaApiError, match="No user found"):
                client.get_user_details("01234567890123")


class TestGetBillDetails:
    """Tests for get_bill_details."""

    def test_success(self, client: WapdaClient) -> None:
        """Test successful bill retrieval."""
        client._initialized = True
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            "bill": {"NETAMT": "5000", "DUEDATE": "2025-02-15"}
        }

        with patch.object(client.session, "request", return_value=mock_resp):
            result = client.get_bill_details("01234567890123")

        assert result["NETAMT"] == "5000"

    def test_no_bill(self, client: WapdaClient) -> None:
        """Test bill details raises when no billing data."""
        client._initialized = True
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"bill": None}

        with patch.object(client.session, "request", return_value=mock_resp):
            with pytest.raises(WapdaApiError, match="No billing data"):
                client.get_bill_details("01234567890123")


class TestGetSchedule:
    """Tests for get_schedule."""

    def test_success(self, client: WapdaClient) -> None:
        """Test successful schedule retrieval."""
        client._initialized = True
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            "loaddata": [{"maintenance_sch": {str(i): 0 for i in range(24)}}]
        }

        with patch.object(client.session, "request", return_value=mock_resp):
            result = client.get_schedule("FDR001", "01000")

        assert "maintenance_sch" in result

    def test_no_schedule(self, client: WapdaClient) -> None:
        """Test schedule raises when no data."""
        client._initialized = True
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"loaddata": []}

        with patch.object(client.session, "request", return_value=mock_resp):
            with pytest.raises(WapdaApiError, match="No schedule data"):
                client.get_schedule("FDR001", "01000")


class TestValidateReference:
    """Tests for validate_reference."""

    def test_valid_reference(self, client: WapdaClient) -> None:
        """Test valid reference returns name."""
        client._initialized = True
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"user": {"NAME": "Test Consumer"}}

        with patch.object(client.session, "request", return_value=mock_resp):
            result = client.validate_reference("01234567890123")

        assert result == "Test Consumer"

    def test_invalid_format(self, client: WapdaClient) -> None:
        """Test invalid reference format raises."""
        with pytest.raises(WapdaApiError, match="14 digits"):
            client.validate_reference("12345")

    def test_empty_name(self, client: WapdaClient) -> None:
        """Test reference with empty name returns None."""
        client._initialized = True
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"user": {"NAME": "  "}}

        with patch.object(client.session, "request", return_value=mock_resp):
            result = client.validate_reference("01234567890123")

        assert result is None
