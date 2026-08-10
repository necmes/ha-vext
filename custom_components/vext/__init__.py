"""The Vext integration."""
from __future__ import annotations

import os
from datetime import timedelta

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import VextApi
from .const import (
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    VERSION,
)
from .coordinator import VextCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.NUMBER, Platform.TIME]

CARD_URL = "/vext_static/vext-card.js"
# Version query so browsers pick up a new card after an integration update.
CARD_JS_URL = f"{CARD_URL}?v={VERSION}"


def _scan_interval(entry: ConfigEntry) -> timedelta:
    seconds = entry.options.get(CONF_SCAN_INTERVAL)
    if seconds is None:
        return DEFAULT_SCAN_INTERVAL
    return timedelta(seconds=int(seconds))


async def _register_card(hass: HomeAssistant) -> None:
    """Serve and auto-load the bundled Lovelace card (once)."""
    if hass.data.get(f"{DOMAIN}_card"):
        return
    path = os.path.join(os.path.dirname(__file__), "www", "vext-card.js")
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, path, False)]
    )
    add_extra_js_url(hass, CARD_JS_URL)
    hass.data[f"{DOMAIN}_card"] = True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply a new poll interval without reloading the whole entry."""
    coordinator: VextCoordinator | None = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator:
        coordinator.set_scan_interval(_scan_interval(entry))


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Vext from a config entry."""
    await _register_card(hass)
    session = async_get_clientsession(hass)
    api = VextApi(session, entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD])
    coordinator = VextCoordinator(hass, entry, api, _scan_interval(entry))

    # The coordinator turns API errors into ConfigEntryAuthFailed / UpdateFailed,
    # which this call already maps to a re-auth flow or a setup retry.
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
