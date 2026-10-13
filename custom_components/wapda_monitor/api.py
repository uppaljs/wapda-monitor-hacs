"""
Roshan Pakistan / CCMS API Client
==================================
Fully async client for the PITC CCMS portal APIs.

Uses aiohttp with Home Assistant's managed websession for efficient,
non-blocking HTTP calls.

The portal throttles bursts ("Too Many Attempts", HTTP 429), so all requests
are serialized with a minimum gap and retried once with a back-off on 429.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://ccms.pitc.com.pk"

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Minimum seconds between two requests to the portal (observed: 429 on bursts,
# fine when spaced >= ~20s; a few seconds is enough between sequential calls
# once a single request is in flight at a time).
MIN_REQUEST_GAP = 5.0
# Seconds to wait before the single retry after a 429.
RATE_LIMIT_BACKOFF = 30.0

_REFERENCE_RE = re.compile(r"^\d{14}$")
_FEEDER_RE = re.compile(r"^[A-Za-z0-9]{1,12}$")
_DISCO_RE = re.compile(r"^\d{1,8}$")

_COMMON_HEADERS: dict[str, str] = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "en-US,en;q=0.9",
}


class WapdaApiError(Exception):
    """Raised when the CCMS portal returns an unexpected response."""


class WapdaConnectionError(WapdaApiError):
    """Raised when we cannot reach the CCMS server."""


class WapdaRateLimitError(WapdaApiError):
    """Raised when the portal keeps answering 429 after a back-off."""


def _check_reference(reference: str) -> str:
    if not isinstance(reference, str) or not _REFERENCE_RE.match(reference):
        raise WapdaApiError("Reference must be exactly 14 digits")
    return reference


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
        self._initialized = False
        self._lock = asyncio.Lock()
        self._last_request = 0.0

    # ------------------------------------------------------------------ #
    #  Internal helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _base_headers() -> dict[str, str]:
        return {
            **_COMMON_HEADERS,
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        }

    @staticmethod
    def _xhr_headers() -> dict[str, str]:
        return {
            **_COMMON_HEADERS,
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": f"{BASE_URL}/FeederDetails",
        }

    async def _throttle(self) -> None:
        """Sleep so consecutive requests are at least MIN_REQUEST_GAP apart."""
        wait = self._last_request + MIN_REQUEST_GAP - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_request = time.monotonic()

    async def _ensure_session(self) -> None:
        """Visit the main page once to pick up session cookies.

        Must be called with ``self._lock`` held.
        """
        if self._initialized:
            return
        await self._throttle()
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
                f"Cannot reach Roshan Pakistan server: {type(exc).__name__}"
            ) from exc
        except TimeoutError as exc:
            raise WapdaConnectionError("Request timed out") from exc

    async def _get_json(
        self, path: str, params: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """GET ``BASE_URL + path`` and return the parsed JSON object.

        Requests are serialized (one in flight at a time) and a single retry
        with back-off is made on HTTP 429. Error messages never include the
        request URL or parameters (they contain the reference number).
        """
        async with self._lock:
            await self._ensure_session()
            for attempt in (1, 2):
                await self._throttle()
                try:
                    async with self._session.get(
                        f"{BASE_URL}{path}",
                        params=params,
                        headers=self._xhr_headers(),
                        timeout=self._timeout,
                    ) as resp:
                        if resp.status == 429:
                            if attempt == 1:
                                _LOGGER.debug("CCMS 429; backing off")
                                await asyncio.sleep(RATE_LIMIT_BACKOFF)
                                continue
                            raise WapdaRateLimitError("Rate limited (429)")
                        if resp.status >= 400:
                            raise WapdaApiError(f"HTTP error ({resp.status})")
                        try:
                            data = await resp.json(content_type=None)
                        except (ValueError, aiohttp.ContentTypeError) as exc:
                            raise WapdaApiError("Invalid JSON from portal") from exc
                except TimeoutError as exc:
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
                    raise WapdaConnectionError(
                        f"Request failed: {type(exc).__name__}"
                    ) from exc

                if not isinstance(data, dict):
                    raise WapdaApiError("Unexpected response shape from portal")
                return data
        raise WapdaRateLimitError("Rate limited (429)")  # pragma: no cover

    # ------------------------------------------------------------------ #
    #  Public API methods
    # ------------------------------------------------------------------ #
    async def get_load_info(self, reference: str) -> dict[str, Any]:
        """GET /get-loadinfo/{reference} — real-time feeder data."""
        _check_reference(reference)
        data = await self._get_json(f"/get-loadinfo/{reference}")

        if data.get("message") != "Success":
            raise WapdaApiError(f"API error: {data.get('message', 'Unknown')}")

        load = data.get("load")
        load_entry = load[0] if isinstance(load, list) and load else {}
        if not isinstance(load_entry, dict) or load_entry.get("statusCode") != 1:
            raise WapdaApiError(
                (load_entry or {}).get("Message", "No data available")
                if isinstance(load_entry, dict)
                else "No data available"
            )

        response = load_entry.get("response")
        records = response.get("data") if isinstance(response, dict) else None
        if not isinstance(records, list) or not records:
            raise WapdaApiError("Load info returned empty data")
        return records[0]

    async def get_user_details(self, reference: str) -> dict[str, Any]:
        """GET /api/details/user?reference={ref} — customer info."""
        _check_reference(reference)
        data = await self._get_json(
            "/api/details/user", params={"reference": reference}
        )
        user = data.get("user")
        if not isinstance(user, dict) or not user:
            raise WapdaApiError("No user found for this reference")
        return user

    async def get_bill_details(self, reference: str) -> dict[str, Any]:
        """GET /api/details/bill?reference={ref} — billing data."""
        _check_reference(reference)
        data = await self._get_json(
            "/api/details/bill", params={"reference": reference}
        )
        bill = data.get("bill")
        if not isinstance(bill, dict) or not bill:
            raise WapdaApiError("No billing data found for this reference")
        return bill

    async def get_schedule(
        self, feeder_code: str, disco_code: str
    ) -> dict[str, Any]:
        """GET /api/schedule_api — hourly outage schedule."""
        if not _FEEDER_RE.match(str(feeder_code)) or not _DISCO_RE.match(
            str(disco_code)
        ):
            raise WapdaApiError("Invalid feeder or disco code")
        data = await self._get_json(
            "/api/schedule_api",
            params={"feeder_code": str(feeder_code), "disco_code": str(disco_code)},
        )
        loaddata = data.get("loaddata")
        if isinstance(loaddata, list) and loaddata and isinstance(loaddata[0], dict):
            return loaddata[0]
        raise WapdaApiError("No schedule data for feeder")

    async def validate_reference(self, reference: str) -> str | None:
        """Quick validation — returns customer name or raises on failure."""
        _check_reference(reference)
        user = await self.get_user_details(reference)
        return (user.get("NAME") or "").strip() or None
