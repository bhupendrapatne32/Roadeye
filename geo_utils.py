import math
from typing import Tuple, List

EARTH_RADIUS_METERS = 6371000.0

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance between two points
    on the earth (specified in decimal degrees), returning meters.
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    return EARTH_RADIUS_METERS * c

def point_to_segment_distance(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    """
    Approximates perpendicular distance in meters from point (px, py) to line segment (x1, y1)-(x2, y2).
    Coordinates are in (lat, lon).
    """
    # Fast projection in equirectangular plane centered at px, py
    cos_lat = math.cos(math.radians(px))
    dx = (x2 - x1) * 111320.0 * cos_lat
    dy = (y2 - y1) * 110540.0

    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq < 1e-6:
        return haversine_distance(px, py, x1, y1)

    px_m = (py - x1) * 111320.0 * cos_lat
    py_m = (px - y1) * 110540.0

    # Project point onto segment: parameterized t in [0, 1]
    t = max(0.0, min(1.0, (px_m * dx + py_m * dy) / seg_len_sq))

    proj_lat = y1 + t * (y2 - y1)
    proj_lon = x1 + t * (x2 - x1)

    return haversine_distance(px, py, proj_lat, proj_lon)

def min_distance_to_polyline(lat: float, lon: float, polyline_coords: List[List[float]]) -> float:
    """
    polyline_coords is list of [lon, lat] pairs (GeoJSON standard).
    Returns minimum distance in meters from (lat, lon) to polyline.
    """
    if not polyline_coords:
        return float('inf')
    if len(polyline_coords) == 1:
        return haversine_distance(lat, lon, polyline_coords[0][1], polyline_coords[0][0])

    min_dist = float('inf')
    for i in range(len(polyline_coords) - 1):
        x1, y1 = polyline_coords[i][0], polyline_coords[i][1]       # lon, lat
        x2, y2 = polyline_coords[i + 1][0], polyline_coords[i + 1][1] # lon, lat
        dist = point_to_segment_distance(lat, lon, x1, y1, x2, y2)
        if dist < min_dist:
            min_dist = dist
    return min_dist
