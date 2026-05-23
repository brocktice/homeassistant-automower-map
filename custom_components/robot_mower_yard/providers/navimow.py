"""Navimow provider."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any
from urllib.parse import urlparse

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from mower_sdk.api import MowerAPI
from mower_sdk.models import DeviceStateMessage, DeviceStatus, MowerCommand
from mower_sdk.sdk import NavimowSDK

from ..auth import NavimowOAuth2Implementation
from ..const import (
    CONF_BASE_STATION_LATITUDE,
    CONF_BASE_STATION_LONGITUDE,
    CONF_POSITION_OFFSET_EAST_M,
    CONF_POSITION_OFFSET_NORTH_M,
    DOMAIN,
    NAVIMOW_API_BASE_URL,
    NAVIMOW_AUTHORIZE_URL,
    NAVIMOW_CLIENT_ID,
    NAVIMOW_CLIENT_SECRET,
    NAVIMOW_HTTP_FALLBACK_MIN_INTERVAL,
    NAVIMOW_MQTT_BROKER,
    NAVIMOW_MQTT_PORT,
    NAVIMOW_MQTT_STALE_SECONDS,
    NAVIMOW_TOKEN_URL,
)
from ..models import MowerSnapshot
from ..position import (
    extract_position,
    extract_relative_xy,
    extract_timestamp,
    position_dict_with_origin,
)
from .base import MowerProvider, SnapshotCallback

_LOGGER = logging.getLogger(__name__)

PROBLEM_STATES = {"error", "unknown"}
PROBLEM_ERRORS = {"stuck", "lifted", "sensor_error", "motor_error", "blade_error"}
LOCATION_MIN_UPDATE_INTERVAL = 5.0
LOCATION_MIN_MOVE_METERS = 0.5


class NavimowProvider(MowerProvider):
    """Fetch and subscribe to live mower snapshots from Navimow."""

    supports_commands = True

    def __init__(self, hass, entry) -> None:
        """Initialize provider."""
        super().__init__(hass, entry)
        self._oauth_session: config_entry_oauth2_flow.OAuth2Session | None = None
        self._api: MowerAPI | None = None
        self._sdk: NavimowSDK | None = None
        self._devices: dict[str, Any] = {}
        self._states: dict[str, DeviceStateMessage] = {}
        self._attributes: dict[str, Any] = {}
        self._last_mqtt_update: float | None = None
        self._last_http_fetch: float | None = None
        self._last_data_source: str | None = None
        self._last_location_timestamp: dict[str, int] = {}
        self._last_location_update_monotonic: dict[str, float] = {}
        self._last_location_relative: dict[str, tuple[float, float]] = {}
        self._last_location_debug: dict[str, Any] = {}
        self._callback: SnapshotCallback | None = None
        self._mqtt_refresh_lock = asyncio.Lock()
        self._unloading = False

    async def async_get_mowers(self) -> list[MowerSnapshot]:
        """Return live Navimow mower snapshots."""
        if await self._async_valid_token() is None:
            return []
        api = await self._async_api()
        devices = await api.async_get_devices()
        self._devices = {device.id: device for device in devices}

        cached_snapshots = self._cached_snapshots()
        if cached_snapshots and not self._should_http_fetch():
            return cached_snapshots

        statuses = await api.async_get_device_statuses([device.id for device in devices])
        for device in devices:
            status = statuses.get(device.id)
            state = self._device_status_to_state(status) if status else None
            if state and state.position is None:
                http_position = await self._async_fetch_http_position(device.id)
                if http_position is not None:
                    state = _state_with_position(state, http_position)
            if state:
                self._states[device.id] = self._state_with_normalized_position(state)
        self._last_http_fetch = time.monotonic()
        self._last_data_source = "http_fallback"
        return self._cached_snapshots()

    async def async_start(self, callback: SnapshotCallback) -> None:
        """Start Navimow MQTT push updates."""
        self._callback = callback
        if self._sdk is not None:
            return
        api = await self._async_api()
        if not self._devices:
            devices = await api.async_get_devices()
            self._devices = {device.id: device for device in devices}
        mqtt_info = await self._async_mqtt_info(api)
        mqtt_host = mqtt_info.get("mqttHost") or self.entry.data.get(
            "mqtt_broker", NAVIMOW_MQTT_BROKER
        )
        mqtt_url = mqtt_info.get("mqttUrl")
        mqtt_username = mqtt_info.get("userName") or self.entry.data.get("mqtt_username")
        mqtt_password = mqtt_info.get("pwdInfo") or self.entry.data.get("mqtt_password")
        mqtt_port = 443 if mqtt_url else self.entry.data.get("mqtt_port", NAVIMOW_MQTT_PORT)
        ws_path = mqtt_url
        if mqtt_url:
            parsed = urlparse(mqtt_url)
            if parsed.scheme in ("ws", "wss") and parsed.hostname:
                mqtt_host = mqtt_host or parsed.hostname
                mqtt_port = parsed.port or mqtt_port
                ws_path = parsed.path or "/"
                if parsed.query:
                    ws_path = f"{ws_path}?{parsed.query}"
        token = await self._async_valid_token()
        auth_headers = {"Authorization": f"Bearer {token}"} if ws_path and token else None

        def _create_sdk() -> NavimowSDK:
            sdk = NavimowSDK(
                broker=mqtt_host,
                port=mqtt_port,
                username=mqtt_username,
                password=mqtt_password,
                ws_path=ws_path,
                auth_headers=auth_headers,
                loop=self.hass.loop,
                records=list(self._devices.values()),
                keepalive_seconds=2400,
                reconnect_min_delay=1,
                reconnect_max_delay=60,
            )
            sdk.connect()
            return sdk

        self._sdk = await self.hass.async_add_executor_job(_create_sdk)
        self._attach_sdk_callbacks(self._sdk, api)
        _LOGGER.info(
            "Navimow MQTT started: broker=%s port=%s ws_path=%s devices=%d",
            mqtt_host,
            mqtt_port,
            ws_path,
            len(self._devices),
        )

    async def async_stop(self) -> None:
        """Stop Navimow MQTT."""
        self._unloading = True
        sdk = self._sdk
        self._sdk = None
        if sdk is not None:
            await self.hass.async_add_executor_job(sdk.disconnect)

    async def async_start_mowing(self, mower_id: str) -> None:
        """Start mowing."""
        await self._async_send_command(mower_id, MowerCommand.START)

    async def async_pause(self, mower_id: str) -> None:
        """Pause mowing."""
        await self._async_send_command(mower_id, MowerCommand.PAUSE)

    async def async_dock(self, mower_id: str) -> None:
        """Dock mower."""
        await self._async_send_command(mower_id, MowerCommand.DOCK)

    async def async_resume(self, mower_id: str) -> None:
        """Resume mowing."""
        await self._async_send_command(mower_id, MowerCommand.RESUME)

    async def _async_send_command(self, mower_id: str, command: MowerCommand) -> None:
        if await self._async_valid_token() is None:
            raise RuntimeError("No Navimow token available")
        api = await self._async_api()
        await api.async_send_command(mower_id, command)

    async def _async_api(self) -> MowerAPI:
        token = await self._async_valid_token()
        if token is None:
            raise RuntimeError("No Navimow token available")
        if self._api is None:
            self._api = MowerAPI(
                session=async_get_clientsession(self.hass),
                token=token,
                base_url=self.entry.data.get("api_base_url", NAVIMOW_API_BASE_URL),
            )
        else:
            self._api.set_token(token)
        return self._api

    async def _async_valid_token(self) -> str | None:
        if "token" not in self.entry.data:
            return None
        if self._oauth_session is None:
            implementation = NavimowOAuth2Implementation(
                self.hass,
                DOMAIN,
                NAVIMOW_CLIENT_ID,
                NAVIMOW_CLIENT_SECRET,
                NAVIMOW_AUTHORIZE_URL,
                NAVIMOW_TOKEN_URL,
            )
            self._oauth_session = config_entry_oauth2_flow.OAuth2Session(
                self.hass,
                self.entry,
                implementation,
            )
        try:
            token: dict[str, Any] | None = None
            if hasattr(self._oauth_session, "async_ensure_token_valid"):
                await self._oauth_session.async_ensure_token_valid()
                token = self._oauth_session.token
            elif hasattr(self._oauth_session, "async_get_valid_token"):
                token = await self._oauth_session.async_get_valid_token()
        except ConfigEntryAuthFailed:
            raise
        except Exception as err:
            _LOGGER.warning("Navimow token refresh failed, using cached token: %s", err)
            token = getattr(self._oauth_session, "token", None)
        if not token:
            token = self.entry.data.get("token")
        return token.get("access_token") if token else None

    async def _async_mqtt_info(self, api: MowerAPI) -> dict[str, Any]:
        try:
            mqtt_info = await api.async_get_mqtt_user_info()
            self.hass.config_entries.async_update_entry(
                self.entry,
                data={
                    **self.entry.data,
                    "cached_mqtt_host": mqtt_info.get("mqttHost"),
                    "cached_mqtt_url": mqtt_info.get("mqttUrl"),
                    "cached_mqtt_username": mqtt_info.get("userName"),
                    "cached_mqtt_password": mqtt_info.get("pwdInfo"),
                },
            )
            return mqtt_info
        except Exception as err:
            _LOGGER.warning("Failed to get Navimow MQTT info, using cached settings: %s", err)
            return {
                "mqttHost": self.entry.data.get("cached_mqtt_host"),
                "mqttUrl": self.entry.data.get("cached_mqtt_url"),
                "userName": self.entry.data.get("cached_mqtt_username"),
                "pwdInfo": self.entry.data.get("cached_mqtt_password"),
            }

    def _attach_sdk_callbacks(self, sdk: NavimowSDK, api: MowerAPI) -> None:
        sdk.on_state(self._handle_state)
        sdk.on_attributes(self._handle_attributes)
        mqtt = sdk._mqtt
        original_client_on_message = mqtt.client.on_message
        original_on_ready = mqtt.on_ready
        original_on_disconnected = mqtt.on_disconnected

        async def _on_ready() -> None:
            if original_on_ready is not None:
                await original_on_ready()
            self._subscribe_location_topics()

        async def _on_disconnected() -> None:
            if original_on_disconnected is not None:
                await original_on_disconnected()
            if self._unloading or self._mqtt_refresh_lock.locked():
                return
            async with self._mqtt_refresh_lock:
                if not self._unloading:
                    await self._async_refresh_mqtt_credentials(sdk, api)

        def _client_on_message(_client, _userdata, msg) -> None:
            topic = msg.topic
            payload_text = (msg.payload or b"").decode("utf-8", errors="replace")
            device_id = _device_id_from_topic(topic)
            if device_id:
                self.hass.loop.call_soon_threadsafe(
                    self._handle_location_message,
                    topic,
                    payload_text,
                    device_id,
                )
            if original_client_on_message is not None:
                original_client_on_message(_client, _userdata, msg)

        mqtt.on_ready = _on_ready
        mqtt.on_disconnected = _on_disconnected
        mqtt.client.on_message = _client_on_message
        self._subscribe_location_topics()

    def _subscribe_location_topics(self) -> None:
        if self._sdk is None:
            return
        mqtt = self._sdk._mqtt
        for device_id in self._devices:
            mqtt.client.subscribe(f"/downlink/vehicle/{device_id}/realtimeDate/location")
            mqtt.client.subscribe(f"/downlink/vehicle/{device_id}/realtimeDate/position")

    async def _async_refresh_mqtt_credentials(self, sdk: NavimowSDK, api: MowerAPI) -> None:
        token = await self._async_valid_token()
        if token:
            api.set_token(token)
        try:
            mqtt_info = await api.async_get_mqtt_user_info()
        except Exception as err:
            _LOGGER.warning("Failed to refresh Navimow MQTT credentials: %s", err)
            return
        self.hass.config_entries.async_update_entry(
            self.entry,
            data={
                **self.entry.data,
                "cached_mqtt_host": mqtt_info.get("mqttHost"),
                "cached_mqtt_url": mqtt_info.get("mqttUrl"),
                "cached_mqtt_username": mqtt_info.get("userName"),
                "cached_mqtt_password": mqtt_info.get("pwdInfo"),
            },
        )

        def _update_credentials() -> None:
            sdk.update_mqtt_credentials(
                auth_headers={"Authorization": f"Bearer {token}"} if token else None,
                username=mqtt_info.get("userName"),
                password=mqtt_info.get("pwdInfo"),
            )

        await self.hass.async_add_executor_job(_update_credentials)

    def _handle_state(self, state: DeviceStateMessage) -> None:
        if state.device_id not in self._devices:
            return
        self._last_mqtt_update = time.monotonic()
        self._last_data_source = "mqtt_push"
        normalized = self._state_with_normalized_position(state)
        self._states[state.device_id] = normalized
        self._publish_snapshots([state.device_id])

    def _handle_attributes(self, attrs) -> None:
        device_id = getattr(attrs, "device_id", None)
        if device_id not in self._devices:
            return
        self._last_mqtt_update = time.monotonic()
        self._attributes[device_id] = attrs
        self._publish_snapshots([device_id])

    def _handle_location_message(self, topic: str, payload_text: str, device_id: str) -> None:
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError:
            return
        if not isinstance(payload, dict | list):
            return
        if not self._update_position(device_id, payload, topic):
            return
        self._publish_snapshots([device_id])

    def _update_position(self, device_id: str, payload: Any, topic: str | None = None) -> bool:
        position = self._position_dict(payload)
        relative = extract_relative_xy(payload)
        timestamp = extract_timestamp(payload)
        if position is None and relative is None:
            return False
        last_timestamp = self._last_location_timestamp.get(device_id)
        if timestamp is not None and last_timestamp is not None and timestamp <= last_timestamp:
            return False
        now = time.monotonic()
        if self._should_throttle_location_update(device_id, now, relative):
            if timestamp is not None:
                self._last_location_timestamp[device_id] = timestamp
            return False
        self._last_location_debug[device_id] = {
            "topic": topic,
            "timestamp": timestamp,
            "relative_x": relative[0] if relative else None,
            "relative_y": relative[1] if relative else None,
            "position": position,
        }
        if position is None:
            return False
        if timestamp is not None:
            self._last_location_timestamp[device_id] = timestamp
        self._last_location_update_monotonic[device_id] = now
        if relative is not None:
            self._last_location_relative[device_id] = relative
        state = self._states.get(device_id)
        if state is None:
            state = DeviceStateMessage(device_id=device_id, timestamp=None, state="unknown", position=position)
        else:
            state = _state_with_position(state, position)
        self._states[device_id] = state
        self._last_data_source = "mqtt_location"
        return True

    def _should_throttle_location_update(
        self,
        device_id: str,
        now: float,
        relative: tuple[float, float] | None,
    ) -> bool:
        last_update = self._last_location_update_monotonic.get(device_id)
        if last_update is None or now - last_update >= LOCATION_MIN_UPDATE_INTERVAL:
            return False
        last_relative = self._last_location_relative.get(device_id)
        if relative is None or last_relative is None:
            return True
        distance = ((relative[0] - last_relative[0]) ** 2 + (relative[1] - last_relative[1]) ** 2) ** 0.5
        return distance < LOCATION_MIN_MOVE_METERS

    def _publish_snapshots(self, device_ids: list[str]) -> None:
        if self._callback is None:
            return
        snapshots = [self._snapshot_for_device(device_id) for device_id in device_ids]
        snapshots = [snapshot for snapshot in snapshots if snapshot is not None]
        if not snapshots:
            return
        self.hass.loop.call_soon_threadsafe(
            lambda: self.hass.async_create_task(self._callback(snapshots))
        )

    def _cached_snapshots(self) -> list[MowerSnapshot]:
        return [
            snapshot
            for device_id in self._devices
            if (snapshot := self._snapshot_for_device(device_id)) is not None
        ]

    def _snapshot_for_device(self, device_id: str) -> MowerSnapshot | None:
        device = self._devices.get(device_id)
        if device is None:
            return None
        return _snapshot_from_state(
            device,
            self._states.get(device_id),
            self._attributes.get(device_id),
            self._last_data_source,
            self._last_location_debug.get(device_id),
        )

    def _device_status_to_state(self, status: DeviceStatus) -> DeviceStateMessage:
        error: dict[str, Any] | None = None
        if status.error_code and status.error_code.value != "none":
            error = {"code": status.error_code.value, "message": status.error_message}
        return DeviceStateMessage(
            device_id=status.device_id,
            timestamp=status.timestamp,
            state=status.status.value,
            battery=status.battery,
            signal_strength=status.signal_strength,
            position=self._position_dict(status.position or status.extra),
            error=error,
            metrics=None,
        )

    def _state_with_normalized_position(self, state: DeviceStateMessage) -> DeviceStateMessage:
        position = self._position_dict(state.position)
        if position is None and state.device_id in self._states:
            position = self._states[state.device_id].position
        if position == state.position:
            return state
        return _state_with_position(state, position)

    async def _async_fetch_http_position(self, device_id: str) -> dict[str, float] | None:
        api = await self._async_api()
        try:
            response = await api._async_request(
                "POST",
                "/openapi/smarthome/getVehicleStatus",
                data={"devices": [{"id": device_id}]},
            )
        except Exception:
            return None
        if response.get("code") != 1:
            return None
        payload = response.get("data", {}).get("payload", {})
        for status_data in payload.get("devices", []):
            if not isinstance(status_data, dict):
                continue
            if status_data.get("id") not in (None, device_id):
                continue
            position = self._position_dict(status_data)
            if position is not None:
                return position
        return None

    def _position_dict(self, position_payload: Any) -> dict[str, float] | None:
        return position_dict_with_origin(
            position_payload,
            _coerce_float(self.entry.options.get(CONF_BASE_STATION_LATITUDE)),
            _coerce_float(self.entry.options.get(CONF_BASE_STATION_LONGITUDE)),
            _coerce_float(self.entry.options.get(CONF_POSITION_OFFSET_NORTH_M)),
            _coerce_float(self.entry.options.get(CONF_POSITION_OFFSET_EAST_M)),
        )

    def _should_http_fetch(self) -> bool:
        now = time.monotonic()
        is_mqtt_stale = (
            self._last_mqtt_update is None
            or now - self._last_mqtt_update > NAVIMOW_MQTT_STALE_SECONDS
        )
        can_http_fetch = (
            self._last_http_fetch is None
            or now - self._last_http_fetch > NAVIMOW_HTTP_FALLBACK_MIN_INTERVAL
        )
        return is_mqtt_stale and can_http_fetch


def _snapshot_from_state(
    device,
    state: DeviceStateMessage | None,
    attrs: Any,
    data_source: str | None,
    location_debug: dict[str, Any] | None,
) -> MowerSnapshot:
    latitude, longitude = extract_position(state.position if state else None)
    error_code = _error_code(state.error if state else None)
    raw = {
        "device": device.to_dict() if hasattr(device, "to_dict") else {},
        "state": _to_dict(state),
        "attributes": _to_dict(attrs),
        "meta": {
            "last_data_source": data_source,
            "last_location_debug": location_debug or {},
        },
    }
    return MowerSnapshot(
        provider="navimow",
        mower_id=device.id,
        name=device.name or getattr(device, "device_name", None),
        model=device.model,
        serial_number=device.serial_number or device.id,
        latitude=latitude,
        longitude=longitude,
        battery_percent=state.battery if state else None,
        state=state.state if state else None,
        activity=state.state if state else None,
        error_code=error_code,
        is_problem=_is_problem_state(state),
        raw=raw,
    )


def _state_with_position(
    state: DeviceStateMessage,
    position: dict[str, float] | None,
) -> DeviceStateMessage:
    return DeviceStateMessage(
        device_id=state.device_id,
        timestamp=state.timestamp,
        state=state.state,
        battery=state.battery,
        signal_strength=state.signal_strength,
        position=position,
        error=state.error,
        metrics=state.metrics,
    )


def _device_id_from_topic(topic: str) -> str | None:
    parts = topic.split("/")
    if parts and parts[0] == "":
        parts = parts[1:]
    if len(parts) >= 3 and parts[0] == "downlink" and parts[1] == "vehicle":
        return parts[2]
    if len(parts) >= 2 and parts[0] == "navimow":
        return parts[1]
    return None


def _is_problem_state(state: DeviceStateMessage | None) -> bool:
    if state is None:
        return False
    if state.state in PROBLEM_STATES:
        return True
    error = state.error
    if isinstance(error, dict):
        code = str(error.get("code") or error.get("error_code") or "").lower()
        return code in PROBLEM_ERRORS or "stuck" in code
    if isinstance(error, str):
        return error.lower() in PROBLEM_ERRORS or "stuck" in error.lower()
    return False


def _error_code(error: Any) -> str | None:
    if isinstance(error, dict):
        code = error.get("code") or error.get("error_code")
        return str(code) if code else None
    if isinstance(error, str):
        return error
    return None


def _to_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return value if isinstance(value, dict) else {}


def _coerce_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
