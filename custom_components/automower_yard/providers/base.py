"""Base provider contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ..models import MowerSnapshot

SnapshotCallback = Callable[[list[MowerSnapshot]], Awaitable[None]]


class MowerProvider(ABC):
    """Base class for provider adapters."""

    supports_commands = False

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the provider."""
        self.hass = hass
        self.entry = entry

    @abstractmethod
    async def async_get_mowers(self) -> list[MowerSnapshot]:
        """Return normalized mower snapshots."""

    async def async_start(self, callback: SnapshotCallback) -> None:
        """Start provider push updates if supported."""

    async def async_start_mowing(self, mower_id: str) -> None:
        """Start mowing if supported."""
        raise NotImplementedError

    async def async_pause(self, mower_id: str) -> None:
        """Pause mowing if supported."""
        raise NotImplementedError

    async def async_dock(self, mower_id: str) -> None:
        """Dock mower if supported."""
        raise NotImplementedError

    async def async_resume(self, mower_id: str) -> None:
        """Resume mowing if supported."""
        raise NotImplementedError
