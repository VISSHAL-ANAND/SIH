"""
SIH26143 - Jurisdiction & Coastal Exclusion Zone Lookup Module
================================================================
Determines jurisdiction zones (Indian EEZ / Maritime Coast Guard regions)
and checks whether coordinates fall within the 500m coastal exclusion zone
using Shapely and GeoPandas.
"""

import math
from typing import Tuple
import geopandas as gpd
from shapely.geometry import Point, Polygon


# -----------------------------------------------------------------------------
# DEFINITION OF MARITIME ZONES (India EEZ Regions & International Waters)
# -----------------------------------------------------------------------------

# Representative Indian EEZ & Territorial Zone Boundaries (WGS84 EPSG:4326)
_ZONE_POLYGONS = {
    "Indian EEZ (West Coast - ICG Regional HQ West / Gandhinagar & Mumbai)": Polygon([
        (65.0, 12.0), (73.5, 8.0), (77.5, 8.0), (73.0, 24.0), (68.0, 24.0), (65.0, 20.0), (65.0, 12.0)
    ]),
    "Indian EEZ (East Coast - ICG Regional HQ East / Chennai & Vizag)": Polygon([
        (77.5, 8.0), (88.0, 10.0), (89.5, 21.5), (87.0, 21.5), (79.0, 14.0), (77.5, 8.0)
    ]),
    "Indian EEZ (Andaman & Nicobar - ICG Regional HQ A&N / Port Blair)": Polygon([
        (91.0, 6.0), (94.5, 6.0), (94.5, 14.0), (91.0, 14.0), (91.0, 6.0)
    ]),
}

# Simplified Indian Coastline Segments (WGS84 Lon, Lat)
_COASTLINE_POINTS = [
    (68.5, 23.7), (69.2, 22.5), (70.2, 20.9), (72.6, 21.1), (72.8, 19.0),
    (73.8, 15.4), (74.8, 12.8), (76.2, 10.0), (77.5, 8.1),   (78.2, 9.2),
    (79.8, 10.8), (80.3, 13.1), (82.2, 16.9), (83.3, 17.7), (85.0, 19.5),
    (87.0, 21.5), (88.2, 21.6)
]


def _build_jurisdiction_gdf() -> gpd.GeoDataFrame:
    """Builds a GeoDataFrame containing the Indian maritime jurisdiction zones."""
    data = []
    for zone_name, geom in _ZONE_POLYGONS.items():
        data.append({"zone_name": zone_name, "geometry": geom})
    return gpd.GeoDataFrame(data, crs="EPSG:4326")


_ZONES_GDF = _build_jurisdiction_gdf()


def find_jurisdiction_zone(lat: float, lon: float) -> str:
    """
    Finds the maritime jurisdiction zone for a given (lat, lon) coordinate.
    """
    point = Point(lon, lat)  # Shapely uses (x=lon, y=lat)
    for _, row in _ZONES_GDF.iterrows():
        if row["geometry"].contains(point):
            return row["zone_name"]
    return "High Seas / International Waters"


def distance_to_coastline_m(lat: float, lon: float) -> float:
    """
    Calculates distance in meters from (lat, lon) to the nearest defined coastline point.
    """
    min_dist_m = float("inf")
    for cl_lon, cl_lat in _COASTLINE_POINTS:
        # 1 deg lat = 111,139m; 1 deg lon = 111,139m * cos(lat)
        dy = (lat - cl_lat) * 111139.0
        dx = (lon - cl_lon) * 111139.0 * math.cos(math.radians((lat + cl_lat) / 2.0))
        dist = math.hypot(dx, dy)
        if dist < min_dist_m:
            min_dist_m = dist
    return round(min_dist_m, 1)


def is_within_500m_exclusion(lat: float, lon: float) -> Tuple[bool, float]:
    """
    Checks whether a coordinate falls within the 500m coastal exclusion zone.
    Returns (within_500m_flag, distance_in_meters).
    """
    dist_m = distance_to_coastline_m(lat, lon)
    return dist_m <= 500.0, dist_m


def get_jurisdiction_info(lat: float, lon: float) -> Tuple[str, bool, float]:
    """
    Full lookup returning (zone_name, within_500m_exclusion, distance_to_coast_m).
    """
    zone = find_jurisdiction_zone(lat, lon)
    within_500m, dist_m = is_within_500m_exclusion(lat, lon)
    return zone, within_500m, dist_m


# -----------------------------------------------------------------------------
# STANDALONE SELF-TESTS
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    print("======================================================================")
    print("RUNNING JURISDICTION_LOOKUP.PY SELF-TESTS")
    print("======================================================================")

    # Test 1: Gujarat Demo Anchor (Lat 20.85, Lon 69.20)
    g_zone, g_500m, g_dist = get_jurisdiction_info(20.85, 69.20)
    print(f"Test 1 (Gujarat Demo Anchor: 20.85, 69.20):")
    print(f"  Zone                : {g_zone}")
    print(f"  Within 500m Exclusion: {g_500m}")
    print(f"  Distance to Coast   : {g_dist} m")
    assert "West Coast" in g_zone, "FAILED Test 1: Should be in West Coast EEZ"
    assert not g_500m, "FAILED Test 1: Gujarat anchor (100km offshore) should NOT be within 500m"

    # Test 2: Point 200m offshore Veraval Coast (Lat 20.90, Lon 70.201926)
    # 70.201926 is ~200m east of coastline point (20.90, 70.20)
    c_lat, c_lon = 20.90, 70.201926
    c_zone, c_500m, c_dist = get_jurisdiction_info(c_lat, c_lon)
    print(f"\nTest 2 (Coastal Point ~200m offshore: {c_lat}, {c_lon}):")
    print(f"  Zone                : {c_zone}")
    print(f"  Within 500m Exclusion: {c_500m}")
    print(f"  Distance to Coast   : {c_dist} m")
    assert c_500m, f"FAILED Test 2: Point {c_dist}m from shore MUST return True for 500m exclusion"

    # Test 3: High Seas (Lat 15.0, Lon 60.0)
    h_zone, h_500m, h_dist = get_jurisdiction_info(15.0, 60.0)
    print(f"\nTest 3 (High Seas: 15.0, 60.0):")
    print(f"  Zone                : {h_zone}")
    print(f"  Within 500m Exclusion: {h_500m}")
    print(f"  Distance to Coast   : {h_dist} m")
    assert h_zone == "High Seas / International Waters", "FAILED Test 3: High seas should resolve correctly"

    print("\n======================================================================")
    print("ALL JURISDICTION SELF-TESTS PASSED (including coastal <500m check)")
    print("======================================================================")

