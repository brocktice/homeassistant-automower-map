"""Automower Yard integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import PLATFORMS
from .coordinator import AutomowerYardCoordinator
from .panel import async_setup_panel, async_unload_panel

AutomowerYardConfigEntry = ConfigEntry[AutomowerYardCoordinator]


async def async_setup_entry(
    hass: HomeAssistant, entry: AutomowerYardConfigEntry
) -> bool:
    """Set up Automower Yard from a config entry."""
    coordinator = AutomowerYardCoordinator(hass, entry)
    await coordinator.async_load_heatmap()
    await coordinator.async_config_entry_first_refresh()
    await coordinator.async_start_websocket()

    entry.runtime_data = coordinator
    await async_setup_panel(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    entry.async_on_unload(coordinator.async_stop)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: AutomowerYardConfigEntry
) -> bool:
    """Unload a config entry."""
    await entry.runtime_data.async_stop()
    await async_unload_panel(hass)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(
    hass: HomeAssistant, entry: AutomowerYardConfigEntry
) -> None:
    """Handle options updates."""
    entry.runtime_data.reload_options()
    await entry.runtime_data.async_request_refresh()
