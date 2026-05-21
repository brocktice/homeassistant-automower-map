"""Device tracker entity for mower GPS position."""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.components.device_tracker.const import SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ATTR_YARD_ZONE, ATTR_YARD_ZONES
from .coordinator import AutomowerYardCoordinator
from .entity import AutomowerYardEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up device trackers."""
    coordinator: AutomowerYardCoordinator = entry.runtime_data
    async_add_entities(
        AutomowerPositionTracker(coordinator, mower_id) for mower_id in coordinator.data
    )


class AutomowerPositionTracker(AutomowerYardEntity, TrackerEntity):
    """Map-capable mower tracker."""

    _attr_name = "Location"
    _attr_source_type = SourceType.GPS

    def __init__(self, coordinator: AutomowerYardCoordinator, mower_id: str) -> None:
        """Initialize tracker."""
        super().__init__(coordinator, mower_id)
        self._attr_unique_id = f"{mower_id}_tracker"
        self._update_location_attrs()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update cached GPS attrs before writing state."""
        self._update_location_attrs()
        super()._handle_coordinator_update()

    def _update_location_attrs(self) -> None:
        """Update Home Assistant's expected GPS attributes."""
        self._attr_latitude = _latest_coordinate(self.attributes, "latitude")
        self._attr_longitude = _latest_coordinate(self.attributes, "longitude")
        self._attr_location_accuracy = 5

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return tracker attributes."""
        return {
            **super().extra_state_attributes,
            ATTR_YARD_ZONE: self.attributes.get("yard_zone"),
            ATTR_YARD_ZONES: self.attributes.get("yard_zones") or [],
        }


def _latest_coordinate(attributes: dict[str, Any], key: str) -> float | None:
    positions = attributes.get("positions")
    if not isinstance(positions, list) or not positions:
        return None
    try:
        return float(positions[0][key])
    except (KeyError, TypeError, ValueError):
        return None
