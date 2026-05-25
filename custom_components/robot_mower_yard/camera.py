"""Cameras for Robot Mower Yard."""

from __future__ import annotations

from io import BytesIO
import math
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from homeassistant.components.camera import Camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ENTRY_KIND, ENTRY_KIND_PROVIDER, ENTRY_KIND_YARD
from .const import ATTR_HEATMAP_MAX_AGE_DAYS, ATTR_HEATMAP_SAMPLE_COUNT
from .coordinator import HEATMAP_MAX_AGE
from .coordinator import ProviderCoordinator, YardCoordinator, runtime
from .entity import mower_device_info, yard_device_info
from .heatmap import apply_signed_evidence_heatmap
from .models import MowerSnapshot

WIDTH = 900
HEIGHT = 500
PADDING = 44
EARTH_RADIUS_M = 6371000


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up cameras."""
    coordinator = entry.runtime_data
    if entry.data[CONF_ENTRY_KIND] == ENTRY_KIND_YARD:
        async_add_entities([YardOverviewCamera(coordinator), YardHeatmapCamera(coordinator)])
    elif entry.data[CONF_ENTRY_KIND] == ENTRY_KIND_PROVIDER:
        async_add_entities(MowerSnapshotCamera(coordinator, mower_id) for mower_id in coordinator.data)


class YardOverviewCamera(CoordinatorEntity[YardCoordinator], Camera):
    """Simple yard overview camera."""

    _attr_name = "Yard Overview"

    def __init__(self, coordinator: YardCoordinator) -> None:
        """Initialize the camera."""
        super().__init__(coordinator)
        Camera.__init__(self)
        self.content_type = "image/png"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_yard_overview"
        self._attr_device_info = yard_device_info(
            coordinator.config_entry.entry_id,
            coordinator.config_entry.title,
        )

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes:
        """Return a yard overview map containing all mower positions."""
        return await self.hass.async_add_executor_job(
            render_yard_map_image,
            self.coordinator.config_entry.title,
            self.coordinator.zones,
            list((self.coordinator.data or {}).values()),
            [],
        )


class YardHeatmapCamera(YardOverviewCamera):
    """Camera entity that renders a signed all-mower yard heatmap."""

    _attr_name = "Yard Heatmap"

    def __init__(self, coordinator: YardCoordinator) -> None:
        """Initialize the camera."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_yard_heatmap"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return heatmap attributes."""
        return {
            ATTR_HEATMAP_SAMPLE_COUNT: len(self.coordinator.heatmap_samples()),
            ATTR_HEATMAP_MAX_AGE_DAYS: HEATMAP_MAX_AGE.days,
        }

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes:
        """Return a yard heatmap containing all provider samples."""
        return await self.hass.async_add_executor_job(
            render_yard_map_image,
            f"{self.coordinator.config_entry.title} Heatmap",
            self.coordinator.zones,
            list((self.coordinator.data or {}).values()),
            self.coordinator.heatmap_samples(),
        )


class MowerSnapshotCamera(CoordinatorEntity[ProviderCoordinator], Camera):
    """Simple per-mower camera."""

    _attr_name = "Snapshot"

    def __init__(self, coordinator: ProviderCoordinator, mower_id: str) -> None:
        """Initialize the camera."""
        super().__init__(coordinator)
        Camera.__init__(self)
        self.content_type = "image/png"
        self.mower_id = mower_id
        self._attr_unique_id = f"{mower_id}_snapshot"

    @property
    def snapshot(self) -> MowerSnapshot:
        """Return mower snapshot."""
        return self.coordinator.data[self.mower_id]

    @property
    def device_info(self):
        """Return mower device info."""
        return mower_device_info(self.coordinator.yard_entry_id, self.snapshot)

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes:
        """Return a yard map centered on the mower's current context."""
        snapshot = self.snapshot
        yard = runtime(self.hass)["yards"].get(self.coordinator.yard_entry_id)
        zones = yard.zones if yard is not None else []
        mowers = list((yard.data or {}).values()) if yard is not None and yard.data else []
        if snapshot.stable_id not in {mower.stable_id for mower in mowers}:
            mowers.append(snapshot)
        return await self.hass.async_add_executor_job(
            render_yard_map_image,
            snapshot.name or snapshot.stable_id,
            zones,
            mowers,
            [],
        )


def _render_lines(lines: list[str]) -> bytes:
    image = Image.new("RGB", (WIDTH, HEIGHT), "#f4f6f5")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    draw.rectangle((28, 28, WIDTH - 28, HEIGHT - 28), fill="#ffffff", outline="#c9d4ce")
    y = 52
    for line in lines:
        draw.text((52, y), line, fill="#17201b", font=font)
        y += 28
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def render_yard_map_image(
    title: str,
    zones: list[dict[str, Any]],
    mowers: list[MowerSnapshot],
    heatmap_samples: list[dict[str, Any]],
) -> bytes:
    image = Image.new("RGB", (WIDTH, HEIGHT), "#f4f6f5")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    draw.rectangle((24, 24, WIDTH - 24, HEIGHT - 24), fill="#ffffff", outline="#c9d4ce")
    draw.text((42, 42), f"{title} Yard Overview", fill="#17201b", font=font)

    points = _collect_points(zones, mowers)
    points.extend(
        (float(sample["latitude"]), float(sample["longitude"]))
        for sample in heatmap_samples
        if _coerce_float(sample.get("latitude")) is not None
        and _coerce_float(sample.get("longitude")) is not None
    )
    if not points:
        draw.text((42, 76), "No mower positions or yard zones available", fill="#52635a", font=font)
        return _png(image)

    bounds = _bounds(points)
    project = _projector(bounds)
    map_box = (PADDING, 82, WIDTH - PADDING, HEIGHT - PADDING)
    draw.rectangle(map_box, fill="#edf3ef", outline="#d6ded8")
    if heatmap_samples:
        evidence_points = []
        for sample in heatmap_samples:
            latitude = _coerce_float(sample.get("latitude"))
            longitude = _coerce_float(sample.get("longitude"))
            if latitude is None or longitude is None:
                continue
            x, y = project((latitude, longitude))
            evidence_points.append(
                (
                    round(x),
                    round(y),
                    -1.0 if sample.get("stuck") else 1.0,
                    1.0,
                )
            )
        if evidence_points:
            apply_signed_evidence_heatmap(
                image,
                (max(1, WIDTH // 4), max(1, HEIGHT // 4)),
                [
                    (round(x / 4), round(y / 4), value, weight)
                    for x, y, value, weight in evidence_points
                ],
                18,
            )
            draw = ImageDraw.Draw(image)
            draw.rectangle(map_box, outline="#d6ded8")

    for index, zone in enumerate(zones):
        color = _zone_color(index)
        if _is_circle(zone):
            center = (float(zone["center"][0]), float(zone["center"][1]))
            x, y = project(center)
            radius = _radius_px(center, float(zone["radius_m"]), project)
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), outline=color, width=3)
            draw.text((x + 6, y + 6), str(zone["name"]), fill=color, font=font)
        elif isinstance(zone.get("polygon"), list):
            polygon = [
                project((float(point[0]), float(point[1])))
                for point in zone["polygon"]
                if isinstance(point, list) and len(point) == 2
            ]
            if len(polygon) >= 3:
                draw.polygon(polygon, fill=_zone_fill(color), outline=color)
                label_x = sum(point[0] for point in polygon) / len(polygon)
                label_y = sum(point[1] for point in polygon) / len(polygon)
                draw.text((label_x + 6, label_y + 6), str(zone["name"]), fill=color, font=font)

    for mower in mowers:
        if mower.latitude is None or mower.longitude is None:
            continue
        x, y = project((mower.latitude, mower.longitude))
        color = "#b42318" if mower.is_problem else "#256d4d"
        draw.ellipse((x - 9, y - 9, x + 9, y + 9), fill=color, outline="#ffffff", width=3)
        label = mower.name or mower.stable_id
        draw.text((x + 12, y - 7), label, fill="#17201b", font=font)

    draw.text((42, HEIGHT - 30), f"{len(mowers)} mowers", fill="#52635a", font=font)
    return _png(image)


def _collect_points(
    zones: list[dict[str, Any]], mowers: list[MowerSnapshot]
) -> list[tuple[float, float]]:
    points = [
        (mower.latitude, mower.longitude)
        for mower in mowers
        if mower.latitude is not None and mower.longitude is not None
    ]
    for zone in zones:
        if _is_circle(zone):
            lat = float(zone["center"][0])
            lon = float(zone["center"][1])
            radius_degrees = float(zone["radius_m"]) / 111111.0
            points.extend(
                [
                    (lat - radius_degrees, lon),
                    (lat + radius_degrees, lon),
                    (lat, lon - radius_degrees),
                    (lat, lon + radius_degrees),
                ]
            )
        elif isinstance(zone.get("polygon"), list):
            points.extend(
                (float(point[0]), float(point[1]))
                for point in zone["polygon"]
                if isinstance(point, list) and len(point) == 2
            )
    return points


def _bounds(points: list[tuple[float, float]]) -> dict[str, float]:
    latitudes = [point[0] for point in points]
    longitudes = [point[1] for point in points]
    min_lat = min(latitudes)
    max_lat = max(latitudes)
    min_lon = min(longitudes)
    max_lon = max(longitudes)
    if math.isclose(min_lat, max_lat):
        min_lat -= 0.0002
        max_lat += 0.0002
    if math.isclose(min_lon, max_lon):
        min_lon -= 0.0002
        max_lon += 0.0002
    return {
        "min_lat": min_lat,
        "max_lat": max_lat,
        "min_lon": min_lon,
        "max_lon": max_lon,
    }


def _projector(bounds: dict[str, float]):
    usable_width = WIDTH - PADDING * 2
    usable_height = HEIGHT - PADDING - 82
    lat_span = bounds["max_lat"] - bounds["min_lat"]
    lon_span = bounds["max_lon"] - bounds["min_lon"]

    def project(point: tuple[float, float]) -> tuple[float, float]:
        lat, lon = point
        x = PADDING + ((lon - bounds["min_lon"]) / lon_span) * usable_width
        y = 82 + ((bounds["max_lat"] - lat) / lat_span) * usable_height
        return x, y

    return project


def _radius_px(center: tuple[float, float], radius_m: float, project) -> float:
    lat, lon = center
    edge = (lat + radius_m / 111111.0, lon)
    x1, y1 = project(center)
    x2, y2 = project(edge)
    return max(4.0, math.dist((x1, y1), (x2, y2)))


def _is_circle(zone: dict[str, Any]) -> bool:
    return (
        isinstance(zone.get("center"), list)
        and len(zone["center"]) == 2
        and isinstance(zone.get("radius_m"), int | float)
    )


def _zone_color(index: int) -> str:
    return ("#256d4d", "#2f5fb3", "#9c5a00", "#7b3f98", "#0f766e")[index % 5]


def _zone_fill(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    base = (237, 243, 239)
    foreground = (int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16))
    alpha = 0.22
    return tuple(round(foreground[i] * alpha + base[i] * (1 - alpha)) for i in range(3))


def _png(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _coerce_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
