"""Route navigation and geographic calculation utilities."""
import math
from typing import Tuple


EARTH_RADIUS_METERS = 6371000.0


def calculate_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two GPS coordinates in meters using Haversine formula."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_RADIUS_METERS * c


def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the initial compass bearing in degrees (0-360) from point 1 to point 2."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_lambda = math.radians(lon2 - lon1)

    y = math.sin(delta_lambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - (math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda))
    initial_bearing = math.degrees(math.atan2(y, x))

    # Normalize to 0-360 degrees
    compass_bearing = (initial_bearing + 360.0) % 360.0
    return round(compass_bearing, 2)


def step_towards(
    current_lat: float,
    current_lon: float,
    target_lat: float,
    target_lon: float,
    step_distance_meters: float,
) -> Tuple[float, float, bool]:
    """Move a step towards target coordinate.

    Returns:
        (new_lat, new_lon, reached_target)
    """
    dist = calculate_distance_meters(current_lat, current_lon, target_lat, target_lon)

    if dist <= step_distance_meters or dist < 1.0:
        return target_lat, target_lon, True

    fraction = step_distance_meters / dist
    new_lat = current_lat + fraction * (target_lat - current_lat)
    new_lon = current_lon + fraction * (target_lon - current_lon)
    return round(new_lat, 6), round(new_lon, 6), False
