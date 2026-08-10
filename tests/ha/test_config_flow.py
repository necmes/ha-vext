"""Config, re-auth and options flow tests."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType

from custom_components.vext.api import VextApiError, VextAuthError
from custom_components.vext.const import (
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    DOMAIN,
)

USER_INPUT = {CONF_EMAIL: "User@Example.com", CONF_PASSWORD: "hunter2"}


async def test_user_flow_creates_entry(hass, mock_api) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "User@Example.com"
    assert result["data"] == {
        CONF_EMAIL: "User@Example.com",
        CONF_PASSWORD: "hunter2",
    }
    assert result["result"].unique_id == "user@example.com"
    mock_api.validate.assert_awaited()


async def test_invalid_credentials_show_error_then_recover(hass, mock_api) -> None:
    mock_api.validate.side_effect = VextAuthError("bad password")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}

    mock_api.validate.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_unreachable_service_shows_cannot_connect(hass, mock_api) -> None:
    mock_api.validate.side_effect = VextApiError("timeout")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_same_account_twice_is_aborted(hass, config_entry, mock_api) -> None:
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_updates_the_stored_password(hass, setup_entry, mock_api) -> None:
    result = await setup_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "new-secret"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert setup_entry.data[CONF_PASSWORD] == "new-secret"
    assert setup_entry.data[CONF_EMAIL] == "user@example.com"


async def test_reauth_rejects_a_still_wrong_password(hass, setup_entry, mock_api) -> None:
    mock_api.validate.side_effect = VextAuthError("nope")
    result = await setup_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "still-wrong"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert setup_entry.data[CONF_PASSWORD] == "hunter2"


async def test_options_flow_sets_the_poll_interval(hass, setup_entry) -> None:
    result = await hass.config_entries.options.async_init(setup_entry.entry_id)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 300}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert setup_entry.options[CONF_SCAN_INTERVAL] == 300
    coordinator = hass.data[DOMAIN][setup_entry.entry_id]
    assert coordinator.update_interval.total_seconds() == 300


async def test_options_flow_refuses_polling_faster_than_the_floor(
    hass, setup_entry
) -> None:
    import voluptuous as vol

    result = await hass.config_entries.options.async_init(setup_entry.entry_id)
    try:
        await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_SCAN_INTERVAL: 5}
        )
    except vol.Invalid:
        pass
    else:
        raise AssertionError("a 5 second interval should be rejected")
