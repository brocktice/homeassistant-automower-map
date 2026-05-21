"""Sensors for Automower Yard."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_ACTIVITY,
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    ATTR_LAST_POSITION_EVENT,
    ATTR_LAST_WEBSOCKET_EVENT,
    ATTR_STATE,
    ATTR_WEBSOCKET_CONNECTED,
    ATTR_YARD_ZONES,
)
from .coordinator import AutomowerYardCoordinator
from .entity import AutomowerYardEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors."""
    coordinator: AutomowerYardCoordinator = entry.runtime_data
    entities = []
    for mower_id in coordinator.data:
        entities.extend(
            [
                AutomowerStatusSensor(coordinator, mower_id),
                AutomowerYardZoneSensor(coordinator, mower_id),
            ]
        )
    async_add_entities(entities)


class AutomowerStatusSensor(AutomowerYardEntity, SensorEntity):
    """Mower status sensor."""

    _attr_name = "Status"

    def __init__(self, coordinator: AutomowerYardCoordinator, mower_id: str) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, mower_id)
        self._attr_unique_id = f"{mower_id}_status"

    @property
    def native_value(self) -> str | None:
        """Return mower state."""
        mower = self.attributes.get("mower") or {}
        return mower.get("state")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return status attributes."""
        mower = self.attributes.get("mower") or {}
        return {
            **super().extra_state_attributes,
            ATTR_ACTIVITY: mower.get("activity"),
            ATTR_STATE: mower.get("state"),
            ATTR_WEBSOCKET_CONNECTED: self.coordinator.websocket_connected,
            ATTR_LAST_WEBSOCKET_EVENT: self.coordinator.last_websocket_event,
            ATTR_LAST_POSITION_EVENT: self.coordinator.last_position_event,
        }


class AutomowerYardZoneSensor(AutomowerYardEntity, SensorEntity):
    """Named yard location sensor."""

    _attr_name = "Yard Zone"

    def __init__(self, coordinator: AutomowerYardCoordinator, mower_id: str) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, mower_id)
        self._attr_unique_id = f"{mower_id}_yard_zone"

    @property
    def native_value(self) -> str | None:
        """Return configured yard zone."""
        return self.attributes.get("yard_zone") or "Unknown"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return location attributes."""
        latitude, longitude = _latest_position(self.attributes)
        return {
            **super().extra_state_attributes,
            ATTR_LATITUDE: latitude,
            ATTR_LONGITUDE: longitude,
            ATTR_YARD_ZONES: self.attributes.get("yard_zones") or [],
        }


def _latest_position(attributes: dict[str, Any]) -> tuple[float | None, float | None]:
    positions = attributes.get("positions")
    if not isinstance(positions, list) or not positions:
        return None, None
    try:
        return float(positions[0]["latitude"]), float(positions[0]["longitude"])
    except (KeyError, TypeError, ValueError):
        return None, None
