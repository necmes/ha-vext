"""Base entity for Vext."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import VextCoordinator


class VextEntity(CoordinatorEntity[VextCoordinator]):
    """Common base: one HA device per cabinet."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: VextCoordinator, frid: str, key: str) -> None:
        super().__init__(coordinator)
        self._frid = frid
        self._attr_unique_id = f"{frid}_{key}"

    @property
    def _cabinet(self) -> dict:
        return self.coordinator.data.get(self._frid, {})

    @property
    def available(self) -> bool:
        return super().available and self._frid in self.coordinator.data

    @property
    def device_info(self) -> DeviceInfo:
        cab = self._cabinet
        return DeviceInfo(
            identifiers={(DOMAIN, self._frid)},
            name=cab.get("name") or "Vext cabinet",
            manufacturer=MANUFACTURER,
            model=MODEL,
            sw_version=cab.get("firmware_version"),
            serial_number=cab.get("serial"),
        )
