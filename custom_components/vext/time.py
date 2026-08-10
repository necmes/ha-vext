"""Vext light-schedule time controls."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import time as dt_time
from typing import Any

from homeassistant.components.time import TimeEntity, TimeEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, FIELD_LIGHTS_OFF, FIELD_LIGHTS_ON
from .coordinator import VextCoordinator
from .entity import VextEntity


@dataclass(frozen=True, kw_only=True)
class VextTimeDescription(TimeEntityDescription):
    """Time description bound to a cabinet_settings field."""

    field: str
    value_key: str


TIMES: tuple[VextTimeDescription, ...] = (
    VextTimeDescription(
        key="lights_on",
        translation_key="lights_on",
        field=FIELD_LIGHTS_ON,
        value_key="lights_on_time",
        icon="mdi:weather-sunny",
    ),
    VextTimeDescription(
        key="lights_off",
        translation_key="lights_off",
        field=FIELD_LIGHTS_OFF,
        value_key="lights_off_time",
        icon="mdi:weather-night",
    ),
)


def _parse(value: Any) -> dt_time | None:
    if not value:
        return None
    try:
        h, m, *rest = str(value).split(":")
        return dt_time(int(h), int(m), int(rest[0]) if rest else 0)
    except (ValueError, IndexError):
        return None


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: VextCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[TimeEntity] = []
    for frid in coordinator.data:
        for desc in TIMES:
            entities.append(VextTime(coordinator, frid, desc))
    async_add_entities(entities)


class VextTime(VextEntity, TimeEntity):
    """A writable light-schedule time."""

    entity_description: VextTimeDescription

    def __init__(self, coordinator: VextCoordinator, frid: str, desc: VextTimeDescription) -> None:
        super().__init__(coordinator, frid, desc.key)
        self.entity_description = desc

    @property
    def native_value(self) -> dt_time | None:
        return _parse(self._cabinet.get(self.entity_description.value_key))

    async def async_set_value(self, value: dt_time) -> None:
        await self.coordinator.api.async_set_settings(
            self._frid, {self.entity_description.field: value.strftime("%H:%M:%S")}
        )
        await self.coordinator.async_request_refresh()
