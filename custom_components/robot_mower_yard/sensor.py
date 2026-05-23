"""Sensors for Robot Mower Yard."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfLength, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ENTRY_KIND, ENTRY_KIND_PROVIDER, ENTRY_KIND_YARD
from .coordinator import ProviderCoordinator, YardCoordinator, runtime
from .const import CUTTING_HEIGHT_UNIT_IN
from .cutting_height import (
    ATTR_CUTTING_HEIGHT_CM,
    ATTR_CUTTING_HEIGHT_IN,
    ATTR_CUTTING_HEIGHT_SETTING,
    cutting_height_cm,
    cutting_height_in,
)
from .entity import mower_attributes, mower_device_info, yard_device_info
from .models import MowerSnapshot
from .yard import find_zone, find_zones


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors."""
    coordinator = entry.runtime_data
    if entry.data[CONF_ENTRY_KIND] == ENTRY_KIND_YARD:
        async_add_entities([YardMowerCountSensor(coordinator)])
        return
    if entry.data[CONF_ENTRY_KIND] == ENTRY_KIND_PROVIDER:
        entities = []
        for mower_id in coordinator.data:
            snapshot = coordinator.data[mower_id]
            mower_entities: list[SensorEntity] = [
                MowerStatusSensor(coordinator, mower_id),
                MowerYardZoneSensor(coordinator, mower_id),
                MowerBatterySensor(coordinator, mower_id),
            ]
            raw_attributes = snapshot.raw.get("attributes") or {}
            if (raw_attributes.get("settings") or {}).get("cuttingHeight") is not None:
                mower_entities.append(MowerCuttingHeightSensor(coordinator, mower_id))
            if isinstance(raw_attributes.get("statistics"), dict):
                mower_entities.extend(
                    [
                        MowerRawStatisticSensor(
                        coordinator,
                        mower_id,
                        "Charging Cycles",
                        "numberOfChargingCycles",
                        "charging_cycles",
                        ),
                        MowerRawStatisticSensor(
                        coordinator,
                        mower_id,
                        "Collisions",
                        "numberOfCollisions",
                        "collisions",
                        ),
                        MowerRawStatisticSensor(
                        coordinator,
                        mower_id,
                        "Total Charging Time",
                        "totalChargingTime",
                        "total_charging_time",
                        SensorDeviceClass.DURATION,
                        UnitOfTime.SECONDS,
                        ),
                        MowerRawStatisticSensor(
                        coordinator,
                        mower_id,
                        "Total Cutting Time",
                        "totalCuttingTime",
                        "total_cutting_time",
                        SensorDeviceClass.DURATION,
                        UnitOfTime.SECONDS,
                        ),
                        MowerRawStatisticSensor(
                        coordinator,
                        mower_id,
                        "Total Running Time",
                        "totalRunningTime",
                        "total_running_time",
                        SensorDeviceClass.DURATION,
                        UnitOfTime.SECONDS,
                        ),
                        MowerRawStatisticSensor(
                        coordinator,
                        mower_id,
                        "Total Searching Time",
                        "totalSearchingTime",
                        "total_searching_time",
                        SensorDeviceClass.DURATION,
                        UnitOfTime.SECONDS,
                        ),
                        MowerRawStatisticSensor(
                        coordinator,
                        mower_id,
                        "Total Drive Distance",
                        "totalDriveDistance",
                        "total_drive_distance",
                        SensorDeviceClass.DISTANCE,
                        UnitOfLength.METERS,
                        ),
                        MowerRawStatisticSensor(
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
            entities.extend(mower_entities)
        async_add_entities(entities)


class YardMowerCountSensor(CoordinatorEntity[YardCoordinator], SensorEntity):
    """Sensor reporting how many mowers are attached to a yard."""

    _attr_name = "Mowers"
    _attr_icon = "mdi:robot-mower"

    def __init__(self, coordinator: YardCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_mowers"
        self._attr_device_info = yard_device_info(
            coordinator.config_entry.entry_id,
            coordinator.config_entry.title,
        )

    @property
    def native_value(self) -> int:
        """Return mower count."""
        return len(self.coordinator.data)


class MowerSensor(CoordinatorEntity[ProviderCoordinator], SensorEntity):
    """Base mower sensor."""

    def __init__(self, coordinator: ProviderCoordinator, mower_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.mower_id = mower_id

    @property
    def snapshot(self) -> MowerSnapshot:
        """Return the current mower snapshot."""
        return self.coordinator.data[self.mower_id]

    @property
    def device_info(self):
        """Return mower device info."""
        return mower_device_info(self.coordinator.yard_entry_id, self.snapshot)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return common attributes."""
        return mower_attributes(self.coordinator.yard_entry_id, self.snapshot)


class MowerStatusSensor(MowerSensor):
    """Mower status sensor."""

    _attr_name = "Status"

    def __init__(self, coordinator: ProviderCoordinator, mower_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, mower_id)
        self._attr_unique_id = f"{mower_id}_status"

    @property
    def native_value(self) -> str | None:
        """Return mower state."""
        return self.snapshot.state


class MowerBatterySensor(MowerSensor):
    """Mower battery sensor."""

    _attr_name = "Battery"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, coordinator: ProviderCoordinator, mower_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, mower_id)
        self._attr_unique_id = f"{mower_id}_battery"

    @property
    def native_value(self) -> int | None:
        """Return battery percent."""
        return self.snapshot.battery_percent


class MowerYardZoneSensor(MowerSensor):
    """Named yard location sensor."""

    _attr_name = "Yard Zone"

    def __init__(self, coordinator: ProviderCoordinator, mower_id: str) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, mower_id)
        self._attr_unique_id = f"{mower_id}_yard_zone"

    @property
    def native_value(self) -> str:
        """Return the smallest matching configured yard zone."""
        zones = self._zones()
        return (
            find_zone(self.snapshot.latitude, self.snapshot.longitude, zones)
            or "Unknown"
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return location attributes."""
        zones = self._zones()
        return {
            **super().extra_state_attributes,
            "latitude": self.snapshot.latitude,
            "longitude": self.snapshot.longitude,
            "yard_zones": find_zones(
                self.snapshot.latitude,
                self.snapshot.longitude,
                zones,
            ),
        }

    def _zones(self) -> list[dict[str, Any]]:
        data = runtime(self.coordinator.hass)
        yard = data["yards"].get(self.coordinator.yard_entry_id)
        return yard.zones if yard else []


class MowerCuttingHeightSensor(MowerSensor):
    """Mower cutting height setting sensor."""

    _attr_name = "Cutting Height"
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: ProviderCoordinator, mower_id: str) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, mower_id)
        self._attr_unique_id = f"{mower_id}_cutting_height"

    @property
    def native_value(self) -> float | None:
        """Return approximate cutting height in the configured unit."""
        if self.coordinator.cutting_height_unit(self.mower_id) == CUTTING_HEIGHT_UNIT_IN:
            return cutting_height_in(self._cutting_height_setting, self.snapshot.model)
        return cutting_height_cm(self._cutting_height_setting, self.snapshot.model)

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the configured cutting height unit."""
        if self.coordinator.cutting_height_unit(self.mower_id) == CUTTING_HEIGHT_UNIT_IN:
            return UnitOfLength.INCHES
        return UnitOfLength.CENTIMETERS

    @property
    def available(self) -> bool:
        """Return true if the provider exposes a cutting-height setting."""
        return super().available and self._cutting_height_setting is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return cutting height attributes."""
        setting = self._cutting_height_setting
        return {
            **super().extra_state_attributes,
            ATTR_CUTTING_HEIGHT_SETTING: setting,
            ATTR_CUTTING_HEIGHT_CM: cutting_height_cm(setting, self.snapshot.model),
            ATTR_CUTTING_HEIGHT_IN: cutting_height_in(setting, self.snapshot.model),
        }

    @property
    def _cutting_height_setting(self) -> int | None:
        """Return raw cutting height setting."""
        return _coerce_int(
            ((self.snapshot.raw.get("attributes") or {}).get("settings") or {}).get(
                "cuttingHeight"
            )
        )


class MowerRawStatisticSensor(MowerSensor):
    """Mower statistic from provider raw payload."""

    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(
        self,
        coordinator: ProviderCoordinator,
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
            ((self.snapshot.raw.get("attributes") or {}).get("statistics") or {}).get(
                self._statistic_key
            )
        )

    @property
    def available(self) -> bool:
        """Return true if the statistic exists."""
        return super().available and self.native_value is not None


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
