"""Entity state and write-path tests."""
from __future__ import annotations

from datetime import timedelta

from homeassistant.components.number import (
    ATTR_VALUE as NUMBER_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE as NUMBER_SET_VALUE,
)
from homeassistant.components.time import (
    ATTR_TIME,
    DOMAIN as TIME_DOMAIN,
    SERVICE_SET_VALUE as TIME_SET_VALUE,
)
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.vext.const import DOMAIN

from .conftest import CABINET_ID, cabinet


def _entity(hass, suffix: str) -> str:
    matches = [s.entity_id for s in hass.states.async_all() if s.entity_id.endswith(suffix)]
    assert matches, f"no entity ending in {suffix}"
    return matches[0]


async def test_sensor_states(hass, setup_entry) -> None:
    assert hass.states.get(_entity(hass, "_temperature")).state == "22.5"
    assert hass.states.get(_entity(hass, "_humidity")).state == "61"
    assert hass.states.get(_entity(hass, "_water")).state == "4.2"
    assert hass.states.get(_entity(hass, "_plant_health")).state == "92"


async def test_diagnostic_sensors_exist_but_stay_disabled(hass, setup_entry) -> None:
    registry = er.async_get(hass)
    entries = {
        entry.unique_id.split("_", 1)[1]: entry
        for entry in er.async_entries_for_config_entry(registry, setup_entry.entry_id)
    }
    assert entries["firmware"].disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert entries["wifi_rssi"].disabled_by is er.RegistryEntryDisabler.INTEGRATION


async def test_pod_sensor_exposes_the_plant_list(hass, setup_entry) -> None:
    assert hass.states.get(_entity(hass, "_pods_ready")).state == "1"

    state = hass.states.get(_entity(hass, "_pods_past_prime"))
    assert state.state == "0"
    assert [pod["plant"] for pod in state.attributes["pods"]] == ["Mint", "Basil"]
    assert state.attributes["pods"][1]["status"] == "READY"

    health = hass.states.get(_entity(hass, "_plant_health"))
    assert health.attributes["message"] == "All good"


async def test_control_states(hass, setup_entry) -> None:
    assert hass.states.get(_entity(hass, "_brightness")).state == "80.0"
    assert hass.states.get(_entity(hass, "_fog_moisture")).state == "15.0"
    assert hass.states.get(_entity(hass, "_lights_on")).state == "07:00:00"
    assert hass.states.get(_entity(hass, "_lights_off")).state == "23:00:00"


async def test_setting_a_number_writes_once(hass, setup_entry, mock_api) -> None:
    entity_id = _entity(hass, "_brightness")
    await hass.services.async_call(
        NUMBER_DOMAIN,
        NUMBER_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id, NUMBER_VALUE: 40},
        blocking=True,
    )
    mock_api.async_set_settings.assert_awaited_once_with(
        CABINET_ID, {"desired_brightness_pct": 40}
    )


async def test_writes_are_debounced_into_one_refresh(
    hass, setup_entry, mock_api, freezer
) -> None:
    mock_api.async_get_all.reset_mock()
    entity_id = _entity(hass, "_brightness")
    for value in (10, 20, 30):
        await hass.services.async_call(
            NUMBER_DOMAIN,
            NUMBER_SET_VALUE,
            {ATTR_ENTITY_ID: entity_id, NUMBER_VALUE: value},
            blocking=True,
        )
    assert mock_api.async_set_settings.await_count == 3

    freezer.tick(timedelta(seconds=10))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_api.async_get_all.await_count == 1


async def test_setting_a_time_writes_the_service_format(
    hass, setup_entry, mock_api
) -> None:
    entity_id = _entity(hass, "_lights_on")
    await hass.services.async_call(
        TIME_DOMAIN,
        TIME_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id, ATTR_TIME: "06:30:00"},
        blocking=True,
    )
    mock_api.async_set_settings.assert_awaited_once_with(
        CABINET_ID, {"lights_on_time": "06:30:00"}
    )


async def test_entities_go_unavailable_when_the_cabinet_disappears(
    hass, setup_entry, mock_api, freezer
) -> None:
    entity_id = _entity(hass, "_temperature")
    mock_api.async_get_all.return_value = {}
    coordinator = hass.data[DOMAIN][setup_entry.entry_id]
    freezer.tick(coordinator.update_interval + timedelta(seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE


async def test_missing_values_render_as_unknown(hass, config_entry, mock_api) -> None:
    mock_api.async_get_all.return_value = {
        CABINET_ID: cabinet(temperature_c=None, water_volume_ml=None, lights_on_time=None)
    }
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(_entity(hass, "_temperature")).state == "unknown"
    assert hass.states.get(_entity(hass, "_water")).state == "unknown"
    assert hass.states.get(_entity(hass, "_lights_on")).state == "unknown"


async def test_unparsable_time_from_the_service_is_unknown(
    hass, config_entry, mock_api
) -> None:
    mock_api.async_get_all.return_value = {CABINET_ID: cabinet(lights_on_time="nope")}
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(_entity(hass, "_lights_on")).state == "unknown"
