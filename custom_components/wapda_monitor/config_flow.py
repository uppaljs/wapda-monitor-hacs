"""Config flow for WAPDA Monitor."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback

from .api import WapdaApiError, WapdaClient, WapdaConnectionError
from .const import (
    CONF_REFERENCE,
    CONF_SCAN_INTERVAL_BILL,
    CONF_SCAN_INTERVAL_LOAD,
    CONF_SCAN_INTERVAL_SCHEDULE,
    DEFAULT_SCAN_INTERVAL_BILL,
    DEFAULT_SCAN_INTERVAL_LOAD,
    DEFAULT_SCAN_INTERVAL_SCHEDULE,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_REFERENCE): str,
    }
)


class WapdaMonitorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for WAPDA Monitor."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step — ask for the 14-digit reference number."""
        errors: dict[str, str] = {}

        if user_input is not None:
            reference = user_input[CONF_REFERENCE].strip()

            # Basic format check
            if len(reference) != 14 or not reference.isdigit():
                errors["base"] = "invalid_reference"
            else:
                # Prevent duplicate entries for the same reference
                await self.async_set_unique_id(reference)
                self._abort_if_unique_id_configured()

                # Test the connection by fetching user details
                client = WapdaClient()
                try:
                    name = await self.hass.async_add_executor_job(
                        client.validate_reference, reference
                    )
                except WapdaConnectionError:
                    errors["base"] = "cannot_connect"
                except WapdaApiError:
                    errors["base"] = "invalid_reference"
                except Exception:  # noqa: BLE001
                    _LOGGER.exception("Unexpected error during WAPDA validation")
                    errors["base"] = "unknown"
                else:
                    title = f"WAPDA {name or reference}"
                    return self.async_create_entry(
                        title=title,
                        data={CONF_REFERENCE: reference},
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> WapdaMonitorOptionsFlow:
        """Return the options flow handler."""
        return WapdaMonitorOptionsFlow(config_entry)


class WapdaMonitorOptionsFlow(config_entries.OptionsFlow):
    """Handle options (polling intervals) for WAPDA Monitor."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL_LOAD,
                        default=self._config_entry.options.get(
                            CONF_SCAN_INTERVAL_LOAD,
                            DEFAULT_SCAN_INTERVAL_LOAD,
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=60, max=3600)),
                    vol.Optional(
                        CONF_SCAN_INTERVAL_BILL,
                        default=self._config_entry.options.get(
                            CONF_SCAN_INTERVAL_BILL,
                            DEFAULT_SCAN_INTERVAL_BILL,
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=3600, max=86400)),
                    vol.Optional(
                        CONF_SCAN_INTERVAL_SCHEDULE,
                        default=self._config_entry.options.get(
                            CONF_SCAN_INTERVAL_SCHEDULE,
                            DEFAULT_SCAN_INTERVAL_SCHEDULE,
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=300, max=7200)),
                }
            ),
        )
