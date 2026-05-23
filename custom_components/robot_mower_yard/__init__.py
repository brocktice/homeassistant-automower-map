"""Robot Mower Yard prototype integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
import voluptuous as vol

from .const import (
    CONF_ENTRY_KIND,
    ENTRY_KIND_PROVIDER,
    ENTRY_KIND_YARD,
    PLATFORMS,
)
from .coordinator import ProviderCoordinator, YardCoordinator, runtime
from .panel import async_setup_panel, async_unload_panel

SERVICE_SET_BLADE_HEIGHT = "set_blade_height"


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up integration-level services."""
    data = runtime(hass)

    async def _handle_set_blade_height(call) -> None:
        raise HomeAssistantError(
            "Blade height changes are not supported by the unified provider API yet"
        )

    if not hass.services.has_service("robot_mower_yard", SERVICE_SET_BLADE_HEIGHT):
        hass.services.async_register(
            "robot_mower_yard",
            SERVICE_SET_BLADE_HEIGHT,
            _handle_set_blade_height,
            schema=vol.Schema(
                {
                    vol.Required("device_id"): str,
                    vol.Required("height"): vol.Coerce(int),
                }
            ),
        )
    if not data.get("stop_listener_registered"):
        async def _async_stop_provider_runtimes(_event) -> None:
            for provider in list(runtime(hass)["providers"].values()):
                await provider.async_stop()

        hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STOP,
            _async_stop_provider_runtimes,
        )
        data["stop_listener_registered"] = True
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Robot Mower Yard from a config entry."""
    data = runtime(hass)
    async with data["panel_lock"]:
        if not data.get("panel_loaded"):
            await async_setup_panel(hass)
            data["panel_loaded"] = True

    entry_kind = entry.data[CONF_ENTRY_KIND]

    if entry_kind == ENTRY_KIND_YARD:
        coordinator = YardCoordinator(hass, entry)
        await coordinator.async_config_entry_first_refresh()
        data["yards"][entry.entry_id] = coordinator
        for provider in data["providers"].values():
            if provider.yard_entry_id == entry.entry_id:
                coordinator.attach_provider(provider)
        entry.runtime_data = coordinator
    elif entry_kind == ENTRY_KIND_PROVIDER:
        coordinator = ProviderCoordinator(hass, entry)
        await coordinator.async_load_heatmap()
        await coordinator.async_config_entry_first_refresh()
        await coordinator.async_start_provider()
        data["providers"][entry.entry_id] = coordinator
        yard = data["yards"].get(coordinator.yard_entry_id)
        if yard:
            yard.attach_provider(coordinator)
            await yard.async_request_refresh()
        entry.runtime_data = coordinator
    else:
        return False

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    data = runtime(hass)
    entry_kind = entry.data[CONF_ENTRY_KIND]
    if entry_kind == ENTRY_KIND_YARD:
        data["yards"].pop(entry.entry_id, None)
    elif entry_kind == ENTRY_KIND_PROVIDER:
        provider = data["providers"].pop(entry.entry_id, None)
        if provider:
            await provider.async_stop()
            yard = data["yards"].get(provider.yard_entry_id)
            if yard:
                yard.detach_provider(entry.entry_id)
                await yard.async_request_refresh()
    async with data["panel_lock"]:
        if not data["yards"] and not data["providers"] and data.get("panel_loaded"):
            await async_unload_panel(hass)
            data["panel_loaded"] = False
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options updates."""
    if entry.data[CONF_ENTRY_KIND] == ENTRY_KIND_YARD:
        entry.runtime_data.reload_options()
        await entry.runtime_data.async_request_refresh()
        data = runtime(hass)
        for provider in entry.runtime_data.providers.values():
            provider.async_update_listeners()
            yard = data["yards"].get(provider.yard_entry_id)
            if yard:
                yard.async_update_listeners()
