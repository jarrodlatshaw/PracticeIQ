"""Straight-line distance, distinct from road distance and drive time."""
from math import asin, cos, isfinite, radians, sin, sqrt


def distance_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    for lat, lon in ((lat1, lon1), (lat2, lon2)):
        if not isfinite(lat) or not isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError("coordinates must be finite WGS84 latitude/longitude")
    a1, a2 = radians(lat1), radians(lat2)
    dlat, dlon = a2 - a1, radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(a1) * cos(a2) * sin(dlon / 2) ** 2
    return 3958.7613 * 2 * asin(sqrt(min(1.0, max(0.0, a))))


def within_radius(lat1: float, lon1: float, lat2: float, lon2: float, radius_miles: float) -> bool:
    if not isfinite(radius_miles) or radius_miles < 0:
        raise ValueError("radius must be finite and nonnegative")
    return distance_miles(lat1, lon1, lat2, lon2) <= radius_miles
