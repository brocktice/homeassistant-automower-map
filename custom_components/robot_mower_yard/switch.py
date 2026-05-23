"""Switches for Robot Mower Yard."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_ENTRY_KIND,
    CUTTING_HEIGHT_UNIT_CM,
    CUTTING_HEIGHT_UNIT_IN,
    ENTRY_KIND_PROVIDER,
)
from .coordinator import ProviderCoordinator
from .entity import mower_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switches."""
    if entry.data[CONF_ENTRY_KIND] != ENTRY_KIND_PROVIDER:
        return
    coordinator: ProviderCoordinator = entry.runtime_data
    async_add_entities(
        MowerCuttingHeightInchesSwitch(coordinator, mower_id)
        for mower_id in coordinator.data
        if _has_cutting_height(coordinator, mower_id)
    )


class MowerCuttingHeightInchesSwitch(
    CoordinatorEntity[ProviderCoordinator], SwitchEntity
):
    """Switch controlling whether cutting height displays in inches."""

    _attr_name = "Cutting Height in Inches"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: ProviderCoordinator, mower_id: str) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self.mower_id = mower_id
        self._attr_unique_id = f"{mower_id}_cutting_height_in_inches"

    @property
    def is_on(self) -> bool:
        """Return true when cutting height displays in inches."""
        return self.coordinator.cutting_height_unit(self.mower_id) == CUTTING_HEIGHT_UNIT_IN

    @property
    def available(self) -> bool:
        """Return true if the mower exposes a cutting-height setting."""
        snapshot = self.coordinator.data.get(self.mower_id)
        if snapshot is None:
            return False
        setting = ((snapshot.raw.get("attributes") or {}).get("settings") or {}).get(
            "cuttingHeight"
        )
        return setting is not None

    @property
    def device_info(self):
        """Return mower device info."""
        return mower_device_info(
            self.coordinator.yard_entry_id,
            self.coordinator.data[self.mower_id],
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


def _has_cutting_height(coordinator: ProviderCoordinator, mower_id: str) -> bool:
    snapshot = coordinator.data.get(mower_id)
    if snapshot is None:
        return False
    setting = ((snapshot.raw.get("attributes") or {}).get("settings") or {}).get(
        "cuttingHeight"
    )
    return setting is not None
