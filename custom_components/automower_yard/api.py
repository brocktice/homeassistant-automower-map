"""Husqvarna Automower API client."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import logging
from typing import Any

import aiohttp

from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .const import AUTH_URL, REST_BASE_URL, WS_URL

_LOGGER = logging.getLogger(__name__)


class AutomowerApiError(Exception):
    """Base API error."""


@dataclass
class Token:
    """OAuth token state."""

    access_token: str
    expires_at: datetime

    @property
    def is_valid(self) -> bool:
        """Return true if token is not close to expiry."""
        return dt_util.utcnow() < self.expires_at - timedelta(minutes=5)


class AutomowerApiClient:
    """Small async client for Husqvarna Automower Connect."""

    def __init__(self, hass, app_key: str, app_secret: str) -> None:
        """Initialize the API client."""
        self._session = async_get_clientsession(hass)
        self._app_key = app_key
        self._app_secret = app_secret
        self._token: Token | None = None

    async def async_get_token(self) -> str:
        """Return a valid access token."""
        if self._token and self._token.is_valid:
            return self._token.access_token

        data = {
            "grant_type": "client_credentials",
            "client_id": self._app_key,
            "client_secret": self._app_secret,
        }
        async with self._session.post(AUTH_URL, data=data) as response:
            payload = await _read_json(response)
            if response.status not in (200, 201):
                raise AutomowerApiError(
                    f"Authentication failed: {response.status} {payload}"
                )

        expires_in = int(payload.get("expires_in", 3600))
        self._token = Token(
            access_token=payload["access_token"],
            expires_at=dt_util.utcnow() + timedelta(seconds=expires_in),
        )
        return self._token.access_token

    async def async_list_mowers(self) -> list[dict[str, Any]]:
        """List mowers paired to the account."""
        payload = await self._request("GET", "/mowers")
        return list(payload.get("data") or [])

    async def async_get_mower(self, mower_id: str) -> dict[str, Any]:
        """Fetch one mower."""
        payload = await self._request("GET", f"/mowers/{mower_id}")
        return dict(payload.get("data") or {})

    async def _request(self, method: str, path: str) -> Mapping[str, Any]:
        """Make an authenticated REST request."""
        token = await self.async_get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Authorization-Provider": "husqvarna",
            "X-Api-Key": self._app_key,
            "Accept": "application/vnd.api+json",
        }
        async with self._session.request(
            method, f"{REST_BASE_URL}{path}", headers=headers
        ) as response:
            payload = await _read_json(response)
            if response.status >= 400:
                if response.status in (401, 404):
                    self._token = None
                raise AutomowerApiError(
                    f"Automower API request failed: {response.status} {payload}"
                )
            return payload

    async def listen_events(self) -> AsyncIterator[dict[str, Any]]:
        """Yield websocket events until the socket closes."""
        token = await self.async_get_token()
        async with self._session.ws_connect(
            WS_URL,
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
                        _LOGGER.debug("Ignoring non-JSON websocket message: %s", msg.data)
                elif msg.type in (
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.CLOSE,
                    aiohttp.WSMsgType.ERROR,
                ):
                    break

    async def async_validate(self) -> None:
        """Validate credentials by fetching mowers."""
        await self.async_list_mowers()


async def _read_json(response: aiohttp.ClientResponse) -> dict[str, Any]:
    """Read a JSON response, tolerating empty bodies."""
    text = await response.text()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError as err:
        raise AutomowerApiError(f"Expected JSON from API, got: {text[:200]}") from err
