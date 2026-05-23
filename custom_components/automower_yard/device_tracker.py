"""Device trackers for Robot Mower Yard."""

from __future__ import annotations

from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ENTRY_KIND, ENTRY_KIND_PROVIDER
from .coordinator import ProviderCoordinator
from .entity import mower_attributes, mower_device_info
from .models import MowerSnapshot


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up device trackers."""
    if entry.data[CONF_ENTRY_KIND] != ENTRY_KIND_PROVIDER:
        return
    coordinator: ProviderCoordinator = entry.runtime_data
    async_add_entities(MowerTrackerEntity(coordinator, mower_id) for mower_id in coordinator.data)


class MowerTrackerEntity(CoordinatorEntity[ProviderCoordinator], TrackerEntity):
    """Mower location tracker."""

    _attr_name = "Location"

    def __init__(self, coordinator: ProviderCoordinator, mower_id: str) -> None:
        """Initialize the tracker."""
        super().__init__(coordinator)
        self.mower_id = mower_id
        self._attr_unique_id = f"{mower_id}_location"

    @property
    def snapshot(self) -> MowerSnapshot:
        """Return the current mower snapshot."""
        return self.coordinator.data[self.mower_id]

    @property
    def latitude(self) -> float | None:
        """Return latitude."""
        return self.snapshot.latitude

    @property
    def longitude(self) -> float | None:
        """Return longitude."""
        return self.snapshot.longitude

    @property
    def source_type(self) -> str:
        """Return source type."""
        return "gps"

    @property
    def device_info(self):
        """Return mower device info."""
        return mower_device_info(self.coordinator.yard_entry_id, self.snapshot)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return common attributes."""
        return mower_attributes(self.coordinator.yard_entry_id, self.snapshot)
