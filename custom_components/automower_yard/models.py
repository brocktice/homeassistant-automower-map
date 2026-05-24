"""Shared models for the Robot Mower Yard prototype."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MowerSnapshot:
    """Normalized mower state provided by a vendor adapter."""

    provider: str
    mower_id: str
    name: str | None
    model: str | None
    serial_number: str | None
    latitude: float | None
    longitude: float | None
    battery_percent: int | None
    state: str | None
    activity: str | None
    error_code: str | int | None
    is_problem: bool
    raw: dict[str, Any]
    updated_at: str | None = None

    @property
    def stable_id(self) -> str:
        """Return an integration-wide stable mower id."""
        return f"{self.provider}_{self.mower_id}"
