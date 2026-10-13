"""Tests for the WAPDA Monitor async API client."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from custom_components.wapda_monitor import api
from custom_components.wapda_monitor.api import (
    WapdaApiError,
    WapdaClient,
    WapdaConnectionError,
    WapdaRateLimitError,
)

REF = "01234567890123"


@pytest.fixture(autouse=True)
def fast_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Disable throttling and back-off sleeps in tests."""
    monkeypatch.setattr(api, "MIN_REQUEST_GAP", 0.0)
    monkeypatch.setattr(api, "RATE_LIMIT_BACKOFF", 0.0)


@pytest.fixture
def mock_session() -> MagicMock:
    """Create a mock aiohttp.ClientSession."""
    return MagicMock(spec=aiohttp.ClientSession)


@pytest.fixture
def client(mock_session: MagicMock) -> WapdaClient:
    """Create a WapdaClient with a mock session, warm-up already done."""
    c = WapdaClient(mock_session, timeout=5)
    c._initialized = True
    return c


def _make_response(status: int = 200, json_data: Any = None) -> MagicMock:
    """Create a mock aiohttp response as an async context manager."""
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value={} if json_data is None else json_data)
    resp.read = AsyncMock(return_value=b"")
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


class TestInit:
    def test_not_initialized_by_default(self, mock_session: MagicMock) -> None:
        assert WapdaClient(mock_session)._initialized is False

    def test_timeouts(self, mock_session: MagicMock) -> None:
        assert WapdaClient(mock_session)._timeout.total == 30
        assert WapdaClient(mock_session, timeout=10)._timeout.total == 10


class TestEnsureSession:
    async def test_success(self, mock_session: MagicMock) -> None:
        c = WapdaClient(mock_session)
        mock_session.get = MagicMock(return_value=_make_response(200))
        await c._ensure_session()
        assert c._initialized is True

    async def test_already_initialized(
        self, client: WapdaClient, mock_session: MagicMock
    ) -> None:
        await client._ensure_session()
        mock_session.get.assert_not_called()

    async def test_connection_error(self, mock_session: MagicMock) -> None:
        c = WapdaClient(mock_session)
        mock_session.get = MagicMock(side_effect=aiohttp.ClientError("boom"))
        with pytest.raises(WapdaConnectionError, match="Cannot reach"):
            await c._ensure_session()
        assert c._initialized is False


class TestGetJson:
    async def test_connection_error(
        self, client: WapdaClient, mock_session: MagicMock
    ) -> None:
        mock_session.get = MagicMock(
            side_effect=aiohttp.ClientConnectorError(
                connection_key=MagicMock(), os_error=OSError("refused")
            )
        )
        with pytest.raises(WapdaConnectionError, match="Connection failed"):
            await client._get_json("/x")

    async def test_timeout(
        self, client: WapdaClient, mock_session: MagicMock
    ) -> None:
        mock_session.get = MagicMock(side_effect=TimeoutError())
        with pytest.raises(WapdaConnectionError, match="timed out"):
            await client._get_json("/x")

    async def test_ssl_error(
        self, client: WapdaClient, mock_session: MagicMock
    ) -> None:
        mock_session.get = MagicMock(
            side_effect=aiohttp.ClientSSLError(
                connection_key=MagicMock(), os_error=OSError("ssl")
            )
        )
        with pytest.raises(WapdaConnectionError, match="SSL/TLS"):
            await client._get_json("/x")

    async def test_429_then_success_retries_once(
        self, client: WapdaClient, mock_session: MagicMock
    ) -> None:
        mock_session.get = MagicMock(
            side_effect=[_make_response(429), _make_response(200, {"ok": 1})]
        )
        assert await client._get_json("/x") == {"ok": 1}
        assert mock_session.get.call_count == 2

    async def test_429_twice_raises_rate_limit(
        self, client: WapdaClient, mock_session: MagicMock
    ) -> None:
        mock_session.get = MagicMock(
            side_effect=[_make_response(429), _make_response(429)]
        )
        with pytest.raises(WapdaRateLimitError, match="Rate limited"):
            await client._get_json("/x")
        assert mock_session.get.call_count == 2

    async def test_http_500(
        self, client: WapdaClient, mock_session: MagicMock
    ) -> None:
        mock_session.get = MagicMock(return_value=_make_response(500))
        with pytest.raises(WapdaApiError, match="HTTP error"):
            await client._get_json("/x")

    async def test_invalid_json(
        self, client: WapdaClient, mock_session: MagicMock
    ) -> None:
        ctx = _make_response(200)
        resp = ctx.__aenter__.return_value
        resp.json = AsyncMock(side_effect=ValueError("no json"))
        mock_session.get = MagicMock(return_value=ctx)
        with pytest.raises(WapdaApiError, match="Invalid JSON"):
            await client._get_json("/x")

    async def test_non_dict_json(
        self, client: WapdaClient, mock_session: MagicMock
    ) -> None:
        mock_session.get = MagicMock(return_value=_make_response(200, [1, 2]))
        with pytest.raises(WapdaApiError, match="Unexpected response"):
            await client._get_json("/x")

    async def test_error_messages_do_not_leak_reference(
        self, client: WapdaClient, mock_session: MagicMock
    ) -> None:
        mock_session.get = MagicMock(return_value=_make_response(404))
        with pytest.raises(WapdaApiError) as exc:
            await client.get_load_info(REF)
        assert REF not in str(exc.value)

    async def test_requests_are_serialized(
        self, client: WapdaClient, mock_session: MagicMock
    ) -> None:
        import asyncio

        in_flight = 0
        peak = 0

        class _Ctx:
            async def __aenter__(self_inner) -> AsyncMock:
                nonlocal in_flight, peak
                in_flight += 1
                peak = max(peak, in_flight)
                await asyncio.sleep(0.01)
                resp = AsyncMock()
                resp.status = 200
                resp.json = AsyncMock(return_value={"a": 1})
                return resp

            async def __aexit__(self_inner, *a: object) -> bool:
                nonlocal in_flight
                in_flight -= 1
                return False

        mock_session.get = MagicMock(side_effect=lambda *a, **k: _Ctx())
        await asyncio.gather(*(client._get_json("/x") for _ in range(4)))
        assert peak == 1


class TestGetLoadInfo:
    async def test_success(
        self, client: WapdaClient, mock_session: MagicMock
    ) -> None:
        json_data = {
            "message": "Success",
            "load": [
                {
                    "statusCode": 1,
                    "response": {
                        "data": [{"feeder_code": "FDR001", "current_status": "ON"}]
                    },
                }
            ],
        }
        mock_session.get = MagicMock(return_value=_make_response(200, json_data))
        result = await client.get_load_info(REF)
        assert result["feeder_code"] == "FDR001"

    async def test_api_error_message(
        self, client: WapdaClient, mock_session: MagicMock
    ) -> None:
        mock_session.get = MagicMock(
            return_value=_make_response(200, {"message": "Error"})
        )
        with pytest.raises(WapdaApiError, match="API error"):
            await client.get_load_info(REF)

    @pytest.mark.parametrize(
        "payload",
        [
            {"message": "Success", "load": []},
            {"message": "Success", "load": None},
            {"message": "Success", "load": [{"statusCode": 0, "Message": "nope"}]},
            {"message": "Success", "load": [{"statusCode": 1, "response": {}}]},
            {
                "message": "Success",
                "load": [{"statusCode": 1, "response": {"data": []}}],
            },
        ],
    )
    async def test_malformed_payloads_raise_api_error(
        self, client: WapdaClient, mock_session: MagicMock, payload: dict
    ) -> None:
        mock_session.get = MagicMock(return_value=_make_response(200, payload))
        with pytest.raises(WapdaApiError):
            await client.get_load_info(REF)

    @pytest.mark.parametrize("bad", ["", "123", "1234567890123x", "../../etc/pass", "0" * 15])
    async def test_rejects_bad_reference(self, client: WapdaClient, bad: str) -> None:
        with pytest.raises(WapdaApiError, match="14 digits"):
            await client.get_load_info(bad)


class TestGetUserDetails:
    async def test_success(
        self, client: WapdaClient, mock_session: MagicMock
    ) -> None:
        mock_session.get = MagicMock(
            return_value=_make_response(200, {"user": {"NAME": "Test User"}})
        )
        assert (await client.get_user_details(REF))["NAME"] == "Test User"

    async def test_no_user(
        self, client: WapdaClient, mock_session: MagicMock
    ) -> None:
        mock_session.get = MagicMock(return_value=_make_response(200, {"user": None}))
        with pytest.raises(WapdaApiError, match="No user found"):
            await client.get_user_details(REF)


class TestGetBillDetails:
    async def test_success(
        self, client: WapdaClient, mock_session: MagicMock
    ) -> None:
        mock_session.get = MagicMock(
            return_value=_make_response(200, {"bill": {"NETAMT": "5000"}})
        )
        assert (await client.get_bill_details(REF))["NETAMT"] == "5000"

    async def test_no_bill(
        self, client: WapdaClient, mock_session: MagicMock
    ) -> None:
        mock_session.get = MagicMock(return_value=_make_response(200, {"bill": None}))
        with pytest.raises(WapdaApiError, match="No billing data"):
            await client.get_bill_details(REF)


class TestGetSchedule:
    async def test_success(
        self, client: WapdaClient, mock_session: MagicMock
    ) -> None:
        mock_session.get = MagicMock(
            return_value=_make_response(200, {"loaddata": [{"maintenance_data": {}}]})
        )
        assert "maintenance_data" in await client.get_schedule("050424", "11000")

    async def test_no_schedule(
        self, client: WapdaClient, mock_session: MagicMock
    ) -> None:
        mock_session.get = MagicMock(return_value=_make_response(200, {"loaddata": []}))
        with pytest.raises(WapdaApiError, match="No schedule data"):
            await client.get_schedule("050424", "11000")

    @pytest.mark.parametrize(
        ("feeder", "disco"),
        [("../x", "11000"), ("050424", "11000&x=1"), ("", "11000"), ("050424", "")],
    )
    async def test_rejects_bad_codes(
        self, client: WapdaClient, feeder: str, disco: str
    ) -> None:
        with pytest.raises(WapdaApiError, match="Invalid feeder"):
            await client.get_schedule(feeder, disco)


class TestValidateReference:
    async def test_valid_reference(
        self, client: WapdaClient, mock_session: MagicMock
    ) -> None:
        mock_session.get = MagicMock(
            return_value=_make_response(200, {"user": {"NAME": "Test Consumer"}})
        )
        assert await client.validate_reference(REF) == "Test Consumer"

    async def test_invalid_format(self, client: WapdaClient) -> None:
        with pytest.raises(WapdaApiError, match="14 digits"):
            await client.validate_reference("12345")

    async def test_empty_name(
        self, client: WapdaClient, mock_session: MagicMock
    ) -> None:
        mock_session.get = MagicMock(
            return_value=_make_response(200, {"user": {"NAME": "  "}})
        )
        assert await client.validate_reference(REF) is None
