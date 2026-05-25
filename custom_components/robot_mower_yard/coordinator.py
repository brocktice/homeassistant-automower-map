"""Coordinators for the Robot Mower Yard prototype."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import timedelta
import logging
import math
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_PROVIDER_TYPE,
    CONF_YARD_ENTRY_ID,
    CONF_ZONES,
    CONF_CUTTING_HEIGHT_UNITS,
    CONF_POSITION_OFFSET_EAST_M,
    CONF_POSITION_OFFSET_NORTH_M,
    CUTTING_HEIGHT_UNIT_CM,
    CUTTING_HEIGHT_UNIT_IN,
    DEFAULT_ZONES,
    DOMAIN,
)
from .models import MowerSnapshot
from .providers import PROVIDERS
from .yard import parse_zones

_LOGGER = logging.getLogger(__name__)

HEATMAP_STORE_VERSION = 1
HEATMAP_MAX_SAMPLES = 5000
HEATMAP_MAX_AGE = timedelta(days=45)
HEATMAP_MIN_SAMPLE_INTERVAL = timedelta(minutes=2)
HEATMAP_SAVE_DELAY = 5


class YardCoordinator(DataUpdateCoordinator[dict[str, MowerSnapshot]]):
    """Aggregate mower snapshots for one yard."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(seconds=30),
        )
        self.providers: dict[str, ProviderCoordinator] = {}
        self.reload_options()

    def reload_options(self) -> None:
        """Reload yard options."""
        self.zones_json = self.config_entry.options.get(CONF_ZONES, DEFAULT_ZONES)
        self.zones = parse_zones(self.zones_json)
        self.zone_names = [str(zone["name"]) for zone in self.zones if zone.get("name")]

    def attach_provider(self, provider: "ProviderCoordinator") -> None:
        """Attach a provider coordinator to this yard."""
        self.providers[provider.config_entry.entry_id] = provider

    def detach_provider(self, entry_id: str) -> None:
        """Detach a provider coordinator from this yard."""
        self.providers.pop(entry_id, None)

    def heatmap_samples(self) -> list[dict[str, Any]]:
        """Return heatmap samples from all attached providers."""
        samples: list[dict[str, Any]] = []
        for provider in self.providers.values():
            samples.extend(provider.heatmap_samples())
        return samples

    async def _async_update_data(self) -> dict[str, MowerSnapshot]:
        """Aggregate provider mower snapshots."""
        snapshots: dict[str, MowerSnapshot] = {}
        for provider in self.providers.values():
            for snapshot in provider.data.values() if provider.data else []:
                snapshots[snapshot.stable_id] = snapshot
        return snapshots


class ProviderCoordinator(DataUpdateCoordinator[dict[str, MowerSnapshot]]):
    """Poll one provider adapter."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the provider coordinator."""
        provider_type = entry.data[CONF_PROVIDER_TYPE]
        provider_class = PROVIDERS[provider_type]
        self.provider = provider_class(hass, entry)
        self._heatmap_save_task: asyncio.Task | None = None
        self._heatmap_samples: list[dict[str, Any]] = []
        self._last_heatmap_sample: dict[str, dict[str, Any]] = {}
        self._heatmap_store: Store[list[dict[str, Any]]] = Store(
            hass,
            HEATMAP_STORE_VERSION,
            f"{DOMAIN}_heatmap_{entry.entry_id}",
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{provider_type}_{entry.entry_id}",
            update_interval=timedelta(seconds=30),
        )

    @property
    def yard_entry_id(self) -> str:
        """Return the yard entry id this provider belongs to."""
        return self.config_entry.data[CONF_YARD_ENTRY_ID]

    async def _async_update_data(self) -> dict[str, MowerSnapshot]:
        """Poll provider data."""
        updated_at = dt_util.utcnow().isoformat()
        previous_data = self.data or {}
        snapshots = {
            snapshot.stable_id: self._snapshot_with_previous_position(
                replace(snapshot, updated_at=updated_at),
                previous_data.get(snapshot.stable_id),
            )
            for snapshot in await self.provider.async_get_mowers()
        }
        for snapshot in snapshots.values():
            self._maybe_record_heatmap_sample(snapshot)
        return snapshots

    async def async_load_heatmap(self) -> None:
        """Load persisted heatmap samples."""
        loaded = await self._heatmap_store.async_load()
        if isinstance(loaded, list):
            self._heatmap_samples = self._pruned_heatmap_samples(loaded)
            self._last_heatmap_sample = {
                str(sample["mower_id"]): sample
                for sample in self._heatmap_samples
                if isinstance(sample.get("mower_id"), str)
            }

    async def async_start_provider(self) -> None:
        """Start provider push updates if supported."""
        await self.provider.async_start(self._async_handle_provider_snapshots)

    async def async_stop(self) -> None:
        """Persist pending provider state before unload."""
        if hasattr(self.provider, "async_stop"):
            await self.provider.async_stop()
        if self._heatmap_save_task and not self._heatmap_save_task.done():
            self._heatmap_save_task.cancel()
            try:
                await self._heatmap_save_task
            except asyncio.CancelledError:
                pass
        await self._async_save_heatmap()

    async def _async_handle_provider_snapshots(
        self, snapshots: list[MowerSnapshot]
    ) -> None:
        """Merge pushed provider snapshots."""
        data = dict(self.data or {})
        updated_at = dt_util.utcnow().isoformat()
        for snapshot in snapshots:
            snapshot = self._snapshot_with_previous_position(
                replace(snapshot, updated_at=updated_at),
                data.get(snapshot.stable_id),
            )
            data[snapshot.stable_id] = snapshot
            self._maybe_record_heatmap_sample(snapshot)
        self.async_set_updated_data(data)
        yard = runtime(self.hass)["yards"].get(self.yard_entry_id)
        if yard is not None:
            await yard.async_request_refresh()

    def heatmap_samples(self, mower_id: str | None = None) -> list[dict[str, Any]]:
        """Return heatmap samples for one mower or the full provider."""
        if mower_id is None:
            return list(self._heatmap_samples)
        return [
            sample
            for sample in self._heatmap_samples
            if sample.get("mower_id") == mower_id
        ]

    def _snapshot_with_previous_position(
        self,
        snapshot: MowerSnapshot,
        previous: MowerSnapshot | None,
    ) -> MowerSnapshot:
        """Keep a mower on the map when a later provider update omits coordinates."""
        if (
            snapshot.latitude is not None
            and snapshot.longitude is not None
        ) or previous is None:
            return snapshot
        if previous.latitude is None or previous.longitude is None:
            return snapshot
        return replace(
            snapshot,
            latitude=previous.latitude,
            longitude=previous.longitude,
        )

    def cutting_height_unit(self, mower_id: str) -> str:
        """Return preferred cutting height unit for a mower."""
        units = self.config_entry.options.get(CONF_CUTTING_HEIGHT_UNITS, {})
        if not isinstance(units, dict):
            return CUTTING_HEIGHT_UNIT_CM
        if units.get(mower_id) == CUTTING_HEIGHT_UNIT_IN:
            return CUTTING_HEIGHT_UNIT_IN
        return CUTTING_HEIGHT_UNIT_CM

    async def async_set_cutting_height_unit(self, mower_id: str, unit: str) -> None:
        """Persist preferred cutting height unit for a mower."""
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
        self.hass.config_entries.async_update_entry(self.config_entry, options=options)
        self.async_update_listeners()

    def _maybe_record_heatmap_sample(self, snapshot: MowerSnapshot) -> None:
        if snapshot.latitude is None or snapshot.longitude is None:
            return
        now = dt_util.utcnow()
        last = self._last_heatmap_sample.get(snapshot.stable_id)
        if last and not _should_record_sample(
            last,
            now,
            snapshot.latitude,
            snapshot.longitude,
            snapshot.is_problem,
        ):
            return
        sample = {
            "mower_id": snapshot.stable_id,
            "provider": snapshot.provider,
            "provider_entry_id": self.config_entry.entry_id,
            "ts": now.isoformat(),
            "latitude": snapshot.latitude,
            "longitude": snapshot.longitude,
            "stuck": snapshot.is_problem,
            "state": snapshot.state,
            "error": snapshot.error_code,
            "position_offset_north_m": self.config_entry.options.get(
                CONF_POSITION_OFFSET_NORTH_M
            ),
            "position_offset_east_m": self.config_entry.options.get(
                CONF_POSITION_OFFSET_EAST_M
            ),
        }
        self._heatmap_samples.append(sample)
        self._last_heatmap_sample[snapshot.stable_id] = sample
        self._heatmap_samples = self._pruned_heatmap_samples(self._heatmap_samples)
        self._schedule_heatmap_save()

    def _pruned_heatmap_samples(
        self, samples: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
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


def runtime(hass: HomeAssistant) -> dict[str, dict[str, Any]]:
    """Return shared runtime storage."""
    return hass.data.setdefault(
        DOMAIN,
        {
            "yards": {},
            "providers": {},
            "panel_loaded": False,
            "panel_lock": asyncio.Lock(),
        },
    )


def _should_record_sample(
    last: dict[str, Any],
    now,
    latitude: float,
    longitude: float,
    is_problem: bool,
) -> bool:
    last_dt = _sample_datetime(last)
    if last_dt is None:
        return True
    if bool(last.get("stuck")) != is_problem:
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


def _coerce_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
