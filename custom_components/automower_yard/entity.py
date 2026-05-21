"""Base entities for Automower Yard."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTR_MODEL, ATTR_MOWER_ID, ATTR_SERIAL_NUMBER, DOMAIN
from .coordinator import AutomowerYardCoordinator


class AutomowerYardEntity(CoordinatorEntity[AutomowerYardCoordinator]):
    """Base Automower Yard entity."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: AutomowerYardCoordinator, mower_id: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.mower_id = mower_id

    @property
    def mower(self) -> dict[str, Any]:
        """Return mower data."""
        return self.coordinator.data[self.mower_id]

    @property
    def attributes(self) -> dict[str, Any]:
        """Return mower attributes."""
        return self.mower.get("attributes") or {}

    @property
    def mower_name(self) -> str:
        """Return user-friendly mower name."""
        system = self.attributes.get("system") or {}
        return system.get("name") or f"Automower {self.mower_id[:8]}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry info."""
        system = self.attributes.get("system") or {}
        return DeviceInfo(
            identifiers={(DOMAIN, self.mower_id)},
            manufacturer="Husqvarna",
            model=system.get("model"),
            name=self.mower_name,
            serial_number=system.get("serialNumber"),
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return common attributes."""
        system = self.attributes.get("system") or {}
        return {
            ATTR_MOWER_ID: self.mower_id,
            ATTR_MODEL: system.get("model"),
            ATTR_SERIAL_NUMBER: system.get("serialNumber"),
        }
