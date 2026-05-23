"""Tests for yard zone matching."""

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


cutting_height = _load_module(
    "cutting_height", "custom_components/robot_mower_yard/cutting_height.py"
)
yard = _load_module("yard", "custom_components/robot_mower_yard/yard.py")
cutting_height_cm = cutting_height.cutting_height_cm
cutting_height_in = cutting_height.cutting_height_in
find_zone = yard.find_zone
find_zones = yard.find_zones


def test_standard_cutting_height_setting_maps_to_centimeters() -> None:
    assert cutting_height_cm(1, "Husqvarna Automower 430X") == 2.0
    assert cutting_height_cm(5, "Automower 430X") == 4.0
    assert cutting_height_cm(9, "Automower 430X") == 6.0


def test_high_cutting_height_setting_maps_to_centimeters_and_inches() -> None:
    assert cutting_height_cm(1, "Automower 430XH") == 5.0
    assert cutting_height_cm(1, "Husqvarna Automower 520H") == 5.0
    assert cutting_height_cm(9, "Automower 430XH") == 9.0
    assert cutting_height_in(9, "Automower 430XH") == 3.54


def test_low_profile_cutting_height_setting_maps_to_centimeters() -> None:
    assert cutting_height_cm(1, "Automower 105") == 2.0
    assert cutting_height_cm(9, "Automower 105") == 5.0


def test_unknown_cutting_height_setting_returns_none() -> None:
    assert cutting_height_cm(None, "Automower 430XH") is None
    assert cutting_height_cm(0, "Automower 430XH") is None
    assert cutting_height_cm(10, "Automower 430XH") is None


def test_smallest_overlapping_polygon_wins() -> None:
    zones = [
        {
            "name": "Large",
            "polygon": [[0, 0], [0, 10], [10, 10], [10, 0]],
        },
        {
            "name": "Small",
            "polygon": [[1, 1], [1, 2], [2, 2], [2, 1]],
        },
    ]

    assert find_zone(1.5, 1.5, zones) == "Small"
    assert find_zones(1.5, 1.5, zones) == ["Small", "Large"]


def test_smallest_overlapping_circle_wins() -> None:
    zones = [
        {"name": "Large", "center": [45.0, -93.0], "radius_m": 50},
        {"name": "Small", "center": [45.0, -93.0], "radius_m": 5},
    ]

    assert find_zone(45.0, -93.0, zones) == "Small"
    assert find_zones(45.0, -93.0, zones) == ["Small", "Large"]
