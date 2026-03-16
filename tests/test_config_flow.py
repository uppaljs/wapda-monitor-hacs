"""Tests for the WAPDA Monitor config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.wapda_monitor.const import DOMAIN

from .const import MOCK_REFERENCE, MOCK_USER_INPUT


async def test_user_flow_success(
    hass: HomeAssistant,
    mock_wapda_client: MagicMock,
    mock_setup_entry,
) -> None:
    """Test a successful config flow initiated by the user."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    with patch(
        "custom_components.wapda_monitor.config_flow.WapdaClient",
        return_value=mock_wapda_client,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input=MOCK_USER_INPUT,
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "WAPDA Test Consumer"
    assert result["data"] == {"reference": MOCK_REFERENCE}
    assert result["result"].unique_id == MOCK_REFERENCE


async def test_user_flow_invalid_reference_format(
    hass: HomeAssistant,
) -> None:
    """Test config flow with invalid reference format (not 14 digits)."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"reference": "12345"},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_reference"}


async def test_user_flow_invalid_reference_not_digits(
    hass: HomeAssistant,
) -> None:
    """Test config flow with non-digit reference."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"reference": "abcdefghijklmn"},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_reference"}


async def test_user_flow_cannot_connect(
    hass: HomeAssistant,
    mock_setup_entry,
) -> None:
    """Test config flow when server is unreachable."""
    from custom_components.wapda_monitor.api import WapdaConnectionError

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    mock_client = MagicMock()
    mock_client.validate_reference = AsyncMock(
        side_effect=WapdaConnectionError("Cannot connect")
    )
    with patch(
        "custom_components.wapda_monitor.config_flow.WapdaClient",
        return_value=mock_client,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input=MOCK_USER_INPUT,
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_invalid_account(
    hass: HomeAssistant,
    mock_setup_entry,
) -> None:
    """Test config flow when reference is not a valid account."""
    from custom_components.wapda_monitor.api import WapdaApiError

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    mock_client = MagicMock()
    mock_client.validate_reference = AsyncMock(
        side_effect=WapdaApiError("No user found")
    )
    with patch(
        "custom_components.wapda_monitor.config_flow.WapdaClient",
        return_value=mock_client,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input=MOCK_USER_INPUT,
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_reference"}


async def test_user_flow_unknown_error(
    hass: HomeAssistant,
    mock_setup_entry,
) -> None:
    """Test config flow with an unexpected exception."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    mock_client = MagicMock()
    mock_client.validate_reference = AsyncMock(
        side_effect=RuntimeError("Boom")
    )
    with patch(
        "custom_components.wapda_monitor.config_flow.WapdaClient",
        return_value=mock_client,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input=MOCK_USER_INPUT,
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}


async def test_user_flow_duplicate_entry(
    hass: HomeAssistant,
    mock_config_entry,
    mock_wapda_client: MagicMock,
    mock_setup_entry,
) -> None:
    """Test config flow rejects duplicate reference numbers."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.wapda_monitor.config_flow.WapdaClient",
        return_value=mock_wapda_client,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input=MOCK_USER_INPUT,
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_flow_success(
    hass: HomeAssistant,
    mock_config_entry,
    mock_wapda_client: MagicMock,
    mock_setup_entry,
) -> None:
    """Test successful reconfiguration with a new reference number."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    result = await mock_config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    new_reference = "99887766554433"
    with patch(
        "custom_components.wapda_monitor.config_flow.WapdaClient",
        return_value=mock_wapda_client,
    ):
        mock_wapda_client.validate_reference = AsyncMock(
            return_value="New Consumer"
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"reference": new_reference},
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data["reference"] == new_reference


async def test_reconfigure_flow_invalid_reference(
    hass: HomeAssistant,
    mock_config_entry,
    mock_setup_entry,
) -> None:
    """Test reconfigure rejects invalid reference format."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    result = await mock_config_entry.start_reconfigure_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"reference": "short"},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_reference"}


async def test_options_flow(
    hass: HomeAssistant,
    mock_config_entry,
    mock_setup_entry,
) -> None:
    """Test the options flow for adjusting polling intervals."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(
        mock_config_entry.entry_id
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "scan_interval_load": 120,
            "scan_interval_bill": 7200,
            "scan_interval_schedule": 600,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        "scan_interval_load": 120,
        "scan_interval_bill": 7200,
        "scan_interval_schedule": 600,
    }
