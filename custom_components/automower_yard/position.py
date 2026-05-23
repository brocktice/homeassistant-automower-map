"""Position helpers for mower payloads."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import math
from typing import Any

LATITUDE_KEYS = (
    "lat",
    "latitude",
    "latGcj02",
    "latWgs84",
    "wgs84Lat",
    "gcj02Lat",
    "latitudeValue",
)
LONGITUDE_KEYS = (
    "lng",
    "lon",
    "longitude",
    "lngGcj02",
    "lngWgs84",
    "wgs84Lng",
    "gcj02Lng",
    "longitudeValue",
)
RELATIVE_X_KEYS = (
    "x",
    "thetaX",
    "theta_x",
    "relativeX",
    "relative_x",
    "postureX",
    "posture_x",
)
RELATIVE_Y_KEYS = (
    "y",
    "thetaY",
    "theta_y",
    "relativeY",
    "relative_y",
    "postureY",
    "posture_y",
)
POSITION_KEYS = ("position", "location", "gps", "coordinate", "coordinates", "point", "pos")
TIMESTAMP_KEYS = ("time", "timestamp", "ts")
METERS_PER_DEGREE_LATITUDE = 111111.0


def extract_position(position: Any) -> tuple[float | None, float | None]:
    """Extract latitude/longitude from known payload shapes."""
    payload = _to_plain(position)
    latitude, longitude = _extract_from_payload(payload, depth=0)
    if latitude is not None and longitude is not None and _looks_like_coordinate(latitude, longitude):
        return latitude, longitude
    return None, None


def position_dict(position: Any) -> dict[str, float] | None:
    """Return normalized position dict when coordinates are available."""
    latitude, longitude = extract_position(position)
    if latitude is None or longitude is None:
        return None
    return {"lat": latitude, "lng": longitude}


def position_dict_with_origin(
    position: Any,
    origin_latitude: float | None,
    origin_longitude: float | None,
    offset_north_meters: float | None = None,
    offset_east_meters: float | None = None,
) -> dict[str, float] | None:
    """Return absolute GPS from payload, using base-station origin for relative x/y."""
    payload = _to_plain(position)
    if origin_latitude is not None and origin_longitude is not None:
        relative = extract_relative_xy(payload)
        if relative is not None and _is_bare_numeric_pair(payload):
            return _position_dict_from_relative(
                relative,
                origin_latitude,
                origin_longitude,
                offset_north_meters,
                offset_east_meters,
            )
    absolute = position_dict(position)
    if absolute is not None:
        return _position_dict_with_offset(
            absolute,
            offset_north_meters,
            offset_east_meters,
        )
    if origin_latitude is None or origin_longitude is None:
        return None
    relative = extract_relative_xy(payload)
    if relative is None:
        return None
    return _position_dict_from_relative(
        relative,
        origin_latitude,
        origin_longitude,
        offset_north_meters,
        offset_east_meters,
    )


def _position_dict_from_relative(
    relative: tuple[float, float],
    origin_latitude: float,
    origin_longitude: float,
    offset_north_meters: float | None = None,
    offset_east_meters: float | None = None,
) -> dict[str, float] | None:
    """Convert base-station-relative x/y meters to absolute GPS."""
    x_meters, y_meters = relative
    longitude_scale = METERS_PER_DEGREE_LATITUDE * math.cos(math.radians(origin_latitude))
    if abs(longitude_scale) < 0.000001:
        return None
    return _position_dict_with_offset(
        {
            "lat": origin_latitude + (y_meters / METERS_PER_DEGREE_LATITUDE),
            "lng": origin_longitude + (x_meters / longitude_scale),
        },
        offset_north_meters,
        offset_east_meters,
    )


def _position_dict_with_offset(
    position: dict[str, float],
    offset_north_meters: float | None,
    offset_east_meters: float | None,
) -> dict[str, float]:
    offset_north = offset_north_meters or 0.0
    offset_east = offset_east_meters or 0.0
    if offset_north == 0 and offset_east == 0:
        return position
    longitude_scale = METERS_PER_DEGREE_LATITUDE * math.cos(math.radians(position["lat"]))
    if abs(longitude_scale) < 0.000001:
        return position
    return {
        "lat": position["lat"] + (offset_north / METERS_PER_DEGREE_LATITUDE),
        "lng": position["lng"] + (offset_east / longitude_scale),
    }


def extract_relative_xy(position: Any) -> tuple[float, float] | None:
    """Extract mower-relative x/y meters from known payload shapes."""
    payload = _to_plain(position)
    x_value, y_value = _extract_relative_from_payload(payload, depth=0)
    if x_value is None or y_value is None:
        return None
    return x_value, y_value


def extract_timestamp(position: Any) -> int | None:
    """Extract a timestamp from known payload shapes."""
    payload = _to_plain(position)
    value = _extract_timestamp_from_payload(payload, depth=0)
    if value is None:
        return None
    return int(value)


def _extract_from_payload(
    payload: Any, depth: int
) -> tuple[float | None, float | None]:
    if depth > 6:
        return None, None
    if isinstance(payload, dict):
        latitude = _first_float(payload, LATITUDE_KEYS)
        longitude = _first_float(payload, LONGITUDE_KEYS)
        if latitude is not None and longitude is not None:
            return latitude, longitude
        for key in POSITION_KEYS:
            if key in payload:
                latitude, longitude = _extract_from_payload(payload[key], depth + 1)
                if latitude is not None and longitude is not None:
                    return latitude, longitude
        for value in payload.values():
            if isinstance(value, dict | list | tuple):
                latitude, longitude = _extract_from_payload(value, depth + 1)
                if latitude is not None and longitude is not None:
                    return latitude, longitude
    if isinstance(payload, list | tuple):
        if len(payload) >= 2:
            first = _as_float(payload[0])
            second = _as_float(payload[1])
            if first is not None and second is not None:
                return first, second
        for value in payload:
            if isinstance(value, dict | list | tuple):
                latitude, longitude = _extract_from_payload(value, depth + 1)
                if latitude is not None and longitude is not None:
                    return latitude, longitude
    return None, None


def _extract_relative_from_payload(
    payload: Any, depth: int
) -> tuple[float | None, float | None]:
    if depth > 6:
        return None, None
    if isinstance(payload, dict):
        x_value = _first_float(payload, RELATIVE_X_KEYS)
        y_value = _first_float(payload, RELATIVE_Y_KEYS)
        if x_value is not None and y_value is not None:
            return x_value, y_value
        for key in POSITION_KEYS:
            if key in payload:
                x_value, y_value = _extract_relative_from_payload(payload[key], depth + 1)
                if x_value is not None and y_value is not None:
                    return x_value, y_value
        for value in payload.values():
            if isinstance(value, dict | list | tuple):
                x_value, y_value = _extract_relative_from_payload(value, depth + 1)
                if x_value is not None and y_value is not None:
                    return x_value, y_value
    if isinstance(payload, list | tuple):
        if len(payload) >= 2:
            first = _as_float(payload[0])
            second = _as_float(payload[1])
            if first is not None and second is not None:
                return first, second
        for value in payload:
            if isinstance(value, dict | list | tuple):
                x_value, y_value = _extract_relative_from_payload(value, depth + 1)
                if x_value is not None and y_value is not None:
                    return x_value, y_value
    return None, None


def _extract_timestamp_from_payload(payload: Any, depth: int) -> float | None:
    if depth > 6:
        return None
    if isinstance(payload, dict):
        value = _first_float(payload, TIMESTAMP_KEYS)
        if value is not None:
            return value
        for key in POSITION_KEYS:
            if key in payload:
                value = _extract_timestamp_from_payload(payload[key], depth + 1)
                if value is not None:
                    return value
        for value in payload.values():
            if isinstance(value, dict | list | tuple):
                timestamp = _extract_timestamp_from_payload(value, depth + 1)
                if timestamp is not None:
                    return timestamp
    if isinstance(payload, list | tuple):
        for value in payload:
            if isinstance(value, dict | list | tuple):
                timestamp = _extract_timestamp_from_payload(value, depth + 1)
                if timestamp is not None:
                    return timestamp
    return None


def _first_float(payload: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        if key in payload:
            value = _as_float(payload[key])
            if value is not None:
                return value
    return None


def _to_plain(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict | list | tuple):
        return value
    if hasattr(value, "to_dict"):
        try:
            return value.to_dict()
        except TypeError:
            pass
    if hasattr(value, "__dict__"):
        return vars(value)
    return value


def _is_bare_numeric_pair(payload: Any) -> bool:
    if not isinstance(payload, list | tuple) or len(payload) != 2:
        return False
    return _as_float(payload[0]) is not None and _as_float(payload[1]) is not None


def _looks_like_coordinate(latitude: float, longitude: float) -> bool:
    return -90 <= latitude <= 90 and -180 <= longitude <= 180


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
