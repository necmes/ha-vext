"""Fixtures for the Home Assistant level tests."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vext.const import CONF_EMAIL, CONF_PASSWORD, DOMAIN

CABINET_ID = "cab-1"


def cabinet(**overrides: Any) -> dict[str, Any]:
    data = {
        "factory_reset_id": CABINET_ID,
        "serial": "SN12345678",
        "name": "Kitchen",
        "temperature_c": 22.5,
        "humidity_pct": 61,
        "water_volume_ml": 4200,
        "nutrient_grow_ml": 300,
        "nutrient_bloom_ml": 250,
        "wifi_ssid": "home",
        "wifi_rssi": -55,
        "firmware_version": "1.2.3",
        "water_refill_predicted_at": "2026-08-25T10:00:00+00:00",
        "nutrient_grow_refill_predicted_at": None,
        "nutrient_bloom_refill_predicted_at": None,
        "desired_brightness_pct": 80,
        "fog_duration_adjust_pct": 15,
        "cycle_length_adjust_pct": -15,
        "lights_on_time": "07:00:00",
        "lights_off_time": "23:00:00",
        "timezone_name_iana": "Europe/Paris",
        "score": 92,
        "score_info": "All good",
        "water_info": "Top up soon",
        "pods_total": 2,
        "pods_ready": 1,
        "pods_growing": 1,
        "pods_past_prime": 0,
        "pods": [
            {"pos": 1, "plant": "Mint", "status": "GROWING", "health": "GOOD", "image": None},
            {"pos": 2, "plant": "Basil", "status": "READY", "health": "GOOD", "image": None},
        ],
    }
    data.update(overrides)
    return data


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load the integration from custom_components/."""
    yield


@pytest.fixture
def config_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="user@example.com",
        unique_id="user@example.com",
        data={CONF_EMAIL: "user@example.com", CONF_PASSWORD: "hunter2"},
    )


@pytest.fixture
def mock_api():
    """Patch the API client used by the integration and the config flow."""
    api = AsyncMock()
    api.user_id = "user-1"
    api.async_get_all.return_value = {CABINET_ID: cabinet()}
    with patch("custom_components.vext.VextApi", return_value=api), patch(
        "custom_components.vext.config_flow.VextApi", return_value=api
    ):
        yield api


@pytest.fixture
async def setup_entry(hass, config_entry, mock_api):
    """Add and set up the config entry."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry
