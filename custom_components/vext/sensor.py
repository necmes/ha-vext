"""Vext sensors."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EntityCategory,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfTemperature,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import VextCoordinator
from .entity import VextEntity


@dataclass(frozen=True, kw_only=True)
class VextSensorDescription(SensorEntityDescription):
    """Sensor description with a value extractor."""

    value_fn: Callable[[dict[str, Any]], Any]
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


def _water_l(cab: dict) -> Any:
    ml = cab.get("water_volume_ml")
    return round(ml / 1000, 1) if ml is not None else None


def _ts(value: Any) -> Any:
    return dt_util.parse_datetime(value) if value else None


SENSORS: tuple[VextSensorDescription, ...] = (
    VextSensorDescription(
        key="temperature",
        translation_key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda c: c.get("temperature_c"),
    ),
    VextSensorDescription(
        key="humidity",
        translation_key="humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        value_fn=lambda c: c.get("humidity_pct"),
    ),
    VextSensorDescription(
        key="water",
        translation_key="water",
        device_class=SensorDeviceClass.VOLUME_STORAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfVolume.LITERS,
        value_fn=_water_l,
    ),
    VextSensorDescription(
        key="nutrient_grow",
        translation_key="nutrient_grow",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfVolume.MILLILITERS,
        value_fn=lambda c: c.get("nutrient_grow_ml"),
    ),
    VextSensorDescription(
        key="nutrient_bloom",
        translation_key="nutrient_bloom",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfVolume.MILLILITERS,
        value_fn=lambda c: c.get("nutrient_bloom_ml"),
    ),
    VextSensorDescription(
        key="wifi_rssi",
        translation_key="wifi_rssi",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.get("wifi_rssi"),
    ),
    VextSensorDescription(
        key="health",
        translation_key="health",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="pts",
        icon="mdi:heart-pulse",
        value_fn=lambda c: c.get("score"),
        attrs_fn=lambda c: {"message": c.get("score_info")},
    ),
    VextSensorDescription(
        key="water_refill",
        translation_key="water_refill",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda c: _ts(c.get("water_refill_predicted_at")),
    ),
    VextSensorDescription(
        key="pods_ready",
        translation_key="pods_ready",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:leaf",
        value_fn=lambda c: c.get("pods_ready"),
    ),
    VextSensorDescription(
        key="pods_past_prime",
        translation_key="pods_past_prime",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:leaf-off",
        value_fn=lambda c: c.get("pods_past_prime"),
        attrs_fn=lambda c: {"pods": c.get("pods")},
    ),
    VextSensorDescription(
        key="firmware",
        translation_key="firmware",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.get("firmware_version"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: VextCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = []
    for frid in coordinator.data:
        for desc in SENSORS:
            entities.append(VextSensor(coordinator, frid, desc))
    async_add_entities(entities)


class VextSensor(VextEntity, SensorEntity):
    """A single Vext sensor."""

    entity_description: VextSensorDescription

    def __init__(self, coordinator: VextCoordinator, frid: str, desc: VextSensorDescription) -> None:
        super().__init__(coordinator, frid, desc.key)
        self.entity_description = desc

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self._cabinet)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn:
            return self.entity_description.attrs_fn(self._cabinet)
        return None
