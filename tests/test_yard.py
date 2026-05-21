"""Tests for yard zone matching."""

from custom_components.automower_yard.yard import find_zone, find_zones


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
