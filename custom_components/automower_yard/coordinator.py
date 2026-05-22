"""Coordinator for Automower Yard."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
import math
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import AutomowerApiClient, AutomowerApiError
from .const import (
    CONF_APP_KEY,
    CONF_APP_SECRET,
    CONF_CUTTING_HEIGHT_UNITS,
    CONF_ZONES,
    CUTTING_HEIGHT_UNIT_CM,
    CUTTING_HEIGHT_UNIT_IN,
    DEFAULT_ZONES,
    DOMAIN,
)
from .yard import find_zones, parse_zones

_LOGGER = logging.getLogger(__name__)

STUCK_STATES = {"ERROR", "FATAL_ERROR", "STOPPED"}
STUCK_ACTIVITIES = {"STOPPED_IN_GARDEN"}
HEATMAP_STORE_VERSION = 1
HEATMAP_MAX_SAMPLES = 5000
HEATMAP_MAX_AGE = timedelta(days=45)
HEATMAP_MIN_SAMPLE_INTERVAL = timedelta(minutes=2)
HEATMAP_SAVE_DELAY = 5


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
        self._heatmap_save_task: asyncio.Task | None = None
        self._stopped = False
        self._zones: list[dict[str, Any]] = []
        self._heatmap_samples: list[dict[str, Any]] = []
        self._last_heatmap_sample: dict[str, dict[str, Any]] = {}
        self._heatmap_store: Store[list[dict[str, Any]]] = Store(
            hass, HEATMAP_STORE_VERSION, f"{DOMAIN}_heatmap_{entry.entry_id}"
        )
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

    async def async_load_heatmap(self) -> None:
        """Load persisted mower heatmap samples."""
        loaded = await self._heatmap_store.async_load()
        if isinstance(loaded, list):
            self._heatmap_samples = self._pruned_heatmap_samples(loaded)
            self._last_heatmap_sample = {}
            for sample in self._heatmap_samples:
                mower_id = sample.get("mower_id")
                if isinstance(mower_id, str):
                    self._last_heatmap_sample[mower_id] = sample

    @callback
    def reload_options(self) -> None:
        """Reload option-backed yard zones."""
        self._zones = parse_zones(
            self.config_entry.options.get(CONF_ZONES, DEFAULT_ZONES)
        )

    def cutting_height_unit(self, mower_id: str) -> str:
        """Return the preferred cutting height unit for a mower."""
        units = self.config_entry.options.get(CONF_CUTTING_HEIGHT_UNITS, {})
        if not isinstance(units, dict):
            return CUTTING_HEIGHT_UNIT_CM
        unit = units.get(mower_id)
        if unit == CUTTING_HEIGHT_UNIT_IN:
            return CUTTING_HEIGHT_UNIT_IN
        return CUTTING_HEIGHT_UNIT_CM

    async def async_set_cutting_height_unit(self, mower_id: str, unit: str) -> None:
        """Persist the preferred cutting height unit for a mower."""
        options = dict(self.config_entry.options)
        current_units = options.get(CONF_CUTTING_HEIGHT_UNITS, {})
        units = dict(current_units) if isinstance(current_units, dict) else {}

        if unit == CUTTING_HEIGHT_UNIT_CM:
            units.pop(mower_id, None)
        else:
            units[mower_id] = CUTTING_HEIGHT_UNIT_IN

        if units:
            options[CONF_CUTTING_HEIGHT_UNITS] = units
        else:
            options.pop(CONF_CUTTING_HEIGHT_UNITS, None)

        self.hass.config_entries.async_update_entry(
            self.config_entry,
            options=options,
        )
        self.async_update_listeners()

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
        if self._heatmap_save_task and not self._heatmap_save_task.done():
            self._heatmap_save_task.cancel()
            try:
                await self._heatmap_save_task
            except asyncio.CancelledError:
                pass
        await self._async_save_heatmap()

    def heatmap_samples(self, mower_id: str) -> list[dict[str, Any]]:
        """Return heatmap samples for one mower."""
        return [
            sample
            for sample in self._heatmap_samples
            if sample.get("mower_id") == mower_id
        ]

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
        is_stuck = (
            state in STUCK_STATES
            or activity in STUCK_ACTIVITIES
            or bool(error_code)
        )
        attributes["is_stuck"] = is_stuck
        self._maybe_record_heatmap_sample(mower.get("id"), latitude, longitude, is_stuck)
        mower["attributes"] = attributes
        return mower

    def _maybe_record_heatmap_sample(
        self,
        mower_id: str | None,
        latitude: float | None,
        longitude: float | None,
        is_stuck: bool,
    ) -> None:
        """Persist a throttled position/status sample for heatmap rendering."""
        if not mower_id or latitude is None or longitude is None:
            return
        now = dt_util.utcnow()
        last = self._last_heatmap_sample.get(mower_id)
        if last and not _should_record_sample(last, now, latitude, longitude, is_stuck):
            return

        sample = {
            "mower_id": mower_id,
            "ts": now.isoformat(),
            "latitude": latitude,
            "longitude": longitude,
            "stuck": is_stuck,
        }
        self._heatmap_samples.append(sample)
        self._last_heatmap_sample[mower_id] = sample
        self._heatmap_samples = self._pruned_heatmap_samples(self._heatmap_samples)
        self._schedule_heatmap_save()

    def _pruned_heatmap_samples(
        self, samples: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Drop old or malformed heatmap samples."""
        cutoff = dt_util.utcnow() - HEATMAP_MAX_AGE
        pruned = [
            sample
            for sample in samples
            if _sample_datetime(sample) is not None
            and _sample_datetime(sample) >= cutoff
            and _coerce_float(sample.get("latitude")) is not None
            and _coerce_float(sample.get("longitude")) is not None
        ]
        return pruned[-HEATMAP_MAX_SAMPLES:]

    def _schedule_heatmap_save(self) -> None:
        """Debounce heatmap persistence."""
        if self._heatmap_save_task and not self._heatmap_save_task.done():
            return
        self._heatmap_save_task = self.hass.async_create_task(
            self._async_delayed_save_heatmap()
        )

    async def _async_delayed_save_heatmap(self) -> None:
        await asyncio.sleep(HEATMAP_SAVE_DELAY)
        await self._async_save_heatmap()

    async def _async_save_heatmap(self) -> None:
        await self._heatmap_store.async_save(self._heatmap_samples)


def _should_record_sample(
    last: dict[str, Any],
    now,
    latitude: float,
    longitude: float,
    is_stuck: bool,
) -> bool:
    """Return true when a heatmap sample is meaningfully new."""
    last_dt = _sample_datetime(last)
    if last_dt is None:
        return True
    if bool(last.get("stuck")) != is_stuck:
        return True
    if now - last_dt >= HEATMAP_MIN_SAMPLE_INTERVAL:
        return True
    last_lat = _coerce_float(last.get("latitude"))
    last_lon = _coerce_float(last.get("longitude"))
    if last_lat is None or last_lon is None:
        return True
    return _distance_m(last_lat, last_lon, latitude, longitude) >= 3


def _sample_datetime(sample: dict[str, Any]):
    value = sample.get("ts")
    if not isinstance(value, str):
        return None
    return dt_util.parse_datetime(value)


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    reference_lat = math.radians((lat1 + lat2) / 2)
    x = math.radians(lon2 - lon1) * 6371000 * math.cos(reference_lat)
    y = math.radians(lat2 - lat1) * 6371000
    return math.hypot(x, y)


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
