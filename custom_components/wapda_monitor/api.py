"""
Roshan Pakistan / CCMS API Client
==================================
Fully async client for the PITC CCMS portal APIs.

Uses aiohttp with Home Assistant's managed websession for efficient,
non-blocking HTTP calls.
"""

from __future__ import annotations

import logging
import random
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://ccms.pitc.com.pk"

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
]

_COMMON_HEADERS: dict[str, str] = {
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
    "Sec-CH-UA": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "Sec-CH-UA-Mobile": "?0",
    "Sec-CH-UA-Platform": '"Windows"',
}


class WapdaApiError(Exception):
    """Raised when the CCMS portal returns an unexpected response."""


class WapdaConnectionError(WapdaApiError):
    """Raised when we cannot reach the CCMS server."""


class WapdaClient:
    """Async client for the PITC CCMS feeder data APIs.

    Accepts an aiohttp.ClientSession (typically from HA's
    async_get_clientsession) so sessions are shared and managed
    by Home Assistant.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        timeout: int = 30,
    ) -> None:
        self._session = session
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._user_agent = random.choice(_USER_AGENTS)
        self._initialized = False

    # ------------------------------------------------------------------ #
    #  Internal helpers
    # ------------------------------------------------------------------ #
    def _base_headers(self) -> dict[str, str]:
        """Return base headers with a random User-Agent."""
        return {
            "User-Agent": self._user_agent,
            **_COMMON_HEADERS,
        }

    def _xhr_headers(self) -> dict[str, str]:
        """Return headers for XHR/JSON requests."""
        return {
            **self._base_headers(),
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Referer": f"{BASE_URL}/FeederDetails",
        }

    async def _ensure_session(self) -> None:
        """Visit the main page once to pick up session cookies."""
        if self._initialized:
            return
        try:
            async with self._session.get(
                f"{BASE_URL}/FeederDetails",
                headers=self._base_headers(),
                timeout=self._timeout,
            ) as resp:
                await resp.read()
            self._initialized = True
        except aiohttp.ClientError as exc:
            raise WapdaConnectionError(
                f"Cannot reach Roshan Pakistan server: {exc}"
            ) from exc

    async def _request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Make an HTTP request and return parsed JSON."""
        kwargs.setdefault("timeout", self._timeout)
        kwargs.setdefault("headers", self._xhr_headers())

        try:
            async with self._session.request(method, url, **kwargs) as resp:
                if resp.status >= 400:
                    _status_messages: dict[int, str] = {
                        429: "Rate limited (429)",
                        403: "Forbidden (403)",
                        404: "Not found (404)",
                        500: "Server error (500)",
                        502: "Bad gateway (502)",
                        503: "Service unavailable (503)",
                        504: "Gateway timeout (504)",
                    }
                    msg = _status_messages.get(
                        resp.status, f"HTTP error ({resp.status})"
                    )
                    raise WapdaApiError(
                        f"{msg} from {url.split('/')[-1]}"
                    )
                try:
                    return await resp.json(content_type=None)
                except (ValueError, aiohttp.ContentTypeError) as exc:
                    raise WapdaApiError(
                        f"Invalid JSON from {url.split('/')[-1]}"
                    ) from exc
        except aiohttp.ServerTimeoutError as exc:
            raise WapdaConnectionError(
                f"Request timed out after {self._timeout.total}s"
            ) from exc
        except aiohttp.ClientSSLError as exc:
            raise WapdaConnectionError(
                "SSL/TLS error — secure connection failed"
            ) from exc
        except aiohttp.ClientConnectorError as exc:
            raise WapdaConnectionError(
                "Connection failed — cannot reach ccms.pitc.com.pk"
            ) from exc
        except aiohttp.ClientError as exc:
            raise WapdaConnectionError(f"Request failed: {exc}") from exc

    # ------------------------------------------------------------------ #
    #  Public API methods
    # ------------------------------------------------------------------ #
    async def get_load_info(self, reference: str) -> dict[str, Any]:
        """GET /get-loadinfo/{reference} — real-time feeder data."""
        await self._ensure_session()
        data = await self._request(
            "GET",
            f"{BASE_URL}/get-loadinfo/{reference}",
        )

        if data.get("message") != "Success":
            raise WapdaApiError(
                f"API error: {data.get('message', 'Unknown')}"
            )

        load_entry: dict[str, Any] = data.get("load", [{}])[0]
        if load_entry.get("statusCode") != 1:
            raise WapdaApiError(
                load_entry.get("Message", "No data available")
            )

        records: list[dict[str, Any]] = (
            load_entry.get("response", {}).get("data", [])
        )
        if not records:
            raise WapdaApiError("Load info returned empty data")
        return records[0]

    async def get_user_details(self, reference: str) -> dict[str, Any]:
        """GET /api/details/user?reference={ref} — customer info."""
        await self._ensure_session()
        data = await self._request(
            "GET",
            f"{BASE_URL}/api/details/user",
            params={"reference": reference},
        )

        user: dict[str, Any] | None = data.get("user")
        if not user:
            raise WapdaApiError("No user found for this reference")
        return user

    async def get_bill_details(self, reference: str) -> dict[str, Any]:
        """GET /api/details/bill?reference={ref} — billing data."""
        await self._ensure_session()
        data = await self._request(
            "GET",
            f"{BASE_URL}/api/details/bill",
            params={"reference": reference},
        )

        bill: dict[str, Any] | None = data.get("bill")
        if not bill:
            raise WapdaApiError("No billing data found for this reference")
        return bill

    async def get_schedule(
        self, feeder_code: str, disco_code: str
    ) -> dict[str, Any]:
        """GET /api/schedule_api — hourly outage schedule."""
        await self._ensure_session()
        data = await self._request(
            "GET",
            f"{BASE_URL}/api/schedule_api",
            params={"feeder_code": feeder_code, "disco_code": disco_code},
        )

        loaddata: list[dict[str, Any]] = data.get("loaddata", [])
        if loaddata:
            return loaddata[0]
        raise WapdaApiError(f"No schedule data for feeder {feeder_code}")

    async def validate_reference(self, reference: str) -> str | None:
        """Quick validation — returns customer name or raises on failure."""
        if not reference or len(reference) != 14 or not reference.isdigit():
            raise WapdaApiError("Reference must be exactly 14 digits")
        user = await self.get_user_details(reference)
        return (user.get("NAME") or "").strip() or None
