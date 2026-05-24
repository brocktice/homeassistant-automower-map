"""Tests for mower position payload parsing."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType


def _load_module(name: str, path: str) -> ModuleType:
    spec = spec_from_file_location(name, Path(__file__).resolve().parents[1] / path)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


position = _load_module(
    "position", "custom_components/robot_mower_yard/position.py"
)
position_dict_with_origin = position.position_dict_with_origin


def test_nested_relative_pair_prefers_origin_over_absolute_coordinates() -> None:
    parsed = position_dict_with_origin(
        {"position": [10.0, 20.0], "timestamp": 123},
        45.0,
        -93.0,
    )

    assert parsed is not None
    assert round(parsed["lat"], 6) == 45.000180
    assert round(parsed["lng"], 6) == -92.999873


def test_explicit_lat_lon_keys_are_kept_as_absolute_coordinates() -> None:
    parsed = position_dict_with_origin(
        {"position": {"lat": 44.5, "lng": -93.5}, "x": 10.0, "y": 20.0},
        45.0,
        -93.0,
    )

    assert parsed == {"lat": 44.5, "lng": -93.5}
