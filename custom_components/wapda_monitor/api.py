"""
Roshan Pakistan / CCMS API Client
==================================
Async-compatible wrapper for the PITC CCMS portal APIs.

Fetches real-time feeder status, billing, customer info, and load-shedding
schedules from the Roshan Pakistan infrastructure (ccms.pitc.com.pk).

All blocking HTTP calls are wrapped to run in the HA executor so they
don't block the event loop.
"""

from __future__ import annotations

import logging
import random
import re
from typing import Any, Optional

import requests

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


class WapdaApiError(Exception):
    """Raised when the CCMS portal returns an unexpected response."""


class WapdaConnectionError(WapdaApiError):
    """Raised when we cannot reach the CCMS server."""


class WapdaClient:
    """Synchronous client for the PITC CCMS feeder data APIs.

    Home Assistant's DataUpdateCoordinator will call these methods inside
    `hass.async_add_executor_job()` so they run in a thread and don't
    block the event loop.
    """

    def __init__(self, timeout: int = 30) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": random.choice(_USER_AGENTS),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
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
        )
        self._initialized = False
        self.timeout = timeout

    # ------------------------------------------------------------------ #
    #  Internal helpers
    # ------------------------------------------------------------------ #
    def _ensure_session(self) -> None:
        """Visit the main page once to pick up session cookies."""
        if not self._initialized:
            try:
                self.session.get(f"{BASE_URL}/FeederDetails", timeout=self.timeout)
                self._initialized = True
            except requests.exceptions.RequestException as exc:
                raise WapdaConnectionError(
                    f"Cannot reach Roshan Pakistan server: {exc}"
                ) from exc

    @staticmethod
    def _xhr_headers() -> dict[str, str]:
        return {
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Referer": f"{BASE_URL}/FeederDetails",
        }

    def _safe_request(
        self, method: str, url: str, **kwargs: Any
    ) -> requests.Response:
        """Make HTTP request with graceful error handling."""
        kwargs.setdefault("timeout", self.timeout)
        try:
            resp = self.session.request(method, url, **kwargs)
        except requests.exceptions.ConnectionError as exc:
            raise WapdaConnectionError(
                "Connection failed — cannot reach ccms.pitc.com.pk"
            ) from exc
        except requests.exceptions.Timeout as exc:
            raise WapdaConnectionError(
                f"Request timed out after {self.timeout}s"
            ) from exc
        except requests.exceptions.SSLError as exc:
            raise WapdaConnectionError(
                "SSL/TLS error — secure connection failed"
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise WapdaConnectionError(f"Request failed: {exc}") from exc

        if resp.status_code >= 400:
            _status_messages = {
                429: "Rate limited (429)",
                403: "Forbidden (403)",
                404: "Not found (404)",
                500: "Server error (500)",
                502: "Bad gateway (502)",
                503: "Service unavailable (503)",
                504: "Gateway timeout (504)",
            }
            msg = _status_messages.get(
                resp.status_code, f"HTTP error ({resp.status_code})"
            )
            raise WapdaApiError(f"{msg} from {url.split('/')[-1]}")
        return resp

    # ------------------------------------------------------------------ #
    #  Public API methods
    # ------------------------------------------------------------------ #
    def get_load_info(self, reference: str) -> dict:
        """GET /get-loadinfo/{reference} — real-time feeder data."""
        self._ensure_session()
        resp = self._safe_request(
            "GET",
            f"{BASE_URL}/get-loadinfo/{reference}",
            headers=self._xhr_headers(),
        )
        try:
            data = resp.json()
        except (ValueError, AttributeError) as exc:
            raise WapdaApiError("Load info returned invalid JSON") from exc

        if data.get("message") != "Success":
            raise WapdaApiError(
                f"API error: {data.get('message', 'Unknown')}"
            )

        load_entry = data.get("load", [{}])[0]
        if load_entry.get("statusCode") != 1:
            raise WapdaApiError(
                load_entry.get("Message", "No data available")
            )

        records = load_entry.get("response", {}).get("data", [])
        if not records:
            raise WapdaApiError("Load info returned empty data")
        return records[0]

    def get_user_details(self, reference: str) -> dict:
        """GET /api/details/user?reference={ref} — customer info."""
        self._ensure_session()
        resp = self._safe_request(
            "GET",
            f"{BASE_URL}/api/details/user",
            params={"reference": reference},
            headers=self._xhr_headers(),
        )
        try:
            data = resp.json()
        except (ValueError, AttributeError) as exc:
            raise WapdaApiError("User details returned invalid response") from exc

        user = data.get("user")
        if not user:
            raise WapdaApiError("No user found for this reference")
        return user

    def get_bill_details(self, reference: str) -> dict:
        """GET /api/details/bill?reference={ref} — billing data."""
        self._ensure_session()
        resp = self._safe_request(
            "GET",
            f"{BASE_URL}/api/details/bill",
            params={"reference": reference},
            headers=self._xhr_headers(),
        )
        try:
            data = resp.json()
        except (ValueError, AttributeError) as exc:
            raise WapdaApiError("Bill details returned invalid response") from exc

        bill = data.get("bill")
        if not bill:
            raise WapdaApiError("No billing data found for this reference")
        return bill

    def get_schedule(self, feeder_code: str, disco_code: str) -> dict:
        """GET /api/schedule_api — hourly outage schedule."""
        self._ensure_session()
        resp = self._safe_request(
            "GET",
            f"{BASE_URL}/api/schedule_api",
            params={"feeder_code": feeder_code, "disco_code": disco_code},
            headers=self._xhr_headers(),
        )
        try:
            data = resp.json()
        except (ValueError, AttributeError) as exc:
            raise WapdaApiError(
                f"Schedule returned invalid response for feeder {feeder_code}"
            ) from exc

        if "loaddata" in data and len(data["loaddata"]) > 0:
            return data["loaddata"][0]
        raise WapdaApiError(f"No schedule data for feeder {feeder_code}")

    def get_all_data(self, reference: str) -> dict:
        """Fetch all available data for a 14-digit reference number."""
        if not reference or len(reference) != 14 or not reference.isdigit():
            raise WapdaApiError(
                f"Reference must be exactly 14 digits, got: '{reference}'"
            )

        result: dict[str, Any] = {}
        errors: list[str] = []

        # 1. Load info
        try:
            result["load"] = self.get_load_info(reference)
        except WapdaApiError as exc:
            result["load"] = None
            errors.append(f"load: {exc}")
            _LOGGER.warning("WAPDA load info failed: %s", exc)

        # 2. User details
        try:
            result["user"] = self.get_user_details(reference)
        except WapdaApiError as exc:
            result["user"] = None
            errors.append(f"user: {exc}")
            _LOGGER.warning("WAPDA user details failed: %s", exc)

        # 3. Bill details
        try:
            result["bill"] = self.get_bill_details(reference)
        except WapdaApiError as exc:
            result["bill"] = None
            errors.append(f"bill: {exc}")
            _LOGGER.warning("WAPDA bill details failed: %s", exc)

        # 4. Schedule (needs feeder_code from load or user)
        feeder_code = None
        if result.get("load") and result["load"].get("feeder_code"):
            feeder_code = result["load"]["feeder_code"]
        elif result.get("user") and result["user"].get("FEEDERCD", "").strip():
            feeder_code = result["user"]["FEEDERCD"].strip()

        if feeder_code:
            disco_code = reference[2:4] + "000"
            try:
                result["schedule"] = self.get_schedule(feeder_code, disco_code)
            except WapdaApiError as exc:
                result["schedule"] = None
                errors.append(f"schedule: {exc}")
                _LOGGER.warning("WAPDA schedule failed: %s", exc)
        else:
            result["schedule"] = None

        # If ALL endpoints failed, propagate so coordinator marks unavailable
        if not any(result.get(k) for k in ("load", "user", "bill", "schedule")):
            if errors:
                raise WapdaConnectionError(
                    f"All endpoints failed: {'; '.join(errors)}"
                )

        result["_errors"] = errors
        return result

    def validate_reference(self, reference: str) -> str | None:
        """Quick validation — returns customer name or raises on failure."""
        if not reference or len(reference) != 14 or not reference.isdigit():
            raise WapdaApiError("Reference must be exactly 14 digits")
        user = self.get_user_details(reference)
        return (user.get("NAME") or "").strip() or None
