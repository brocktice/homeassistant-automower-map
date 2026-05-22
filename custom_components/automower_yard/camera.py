"""Read-only yard map camera for Automower Yard."""

from __future__ import annotations

import asyncio
import base64
from io import BytesIO
from html import escape
import math
from typing import Any

from aiohttp import ClientError
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from homeassistant.components.camera import Camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .const import ATTR_HEATMAP_MAX_AGE_DAYS, ATTR_HEATMAP_SAMPLE_COUNT, ATTR_YARD_ZONES
from .coordinator import HEATMAP_MAX_AGE, AutomowerYardCoordinator
from .entity import AutomowerYardEntity

WIDTH = 1600
HEIGHT = 900
DETAIL_WIDTH = 800
DETAIL_HEIGHT = 800
PADDING = 40
TEXT_SCALE = WIDTH / 900
DETAIL_TEXT_SCALE = DETAIL_WIDTH / 900
MAP_LEFT = 0
MAP_TOP = 0
MAP_RIGHT = WIDTH
MAP_BOTTOM = HEIGHT
FONT_PATHS = (
    "/usr/local/lib/python3.14/site-packages/aioslimproto/font/DejaVu-Sans.ttf",
    "/usr/local/lib/python3.13/site-packages/aioslimproto/font/DejaVu-Sans.ttf",
    "/usr/local/lib/python3.12/site-packages/aioslimproto/font/DejaVu-Sans.ttf",
)
EARTH_RADIUS_M = 6371000
MAX_TILE_COUNT = 16
# Match Leaflet's Esri maxNativeZoom in the editor. Higher zooms often return
# Esri placeholder tiles ("map data not available yet") in residential areas.
MAX_TILE_ZOOM = 19
MIN_TILE_ZOOM = 16


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up yard map cameras."""
    coordinator: AutomowerYardCoordinator = entry.runtime_data
    entities = []
    for mower_id in coordinator.data:
        entities.extend(
            [
                AutomowerYardMapCamera(coordinator, mower_id),
                AutomowerYardDetailMapCamera(coordinator, mower_id),
                AutomowerYardHeatmapCamera(coordinator, mower_id),
            ]
        )
    async_add_entities(entities)


class AutomowerYardMapCamera(AutomowerYardEntity, Camera):
    """Camera entity that renders a static yard-zone map."""

    _attr_name = "Yard Map"

    def __init__(self, coordinator: AutomowerYardCoordinator, mower_id: str) -> None:
        """Initialize the camera."""
        super().__init__(coordinator, mower_id)
        Camera.__init__(self)
        self.content_type = "image/png"
        self._attr_unique_id = f"{mower_id}_yard_map"

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return SVG image bytes."""
        zones = self.coordinator.zones
        mower_point = _latest_position(self.attributes)
        points = _collect_points(zones, mower_point)
        if not points:
            return _empty_svg("No mower position or yard zones available").encode()

        bounds = _bounds(points, WIDTH, HEIGHT)
        tile_data = await _satellite_tiles(self.hass, bounds)
        return await self.hass.async_add_executor_job(
            _render_png,
            bounds,
            zones,
            mower_point,
            self.mower_name,
            self.attributes.get("yard_zone") or "Unknown",
            tile_data,
            WIDTH,
            HEIGHT,
            70,
            112,
            TEXT_SCALE,
            [],
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return map attributes."""
        return {
            **super().extra_state_attributes,
            ATTR_YARD_ZONES: self.attributes.get("yard_zones") or [],
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        """Force the frontend to fetch a fresh still image after state updates."""
        self.async_update_token()
        super()._handle_coordinator_update()

    def _render_svg(self, bounds: dict[str, float], satellite_markup: str) -> str:
        zones = self.coordinator.zones
        mower_point = _latest_position(self.attributes)
        project = _projector(bounds)
        zone_markup = []
        for index, zone in enumerate(zones):
            color = _zone_color(index)
            if _is_circle(zone):
                center = _to_xy(float(zone["center"][0]), float(zone["center"][1]), bounds)
                x, y = project(center)
                radius = max(4, _radius_px(float(zone["radius_m"]), bounds))
                zone_markup.append(
                    f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" '
                    f'fill="{color}" fill-opacity="0.22" stroke="{color}" '
                    'stroke-width="3" />'
                )
                zone_markup.append(_label(zone["name"], x, y, color))
            elif isinstance(zone.get("polygon"), list):
                xy_points = [
                    project(_to_xy(float(point[0]), float(point[1]), bounds))
                    for point in zone["polygon"]
                    if isinstance(point, list) and len(point) == 2
                ]
                if len(xy_points) < 3:
                    continue
                points_attr = " ".join(f"{x:.1f},{y:.1f}" for x, y in xy_points)
                center_x = sum(x for x, _ in xy_points) / len(xy_points)
                center_y = sum(y for _, y in xy_points) / len(xy_points)
                zone_markup.append(
                    f'<polygon points="{points_attr}" fill="{color}" '
                    f'fill-opacity="0.22" stroke="{color}" stroke-width="3" />'
                )
                zone_markup.append(_label(zone["name"], center_x, center_y, color))

        mower_markup = ""
        if mower_point:
            x, y = project(_to_xy(mower_point[0], mower_point[1], bounds))
            mower_markup = f"""
              <g transform="translate({x - 18:.1f} {y - 18:.1f})">
                <circle cx="18" cy="18" r="18" fill="#256d4d" stroke="#fff" stroke-width="4" />
                <path transform="translate(6 6) scale(1)" fill="#fff"
                  d="M1 14V5H13C18.5 5 23 9.5 23 15V17H20.83C20.42 18.17 19.31 19 18 19C16.69 19 15.58 18.17 15.17 17H10C9.09 18.21 7.64 19 6 19C3.24 19 1 16.76 1 14M6 11C4.34 11 3 12.34 3 14C3 15.66 4.34 17 6 17C7.66 17 9 15.66 9 14C9 12.34 7.66 11 6 11M15 10V12H20.25C19.92 11.27 19.5 10.6 19 10H15Z" />
              </g>
            """

        zone_text = escape(self.attributes.get("yard_zone") or "Unknown")
        return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">
          <rect width="100%" height="100%" fill="#f4f6f5" />
          <rect x="24" y="24" width="{WIDTH - 48}" height="{HEIGHT - 48}" rx="10" fill="#fff" stroke="#d6ded8" />
          <clipPath id="map-area"><rect x="24" y="104" width="{WIDTH - 48}" height="{HEIGHT - 128}" rx="10" /></clipPath>
          <g clip-path="url(#map-area)">
            {satellite_markup}
            <rect x="24" y="104" width="{WIDTH - 48}" height="{HEIGHT - 128}" fill="none" stroke="#d6ded8" />
          </g>
          <text x="42" y="58" font-family="Arial, sans-serif" font-size="24" font-weight="700" fill="#17201b">{escape(self.mower_name)} Yard Map</text>
          <text x="42" y="88" font-family="Arial, sans-serif" font-size="17" fill="#52635a">Current zone: {zone_text}</text>
          <g>{''.join(zone_markup)}</g>
          {mower_markup}
        </svg>"""


class AutomowerYardDetailMapCamera(AutomowerYardMapCamera):
    """Camera entity that renders a square mower-centered map."""

    _attr_name = "Yard Map Detail"

    def __init__(self, coordinator: AutomowerYardCoordinator, mower_id: str) -> None:
        """Initialize the camera."""
        super().__init__(coordinator, mower_id)
        self._attr_unique_id = f"{mower_id}_yard_map_detail"

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return square PNG image bytes centered on the mower."""
        zones = self.coordinator.zones
        mower_point = _latest_position(self.attributes)
        points = _collect_points(zones, mower_point)
        if not points:
            return _empty_svg("No mower position or yard zones available").encode()

        full_bounds = _bounds(points, WIDTH, HEIGHT)
        bounds = _detail_bounds(full_bounds, mower_point)
        tile_data = await _satellite_tiles(self.hass, bounds)
        return await self.hass.async_add_executor_job(
            _render_png,
            bounds,
            zones,
            mower_point,
            self.mower_name,
            self.attributes.get("yard_zone") or "Unknown",
            tile_data,
            DETAIL_WIDTH,
            DETAIL_HEIGHT,
            0,
            0,
            DETAIL_TEXT_SCALE,
            [],
        )


class AutomowerYardHeatmapCamera(AutomowerYardMapCamera):
    """Camera entity that renders an aging stuck/ok heatmap."""

    _attr_name = "Yard Heatmap"

    def __init__(self, coordinator: AutomowerYardCoordinator, mower_id: str) -> None:
        """Initialize the camera."""
        super().__init__(coordinator, mower_id)
        self._attr_unique_id = f"{mower_id}_yard_heatmap"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return heatmap attributes."""
        return {
            **super().extra_state_attributes,
            ATTR_HEATMAP_SAMPLE_COUNT: len(
                self.coordinator.heatmap_samples(self.mower_id)
            ),
            ATTR_HEATMAP_MAX_AGE_DAYS: HEATMAP_MAX_AGE.days,
        }

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return heatmap PNG image bytes."""
        zones = self.coordinator.zones
        mower_point = _latest_position(self.attributes)
        samples = self.coordinator.heatmap_samples(self.mower_id)
        sample_points = [
            (float(sample["latitude"]), float(sample["longitude"]))
            for sample in samples
            if _coerce_float(sample.get("latitude")) is not None
            and _coerce_float(sample.get("longitude")) is not None
        ]
        points = _collect_points(zones, mower_point) + sample_points
        if not points:
            return _empty_svg("No mower position, yard zones, or heatmap samples available").encode()

        bounds = _bounds(points, WIDTH, HEIGHT)
        tile_data = await _satellite_tiles(self.hass, bounds)
        return await self.hass.async_add_executor_job(
            _render_png,
            bounds,
            zones,
            mower_point,
            self.mower_name,
            self.attributes.get("yard_zone") or "Unknown",
            tile_data,
            WIDTH,
            HEIGHT,
            70,
            112,
            TEXT_SCALE,
            samples,
        )


def _latest_position(attributes: dict[str, Any]) -> tuple[float, float] | None:
    positions = attributes.get("positions")
    if not isinstance(positions, list) or not positions:
        return None
    try:
        return float(positions[0]["latitude"]), float(positions[0]["longitude"])
    except (KeyError, TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _collect_points(
    zones: list[dict[str, Any]], mower_point: tuple[float, float] | None
) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    if mower_point:
        points.append(mower_point)
    for zone in zones:
        if _is_circle(zone):
            lat = float(zone["center"][0])
            lon = float(zone["center"][1])
            radius = float(zone["radius_m"])
            delta_lat = math.degrees(radius / EARTH_RADIUS_M)
            delta_lon = math.degrees(radius / (EARTH_RADIUS_M * math.cos(math.radians(lat))))
            points.extend(
                [
                    (lat - delta_lat, lon - delta_lon),
                    (lat + delta_lat, lon + delta_lon),
                ]
            )
        elif isinstance(zone.get("polygon"), list):
            for point in zone["polygon"]:
                if isinstance(point, list) and len(point) == 2:
                    points.append((float(point[0]), float(point[1])))
    return points


def _bounds(
    points: list[tuple[float, float]], image_width: int, image_height: int
) -> dict[str, float]:
    reference_lat = sum(lat for lat, _ in points) / len(points)
    xy_points = [_to_xy(lat, lon, {"reference_lat": reference_lat}) for lat, lon in points]
    min_x = min(x for x, _ in xy_points)
    max_x = max(x for x, _ in xy_points)
    min_y = min(y for _, y in xy_points)
    max_y = max(y for _, y in xy_points)
    if max_x == min_x:
        max_x += 1
        min_x -= 1
    if max_y == min_y:
        max_y += 1
        min_y -= 1
    margin_x = max((max_x - min_x) * 0.28, 8)
    margin_y = max((max_y - min_y) * 0.28, 8)
    min_x -= margin_x
    max_x += margin_x
    min_y -= margin_y
    max_y += margin_y

    target_aspect = (image_width - PADDING * 2) / (image_height - PADDING * 2 - 70)
    current_aspect = (max_x - min_x) / (max_y - min_y)
    if current_aspect < target_aspect:
        needed_width = (max_y - min_y) * target_aspect
        extra = (needed_width - (max_x - min_x)) / 2
        min_x -= extra
        max_x += extra
    else:
        needed_height = (max_x - min_x) / target_aspect
        extra = (needed_height - (max_y - min_y)) / 2
        min_y -= extra
        max_y += extra

    return {
        "reference_lat": reference_lat,
        "min_x": min_x,
        "max_x": max_x,
        "min_y": min_y,
        "max_y": max_y,
    }


def _detail_bounds(
    full_bounds: dict[str, float], mower_point: tuple[float, float] | None
) -> dict[str, float]:
    """Return a square crop centered on the mower, roughly half the full map width."""
    if mower_point is None:
        return full_bounds
    mower_x, mower_y = _to_xy(mower_point[0], mower_point[1], full_bounds)
    full_width = full_bounds["max_x"] - full_bounds["min_x"]
    full_height = full_bounds["max_y"] - full_bounds["min_y"]
    side = max(full_width * 0.5, full_height * 0.5, 18)
    half = side / 2
    return {
        "reference_lat": full_bounds["reference_lat"],
        "min_x": mower_x - half,
        "max_x": mower_x + half,
        "min_y": mower_y - half,
        "max_y": mower_y + half,
    }


def _to_xy(lat: float, lon: float, bounds: dict[str, float]) -> tuple[float, float]:
    reference_lat = bounds["reference_lat"]
    x = math.radians(lon) * EARTH_RADIUS_M * math.cos(math.radians(reference_lat))
    y = math.radians(lat) * EARTH_RADIUS_M
    return x, y


def _projector(
    bounds: dict[str, float],
    image_width: int = WIDTH,
    image_height: int = HEIGHT,
    top_offset: int = 70,
    y_base: int = 112,
):
    drawable_width = image_width - PADDING * 2
    drawable_height = image_height - PADDING * 2 - top_offset
    scale = max(
        drawable_width / (bounds["max_x"] - bounds["min_x"]),
        drawable_height / (bounds["max_y"] - bounds["min_y"]),
    )
    offset_x = (image_width - (bounds["max_x"] - bounds["min_x"]) * scale) / 2
    offset_y = y_base + (drawable_height - (bounds["max_y"] - bounds["min_y"]) * scale) / 2

    def project(point: tuple[float, float]) -> tuple[float, float]:
        x, y = point
        return (
            offset_x + (x - bounds["min_x"]) * scale,
            offset_y + (bounds["max_y"] - y) * scale,
        )

    return project


def _radius_px(
    radius_m: float,
    bounds: dict[str, float],
    image_width: int = WIDTH,
    image_height: int = HEIGHT,
    top_offset: int = 70,
) -> float:
    scale = max(
        (image_width - PADDING * 2) / (bounds["max_x"] - bounds["min_x"]),
        (image_height - PADDING * 2 - top_offset)
        / (bounds["max_y"] - bounds["min_y"]),
    )
    return radius_m * scale


def _is_circle(zone: dict[str, Any]) -> bool:
    center = zone.get("center")
    return (
        isinstance(center, list)
        and len(center) == 2
        and isinstance(zone.get("radius_m"), int | float)
    )


def _label(text: str, x: float, y: float, color: str) -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="middle" '
        'font-family="Arial, sans-serif" font-size="15" font-weight="700" '
        f'fill="#17201b" stroke="#fff" stroke-width="4" paint-order="stroke">{escape(text)}</text>'
    )


def _zone_color(index: int) -> str:
    colors = ["#256d4d", "#2f6da3", "#9a5b21", "#7b4fa3", "#a33f4b", "#60752f"]
    return colors[index % len(colors)]


def _empty_svg(message: str) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">
      <rect width="100%" height="100%" fill="#f4f6f5" />
      <text x="{WIDTH / 2}" y="{HEIGHT / 2}" text-anchor="middle" font-family="Arial, sans-serif" font-size="24" fill="#52635a">{escape(message)}</text>
    </svg>"""


async def _satellite_markup(hass: HomeAssistant, bounds: dict[str, float]) -> str:
    lat_lon_bounds = _lat_lon_bounds(bounds)
    zoom, tiles = _select_tiles(lat_lon_bounds)
    session = async_get_clientsession(hass)
    tile_results = await asyncio.gather(
        *[_fetch_tile(session, zoom, x, y) for x, y in tiles],
        return_exceptions=True,
    )
    project = _projector(bounds)
    markup = []
    for (tile_x, tile_y), result in zip(tiles, tile_results, strict=True):
        if isinstance(result, Exception) or not result:
            continue
        north, west, south, east = _tile_bounds(zoom, tile_x, tile_y)
        x1, y1 = project(_to_xy(north, west, bounds))
        x2, y2 = project(_to_xy(south, east, bounds))
        href = f"data:image/jpeg;base64,{result}"
        markup.append(
            f'<image href="{href}" x="{min(x1, x2):.1f}" y="{min(y1, y2):.1f}" '
            f'width="{abs(x2 - x1):.1f}" height="{abs(y2 - y1):.1f}" '
            'preserveAspectRatio="none" />'
        )
    if not markup:
        return '<rect x="24" y="104" width="852" height="512" fill="#dfe7e1" />'
    return "".join(markup)


async def _satellite_tiles(
    hass: HomeAssistant, bounds: dict[str, float]
) -> list[tuple[int, int, int, bytes]]:
    lat_lon_bounds = _lat_lon_bounds(bounds)
    zoom, tiles = _select_tiles(lat_lon_bounds)
    session = async_get_clientsession(hass)
    tile_results = await asyncio.gather(
        *[_fetch_tile_bytes(session, zoom, x, y) for x, y in tiles],
        return_exceptions=True,
    )
    return [
        (zoom, x, y, result)
        for (x, y), result in zip(tiles, tile_results, strict=True)
        if isinstance(result, bytes)
    ]


async def _fetch_tile(session, zoom: int, x: int, y: int) -> str | None:
    url = (
        "https://server.arcgisonline.com/ArcGIS/rest/services/"
        f"World_Imagery/MapServer/tile/{zoom}/{y}/{x}"
    )
    try:
        async with asyncio.timeout(8):
            async with session.get(url) as response:
                if response.status != 200:
                    return None
                return base64.b64encode(await response.read()).decode()
    except (TimeoutError, ClientError):
        return None


async def _fetch_tile_bytes(session, zoom: int, x: int, y: int) -> bytes | None:
    url = (
        "https://server.arcgisonline.com/ArcGIS/rest/services/"
        f"World_Imagery/MapServer/tile/{zoom}/{y}/{x}"
    )
    try:
        async with asyncio.timeout(8):
            async with session.get(url) as response:
                if response.status != 200:
                    return None
                return await response.read()
    except (TimeoutError, ClientError):
        return None


def _render_png(
    bounds: dict[str, float],
    zones: list[dict[str, Any]],
    mower_point: tuple[float, float] | None,
    mower_name: str,
    yard_zone: str,
    tile_data: list[tuple[int, int, int, bytes]],
    image_width: int = WIDTH,
    image_height: int = HEIGHT,
    top_offset: int = 70,
    y_base: int = 112,
    text_scale: float = TEXT_SCALE,
    heatmap_samples: list[dict[str, Any]] | None = None,
) -> bytes:
    image = Image.new("RGB", (image_width, image_height), "#f4f6f5")
    draw = ImageDraw.Draw(image, "RGBA")
    draw.rectangle((0, 0, image_width, image_height), fill="#dfe7e1")

    project = _projector(bounds, image_width, image_height, top_offset, y_base)
    for zoom, tile_x, tile_y, data in tile_data:
        try:
            tile = Image.open(BytesIO(data)).convert("RGB")
        except OSError:
            continue
        north, west, south, east = _tile_bounds(zoom, tile_x, tile_y)
        x1, y1 = project(_to_xy(north, west, bounds))
        x2, y2 = project(_to_xy(south, east, bounds))
        box = (
            int(min(x1, x2)),
            int(min(y1, y2)),
            max(1, int(abs(x2 - x1))),
            max(1, int(abs(y2 - y1))),
        )
        tile = tile.resize((box[2], box[3]))
        intersection = _intersect_rect(
            (box[0], box[1], box[0] + box[2], box[1] + box[3]),
            (MAP_LEFT, MAP_TOP, image_width, image_height),
        )
        if intersection is None:
            continue
        crop = (
            intersection[0] - box[0],
            intersection[1] - box[1],
            intersection[2] - box[0],
            intersection[3] - box[1],
        )
        image.paste(tile.crop(crop), (intersection[0], intersection[1]))

    if heatmap_samples:
        _apply_heatmap(
            image,
            bounds,
            heatmap_samples,
            image_width,
            image_height,
            top_offset,
            y_base,
        )

    label_font = _font(8, text_scale)

    labels: list[tuple[str, float, float]] = []
    for index, zone in enumerate(zones):
        color = _hex_to_rgba(_zone_color(index), 72)
        outline = _hex_to_rgba(_zone_color(index), 255)
        if _is_circle(zone):
            center = _to_xy(float(zone["center"][0]), float(zone["center"][1]), bounds)
            x, y = project(center)
            radius = max(
                4,
                _radius_px(
                    float(zone["radius_m"]), bounds, image_width, image_height, top_offset
                ),
            )
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color, outline=outline, width=5)
            labels.append((str(zone["name"]), x, y))
        elif isinstance(zone.get("polygon"), list):
            points = [
                project(_to_xy(float(point[0]), float(point[1]), bounds))
                for point in zone["polygon"]
                if isinstance(point, list) and len(point) == 2
            ]
            if len(points) < 3:
                continue
            draw.polygon(points, fill=color)
            draw.line([*points, points[0]], fill=outline, width=5)
            cx = sum(x for x, _ in points) / len(points)
            cy = sum(y for _, y in points) / len(points)
            labels.append((str(zone["name"]), cx, cy))

    for text, x, y in labels:
        _draw_label(draw, text, x, y, label_font, text_scale)

    if mower_point:
        x, y = project(_to_xy(mower_point[0], mower_point[1], bounds))
        marker_radius = 34
        draw.ellipse(
            (x - marker_radius, y - marker_radius, x + marker_radius, y + marker_radius),
            fill="#256d4d",
            outline="#ffffff",
            width=7,
        )
        # Simple white mower glyph based on mdi:robot-mower proportions.
        glyph = [(x - 22, y - 9), (x + 4, y - 9), (x + 22, y + 9), (x + 22, y + 18), (x - 22, y + 18)]
        draw.polygon(glyph, fill="#ffffff")
        draw.ellipse((x - 22, y + 5, x - 8, y + 19), fill="#256d4d")
        draw.ellipse((x + 9, y + 8, x + 22, y + 21), fill="#256d4d")

    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _apply_heatmap(
    image: Image.Image,
    bounds: dict[str, float],
    samples: list[dict[str, Any]],
    image_width: int,
    image_height: int,
    top_offset: int,
    y_base: int,
) -> None:
    """Composite an age-decayed smooth stuck/ok heatmap over the satellite map."""
    now = dt_util.utcnow()
    max_age_seconds = HEATMAP_MAX_AGE.total_seconds()
    scale = 0.5
    layer_size = (round(image_width * scale), round(image_height * scale))
    layer_width, layer_height = layer_size
    red_values = [0] * (layer_width * layer_height)
    green_values = [0] * (layer_width * layer_height)
    project = _projector(bounds, image_width, image_height, top_offset, y_base)
    sample_radius = max(3, round(5 * scale))

    for sample in samples:
        latitude = _coerce_float(sample.get("latitude"))
        longitude = _coerce_float(sample.get("longitude"))
        sample_time = _sample_datetime(sample)
        if latitude is None or longitude is None or sample_time is None:
            continue
        age_seconds = max(0.0, (now - sample_time).total_seconds())
        weight = max(0.0, 1.0 - (age_seconds / max_age_seconds))
        if weight <= 0:
            continue
        x, y = project(_to_xy(latitude, longitude, bounds))
        layer_x = round(x * scale)
        layer_y = round(y * scale)
        intensity = round(85 + 170 * weight)
        values = red_values if sample.get("stuck") else green_values
        if sample.get("stuck"):
            sample_intensity = intensity
        else:
            sample_intensity = round(intensity * 0.9)
        for offset_y in range(-sample_radius, sample_radius + 1):
            point_y = layer_y + offset_y
            if point_y < 0 or point_y >= layer_height:
                continue
            for offset_x in range(-sample_radius, sample_radius + 1):
                if offset_x * offset_x + offset_y * offset_y > sample_radius * sample_radius:
                    continue
                point_x = layer_x + offset_x
                if point_x < 0 or point_x >= layer_width:
                    continue
                index = point_y * layer_width + point_x
                values[index] = min(255, values[index] + sample_intensity)

    blur_radius = max(4, round(9 * scale))
    red = Image.frombytes("L", layer_size, bytes(red_values))
    green = Image.frombytes("L", layer_size, bytes(green_values))
    red = red.filter(ImageFilter.GaussianBlur(blur_radius))
    green = green.filter(ImageFilter.GaussianBlur(blur_radius))

    overlay = Image.new("RGBA", layer_size, (0, 0, 0, 0))
    red_pixels = red.load()
    green_pixels = green.load()
    overlay_pixels = overlay.load()
    for y in range(layer_height):
        for x in range(layer_width):
            red_value = red_pixels[x, y]
            green_value = green_pixels[x, y]
            value = max(red_value, green_value)
            if value < 3:
                continue
            alpha = min(185, round(value * 1.15))
            if red_value >= green_value:
                overlay_pixels[x, y] = (235, 38, 38, alpha)
            else:
                overlay_pixels[x, y] = (30, 180, 92, round(alpha * 0.9))

    overlay = overlay.resize((image_width, image_height), Image.Resampling.BICUBIC)
    image.paste(Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB"))


def _sample_datetime(sample: dict[str, Any]):
    value = sample.get("ts")
    if not isinstance(value, str):
        return None
    return dt_util.parse_datetime(value)


def _font(size: int, text_scale: float = TEXT_SCALE):
    scaled_size = round(size * text_scale)
    for path in FONT_PATHS:
        try:
            return ImageFont.truetype(path, scaled_size)
        except OSError:
            continue
    return ImageFont.load_default(scaled_size)


def _draw_label(
    draw: ImageDraw.ImageDraw, text: str, x: float, y: float, font, text_scale: float
) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    pos = (x - width / 2, y - height / 2)
    pad_x = round(4 * text_scale)
    pad_y = round(2 * text_scale)
    box = (
        pos[0] - pad_x,
        pos[1] - pad_y,
        pos[0] + width + pad_x,
        pos[1] + height + pad_y,
    )
    draw.rounded_rectangle(box, radius=round(5 * text_scale), fill=(255, 255, 255, 218))
    draw.rounded_rectangle(box, radius=round(5 * text_scale), outline=(23, 32, 27, 80), width=1)
    draw.text(pos, text, fill="#17201b", font=font)


def _hex_to_rgba(color: str, alpha: int) -> tuple[int, int, int, int]:
    color = color.lstrip("#")
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16), alpha


def _intersect_rect(
    first: tuple[int, int, int, int], second: tuple[int, int, int, int]
) -> tuple[int, int, int, int] | None:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def _lat_lon_bounds(bounds: dict[str, float]) -> dict[str, float]:
    reference_lat = bounds["reference_lat"]

    def lon_from_x(x: float) -> float:
        return math.degrees(x / (EARTH_RADIUS_M * math.cos(math.radians(reference_lat))))

    def lat_from_y(y: float) -> float:
        return math.degrees(y / EARTH_RADIUS_M)

    return {
        "north": lat_from_y(bounds["max_y"]),
        "south": lat_from_y(bounds["min_y"]),
        "west": lon_from_x(bounds["min_x"]),
        "east": lon_from_x(bounds["max_x"]),
    }


def _select_tiles(lat_lon_bounds: dict[str, float]) -> tuple[int, list[tuple[int, int]]]:
    for zoom in range(MAX_TILE_ZOOM, MIN_TILE_ZOOM - 1, -1):
        tiles = _tiles_for_bounds(lat_lon_bounds, zoom)
        if len(tiles) <= MAX_TILE_COUNT:
            return zoom, tiles
    return MIN_TILE_ZOOM, _tiles_for_bounds(lat_lon_bounds, MIN_TILE_ZOOM)[:MAX_TILE_COUNT]


def _tiles_for_bounds(
    lat_lon_bounds: dict[str, float], zoom: int
) -> list[tuple[int, int]]:
    west = lat_lon_bounds["west"]
    east = lat_lon_bounds["east"]
    north = lat_lon_bounds["north"]
    south = lat_lon_bounds["south"]
    min_x, min_y = _lat_lon_to_tile(north, west, zoom)
    max_x, max_y = _lat_lon_to_tile(south, east, zoom)
    return [
        (x, y)
        for x in range(min(min_x, max_x), max(min_x, max_x) + 1)
        for y in range(min(min_y, max_y), max(min_y, max_y) + 1)
    ]


def _lat_lon_to_tile(lat: float, lon: float, zoom: int) -> tuple[int, int]:
    lat = max(min(lat, 85.05112878), -85.05112878)
    n = 2**zoom
    x = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int(
        (1.0 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi)
        / 2.0
        * n
    )
    return max(0, min(n - 1, x)), max(0, min(n - 1, y))


def _tile_bounds(zoom: int, x: int, y: int) -> tuple[float, float, float, float]:
    north, west = _tile_to_lat_lon(x, y, zoom)
    south, east = _tile_to_lat_lon(x + 1, y + 1, zoom)
    return north, west, south, east


def _tile_to_lat_lon(x: int, y: int, zoom: int) -> tuple[float, float]:
    n = 2**zoom
    lon = x / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    lat = math.degrees(lat_rad)
    return lat, lon
