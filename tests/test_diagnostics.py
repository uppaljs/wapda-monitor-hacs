"""Tests for WAPDA Monitor diagnostics."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from homeassistant.core import HomeAssistant

from custom_components.wapda_monitor.const import DOMAIN
from custom_components.wapda_monitor.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .const import MOCK_COORDINATOR_DATA, MOCK_REFERENCE

PATCH_CLIENT = "custom_components.wapda_monitor.WapdaClient"
PATCH_SESSION = "custom_components.wapda_monitor.async_get_clientsession"


async def test_config_entry_diagnostics(
    hass: HomeAssistant,
    mock_config_entry,
    mock_wapda_client: MagicMock,
) -> None:
    """Test diagnostics returns expected data with redaction."""
    mock_config_entry.add_to_hass(hass)

    with (
        patch(PATCH_SESSION, return_value=MagicMock()),
        patch(PATCH_CLIENT, return_value=mock_wapda_client),
        patch(
            "custom_components.wapda_monitor.coordinator.WapdaDataCoordinator._async_update_data",
            return_value=MOCK_COORDINATOR_DATA,
        ),
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    # Verify structure
    assert "config_entry" in result
    assert "coordinator" in result
    assert "data" in result

    # Verify reference is redacted
    assert result["config_entry"]["data"]["reference"] == "**REDACTED**"

    # Verify sensitive user data is redacted
    user_data = result["data"]["user"]
    assert user_data is not None
    assert user_data["CONSNAME"] == "**REDACTED**"
    assert user_data["CONSADDRESS"] == "**REDACTED**"
    assert user_data["CNIC"] == "**REDACTED**"
    assert user_data["MOBILE"] == "**REDACTED**"

    # Verify non-sensitive data is preserved
    assert user_data["TARIFF"] == "A1"
    assert user_data["FEEDERCD"] == "FDR001"

    # Verify coordinator state
    assert result["coordinator"]["last_update_success"] is True

    # Verify schedule data is not redacted (no PII)
    assert result["data"]["schedule"] is not None


async def test_config_entry_diagnostics_no_data(
    hass: HomeAssistant,
    mock_config_entry,
    mock_wapda_client: MagicMock,
) -> None:
    """Test diagnostics when coordinator has no data."""
    mock_config_entry.add_to_hass(hass)

    with (
        patch(PATCH_SESSION, return_value=MagicMock()),
        patch(PATCH_CLIENT, return_value=mock_wapda_client),
        patch(
            "custom_components.wapda_monitor.coordinator.WapdaDataCoordinator._async_update_data",
            return_value={},
        ),
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    assert result["data"]["load"] is None
    assert result["data"]["user"] is None
    assert result["data"]["bill"] is None
    assert result["data"]["schedule"] is None


def test_redaction_covers_real_ccms_keys() -> None:
    """Keys seen in live CCMS bill/user payloads must never leak."""
    from custom_components.wapda_monitor.diagnostics import REDACTED, _redact

    payload = {
        "basicInfo": {
            "consumerName": "X", "consumerAddress1": "Y", "consumerContactNo": "Z",
            "owner_cnic": "1", "consumerEmail": "e", "refNo": "r", "ckey": "k",
            "appNo": "a", "barCodeMsg": "b", "feederName": "FEEDER", "currAmntDue": "100",
        },
        "metersInfo": [{"mtrNo": "E 123", "mtrKwhConsump": 5}],
        "msn": "329",
    }
    out = _redact(payload)
    assert out["basicInfo"]["feederName"] == "FEEDER"
    assert out["basicInfo"]["currAmntDue"] == "100"
    assert out["metersInfo"][0]["mtrKwhConsump"] == 5
    for k in ("consumerName", "consumerAddress1", "consumerContactNo", "owner_cnic",
              "consumerEmail", "refNo", "ckey", "appNo", "barCodeMsg"):
        assert out["basicInfo"][k] == REDACTED, k
    assert out["metersInfo"][0]["mtrNo"] == REDACTED and out["msn"] == REDACTED


def test_redaction_covers_user_endpoint_keys() -> None:
    """Keys of /api/details/user, found leaking in a real diagnostics download."""
    from custom_components.wapda_monitor.diagnostics import REDACTED, _redact

    user = {
        "REFNO": "1", "NAME": "n", "FNAME": "f", "ADDR1": "a1", "ADDR2": "a2",
        "CONTACTNO": "c", "NICNO": "id", "GPSLONG": "74.1", "GPSLATI": "31.5",
        "CONDATE": "d", "TARIFF": "03", "SLOAD": "10", "FEEDERCD": "050424",
        "CURSTATUS": "1",
    }
    out = _redact(user)
    for k in ("REFNO", "NAME", "FNAME", "ADDR1", "ADDR2", "CONTACTNO", "NICNO",
              "GPSLONG", "GPSLATI"):
        assert out[k] == REDACTED, k
    for k in ("TARIFF", "SLOAD", "FEEDERCD", "CURSTATUS", "CONDATE"):
        assert out[k] == user[k], k
