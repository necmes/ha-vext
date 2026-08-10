"""Vext number controls (brightness, fog moisture, fog rhythm)."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    FIELD_BRIGHTNESS,
    FIELD_FOG_MOISTURE,
    FIELD_FOG_RHYTHM,
)
from .coordinator import VextCoordinator
from .entity import VextEntity


@dataclass(frozen=True, kw_only=True)
class VextNumberDescription(NumberEntityDescription):
    """Number description bound to a cabinet_settings field."""

    field: str
    value_fn: Callable[[dict[str, Any]], Any]


NUMBERS: tuple[VextNumberDescription, ...] = (
    VextNumberDescription(
        key="brightness",
        translation_key="brightness",
        field=FIELD_BRIGHTNESS,
        icon="mdi:brightness-6",
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement="%",
        value_fn=lambda c: c.get("desired_brightness_pct"),
    ),
    VextNumberDescription(
        key="fog_moisture",
        translation_key="fog_moisture",
        field=FIELD_FOG_MOISTURE,
        icon="mdi:water-percent",
        native_min_value=-45,
        native_max_value=45,
        native_step=15,
        native_unit_of_measurement="%",
        mode=NumberMode.SLIDER,
        value_fn=lambda c: c.get("fog_duration_adjust_pct"),
    ),
    VextNumberDescription(
        key="fog_rhythm",
        translation_key="fog_rhythm",
        field=FIELD_FOG_RHYTHM,
        icon="mdi:timer-sand",
        native_min_value=-45,
        native_max_value=45,
        native_step=15,
        native_unit_of_measurement="%",
        mode=NumberMode.SLIDER,
        value_fn=lambda c: c.get("cycle_length_adjust_pct"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: VextCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[NumberEntity] = []
    for frid in coordinator.data:
        for desc in NUMBERS:
            entities.append(VextNumber(coordinator, frid, desc))
    async_add_entities(entities)


class VextNumber(VextEntity, NumberEntity):
    """A writable Vext setting exposed as a number."""

    entity_description: VextNumberDescription

    def __init__(self, coordinator: VextCoordinator, frid: str, desc: VextNumberDescription) -> None:
        super().__init__(coordinator, frid, desc.key)
        self.entity_description = desc

    @property
    def native_value(self) -> float | None:
        val = self.entity_description.value_fn(self._cabinet)
        return float(val) if val is not None else None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.api.async_set_settings(
            self._frid, {self.entity_description.field: int(value)}
        )
        await self.coordinator.async_request_refresh()
