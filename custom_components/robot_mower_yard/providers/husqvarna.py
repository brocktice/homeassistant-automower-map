"""Husqvarna Automower provider."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from typing import Any

import aiohttp

from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from ..const import (
    CONF_APP_KEY,
    CONF_APP_SECRET,
    HUSQVARNA_AUTH_URL,
    HUSQVARNA_REST_BASE_URL,
    HUSQVARNA_WS_URL,
)
from ..models import MowerSnapshot
from .base import MowerProvider, SnapshotCallback


class HusqvarnaProvider(MowerProvider):
    """Fetch live mower snapshots from Husqvarna Automower Connect."""

    def __init__(self, hass, entry) -> None:
        """Initialize the provider."""
        super().__init__(hass, entry)
        self._session = async_get_clientsession(hass)
        self._token: _Token | None = None
        self._mowers: dict[str, dict[str, Any]] = {}
        self._ws_task: asyncio.Task | None = None
        self._stopped = False

    async def async_get_mowers(self) -> list[MowerSnapshot]:
        """Return live Husqvarna mower snapshots."""
        payload = await self._request("GET", "/mowers")
        self._mowers = {
            str(mower.get("id")): mower
            for mower in payload.get("data") or []
            if mower.get("id") is not None
        }
        return [_snapshot(mower) for mower in self._mowers.values()]

    async def async_start(self, callback: SnapshotCallback) -> None:
        """Start websocket updates."""
        if self._ws_task is not None:
            return
        self._stopped = False
        self._ws_task = self.hass.loop.create_task(self._websocket_loop(callback))

    async def async_stop(self) -> None:
        """Stop websocket updates."""
        self._stopped = True
        if self._ws_task is None:
            return
        self._ws_task.cancel()
        try:
            await self._ws_task
        except asyncio.CancelledError:
            pass
        self._ws_task = None

    async def _get_token(self) -> str:
        if self._token and self._token.is_valid:
            return self._token.access_token

        data = {
            "grant_type": "client_credentials",
            "client_id": self.entry.data[CONF_APP_KEY],
            "client_secret": self.entry.data[CONF_APP_SECRET],
        }
        async with self._session.post(HUSQVARNA_AUTH_URL, data=data) as response:
            payload = await _read_json(response)
            if response.status not in (200, 201):
                raise RuntimeError(f"Husqvarna authentication failed: {response.status} {payload}")

        self._token = _Token(
            access_token=payload["access_token"],
            expires_at=dt_util.utcnow()
            + timedelta(seconds=int(payload.get("expires_in", 3600))),
        )
        return self._token.access_token

    async def _request(self, method: str, path: str) -> dict[str, Any]:
        token = await self._get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Authorization-Provider": "husqvarna",
            "X-Api-Key": self.entry.data[CONF_APP_KEY],
            "Accept": "application/vnd.api+json",
        }
        async with self._session.request(
            method,
            f"{HUSQVARNA_REST_BASE_URL}{path}",
            headers=headers,
        ) as response:
            payload = await _read_json(response)
            if response.status >= 400:
                if response.status in (401, 403):
                    self._token = None
                raise RuntimeError(f"Husqvarna API failed: {response.status} {payload}")
            return payload

    async def _websocket_loop(self, callback: SnapshotCallback) -> None:
        delay = 1
        while not self._stopped:
            try:
                async for event in self._listen_events():
                    snapshot = self._merge_event(event)
                    if snapshot is not None:
                        await callback([snapshot])
                delay = 1
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60)

    async def _listen_events(self) -> AsyncIterator[dict[str, Any]]:
        token = await self._get_token()
        async with self._session.ws_connect(
            HUSQVARNA_WS_URL,
            headers={"Authorization": f"Bearer {token}"},
            heartbeat=60,
        ) as ws:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    if not msg.data or msg.data == "ping":
                        continue
                    try:
                        yield json.loads(msg.data)
                    except json.JSONDecodeError:
                        continue
                elif msg.type in (
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.CLOSE,
                    aiohttp.WSMsgType.ERROR,
                ):
                    break

    def _merge_event(self, event: dict[str, Any]) -> MowerSnapshot | None:
        mower_id = event.get("id")
        if not mower_id:
            return None
        mower_id = str(mower_id)
        mower = dict(self._mowers.get(mower_id, {"id": mower_id, "attributes": {}}))
        attributes = dict(mower.get("attributes") or {})
        event_attributes = event.get("attributes") or {}
        event_type = event.get("type")

        if event_type == "position-event-v2":
            position = event_attributes.get("position")
            if isinstance(position, dict):
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
            return None

        mower["attributes"] = attributes
        self._mowers[mower_id] = mower
        return _snapshot(mower)


@dataclass
class _Token:
    access_token: str
    expires_at: datetime

    @property
    def is_valid(self) -> bool:
        """Return true if token is not close to expiry."""
        return dt_util.utcnow() < self.expires_at - timedelta(minutes=5)


def _snapshot(mower: dict[str, Any]) -> MowerSnapshot:
    attrs = mower.get("attributes") or {}
    system = attrs.get("system") or {}
    battery = attrs.get("battery") or {}
    mower_status = attrs.get("mower") or {}
    positions = attrs.get("positions") or []
    position = positions[0] if positions else {}
    state = mower_status.get("state")
    activity = mower_status.get("activity")
    error_code = mower_status.get("errorCode")
    return MowerSnapshot(
        provider="husqvarna",
        mower_id=str(mower.get("id")),
        name=system.get("name"),
        model=system.get("model"),
        serial_number=system.get("serialNumber"),
        latitude=_coerce_float(position.get("latitude")),
        longitude=_coerce_float(position.get("longitude")),
        battery_percent=_coerce_int(battery.get("batteryPercent")),
        state=state,
        activity=activity,
        error_code=error_code,
        is_problem=(
            state in {"ERROR", "FATAL_ERROR", "STOPPED"}
            or activity in {"STOPPED_IN_GARDEN"}
            or bool(error_code)
        ),
        raw=mower,
    )


async def _read_json(response: aiohttp.ClientResponse) -> dict[str, Any]:
    text = await response.text()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError as err:
        raise RuntimeError(f"Expected JSON from Husqvarna API, got: {text[:200]}") from err


def _coerce_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> int | None:
    try:
        return round(float(value))
    except (TypeError, ValueError):
        return None
