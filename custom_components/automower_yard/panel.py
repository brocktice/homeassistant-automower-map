"""Home Assistant panel and HTTP API for Automower Yard zone editing."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from aiohttp import web

from homeassistant.components import frontend, panel_custom
from homeassistant.components.frontend import StaticPathConfig
from homeassistant.components.http import HomeAssistantView
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_ZONES, DOMAIN

_LOGGER = logging.getLogger(__name__)

PANEL_URL_PATH = "automower-yard"
STATIC_URL_PATH = "/automower_yard_static"
API_URL = "/api/automower_yard/zones"
WWW_DIR = Path(__file__).parent / "www"


async def async_setup_panel(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register the zone editor panel and API."""
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL_PATH, str(WWW_DIR), cache_headers=False)]
    )
    hass.http.register_view(AutomowerYardZonesView(entry.entry_id))

    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL_PATH,
        webcomponent_name="automower-yard-panel",
        sidebar_title="Automower Yard",
        sidebar_icon="mdi:robot-mower",
        module_url=f"{STATIC_URL_PATH}/panel.js",
        embed_iframe=False,
        require_admin=True,
        config_panel_domain=DOMAIN,
        config={
            "url": f"{STATIC_URL_PATH}/zone_editor.html?ha=1",
        },
    )


async def async_unload_panel(hass: HomeAssistant) -> None:
    """Remove the zone editor panel."""
    frontend.async_remove_panel(hass, PANEL_URL_PATH, warn_if_unknown=False)


class AutomowerYardZonesView(HomeAssistantView):
    """Load and save Automower Yard zone editor state."""

    url = API_URL
    name = "api:automower_yard:zones"
    requires_auth = True

    def __init__(self, entry_id: str) -> None:
        """Initialize the view."""
        self._entry_id = entry_id

    async def get(self, request: web.Request) -> web.Response:
        """Return saved zones and current mower locations."""
        hass: HomeAssistant = request.app["hass"]
        entry = hass.config_entries.async_get_entry(self._entry_id)
        if entry is None:
            return self.json_message("Automower Yard entry not found", status_code=404)

        coordinator = entry.runtime_data
        zones = _parse_zones(entry.options.get(CONF_ZONES, "[]"))
        mowers = []
        for mower_id, mower in (coordinator.data or {}).items():
            attrs = mower.get("attributes") or {}
            system = attrs.get("system") or {}
            positions = attrs.get("positions") or []
            latest = positions[0] if positions else {}
            if latest.get("latitude") is None or latest.get("longitude") is None:
                continue
            mowers.append(
                {
                    "id": mower_id,
                    "name": system.get("name") or mower_id,
                    "latitude": float(latest["latitude"]),
                    "longitude": float(latest["longitude"]),
                    "yard_zone": attrs.get("yard_zone"),
                    "yard_zones": attrs.get("yard_zones") or [],
                }
            )

        return self.json({"zones": zones, "mowers": mowers})

    async def post(self, request: web.Request) -> web.Response:
        """Save zones to the config entry options."""
        hass: HomeAssistant = request.app["hass"]
        entry = hass.config_entries.async_get_entry(self._entry_id)
        if entry is None:
            return self.json_message("Automower Yard entry not found", status_code=404)

        try:
            payload = await request.json()
        except json.JSONDecodeError:
            return self.json_message("Invalid JSON", status_code=400)

        zones = payload.get("zones")
        if not isinstance(zones, list):
            return self.json_message("Expected zones list", status_code=400)

        clean_zones = _clean_zones(zones)
        options = dict(entry.options)
        options[CONF_ZONES] = json.dumps(clean_zones, indent=2)
        hass.config_entries.async_update_entry(entry, options=options)
        _LOGGER.info("Saved %s Automower Yard zones", len(clean_zones))
        await coordinator_refresh(entry)
        return self.json({"zones": clean_zones})


async def coordinator_refresh(entry: ConfigEntry) -> None:
    """Refresh coordinator state after saving options."""
    if entry.runtime_data:
        entry.runtime_data.reload_options()
        await entry.runtime_data.async_request_refresh()


def _parse_zones(raw: str) -> list[dict[str, Any]]:
    try:
        zones = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(zones, list):
        return []
    return _clean_zones(zones)


def _clean_zones(zones: list[Any]) -> list[dict[str, Any]]:
    clean: list[dict[str, Any]] = []
    for zone in zones:
        if not isinstance(zone, dict) or not zone.get("name"):
            continue
        clean_zone: dict[str, Any] = {"name": str(zone["name"])}
        if _valid_center(zone):
            clean_zone["center"] = [
                float(zone["center"][0]),
                float(zone["center"][1]),
            ]
            clean_zone["radius_m"] = float(zone["radius_m"])
            clean.append(clean_zone)
            continue
        polygon = zone.get("polygon")
        if isinstance(polygon, list) and len(polygon) >= 3:
            points = []
            for point in polygon:
                if not isinstance(point, list) or len(point) != 2:
                    points = []
                    break
                points.append([float(point[0]), float(point[1])])
            if points:
                clean_zone["polygon"] = points
                clean.append(clean_zone)
    return clean


def _valid_center(zone: dict[str, Any]) -> bool:
    center = zone.get("center")
    return (
        isinstance(center, list)
        and len(center) == 2
        and isinstance(zone.get("radius_m"), int | float)
    )
