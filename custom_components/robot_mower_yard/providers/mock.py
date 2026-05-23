"""Mock mower provider for configuration-flow and entity-model testing."""

from __future__ import annotations

from datetime import datetime
import math

from homeassistant.util import dt as dt_util

from ..models import MowerSnapshot
from .base import MowerProvider


class MockProvider(MowerProvider):
    """Return deterministic moving mower snapshots."""

    async def async_get_mowers(self) -> list[MowerSnapshot]:
        """Return two fake mowers in one yard."""
        now = dt_util.utcnow()
        angle = _day_angle(now)
        return [
            MowerSnapshot(
                provider="mock",
                mower_id="front",
                name="Front Mock Mower",
                model="MockMow 100",
                serial_number="MOCK-FRONT",
                latitude=44.9778 + math.sin(angle) * 0.00012,
                longitude=-93.2650 + math.cos(angle) * 0.00012,
                battery_percent=78,
                state="MOWING",
                activity="MOWING",
                error_code=None,
                is_problem=False,
                raw={"source": "mock"},
            ),
            MowerSnapshot(
                provider="mock",
                mower_id="back",
                name="Back Mock Mower",
                model="MockMow 200",
                serial_number="MOCK-BACK",
                latitude=44.9773 + math.cos(angle * 0.7) * 0.00010,
                longitude=-93.2644 + math.sin(angle * 0.7) * 0.00010,
                battery_percent=41,
                state="ERROR",
                activity="STOPPED",
                error_code="MOCK_STUCK",
                is_problem=True,
                raw={"source": "mock"},
            ),
        ]


def _day_angle(now: datetime) -> float:
    seconds = now.hour * 3600 + now.minute * 60 + now.second
    return seconds / 86400 * math.tau
