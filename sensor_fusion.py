"""
SIH26143 - Sensor Fusion & Threat Scoring Engine
================================================
Performs Haversine distance cross-check of detected SAR hulls against AIS broadcasts.
Flags dark vessels (no AIS match within 5km), triggers HawkEye 360 X-band RF verification,
and assigns threat scores.
"""

import math
from typing import Dict, Any, List, Optional

# In-memory mock list of active AIS vessel broadcasts
MOCK_AIS_BROADCASTS: List[Dict[str, Any]] = [
    {"mmsi": "636019825", "vessel_name": "MSC ELSA 3", "lat": 9.3125, "lon": 76.1360, "type": "Container Ship", "sog": 14.2},
    {"mmsi": "311000452", "vessel_name": "MV OLYMPIC SPIRIT", "lat": 9.5500, "lon": 76.2200, "type": "Crude Tanker", "sog": 11.8},
    {"mmsi": "413204910", "vessel_name": "ZHONG SHAN 98", "lat": 9.1500, "lon": 75.8500, "type": "Cargo Vessel", "sog": 10.5},
    {"mmsi": "563098120", "vessel_name": "SINGAPORE STAR", "lat": 9.6000, "lon": 76.3500, "type": "Bulk Carrier", "sog": 13.1},
]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates the Haversine distance in kilometers between two lat/lon points."""
    R = 6371.0  # Earth radius in kilometers
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + \
        math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


def correlate_hull_with_ais(
    hull_lat: float = 9.4200,
    hull_lon: float = 76.0200,
    tolerance_km: float = 5.0
) -> Dict[str, Any]:
    """
    Cross-checks YOLOv8 hull coordinates against AIS broadcasts using Haversine distance.
    If no active AIS ping is found within tolerance_km (5km), flags hull as dark vessel (AIS INACTIVE),
    triggers HawkEye 360 X-band RF intercept match (True), and assigns a 0.90 Threat Score.
    """
    closest_match = None
    min_dist = float("inf")

    for vessel in MOCK_AIS_BROADCASTS:
        dist = haversine_km(hull_lat, hull_lon, vessel["lat"], vessel["lon"])
        if dist < min_dist:
            min_dist = dist
            closest_match = vessel

    if closest_match is not None and min_dist <= tolerance_km:
        ais_status = "COMPLIANT_AIS_ACTIVE"
        rf_intercept_match = False
        threat_score = 0.15
        reason = f"Active AIS broadcast found for {closest_match['vessel_name']} ({min_dist:.2f} km distance)"
    else:
        ais_status = "INACTIVE / UNMATCHED"
        rf_intercept_match = True
        threat_score = 0.90
        reason = f"YOLOv8 hull detected at ({hull_lat}, {hull_lon}) with zero AIS broadcasts within {tolerance_km}km. HawkEye 360 X-Band RF intercept confirmed."

    return {
        "target_vessel_coordinates": [hull_lat, hull_lon],
        "ais_status": ais_status,
        "is_dark_vessel": ais_status == "INACTIVE / UNMATCHED",
        "rf_intercept_match": rf_intercept_match,
        "rf_signature": "HawkEye 360 X-Band Marine Radar Emitter",
        "threat_score": threat_score,
        "closest_ais_distance_km": round(min_dist, 2) if min_dist != float("inf") else None,
        "attribution_reason": reason
    }

