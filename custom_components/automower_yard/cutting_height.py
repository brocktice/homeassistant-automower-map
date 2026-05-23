"""Helpers for presenting mower cutting height settings."""

from __future__ import annotations

import re

CM_PER_INCH = 2.54

ATTR_CUTTING_HEIGHT_SETTING = "cutting_height_setting"
ATTR_CUTTING_HEIGHT_CM = "cutting_height_cm"
ATTR_CUTTING_HEIGHT_IN = "cutting_height_in"

_SETTING_MIN = 1
_SETTING_MAX = 9
_HIGH_CUT_RANGE_CM = (5.0, 9.0)
_STANDARD_CUT_RANGE_CM = (2.0, 6.0)
_LOW_PROFILE_CUT_RANGE_CM = (2.0, 5.0)


def cutting_height_cm(setting: int | None, model: str | None) -> float | None:
    """Return approximate cutting height in cm for a mower setting."""
    if setting is None or setting < _SETTING_MIN or setting > _SETTING_MAX:
        return None
    min_cm, max_cm = _cutting_height_range_cm(model)
    height = min_cm + (setting - _SETTING_MIN) * (
        (max_cm - min_cm) / (_SETTING_MAX - _SETTING_MIN)
    )
    return round(height, 2)


def cutting_height_in(setting: int | None, model: str | None) -> float | None:
    """Return approximate cutting height in inches for a mower setting."""
    height_cm = cutting_height_cm(setting, model)
    if height_cm is None:
        return None
    return round(height_cm / CM_PER_INCH, 2)


def _cutting_height_range_cm(model: str | None) -> tuple[float, float]:
    """Return the published cutting height range for known model families."""
    if not model:
        return _STANDARD_CUT_RANGE_CM
    normalized = re.sub(r"[^A-Z0-9]", "", model.upper())
    if re.search(r"\d{3,4}X?H(?:$|[A-Z])", normalized):
        return _HIGH_CUT_RANGE_CM
    if normalized.endswith("105") or "AUTOMOWER105" in normalized:
        return _LOW_PROFILE_CUT_RANGE_CM
    return _STANDARD_CUT_RANGE_CM
