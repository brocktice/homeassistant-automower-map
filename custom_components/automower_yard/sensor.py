"""Sensors for Automower Yard."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfLength, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_ACTIVITY,
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    ATTR_LAST_POSITION_EVENT,
    ATTR_LAST_WEBSOCKET_EVENT,
    ATTR_STATE,
    ATTR_WEBSOCKET_CONNECTED,
    ATTR_YARD_ZONES,
    CUTTING_HEIGHT_UNIT_IN,
)
from .coordinator import AutomowerYardCoordinator
from .cutting_height import (
    ATTR_CUTTING_HEIGHT_CM,
    ATTR_CUTTING_HEIGHT_IN,
    ATTR_CUTTING_HEIGHT_SETTING,
    cutting_height_cm,
    cutting_height_in,
)
from .entity import AutomowerYardEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors."""
    coordinator: AutomowerYardCoordinator = entry.runtime_data
    entities = []
    for mower_id in coordinator.data:
        entities.extend(
            [
                AutomowerStatusSensor(coordinator, mower_id),
                AutomowerYardZoneSensor(coordinator, mower_id),
                AutomowerBatterySensor(coordinator, mower_id),
                AutomowerRemainingChargingTimeSensor(coordinator, mower_id),
                AutomowerCuttingHeightSensor(coordinator, mower_id),
                AutomowerStatisticSensor(
                    coordinator,
                    mower_id,
                    "Charging Cycles",
                    "numberOfChargingCycles",
                    "charging_cycles",
                ),
                AutomowerStatisticSensor(
                    coordinator,
                    mower_id,
                    "Collisions",
                    "numberOfCollisions",
                    "collisions",
                ),
                AutomowerStatisticSensor(
                    coordinator,
                    mower_id,
                    "Total Charging Time",
                    "totalChargingTime",
                    "total_charging_time",
                    SensorDeviceClass.DURATION,
                    UnitOfTime.SECONDS,
                ),
                AutomowerStatisticSensor(
                    coordinator,
                    mower_id,
                    "Total Cutting Time",
                    "totalCuttingTime",
                    "total_cutting_time",
                    SensorDeviceClass.DURATION,
                    UnitOfTime.SECONDS,
                ),
                AutomowerStatisticSensor(
                    coordinator,
                    mower_id,
                    "Total Running Time",
                    "totalRunningTime",
                    "total_running_time",
                    SensorDeviceClass.DURATION,
                    UnitOfTime.SECONDS,
                ),
                AutomowerStatisticSensor(
                    coordinator,
                    mower_id,
                    "Total Searching Time",
                    "totalSearchingTime",
                    "total_searching_time",
                    SensorDeviceClass.DURATION,
                    UnitOfTime.SECONDS,
                ),
                AutomowerStatisticSensor(
                    coordinator,
                    mower_id,
                    "Total Drive Distance",
                    "totalDriveDistance",
                    "total_drive_distance",
                    SensorDeviceClass.DISTANCE,
                    UnitOfLength.METERS,
                ),
                AutomowerStatisticSensor(
                    coordinator,
                    mower_id,
                    "Uptime",
                    "upTime",
                    "uptime",
                    SensorDeviceClass.DURATION,
                    UnitOfTime.SECONDS,
                ),
            ]
        )
    async_add_entities(entities)


class AutomowerStatusSensor(AutomowerYardEntity, SensorEntity):
    """Mower status sensor."""

    _attr_name = "Status"

    def __init__(self, coordinator: AutomowerYardCoordinator, mower_id: str) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, mower_id)
        self._attr_unique_id = f"{mower_id}_status"

    @property
    def native_value(self) -> str | None:
        """Return mower state."""
        mower = self.attributes.get("mower") or {}
        return mower.get("state")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return status attributes."""
        mower = self.attributes.get("mower") or {}
        return {
            **super().extra_state_attributes,
            ATTR_ACTIVITY: mower.get("activity"),
            ATTR_STATE: mower.get("state"),
            ATTR_WEBSOCKET_CONNECTED: self.coordinator.websocket_connected,
            ATTR_LAST_WEBSOCKET_EVENT: self.coordinator.last_websocket_event,
            ATTR_LAST_POSITION_EVENT: self.coordinator.last_position_event,
        }


class AutomowerYardZoneSensor(AutomowerYardEntity, SensorEntity):
    """Named yard location sensor."""

    _attr_name = "Yard Zone"

    def __init__(self, coordinator: AutomowerYardCoordinator, mower_id: str) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, mower_id)
        self._attr_unique_id = f"{mower_id}_yard_zone"

    @property
    def native_value(self) -> str | None:
        """Return configured yard zone."""
        return self.attributes.get("yard_zone") or "Unknown"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return location attributes."""
        latitude, longitude = _latest_position(self.attributes)
        return {
            **super().extra_state_attributes,
            ATTR_LATITUDE: latitude,
            ATTR_LONGITUDE: longitude,
            ATTR_YARD_ZONES: self.attributes.get("yard_zones") or [],
        }


class AutomowerBatterySensor(AutomowerYardEntity, SensorEntity):
    """Mower battery percentage sensor."""

    _attr_name = "Battery"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: AutomowerYardCoordinator, mower_id: str) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, mower_id)
        self._attr_unique_id = f"{mower_id}_battery"

    @property
    def native_value(self) -> int | None:
        """Return battery percentage."""
        return _coerce_int((self.attributes.get("battery") or {}).get("batteryPercent"))


class AutomowerRemainingChargingTimeSensor(AutomowerYardEntity, SensorEntity):
    """Mower remaining charging time sensor."""

    _attr_name = "Remaining Charging Time"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: AutomowerYardCoordinator, mower_id: str) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, mower_id)
        self._attr_unique_id = f"{mower_id}_remaining_charging_time"

    @property
    def native_value(self) -> int | None:
        """Return remaining charging time in minutes."""
        return _coerce_int(
            (self.attributes.get("battery") or {}).get("remainingChargingTime")
        )


class AutomowerCuttingHeightSensor(AutomowerYardEntity, SensorEntity):
    """Mower cutting height setting sensor."""

    _attr_name = "Cutting Height"
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: AutomowerYardCoordinator, mower_id: str) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, mower_id)
        self._attr_unique_id = f"{mower_id}_cutting_height"

    @property
    def native_value(self) -> float | None:
        """Return approximate cutting height in the configured unit."""
        if (
            self.coordinator.cutting_height_unit(self.mower_id)
            == CUTTING_HEIGHT_UNIT_IN
        ):
            return cutting_height_in(self._cutting_height_setting, self.mower_model)
        return cutting_height_cm(self._cutting_height_setting, self.mower_model)

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the configured cutting height unit."""
        if (
            self.coordinator.cutting_height_unit(self.mower_id)
            == CUTTING_HEIGHT_UNIT_IN
        ):
            return UnitOfLength.INCHES
        return UnitOfLength.CENTIMETERS

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return cutting height attributes."""
        setting = self._cutting_height_setting
        return {
            **super().extra_state_attributes,
            ATTR_CUTTING_HEIGHT_SETTING: setting,
            ATTR_CUTTING_HEIGHT_CM: cutting_height_cm(setting, self.mower_model),
            ATTR_CUTTING_HEIGHT_IN: cutting_height_in(setting, self.mower_model),
        }

    @property
    def mower_model(self) -> str | None:
        """Return mower model."""
        return (self.attributes.get("system") or {}).get("model")

    @property
    def _cutting_height_setting(self) -> int | None:
        """Return raw cutting height setting."""
        return _coerce_int((self.attributes.get("settings") or {}).get("cuttingHeight"))


class AutomowerStatisticSensor(AutomowerYardEntity, SensorEntity):
    """Mower statistics sensor."""

    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(
        self,
        coordinator: AutomowerYardCoordinator,
        mower_id: str,
        name: str,
        statistic_key: str,
        unique_suffix: str,
        device_class: SensorDeviceClass | None = None,
        unit: str | None = None,
    ) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, mower_id)
        self._attr_name = name
        self._statistic_key = statistic_key
        self._attr_unique_id = f"{mower_id}_{unique_suffix}"
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self) -> int | None:
        """Return statistic value."""
        return _coerce_int(
            (self.attributes.get("statistics") or {}).get(self._statistic_key)
        )


def _latest_position(attributes: dict[str, Any]) -> tuple[float | None, float | None]:
    positions = attributes.get("positions")
    if not isinstance(positions, list) or not positions:
        return None, None
    try:
        return float(positions[0]["latitude"]), float(positions[0]["longitude"])
    except (KeyError, TypeError, ValueError):
        return None, None


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
