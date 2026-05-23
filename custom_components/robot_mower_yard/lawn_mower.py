"""Lawn mower entities for Robot Mower Yard."""

from __future__ import annotations

from typing import Any

from homeassistant.components.lawn_mower import (
    LawnMowerActivity,
    LawnMowerEntity,
    LawnMowerEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ENTRY_KIND, ENTRY_KIND_PROVIDER
from .coordinator import ProviderCoordinator
from .entity import mower_attributes, mower_device_info
from .models import MowerSnapshot

STATE_TO_ACTIVITY = {
    "idle": LawnMowerActivity.DOCKED,
    "mowing": LawnMowerActivity.MOWING,
    "paused": LawnMowerActivity.PAUSED,
    "docked": LawnMowerActivity.DOCKED,
    "charging": LawnMowerActivity.DOCKED,
    "returning": LawnMowerActivity.RETURNING,
    "ERROR": LawnMowerActivity.ERROR,
    "FATAL_ERROR": LawnMowerActivity.ERROR,
    "error": LawnMowerActivity.ERROR,
    "unknown": LawnMowerActivity.ERROR,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up lawn mower entities."""
    if entry.data[CONF_ENTRY_KIND] != ENTRY_KIND_PROVIDER:
        return
    coordinator: ProviderCoordinator = entry.runtime_data
    async_add_entities(
        RobotMowerLawnMower(coordinator, mower_id)
        for mower_id in coordinator.data
        if _supports_commands(coordinator)
    )


class RobotMowerLawnMower(CoordinatorEntity[ProviderCoordinator], LawnMowerEntity):
    """A command-capable mower entity backed by a provider."""

    _attr_supported_features = (
        LawnMowerEntityFeature.START_MOWING
        | LawnMowerEntityFeature.PAUSE
        | LawnMowerEntityFeature.DOCK
    )

    def __init__(self, coordinator: ProviderCoordinator, mower_id: str) -> None:
        """Initialize entity."""
        super().__init__(coordinator)
        self.mower_id = mower_id
        self._attr_name = self.snapshot.name or self.snapshot.stable_id
        self._attr_unique_id = f"{mower_id}_lawn_mower"

    @property
    def snapshot(self) -> MowerSnapshot:
        """Return current mower snapshot."""
        return self.coordinator.data[self.mower_id]

    @property
    def device_info(self):
        """Return mower device info."""
        return mower_device_info(self.coordinator.yard_entry_id, self.snapshot)

    @property
    def activity(self) -> LawnMowerActivity | None:
        """Return mower activity."""
        state = self.snapshot.state
        return STATE_TO_ACTIVITY.get(state)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra mower attributes."""
        return {
            **mower_attributes(self.coordinator.yard_entry_id, self.snapshot),
            "battery": self.snapshot.battery_percent,
            "status": self.snapshot.state,
            "activity": self.snapshot.activity,
            "error_code": self.snapshot.error_code,
        }

    async def async_start_mowing(self) -> None:
        """Start mowing."""
        await self.coordinator.provider.async_start_mowing(self.snapshot.mower_id)
        await self.coordinator.async_request_refresh()

    async def async_pause(self) -> None:
        """Pause mowing."""
        await self.coordinator.provider.async_pause(self.snapshot.mower_id)
        await self.coordinator.async_request_refresh()

    async def async_dock(self) -> None:
        """Dock mower."""
        await self.coordinator.provider.async_dock(self.snapshot.mower_id)
        await self.coordinator.async_request_refresh()

    async def async_resume(self) -> None:
        """Resume mowing."""
        await self.coordinator.provider.async_resume(self.snapshot.mower_id)
        await self.coordinator.async_request_refresh()


def _supports_commands(coordinator: ProviderCoordinator) -> bool:
    return bool(getattr(coordinator.provider, "supports_commands", False))
