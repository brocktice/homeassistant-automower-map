"""Binary sensors for Automower Yard."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from .const import ATTR_ACTIVITY, ATTR_ERROR_CODE, ATTR_STATE, ATTR_YARD_ZONES
from .coordinator import AutomowerYardCoordinator
from .entity import AutomowerYardEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    coordinator: AutomowerYardCoordinator = entry.runtime_data
    added_zone_entities: set[tuple[str, str]] = set()

    @callback
    def add_missing_zone_entities() -> None:
        entities: list[BinarySensorEntity] = []
        for mower_id in coordinator.data:
            for zone_name in coordinator.zone_names:
                key = (mower_id, zone_name)
                if key in added_zone_entities:
                    continue
                added_zone_entities.add(key)
                entities.append(AutomowerZoneBinarySensor(coordinator, mower_id, zone_name))
        if entities:
            async_add_entities(entities)

    entities: list[BinarySensorEntity] = []
    for mower_id in coordinator.data:
        entities.append(AutomowerStuckBinarySensor(coordinator, mower_id))
    async_add_entities(entities)
    add_missing_zone_entities()
    entry.async_on_unload(coordinator.async_add_listener(add_missing_zone_entities))


class AutomowerStuckBinarySensor(AutomowerYardEntity, BinarySensorEntity):
    """Mower stuck/problem sensor."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_name = "Stuck"

    def __init__(self, coordinator: AutomowerYardCoordinator, mower_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, mower_id)
        self._attr_unique_id = f"{mower_id}_stuck"

    @property
    def is_on(self) -> bool:
        """Return true if mower appears stuck or in error."""
        return bool(self.attributes.get("is_stuck"))

    @property
    def extra_state_attributes(self) -> dict:
        """Return diagnostic attributes."""
        mower = self.attributes.get("mower") or {}
        return {
            **super().extra_state_attributes,
            ATTR_STATE: mower.get("state"),
            ATTR_ACTIVITY: mower.get("activity"),
            ATTR_ERROR_CODE: mower.get("errorCode"),
        }


class AutomowerZoneBinarySensor(AutomowerYardEntity, BinarySensorEntity):
    """Sensor indicating whether the mower is in a configured yard zone."""

    def __init__(
        self, coordinator: AutomowerYardCoordinator, mower_id: str, zone_name: str
    ) -> None:
        """Initialize the zone sensor."""
        super().__init__(coordinator, mower_id)
        self.zone_name = zone_name
        self._attr_name = f"In {zone_name}"
        self._attr_unique_id = f"{mower_id}_in_zone_{slugify(zone_name)}"

    @property
    def is_on(self) -> bool:
        """Return true if mower is in this zone."""
        return self.zone_name in (self.attributes.get("yard_zones") or [])

    @property
    def extra_state_attributes(self) -> dict:
        """Return zone attributes."""
        return {
            **super().extra_state_attributes,
            "zone": self.zone_name,
            ATTR_YARD_ZONES: self.attributes.get("yard_zones") or [],
        }
