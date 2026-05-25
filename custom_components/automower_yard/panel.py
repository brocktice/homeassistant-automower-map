"""Sidebar panel for the Robot Mower Yard prototype."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from aiohttp import web

from homeassistant.components import frontend, panel_custom
from homeassistant.components.frontend import StaticPathConfig
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .camera import render_yard_map_image
from .const import (
    CONF_BASE_STATION_LATITUDE,
    CONF_BASE_STATION_LONGITUDE,
    CONF_POSITION_OFFSET_EAST_M,
    CONF_POSITION_OFFSET_NORTH_M,
    CONF_PROVIDER_TYPE,
    CONF_ZONES,
    DOMAIN,
    PROVIDER_NAVIMOW,
)
from .coordinator import runtime
from .position import position_dict_with_origin
from .yard import find_zone, find_zones, parse_zones

PANEL_URL_PATH = "robot-mower-yard"
STATIC_URL_PATH = "/robot_mower_yard_static"
API_URL = "/api/robot_mower_yard/overview"
ZONES_API_URL = "/api/robot_mower_yard/zones"
PROVIDER_API_URL = "/api/robot_mower_yard/provider"
MAP_API_URL = "/api/robot_mower_yard/map"
HEATMAP_API_URL = "/api/robot_mower_yard/heatmap"
WWW_DIR = Path(__file__).parent / "www"
MAX_HEATMAP_SAMPLE_DISTANCE_M = 3000.0


async def async_setup_panel(hass: HomeAssistant) -> None:
    """Register the sidebar panel and overview API."""
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL_PATH, str(WWW_DIR), cache_headers=False)]
    )
    hass.http.register_view(RobotMowerYardOverviewView())
    hass.http.register_view(RobotMowerYardZonesView())
    hass.http.register_view(RobotMowerYardProviderView())
    hass.http.register_view(RobotMowerYardMapView())
    hass.http.register_view(RobotMowerYardHeatmapView())
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL_PATH,
        webcomponent_name="robot-mower-yard-panel",
        sidebar_title="Robot Mower Yard",
        sidebar_icon="mdi:robot-mower",
        module_url=f"{STATIC_URL_PATH}/panel.js?v=20260524-mobile-back",
        embed_iframe=False,
        require_admin=True,
    )


async def async_unload_panel(hass: HomeAssistant) -> None:
    """Remove the sidebar panel."""
    frontend.async_remove_panel(hass, PANEL_URL_PATH, warn_if_unknown=False)


class RobotMowerYardOverviewView(HomeAssistantView):
    """Return yard/provider/mower overview state."""

    url = API_URL
    name = "api:robot_mower_yard:overview"
    requires_auth = True

    async def get(self, request):
        """Return current prototype overview data."""
        hass: HomeAssistant = request.app["hass"]
        data = runtime(hass)
        yards = []
        for yard in data["yards"].values():
            zones = parse_zones(yard.config_entry.options.get(CONF_ZONES, "[]"))
            yards.append(
                {
                    "entry_id": yard.config_entry.entry_id,
                    "title": yard.config_entry.title,
                    "mower_count": len(yard.data or {}),
                    "zones_json": yard.config_entry.options.get(CONF_ZONES, "[]"),
                    "providers": [_provider_payload(provider) for provider in yard.providers.values()],
                    "mowers": [
                        {
                            "id": snapshot.stable_id,
                            "name": snapshot.name,
                            "provider": snapshot.provider,
                            "state": snapshot.state,
                            "activity": snapshot.activity,
                            "error_code": snapshot.error_code,
                            "battery_percent": snapshot.battery_percent,
                            "is_problem": snapshot.is_problem,
                            "updated_at": snapshot.updated_at,
                            "latitude": snapshot.latitude,
                            "longitude": snapshot.longitude,
                            "yard_zone": find_zone(
                                snapshot.latitude,
                                snapshot.longitude,
                                zones,
                            ),
                            "yard_zones": find_zones(
                                snapshot.latitude,
                                snapshot.longitude,
                                zones,
                            ),
                            "data_source": _data_source(snapshot.raw),
                        }
                        for snapshot in (yard.data or {}).values()
                    ],
                }
            )
        return self.json({"yards": yards})

    async def post(self, request: web.Request):
        """Save zones for a yard entry."""
        hass: HomeAssistant = request.app["hass"]
        try:
            payload = await request.json()
        except json.JSONDecodeError:
            return self.json_message("Invalid JSON payload", status_code=400)

        yard_entry_id = payload.get("yard_entry_id")
        zones_json = payload.get("zones_json")
        if not isinstance(yard_entry_id, str) or not isinstance(zones_json, str):
            return self.json_message("Expected yard_entry_id and zones_json", status_code=400)

        try:
            zones = json.loads(zones_json)
        except json.JSONDecodeError:
            return self.json_message("Zones JSON is invalid", status_code=400)
        if not isinstance(zones, list):
            return self.json_message("Zones JSON must be a list", status_code=400)

        data = runtime(hass)
        yard = data["yards"].get(yard_entry_id)
        if yard is None:
            return self.json_message("Yard entry not found", status_code=404)

        options = dict(yard.config_entry.options)
        options[CONF_ZONES] = json.dumps(zones, indent=2)
        hass.config_entries.async_update_entry(yard.config_entry, options=options)
        yard.reload_options()
        await yard.async_request_refresh()
        return self.json(
            {
                "yard_entry_id": yard_entry_id,
                "zones_json": options[CONF_ZONES],
            }
        )


class RobotMowerYardZonesView(HomeAssistantView):
    """Load and save zones for the map editor."""

    url = ZONES_API_URL
    name = "api:robot_mower_yard:zones"
    requires_auth = True

    async def get(self, request: web.Request):
        """Return zones and mower locations for one yard."""
        yard = _yard_from_request(request)
        if yard is None:
            return self.json_message("Yard entry not found", status_code=404)
        zones = parse_zones(yard.config_entry.options.get(CONF_ZONES, "[]"))
        return self.json(
            {
                "zones": zones,
                "heatmap_samples": _heatmap_sample_payloads(yard, zones),
                "mowers": [
                    _map_mower_payload(snapshot, yard, zones)
                    for snapshot in (yard.data or {}).values()
                    if _map_mower_payload(snapshot, yard, zones) is not None
                ],
                "base_stations": _base_station_payloads(yard),
            }
        )

    async def post(self, request: web.Request):
        """Save zones from the map editor."""
        yard = _yard_from_request(request)
        if yard is None:
            return self.json_message("Yard entry not found", status_code=404)

        try:
            payload = await request.json()
        except json.JSONDecodeError:
            return self.json_message("Invalid JSON payload", status_code=400)
        zones = payload.get("zones")
        if not isinstance(zones, list):
            return self.json_message("Expected zones list", status_code=400)

        options = dict(yard.config_entry.options)
        options[CONF_ZONES] = json.dumps(zones, indent=2)
        hass: HomeAssistant = request.app["hass"]
        hass.config_entries.async_update_entry(yard.config_entry, options=options)
        yard.reload_options()
        await yard.async_request_refresh()
        return self.json({"zones": zones})


class RobotMowerYardProviderView(HomeAssistantView):
    """Save provider settings from the sidebar panel."""

    url = PROVIDER_API_URL
    name = "api:robot_mower_yard:provider"
    requires_auth = True

    async def post(self, request: web.Request):
        """Update provider options."""
        hass: HomeAssistant = request.app["hass"]
        try:
            payload = await request.json()
        except json.JSONDecodeError:
            return self.json_message("Invalid JSON payload", status_code=400)

        provider_entry_id = payload.get("provider_entry_id")
        if not isinstance(provider_entry_id, str):
            return self.json_message("Expected provider_entry_id", status_code=400)

        data = runtime(hass)
        provider = data["providers"].get(provider_entry_id)
        if provider is None:
            return self.json_message("Provider entry not found", status_code=404)
        if provider.config_entry.data.get(CONF_PROVIDER_TYPE) != PROVIDER_NAVIMOW:
            return self.json_message("Provider settings are not supported", status_code=400)

        latitude = _optional_float(payload.get(CONF_BASE_STATION_LATITUDE))
        longitude = _optional_float(payload.get(CONF_BASE_STATION_LONGITUDE))
        offset_north = _optional_float(payload.get(CONF_POSITION_OFFSET_NORTH_M))
        offset_east = _optional_float(payload.get(CONF_POSITION_OFFSET_EAST_M))
        if (
            latitude == "invalid"
            or longitude == "invalid"
            or offset_north == "invalid"
            or offset_east == "invalid"
        ):
            return self.json_message("Provider settings must be numbers", status_code=400)

        options = dict(provider.config_entry.options)
        _set_optional_option(options, CONF_BASE_STATION_LATITUDE, latitude)
        _set_optional_option(options, CONF_BASE_STATION_LONGITUDE, longitude)
        _set_optional_option(options, CONF_POSITION_OFFSET_NORTH_M, offset_north)
        _set_optional_option(options, CONF_POSITION_OFFSET_EAST_M, offset_east)

        hass.config_entries.async_update_entry(provider.config_entry, options=options)
        await provider.async_request_refresh()
        yard = data["yards"].get(provider.yard_entry_id)
        if yard is not None:
            await yard.async_request_refresh()

        return self.json({"provider": _provider_payload(provider)})


class RobotMowerYardMapView(HomeAssistantView):
    """Render a yard overview map image."""

    url = MAP_API_URL
    name = "api:robot_mower_yard:map"
    requires_auth = True

    async def get(self, request: web.Request):
        """Return a PNG yard map."""
        yard = _yard_from_request(request)
        if yard is None:
            return self.json_message("Yard entry not found", status_code=404)
        image = await request.app["hass"].async_add_executor_job(
            render_yard_map_image,
            yard.config_entry.title,
            yard.zones,
            list((yard.data or {}).values()),
            [],
        )
        return web.Response(body=image, content_type="image/png")


class RobotMowerYardHeatmapView(HomeAssistantView):
    """Render a yard heatmap image."""

    url = HEATMAP_API_URL
    name = "api:robot_mower_yard:heatmap"
    requires_auth = True

    async def get(self, request: web.Request):
        """Return a PNG yard heatmap."""
        yard = _yard_from_request(request)
        if yard is None:
            return self.json_message("Yard entry not found", status_code=404)
        image = await request.app["hass"].async_add_executor_job(
            render_yard_map_image,
            f"{yard.config_entry.title} Heatmap",
            yard.zones,
            list((yard.data or {}).values()),
            _heatmap_sample_payloads(yard, yard.zones),
        )
        return web.Response(body=image, content_type="image/png")


def _yard_from_request(request: web.Request):
    hass: HomeAssistant = request.app["hass"]
    yard_entry_id = request.query.get("yard_entry_id")
    data = runtime(hass)
    if yard_entry_id:
        return data["yards"].get(yard_entry_id)
    return next(iter(data["yards"].values()), None)


def _provider_payload(provider) -> dict:
    return {
        "entry_id": provider.config_entry.entry_id,
        "title": provider.config_entry.title,
        "provider_type": provider.config_entry.data.get(CONF_PROVIDER_TYPE),
        "options": {
            CONF_BASE_STATION_LATITUDE: provider.config_entry.options.get(
                CONF_BASE_STATION_LATITUDE
            ),
            CONF_BASE_STATION_LONGITUDE: provider.config_entry.options.get(
                CONF_BASE_STATION_LONGITUDE
            ),
            CONF_POSITION_OFFSET_NORTH_M: provider.config_entry.options.get(
                CONF_POSITION_OFFSET_NORTH_M
            ),
            CONF_POSITION_OFFSET_EAST_M: provider.config_entry.options.get(
                CONF_POSITION_OFFSET_EAST_M
            ),
        },
    }


def _optional_float(value) -> float | None | str:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return "invalid"


def _set_optional_option(options: dict, key: str, value: float | None) -> None:
    if value is None:
        options.pop(key, None)
    else:
        options[key] = value


def _data_source(raw: dict) -> str | None:
    meta = raw.get("meta") if isinstance(raw, dict) else None
    if not isinstance(meta, dict):
        return None
    value = meta.get("last_data_source")
    return str(value) if value else None


def _heatmap_sample_payloads(yard, zones: list[dict]) -> list[dict]:
    reference_points = _yard_reference_points(yard, zones)
    samples = []
    for sample in yard.heatmap_samples():
        latitude = _optional_float(sample.get("latitude"))
        longitude = _optional_float(sample.get("longitude"))
        if not _valid_coordinate(latitude, longitude):
            continue
        calibrated = _calibrated_heatmap_sample_position(yard, sample, latitude, longitude)
        if calibrated is not None:
            latitude, longitude = calibrated
        if reference_points and min(
            _distance_m(latitude, longitude, ref_lat, ref_lon)
            for ref_lat, ref_lon in reference_points
        ) > MAX_HEATMAP_SAMPLE_DISTANCE_M:
            continue
        samples.append(
            {
                "latitude": latitude,
                "longitude": longitude,
                "stuck": bool(sample.get("stuck")),
            }
        )
    return samples


def _calibrated_heatmap_sample_position(
    yard,
    sample: dict,
    latitude: float,
    longitude: float,
) -> tuple[float, float] | None:
    provider = _sample_provider(yard, sample)
    if provider is None:
        return None
    if provider.config_entry.data.get(CONF_PROVIDER_TYPE) != PROVIDER_NAVIMOW:
        return None
    calibrated = _position_with_provider_offset_delta(provider, sample, latitude, longitude)
    if calibrated is None:
        return None
    return calibrated["lat"], calibrated["lng"]


def _sample_provider(yard, sample: dict):
    provider_entry_id = sample.get("provider_entry_id")
    if isinstance(provider_entry_id, str) and provider_entry_id in yard.providers:
        return yard.providers[provider_entry_id]

    mower_id = sample.get("mower_id")
    if isinstance(mower_id, str):
        for provider in yard.providers.values():
            if provider.data and mower_id in provider.data:
                return provider

    provider_type = sample.get("provider")
    matching = [
        provider
        for provider in yard.providers.values()
        if provider.config_entry.data.get(CONF_PROVIDER_TYPE) == provider_type
    ]
    if len(matching) == 1:
        return matching[0]
    return None


def _base_station_payloads(yard) -> list[dict]:
    payloads = []
    for provider in yard.providers.values():
        payloads.extend(_provider_base_station_payload(provider))
    return payloads


def _yard_reference_points(yard, zones: list[dict]) -> list[tuple[float, float]]:
    points = _zone_reference_points(zones)
    for provider in yard.providers.values():
        for base_station in _provider_base_station_payload(provider):
            points.append((base_station["latitude"], base_station["longitude"]))
    if points:
        return points

    mower_points = []
    for snapshot in (yard.data or {}).values():
        if _valid_coordinate(snapshot.latitude, snapshot.longitude):
            mower_points.append((snapshot.latitude, snapshot.longitude))
    return mower_points


def _provider_base_station_payload(provider) -> list[dict]:
    if provider.config_entry.data.get(CONF_PROVIDER_TYPE) != PROVIDER_NAVIMOW:
        return []
    latitude = _optional_float(
        provider.config_entry.options.get(CONF_BASE_STATION_LATITUDE)
    )
    longitude = _optional_float(
        provider.config_entry.options.get(CONF_BASE_STATION_LONGITUDE)
    )
    if not _valid_coordinate(latitude, longitude):
        return []
    offset_north = _optional_float(
        provider.config_entry.options.get(CONF_POSITION_OFFSET_NORTH_M)
    )
    offset_east = _optional_float(
        provider.config_entry.options.get(CONF_POSITION_OFFSET_EAST_M)
    )
    calibrated = _position_with_offset(
        latitude,
        longitude,
        offset_north if isinstance(offset_north, float) else None,
        offset_east if isinstance(offset_east, float) else None,
    )
    if calibrated is not None:
        latitude = calibrated["lat"]
        longitude = calibrated["lng"]
    return [
        {
            "id": provider.config_entry.entry_id,
            "name": provider.config_entry.title,
            "provider": PROVIDER_NAVIMOW,
            "latitude": latitude,
            "longitude": longitude,
        }
    ]


def _position_with_provider_offset(
    provider,
    latitude: float,
    longitude: float,
) -> dict[str, float] | None:
    offset_north = _optional_float(
        provider.config_entry.options.get(CONF_POSITION_OFFSET_NORTH_M)
    )
    offset_east = _optional_float(
        provider.config_entry.options.get(CONF_POSITION_OFFSET_EAST_M)
    )
    return _position_with_offset(
        latitude,
        longitude,
        offset_north if isinstance(offset_north, float) else None,
        offset_east if isinstance(offset_east, float) else None,
    )


def _position_with_provider_offset_delta(
    provider,
    sample: dict,
    latitude: float,
    longitude: float,
) -> dict[str, float] | None:
    current_north = _optional_float(
        provider.config_entry.options.get(CONF_POSITION_OFFSET_NORTH_M)
    )
    current_east = _optional_float(
        provider.config_entry.options.get(CONF_POSITION_OFFSET_EAST_M)
    )
    sample_north = _optional_float(sample.get(CONF_POSITION_OFFSET_NORTH_M))
    sample_east = _optional_float(sample.get(CONF_POSITION_OFFSET_EAST_M))
    north_delta = (current_north if isinstance(current_north, float) else 0.0) - (
        sample_north if isinstance(sample_north, float) else 0.0
    )
    east_delta = (current_east if isinstance(current_east, float) else 0.0) - (
        sample_east if isinstance(sample_east, float) else 0.0
    )
    return _position_with_offset(latitude, longitude, north_delta, east_delta)


def _position_with_offset(
    latitude: float,
    longitude: float,
    offset_north: float | None,
    offset_east: float | None,
) -> dict[str, float] | None:
    return position_dict_with_origin(
        {"lat": latitude, "lng": longitude},
        None,
        None,
        offset_north,
        offset_east,
    )


def _zone_reference_points(zones: list[dict]) -> list[tuple[float, float]]:
    points = []
    for zone in zones:
        center = zone.get("center")
        if (
            isinstance(center, list)
            and len(center) == 2
            and _valid_coordinate(_optional_float(center[0]), _optional_float(center[1]))
        ):
            points.append((float(center[0]), float(center[1])))
        polygon = zone.get("polygon")
        if not isinstance(polygon, list):
            continue
        for point in polygon:
            if (
                isinstance(point, list)
                and len(point) == 2
                and _valid_coordinate(_optional_float(point[0]), _optional_float(point[1]))
            ):
                points.append((float(point[0]), float(point[1])))
    return points


def _valid_coordinate(latitude: Any, longitude: Any) -> bool:
    return (
        isinstance(latitude, float)
        and isinstance(longitude, float)
        and math.isfinite(latitude)
        and math.isfinite(longitude)
        and -90 <= latitude <= 90
        and -180 <= longitude <= 180
        and (latitude != 0 or longitude != 0)
    )


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius_m = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return earth_radius_m * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _map_mower_payload(snapshot, yard, zones: list[dict]) -> dict | None:
    latitude = snapshot.latitude
    longitude = snapshot.longitude
    location_source = "reported"
    if latitude is None or longitude is None:
        fallback = _fallback_location(snapshot, yard)
        if fallback is None:
            return None
        latitude, longitude = fallback
        location_source = "base_station"

    return {
        "id": snapshot.stable_id,
        "name": snapshot.name or snapshot.stable_id,
        "provider": snapshot.provider,
        "latitude": latitude,
        "longitude": longitude,
        "location_source": location_source,
        "yard_zone": find_zone(latitude, longitude, zones),
        "yard_zones": find_zones(latitude, longitude, zones),
        "is_problem": snapshot.is_problem,
        "state": snapshot.state,
    }


def _fallback_location(snapshot, yard) -> tuple[float, float] | None:
    if snapshot.provider != PROVIDER_NAVIMOW:
        return None
    state = (snapshot.state or snapshot.activity or "").lower()
    if state not in {"idle", "docked", "charging", "returning", "unknown"}:
        return None
    for provider in yard.providers.values():
        if provider.config_entry.data.get(CONF_PROVIDER_TYPE) != PROVIDER_NAVIMOW:
            continue
        latitude = _optional_float(
            provider.config_entry.options.get(CONF_BASE_STATION_LATITUDE)
        )
        longitude = _optional_float(
            provider.config_entry.options.get(CONF_BASE_STATION_LONGITUDE)
        )
        if isinstance(latitude, float) and isinstance(longitude, float):
            return latitude, longitude
    return None
