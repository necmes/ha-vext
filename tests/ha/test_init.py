"""Set-up, teardown and failure-path tests for the integration entry."""
from __future__ import annotations

from datetime import timedelta

import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr

from custom_components.vext.api import VextApiError, VextAuthError
from custom_components.vext.const import CONF_SCAN_INTERVAL, DOMAIN

from .conftest import CABINET_ID


async def test_setup_creates_a_device_and_entities(hass, setup_entry) -> None:
    assert setup_entry.state is ConfigEntryState.LOADED

    devices = dr.async_entries_for_config_entry(
        dr.async_get(hass), setup_entry.entry_id
    )
    assert len(devices) == 1
    assert devices[0].name == "Kitchen"
    assert devices[0].serial_number == "SN12345678"
    assert devices[0].sw_version == "1.2.3"
    assert (DOMAIN, CABINET_ID) in devices[0].identifiers

    suffixes = {
        state.entity_id.split(".")[1].removeprefix("kitchen_")
        for state in hass.states.async_all()
    }
    # every enabled sensor and control of the cabinet is present
    assert {
        "temperature",
        "humidity",
        "water",
        "nutrient_grow",
        "nutrient_bloom",
        "plant_health",
        "water_refill",
        "pods_ready",
        "pods_past_prime",
        "brightness",
        "fog_moisture",
        "fog_rhythm",
        "lights_on",
        "lights_off",
    } <= suffixes
    # the diagnostic ones stay out of the state machine until enabled
    assert {"firmware", "wifi_signal"}.isdisjoint(suffixes)


async def test_unload_removes_the_coordinator(hass, setup_entry) -> None:
    assert await hass.config_entries.async_unload(setup_entry.entry_id)
    await hass.async_block_till_done()
    assert setup_entry.state is ConfigEntryState.NOT_LOADED
    assert setup_entry.entry_id not in hass.data[DOMAIN]


async def test_bad_credentials_trigger_reauth_instead_of_retrying(
    hass, config_entry, mock_api
) -> None:
    mock_api.async_get_all.side_effect = VextAuthError("invalid login")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [flow["context"]["source"] for flow in flows] == ["reauth"]


async def test_service_error_defers_setup(hass, config_entry, mock_api) -> None:
    mock_api.async_get_all.side_effect = VextApiError("HTTP 500")
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_configured_interval_is_used_at_setup(hass, config_entry, mock_api) -> None:
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(config_entry, options={CONF_SCAN_INTERVAL: 240})
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    assert coordinator.update_interval == timedelta(seconds=240)


async def test_two_accounts_run_side_by_side_with_their_own_cabinets(hass) -> None:
    """The integration is per-account: a second login brings its own cabinets."""
    from unittest.mock import AsyncMock, patch

    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.vext.const import CONF_EMAIL, CONF_PASSWORD

    from .conftest import cabinet

    apis = {
        "alice@example.com": AsyncMock(
            user_id="user-a",
            **{
                "async_get_all.return_value": {
                    "cab-a": cabinet(factory_reset_id="cab-a", name="Alice kitchen", serial="SN-A")
                }
            },
        ),
        "bob@example.com": AsyncMock(
            user_id="user-b",
            **{
                "async_get_all.return_value": {
                    "cab-b": cabinet(factory_reset_id="cab-b", name="Bob balcony", serial="SN-B")
                }
            },
        ),
    }

    entries = {}
    with patch(
        "custom_components.vext.VextApi", side_effect=lambda _s, email, _p: apis[email]
    ):
        for email in apis:
            entry = MockConfigEntry(
                domain=DOMAIN,
                title=email,
                unique_id=email,
                data={CONF_EMAIL: email, CONF_PASSWORD: "hunter2"},
            )
            entry.add_to_hass(hass)
            assert await hass.config_entries.async_setup(entry.entry_id)
            entries[email] = entry
        await hass.async_block_till_done()

    registry = dr.async_get(hass)
    alice = dr.async_entries_for_config_entry(registry, entries["alice@example.com"].entry_id)
    bob = dr.async_entries_for_config_entry(registry, entries["bob@example.com"].entry_id)

    assert [d.name for d in alice] == ["Alice kitchen"]
    assert [d.name for d in bob] == ["Bob balcony"]
    assert (DOMAIN, "cab-a") in alice[0].identifiers
    assert (DOMAIN, "cab-b") in bob[0].identifiers
    assert alice[0].id != bob[0].id

    # each account only ever asks its own session for data
    apis["alice@example.com"].async_get_all.assert_awaited()
    apis["bob@example.com"].async_get_all.assert_awaited()

    states = {s.entity_id for s in hass.states.async_all()}
    assert any("alice_kitchen" in e for e in states)
    assert any("bob_balcony" in e for e in states)


async def test_changing_options_of_an_unloaded_entry_is_a_no_op(
    hass, setup_entry
) -> None:
    """Options can be edited while the entry is unloaded; nothing should blow up."""
    assert await hass.config_entries.async_unload(setup_entry.entry_id)
    await hass.async_block_till_done()

    hass.config_entries.async_update_entry(setup_entry, options={CONF_SCAN_INTERVAL: 900})
    await hass.async_block_till_done()

    assert setup_entry.options[CONF_SCAN_INTERVAL] == 900
    assert setup_entry.entry_id not in hass.data[DOMAIN]


# The point of this test is that the entry stays loaded after a failed unload,
# so the coordinator's refresh timer is still scheduled at teardown.
@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_a_platform_refusing_to_unload_keeps_the_coordinator(
    hass, setup_entry
) -> None:
    """A failed unload must not drop the coordinator other platforms still use."""
    from unittest.mock import patch

    with patch.object(
        hass.config_entries, "async_unload_platforms", return_value=False
    ):
        assert await hass.config_entries.async_unload(setup_entry.entry_id) is False

    assert setup_entry.entry_id in hass.data[DOMAIN]


async def test_the_options_listener_tolerates_a_missing_coordinator(
    hass, config_entry
) -> None:
    """Guard against an options update racing with a reload of the entry."""
    from custom_components.vext import _async_options_updated

    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(config_entry, options={CONF_SCAN_INTERVAL: 300})

    await _async_options_updated(hass, config_entry)  # must not raise

    assert config_entry.entry_id not in hass.data.get(DOMAIN, {})


async def test_the_card_url_is_versioned_so_browsers_reload_it(hass, setup_entry) -> None:
    """A stale cached card after an update would silently show old rendering."""
    from custom_components.vext import CARD_JS_URL, CARD_URL
    from custom_components.vext.const import VERSION

    assert CARD_JS_URL == f"{CARD_URL}?v={VERSION}"
