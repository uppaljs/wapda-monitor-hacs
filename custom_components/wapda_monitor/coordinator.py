"""DataUpdateCoordinator for WAPDA Monitor."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import WapdaApiError, WapdaClient, WapdaConnectionError
from .const import (
    CONF_REFERENCE,
    CONF_SCAN_INTERVAL_BILL,
    CONF_SCAN_INTERVAL_LOAD,
    CONF_SCAN_INTERVAL_SCHEDULE,
    DATA_BILL,
    DATA_LOAD,
    DATA_SCHEDULE,
    DATA_USER,
    DEFAULT_SCAN_INTERVAL_BILL,
    DEFAULT_SCAN_INTERVAL_LOAD,
    DEFAULT_SCAN_INTERVAL_SCHEDULE,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class WapdaDataCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that polls the Roshan Pakistan / CCMS server.

    Uses a single fast interval (load data) as the heartbeat.  Bill and
    schedule data are refreshed on their own slower cadence by tracking
    the last successful fetch time internally.
    """

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: WapdaClient,
    ) -> None:
        self.client = client
        self.reference: str = entry.data[CONF_REFERENCE]
        self._entry = entry

        # Separate tick counters for slow-polled data
        self._bill_ticks: int = 0
        self._schedule_ticks: int = 0

        # Cached slow data (kept across fast-poll cycles)
        self._cached_user: dict[str, Any] | None = None
        self._cached_bill: dict[str, Any] | None = None
        self._cached_schedule: dict[str, Any] | None = None

        # Track connection state for log-when-unavailable
        self._was_unavailable: bool = False

        interval = timedelta(
            seconds=entry.options.get(
                CONF_SCAN_INTERVAL_LOAD, DEFAULT_SCAN_INTERVAL_LOAD
            )
        )

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{self.reference}",
            update_interval=interval,
            config_entry=entry,
        )

    @property
    def _bill_interval(self) -> int:
        return self._entry.options.get(
            CONF_SCAN_INTERVAL_BILL, DEFAULT_SCAN_INTERVAL_BILL
        )

    @property
    def _schedule_interval(self) -> int:
        return self._entry.options.get(
            CONF_SCAN_INTERVAL_SCHEDULE, DEFAULT_SCAN_INTERVAL_SCHEDULE
        )

    @property
    def _load_interval(self) -> int:
        return self._entry.options.get(
            CONF_SCAN_INTERVAL_LOAD, DEFAULT_SCAN_INTERVAL_LOAD
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the Roshan Pakistan / CCMS portal.

        Every tick fetches load info (fast).
        User details are fetched once and cached.
        Bill and schedule have their own slower cadence.
        """
        result: dict[str, Any] = {}

        # --- Load info (every tick) ---
        try:
            result[DATA_LOAD] = await self.client.get_load_info(self.reference)
            # Log recovery if previously unavailable
            if self._was_unavailable:
                _LOGGER.info(
                    "WAPDA connection restored for reference %s", self.reference
                )
                self._was_unavailable = False
        except WapdaConnectionError as exc:
            if not self._cached_user and not self._cached_bill:
                if not self._was_unavailable:
                    _LOGGER.warning(
                        "WAPDA connection unavailable for reference %s: %s",
                        self.reference,
                        exc,
                    )
                    self._was_unavailable = True
                raise UpdateFailed(f"Cannot reach CCMS: {exc}") from exc
            result[DATA_LOAD] = None
            if not self._was_unavailable:
                _LOGGER.warning(
                    "WAPDA load info unavailable for reference %s: %s",
                    self.reference,
                    exc,
                )
                self._was_unavailable = True
        except WapdaApiError as exc:
            result[DATA_LOAD] = None
            _LOGGER.debug("WAPDA load info error: %s", exc)

        # --- User details (fetch once, cache forever) ---
        if self._cached_user is None:
            try:
                self._cached_user = await self.client.get_user_details(
                    self.reference
                )
            except WapdaApiError as exc:
                _LOGGER.warning("WAPDA user details failed: %s", exc)
        result[DATA_USER] = self._cached_user

        # --- Bill details (slow cadence) ---
        bill_every_n = max(1, self._bill_interval // self._load_interval)
        self._bill_ticks += 1
        if self._cached_bill is None or self._bill_ticks >= bill_every_n:
            self._bill_ticks = 0
            try:
                self._cached_bill = await self.client.get_bill_details(
                    self.reference
                )
            except WapdaApiError as exc:
                _LOGGER.warning("WAPDA bill details failed: %s", exc)
        result[DATA_BILL] = self._cached_bill

        # --- Schedule (slow cadence) ---
        schedule_every_n = max(1, self._schedule_interval // self._load_interval)
        self._schedule_ticks += 1
        if self._cached_schedule is None or self._schedule_ticks >= schedule_every_n:
            self._schedule_ticks = 0
            feeder_code = self._resolve_feeder_code(result)
            if feeder_code:
                disco_code = self.reference[2:4] + "000"
                try:
                    self._cached_schedule = await self.client.get_schedule(
                        feeder_code, disco_code
                    )
                except WapdaApiError as exc:
                    _LOGGER.warning("WAPDA schedule failed: %s", exc)
        result[DATA_SCHEDULE] = self._cached_schedule

        return result

    @staticmethod
    def _resolve_feeder_code(data: dict[str, Any]) -> str | None:
        """Get feeder_code from load info or user details."""
        load = data.get(DATA_LOAD)
        if load and load.get("feeder_code"):
            return str(load["feeder_code"])
        user = data.get(DATA_USER)
        if user and user.get("FEEDERCD", "").strip():
            return str(user["FEEDERCD"]).strip()
        return None
