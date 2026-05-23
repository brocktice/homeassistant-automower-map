"""Existing Home Assistant entity provider."""

from __future__ import annotations

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import State

from ..const import (
    CONF_BATTERY_ENTITY,
    CONF_MOWER_NAME,
    CONF_PROBLEM_ENTITY,
    CONF_STATUS_ENTITY,
    CONF_TRACKER_ENTITY,
)
from ..models import MowerSnapshot
from .base import MowerProvider


class EntityProvider(MowerProvider):
    """Normalize one mower from existing Home Assistant entities."""

    async def async_get_mowers(self) -> list[MowerSnapshot]:
        """Return one mower snapshot from configured entities."""
        name = self.entry.data[CONF_MOWER_NAME]
        tracker = self._state(self.entry.data.get(CONF_TRACKER_ENTITY))
        status = self._state(self.entry.data.get(CONF_STATUS_ENTITY))
        battery = self._state(self.entry.data.get(CONF_BATTERY_ENTITY))
        problem = self._state(self.entry.data.get(CONF_PROBLEM_ENTITY))
        return [
            MowerSnapshot(
                provider="entity",
                mower_id=self.entry.entry_id,
                name=name,
                model="Existing HA entities",
                serial_number=None,
                latitude=_float_attr(tracker, "latitude"),
                longitude=_float_attr(tracker, "longitude"),
                battery_percent=_int_state(battery),
                state=_clean_state(status),
                activity=None,
                error_code=None,
                is_problem=_bool_state(problem),
                raw={
                    "status_entity": self.entry.data.get(CONF_STATUS_ENTITY),
                    "battery_entity": self.entry.data.get(CONF_BATTERY_ENTITY),
                    "problem_entity": self.entry.data.get(CONF_PROBLEM_ENTITY),
                    "tracker_entity": self.entry.data.get(CONF_TRACKER_ENTITY),
                },
            )
        ]

    def _state(self, entity_id: str | None) -> State | None:
        if not entity_id:
            return None
        return self.hass.states.get(entity_id)


def _clean_state(state: State | None) -> str | None:
    if state is None or state.state in {STATE_UNAVAILABLE, STATE_UNKNOWN}:
        return None
    return state.state


def _int_state(state: State | None) -> int | None:
    value = _clean_state(state)
    if value is None:
        return None
    try:
        return round(float(value))
    except ValueError:
        return None


def _bool_state(state: State | None) -> bool:
    value = _clean_state(state)
    if value is None:
        return False
    return value.lower() in {"on", "true", "problem", "stuck", "error"}


def _float_attr(state: State | None, attr: str) -> float | None:
    if state is None:
        return None
    value = state.attributes.get(attr)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
