import httpx
import math
from typing import List, Dict, Any, Tuple, Optional
from geo_utils import haversine_distance, min_distance_to_polyline

OSRM_BASE_URL = "http://router.project-osrm.org/route/v1/driving"

# Penalty constants by severity
SEVERITY_PENALTY_SECONDS = {
    "Low": 120,       # 2 minutes penalty
    "Moderate": 450,  # 7.5 minutes penalty
    "Critical": 1800  # 30 minutes penalty (forces detour)
}

# Distance threshold to consider a hazard on a route segment
HAZARD_ON_ROUTE_THRESHOLD_METERS = 75.0

async def fetch_osrm_route(coords: List[Tuple[float, float]], alternatives: bool = True) -> Optional[Dict[str, Any]]:
    """
    coords: List of (lat, lon)
    Returns OSRM GeoJSON response.
    """
    if len(coords) < 2:
        return None

    # OSRM expects lon,lat;lon,lat
    coord_str = ";".join([f"{lon:.6f},{lat:.6f}" for lat, lon in coords])
    url = f"{OSRM_BASE_URL}/{coord_str}?overview=full&geometries=geojson&alternatives={'true' if alternatives else 'false'}&steps=true"

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("code") == "Ok" and "routes" in data:
                    return data
    except Exception as e:
        print(f"[OSRM Error] {e}")

    return None

def analyze_route_hazards(geometry_coords: List[List[float]], hazards: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], float]:
    """
    geometry_coords: [[lon, lat], ...]
    Returns (affecting_hazards, total_safety_penalty_seconds)
    """
    affecting_hazards = []
    total_penalty = 0.0

    for h in hazards:
        if h.get("status") not in ["ACTIVE", "LOW_CONFIDENCE"]:
            continue

        h_lat = float(h["latitude"])
        h_lon = float(h["longitude"])
        dist = min_distance_to_polyline(h_lat, h_lon, geometry_coords)

        if dist <= HAZARD_ON_ROUTE_THRESHOLD_METERS:
            sev = h.get("severity", "Moderate")
            base_pen = SEVERITY_PENALTY_SECONDS.get(sev, 300)
            conf = float(h.get("confidence_score", 50)) / 100.0
            penalty = base_pen * conf

            affecting_hazards.append({
                **h,
                "distance_to_route_meters": round(dist, 1),
                "penalty_seconds": round(penalty, 1)
            })
            total_penalty += penalty

    return affecting_hazards, total_penalty

async def calculate_safe_navigation(
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float,
    hazards: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Calculates direct route and safe route by factoring in active road hazards.
    If direct route intersects critical hazards, finds or synthesizes a safe detour bypassing them.
    """
    primary_osrm = await fetch_osrm_route([(start_lat, start_lon), (end_lat, end_lon)], alternatives=True)

    routes_evaluated = []

    if primary_osrm and primary_osrm.get("routes"):
        for idx, r in enumerate(primary_osrm["routes"]):
            coords = r["geometry"]["coordinates"] # [[lon, lat], ...]
            duration = r["duration"]             # in seconds
            distance = r["distance"]             # in meters

            affecting_hazards, penalty = analyze_route_hazards(coords, hazards)
            total_cost = duration + penalty

            routes_evaluated.append({
                "type": "direct" if idx == 0 else f"alternative_{idx}",
                "coordinates": coords,
                "distance_meters": distance,
                "travel_time_seconds": duration,
                "safety_penalty_seconds": penalty,
                "total_cost_score": total_cost,
                "hazards_encountered": affecting_hazards,
                "hazard_count": len(affecting_hazards),
                "has_critical": any(h.get("severity") == "Critical" for h in affecting_hazards)
            })

    # Sort routes by total cost (Duration + Hazard Penalty)
    routes_evaluated.sort(key=lambda x: x["total_cost_score"])

    # If the fastest direct route has hazards, check if an alternative avoids them or generate a waypoint bypass
    direct_route = routes_evaluated[0] if routes_evaluated else None
    
    # If the default shortest has critical hazards, attempt finding a detour via an offset waypoint
    if direct_route and direct_route["hazard_count"] > 0:
        worst_hazard = max(direct_route["hazards_encountered"], key=lambda h: h.get("penalty_seconds", 0))
        h_lat = worst_hazard["latitude"]
        h_lon = worst_hazard["longitude"]

        # Calculate a perpendicular waypoint offset ~400-500 meters to route around
        # Vector from start to end
        d_lat = end_lat - start_lat
        d_lon = end_lon - start_lon
        norm = math.sqrt(d_lat*d_lat + d_lon*d_lon) or 1.0
        # Perpendicular vector
        perp_lat = -d_lon / norm * 0.004
        perp_lon = d_lat / norm * 0.004

        waypoint_1 = (h_lat + perp_lat, h_lon + perp_lon)
        detour_osrm = await fetch_osrm_route([(start_lat, start_lon), waypoint_1, (end_lat, end_lon)], alternatives=False)

        if detour_osrm and detour_osrm.get("routes"):
            detour_r = detour_osrm["routes"][0]
            d_coords = detour_r["geometry"]["coordinates"]
            d_duration = detour_r["duration"]
            d_distance = detour_r["distance"]
            d_hazards, d_pen = analyze_route_hazards(d_coords, hazards)

            routes_evaluated.append({
                "type": "safe_detour",
                "coordinates": d_coords,
                "distance_meters": d_distance,
                "travel_time_seconds": d_duration,
                "safety_penalty_seconds": d_pen,
                "total_cost_score": d_duration + d_pen,
                "hazards_encountered": d_hazards,
                "hazard_count": len(d_hazards),
                "has_critical": any(h.get("severity") == "Critical" for h in d_hazards)
            })

    # Fallback synthetic geometry if OSRM is offline
    if not routes_evaluated:
        synthetic_coords = [
            [start_lon, start_lat],
            [(start_lon + end_lon) / 2.0, (start_lat + end_lat) / 2.0],
            [end_lon, end_lat]
        ]
        dist = haversine_distance(start_lat, start_lon, end_lat, end_lon)
        routes_evaluated.append({
            "type": "direct_offline",
            "coordinates": synthetic_coords,
            "distance_meters": dist,
            "travel_time_seconds": dist / 8.33, # ~30km/h
            "safety_penalty_seconds": 0,
            "total_cost_score": dist / 8.33,
            "hazards_encountered": [],
            "hazard_count": 0,
            "has_critical": False
        })

    # Select the safest optimal route (lowest total cost) vs standard fastest
    routes_evaluated.sort(key=lambda x: x["total_cost_score"])
    safest_route = routes_evaluated[0]

    # Find raw fastest route for comparison
    fastest_route = min(routes_evaluated, key=lambda x: x["travel_time_seconds"])

    return {
        "status": "success",
        "fastest_route": fastest_route,
        "safest_route": safest_route,
        "route_recommended": "safest" if safest_route["total_cost_score"] < fastest_route["total_cost_score"] else "fastest",
        "hazards_avoided": len(fastest_route.get("hazards_encountered", [])) - len(safest_route.get("hazards_encountered", [])),
        "all_options": routes_evaluated
    }
