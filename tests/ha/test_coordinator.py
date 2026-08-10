"""Polling behaviour: backoff, rate limiting and re-auth."""
from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.vext.api import VextApiError, VextAuthError, VextRateLimitError
from custom_components.vext.const import DOMAIN, MAX_BACKOFF_INTERVAL, MIN_SCAN_INTERVAL

from .conftest import CABINET_ID, cabinet


async def _tick(hass, freezer: FrozenDateTimeFactory, coordinator) -> None:
    freezer.tick(coordinator.update_interval + timedelta(seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_interval_doubles_while_the_service_errors(
    hass, setup_entry, mock_api, freezer
) -> None:
    coordinator = hass.data[DOMAIN][setup_entry.entry_id]
    assert coordinator.update_interval == timedelta(seconds=120)

    mock_api.async_get_all.side_effect = VextApiError("HTTP 500")
    await _tick(hass, freezer, coordinator)
    assert coordinator.update_interval == timedelta(seconds=120)
    await _tick(hass, freezer, coordinator)
    assert coordinator.update_interval == timedelta(seconds=240)
    await _tick(hass, freezer, coordinator)
    assert coordinator.update_interval == timedelta(seconds=480)
    assert coordinator.last_update_success is False


async def test_interval_returns_to_normal_after_recovery(
    hass, setup_entry, mock_api, freezer
) -> None:
    coordinator = hass.data[DOMAIN][setup_entry.entry_id]
    mock_api.async_get_all.side_effect = VextApiError("HTTP 500")
    await _tick(hass, freezer, coordinator)
    await _tick(hass, freezer, coordinator)
    assert coordinator.update_interval == timedelta(seconds=240)

    mock_api.async_get_all.side_effect = None
    mock_api.async_get_all.return_value = {CABINET_ID: cabinet(temperature_c=23.5)}
    await _tick(hass, freezer, coordinator)

    assert coordinator.last_update_success is True
    assert coordinator.update_interval == timedelta(seconds=120)
    assert coordinator.data[CABINET_ID]["temperature_c"] == 23.5


async def test_retry_after_is_honoured(hass, setup_entry, mock_api, freezer) -> None:
    coordinator = hass.data[DOMAIN][setup_entry.entry_id]
    mock_api.async_get_all.side_effect = VextRateLimitError("slow down", 900)
    await _tick(hass, freezer, coordinator)
    assert coordinator.update_interval == timedelta(seconds=900)


async def test_backoff_never_exceeds_the_ceiling(
    hass, setup_entry, mock_api, freezer
) -> None:
    coordinator = hass.data[DOMAIN][setup_entry.entry_id]
    mock_api.async_get_all.side_effect = VextApiError("HTTP 500")
    for _ in range(8):
        await _tick(hass, freezer, coordinator)
    assert coordinator.update_interval == MAX_BACKOFF_INTERVAL


async def test_revoked_session_stops_polling_and_asks_for_reauth(
    hass, setup_entry, mock_api, freezer
) -> None:
    coordinator = hass.data[DOMAIN][setup_entry.entry_id]
    mock_api.async_get_all.side_effect = VextAuthError("session rejected")
    await _tick(hass, freezer, coordinator)

    assert coordinator.last_update_success is False
    flows = hass.config_entries.flow.async_progress()
    assert [flow["context"]["source"] for flow in flows] == ["reauth"]


async def test_scan_interval_is_floored(hass, setup_entry) -> None:
    coordinator = hass.data[DOMAIN][setup_entry.entry_id]
    coordinator.set_scan_interval(timedelta(seconds=5))
    assert coordinator.update_interval == MIN_SCAN_INTERVAL


async def test_setting_the_interval_clears_backoff(
    hass, setup_entry, mock_api, freezer
) -> None:
    coordinator = hass.data[DOMAIN][setup_entry.entry_id]
    mock_api.async_get_all.side_effect = VextApiError("HTTP 500")
    await _tick(hass, freezer, coordinator)
    await _tick(hass, freezer, coordinator)
    assert coordinator.update_interval == timedelta(seconds=240)

    coordinator.set_scan_interval(timedelta(seconds=180))
    assert coordinator.update_interval == timedelta(seconds=180)
    await _tick(hass, freezer, coordinator)
    assert coordinator.update_interval == timedelta(seconds=180)


async def test_a_hand_edited_interval_below_the_floor_is_clamped_at_setup(
    hass, config_entry, mock_api
) -> None:
    """Options written outside the UI (edited .storage) must not beat the floor."""
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(config_entry, options={"scan_interval": 5})
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    assert coordinator.update_interval == MIN_SCAN_INTERVAL

    # and the backoff it starts from is the floor too, not the 5 seconds asked for
    coordinator._slow_down()
    assert coordinator.update_interval == MIN_SCAN_INTERVAL
