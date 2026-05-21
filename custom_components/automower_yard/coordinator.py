"""Coordinator for Automower Yard."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import AutomowerApiClient, AutomowerApiError
from .const import CONF_APP_KEY, CONF_APP_SECRET, CONF_ZONES, DEFAULT_ZONES, DOMAIN
from .yard import find_zones, parse_zones

_LOGGER = logging.getLogger(__name__)

STUCK_STATES = {"ERROR", "FATAL_ERROR", "STOPPED"}
STUCK_ACTIVITIES = {"STOPPED_IN_GARDEN"}


class AutomowerYardCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Holds mower state and manages websocket updates."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.api = AutomowerApiClient(
            hass,
            entry.data[CONF_APP_KEY],
            entry.data[CONF_APP_SECRET],
        )
        self._ws_task: asyncio.Task | None = None
        self._stopped = False
        self._zones: list[dict[str, Any]] = []
        self.websocket_connected = False
        self.last_websocket_event: str | None = None
        self.last_position_event: str | None = None
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=15),
        )
        self.reload_options()

    @callback
    def reload_options(self) -> None:
        """Reload option-backed yard zones."""
        self._zones = parse_zones(
            self.config_entry.options.get(CONF_ZONES, DEFAULT_ZONES)
        )

    @property
    def zone_names(self) -> list[str]:
        """Return configured yard zone names."""
        return [str(zone["name"]) for zone in self._zones if zone.get("name")]

    @property
    def zones(self) -> list[dict[str, Any]]:
        """Return configured yard zones."""
        return list(self._zones)

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Poll all mower state."""
        try:
            mowers = await self.api.async_list_mowers()
        except AutomowerApiError as err:
            raise UpdateFailed(str(err)) from err
        return {mower["id"]: self._normalize_mower(mower) for mower in mowers}

    async def async_start_websocket(self) -> None:
        """Start websocket listener."""
        if self._ws_task:
            return
        self._stopped = False
        self._ws_task = self.hass.loop.create_task(self._websocket_loop())

    async def async_stop(self) -> None:
        """Stop websocket listener."""
        self._stopped = True
        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
            self._ws_task = None

    async def _websocket_loop(self) -> None:
        """Reconnect websocket forever while integration is loaded."""
        delay = 1
        while not self._stopped:
            try:
                self.websocket_connected = True
                async for event in self.api.listen_events():
                    self.last_websocket_event = dt_util.utcnow().isoformat()
                    self._merge_event(event)
                    self.async_set_updated_data(self.data or {})
                delay = 1
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001
                self.websocket_connected = False
                _LOGGER.debug("Automower websocket disconnected: %s", err)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60)
            finally:
                if not self._stopped:
                    self.websocket_connected = False

    @callback
    def _merge_event(self, event: dict[str, Any]) -> None:
        """Merge a websocket event into coordinator state."""
        mower_id = event.get("id")
        if not mower_id:
            return

        data = dict(self.data or {})
        mower = dict(data.get(mower_id, {"id": mower_id, "attributes": {}}))
        attributes = dict(mower.get("attributes") or {})
        event_attributes = event.get("attributes") or {}
        event_type = event.get("type")

        if event_type == "position-event-v2":
            position = event_attributes.get("position")
            if isinstance(position, dict):
                self.last_position_event = dt_util.utcnow().isoformat()
                positions = list(attributes.get("positions") or [])
                attributes["positions"] = [position, *positions[:49]]
        elif event_type == "mower-event-v2":
            if isinstance(event_attributes.get("mower"), dict):
                attributes["mower"] = event_attributes["mower"]
        elif event_type == "battery-event-v2":
            if isinstance(event_attributes.get("battery"), dict):
                attributes["battery"] = event_attributes["battery"]
        elif event_type == "planner-event-v2":
            if isinstance(event_attributes.get("planner"), dict):
                attributes["planner"] = event_attributes["planner"]
        else:
            return

        mower["attributes"] = attributes
        data[mower_id] = self._normalize_mower(mower)
        self.data = data

    def _normalize_mower(self, mower: dict[str, Any]) -> dict[str, Any]:
        """Add derived values used by entities."""
        attributes = dict(mower.get("attributes") or {})
        position = _latest_position(attributes)
        latitude = _coerce_float(position.get("latitude")) if position else None
        longitude = _coerce_float(position.get("longitude")) if position else None
        mower_status = attributes.get("mower") or {}
        state = mower_status.get("state")
        activity = mower_status.get("activity")
        error_code = mower_status.get("errorCode")

        yard_zones = find_zones(latitude, longitude, self._zones)
        attributes["yard_zones"] = yard_zones
        attributes["yard_zone"] = " + ".join(yard_zones) if yard_zones else None
        attributes["is_stuck"] = (
            state in STUCK_STATES
            or activity in STUCK_ACTIVITIES
            or bool(error_code)
        )
        mower["attributes"] = attributes
        return mower


def _latest_position(attributes: dict[str, Any]) -> dict[str, Any] | None:
    positions = attributes.get("positions")
    if isinstance(positions, list) and positions and isinstance(positions[0], dict):
        return positions[0]
    return None


def _coerce_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
