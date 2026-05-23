"""Entity helpers for Robot Mower Yard."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo

from .const import ATTR_PROVIDER, ATTR_PROVIDER_MOWER_ID, ATTR_YARD_ENTRY_ID, DOMAIN
from .models import MowerSnapshot


def yard_device_info(entry_id: str, name: str) -> DeviceInfo:
    """Return the yard device info."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"yard_{entry_id}")},
        manufacturer="Robot Mower Yard",
        model="Yard",
        name=name,
    )


def mower_device_info(yard_entry_id: str, snapshot: MowerSnapshot) -> DeviceInfo:
    """Return mower device info."""
    return DeviceInfo(
        identifiers={(DOMAIN, snapshot.stable_id)},
        manufacturer=snapshot.provider.title(),
        model=snapshot.model,
        name=snapshot.name or snapshot.stable_id,
        serial_number=snapshot.serial_number,
        via_device=(DOMAIN, f"yard_{yard_entry_id}"),
    )


def mower_attributes(yard_entry_id: str, snapshot: MowerSnapshot) -> dict[str, object]:
    """Return common mower attributes."""
    return {
        ATTR_PROVIDER: snapshot.provider,
        ATTR_PROVIDER_MOWER_ID: snapshot.mower_id,
        ATTR_YARD_ENTRY_ID: yard_entry_id,
    }
