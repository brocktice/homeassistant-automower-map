"""Switches for Automower Yard."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CUTTING_HEIGHT_UNIT_CM, CUTTING_HEIGHT_UNIT_IN
from .coordinator import AutomowerYardCoordinator
from .entity import AutomowerYardEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switches."""
    coordinator: AutomowerYardCoordinator = entry.runtime_data
    async_add_entities(
        AutomowerCuttingHeightInchesSwitch(coordinator, mower_id)
        for mower_id in coordinator.data
    )


class AutomowerCuttingHeightInchesSwitch(AutomowerYardEntity, SwitchEntity):
    """Switch controlling whether cutting height displays in inches."""

    _attr_name = "Cutting Height in Inches"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: AutomowerYardCoordinator, mower_id: str) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, mower_id)
        self._attr_unique_id = f"{mower_id}_cutting_height_in_inches"

    @property
    def is_on(self) -> bool:
        """Return true when cutting height is displayed in inches."""
        return (
            self.coordinator.cutting_height_unit(self.mower_id)
            == CUTTING_HEIGHT_UNIT_IN
        )

    async def async_turn_on(self, **kwargs: object) -> None:
        """Display cutting height in inches."""
        await self.coordinator.async_set_cutting_height_unit(
            self.mower_id,
            CUTTING_HEIGHT_UNIT_IN,
        )

    async def async_turn_off(self, **kwargs: object) -> None:
        """Display cutting height in centimeters."""
        await self.coordinator.async_set_cutting_height_unit(
            self.mower_id,
            CUTTING_HEIGHT_UNIT_CM,
        )
