"""Binary sensors for Robot Mower Yard."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import CONF_ENTRY_KIND, ENTRY_KIND_PROVIDER
from .coordinator import ProviderCoordinator, runtime
from .entity import mower_attributes, mower_device_info
from .models import MowerSnapshot
from .yard import find_zones


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    if entry.data[CONF_ENTRY_KIND] != ENTRY_KIND_PROVIDER:
        return
    coordinator: ProviderCoordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = []
    for mower_id in coordinator.data:
        entities.extend(
            [
                MowerProblemBinarySensor(coordinator, mower_id),
                MowerChargingBinarySensor(coordinator, mower_id),
            ]
        )
    async_add_entities(entities)

    added_zone_entities: set[tuple[str, str]] = set()

    @callback
    def add_missing_zone_entities() -> None:
        data = runtime(hass)
        yard = data["yards"].get(coordinator.yard_entry_id)
        if yard is None:
            return
        entities: list[BinarySensorEntity] = []
        for mower_id in coordinator.data:
            for zone_name in yard.zone_names:
                key = (mower_id, zone_name)
                if key in added_zone_entities:
                    continue
                added_zone_entities.add(key)
                entities.append(MowerZoneBinarySensor(coordinator, mower_id, zone_name))
        if entities:
            async_add_entities(entities)

    add_missing_zone_entities()
    data = runtime(hass)
    yard = data["yards"].get(coordinator.yard_entry_id)
    if yard is not None:
        entry.async_on_unload(yard.async_add_listener(add_missing_zone_entities))


class MowerProblemBinarySensor(
    CoordinatorEntity[ProviderCoordinator], BinarySensorEntity
):
    """Mower problem sensor."""

    _attr_name = "Problem"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: ProviderCoordinator, mower_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.mower_id = mower_id
        self._attr_unique_id = f"{mower_id}_problem"

    @property
    def snapshot(self) -> MowerSnapshot:
        """Return the current mower snapshot."""
        return self.coordinator.data[self.mower_id]

    @property
    def is_on(self) -> bool:
        """Return true if the mower has a problem."""
        return self.snapshot.is_problem

    @property
    def device_info(self):
        """Return mower device info."""
        return mower_device_info(self.coordinator.yard_entry_id, self.snapshot)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return common attributes."""
        return {
            **mower_attributes(self.coordinator.yard_entry_id, self.snapshot),
            "error_code": self.snapshot.error_code,
        }


class MowerChargingBinarySensor(
    CoordinatorEntity[ProviderCoordinator], BinarySensorEntity
):
    """Mower battery charging sensor."""

    _attr_name = "Charging"
    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING

    def __init__(self, coordinator: ProviderCoordinator, mower_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.mower_id = mower_id
        self._attr_unique_id = f"{mower_id}_charging"

    @property
    def snapshot(self) -> MowerSnapshot:
        """Return the current mower snapshot."""
        return self.coordinator.data[self.mower_id]

    @property
    def is_on(self) -> bool | None:
        """Return true if the mower is charging."""
        return _charging_state(self.snapshot)

    @property
    def device_info(self):
        """Return mower device info."""
        return mower_device_info(self.coordinator.yard_entry_id, self.snapshot)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return common attributes."""
        return {
            **mower_attributes(self.coordinator.yard_entry_id, self.snapshot),
            "battery": self.snapshot.battery_percent,
            "status": self.snapshot.state,
            "activity": self.snapshot.activity,
        }


class MowerZoneBinarySensor(
    CoordinatorEntity[ProviderCoordinator], BinarySensorEntity
):
    """Sensor indicating whether the mower is in a configured yard zone."""

    def __init__(
        self, coordinator: ProviderCoordinator, mower_id: str, zone_name: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.mower_id = mower_id
        self.zone_name = zone_name
        self._attr_name = f"In {zone_name}"
        self._attr_unique_id = f"{mower_id}_in_zone_{slugify(zone_name)}"

    @property
    def snapshot(self) -> MowerSnapshot:
        """Return the current mower snapshot."""
        return self.coordinator.data[self.mower_id]

    @property
    def is_on(self) -> bool:
        """Return true if the mower is in this zone."""
        return self.zone_name in find_zones(
            self.snapshot.latitude,
            self.snapshot.longitude,
            self._zones(),
        )

    @property
    def device_info(self):
        """Return mower device info."""
        return mower_device_info(self.coordinator.yard_entry_id, self.snapshot)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return zone attributes."""
        return {
            **mower_attributes(self.coordinator.yard_entry_id, self.snapshot),
            "zone": self.zone_name,
            "yard_zones": find_zones(
                self.snapshot.latitude,
                self.snapshot.longitude,
                self._zones(),
            ),
        }

    def _zones(self) -> list[dict[str, Any]]:
        data = runtime(self.coordinator.hass)
        yard = data["yards"].get(self.coordinator.yard_entry_id)
        return yard.zones if yard else []


def _charging_state(snapshot: MowerSnapshot) -> bool | None:
    raw_state = _raw_battery_charging_state(snapshot.raw)
    if raw_state is not None:
        return raw_state
    for value in (snapshot.activity, snapshot.state):
        if value is None:
            continue
        text = str(value).lower()
        if text in {"charging", "charge", "charging_in_station"}:
            return True
        if text not in {"", "unknown", "unavailable", "none"}:
            return False
    return None


def _raw_battery_charging_state(raw: dict[str, Any]) -> bool | None:
    attributes = raw.get("attributes") if isinstance(raw, dict) else None
    battery = attributes.get("battery") if isinstance(attributes, dict) else None
    if not isinstance(battery, dict):
        return None
    for key in ("charging", "isCharging", "is_charging"):
        if key in battery:
            return _coerce_charging_bool(battery.get(key))
    for key in ("state", "status", "batteryState", "battery_state"):
        value = battery.get(key)
        if value is None:
            continue
        parsed = _coerce_charging_bool(value)
        if parsed is not None:
            return parsed
    return None


def _coerce_charging_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).lower()
    if text in {"charging", "charge", "true", "on", "yes", "1"}:
        return True
    if text in {"not_charging", "discharging", "false", "off", "no", "0"}:
        return False
    return None
