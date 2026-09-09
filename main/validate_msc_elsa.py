"""Reproducible MSC Elsa 3 incident-validation scenario.

This script is an evidentiary *demonstration*, not a live Coast Guard alert:
the AIS observations and environmental inputs below are in-memory scenario data.
Replace them with authenticated AIS/SAR and historical ocean-weather records
before using any output in an operational or legal proceeding.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from ais_matcher import match_all_hulls
from drift_simulation import simulate_backward_drift
from jurisdiction_lookup import get_jurisdiction_info


GROUND_TRUTH_LAT = 9.3125
GROUND_TRUTH_LON = 76.1360
INCIDENT_TIME = datetime(2025, 5, 24, 13, 0, 0)
MATCH_MMSI = "636019825"
SUSPECT_LAT = 9.4200
SUSPECT_LON = 76.0200
SLICK_LAT = 9.3764
SLICK_LON = 75.9758
SLICK_AREA_SQ_M = 100_000
KOCHI_BASE_LAT = 9.95
KOCHI_BASE_LON = 76.26
INCIDENT_ID = "MSC-ELSA-3-2025-05-24"
RESPONDING_UNIT = "Coast Guard District HQ No. 4 (Kochi)"
SQUARE_METRES_PER_PIXEL = 100


def geodesic_distance_km(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    """Return great-circle distance using the haversine geodesic approximation."""
    earth_radius_km = 6371.0088
    lat_a, lon_a, lat_b, lon_b = map(math.radians, (lat_a, lon_a, lat_b, lon_b))
    delta_lat = lat_b - lat_a
    delta_lon = lon_b - lon_a
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * earth_radius_km * math.asin(math.sqrt(haversine))


def build_ais_evidence() -> pd.DataFrame:
    """Create the in-memory AIS evidence: MSC ELSA 3 only.

    The suspect is deliberately absent because a dark vessel does not transmit
    AIS; its physical presence is represented exclusively by a SAR hull.
    """
    return pd.DataFrame(
        [
            {
                "evidence_label": "Match Target",
                "mmsi": MATCH_MMSI,
                "lat": GROUND_TRUTH_LAT,
                "lon": GROUND_TRUTH_LON,
                "timestamp": INCIDENT_TIME,
                "vessel_name": "MSC ELSA 3 MATCH TARGET",
            },
        ]
    )


def slick_polygon_coordinates(
    center_lat: float, center_lon: float, area_sq_m: float, vertices: int = 64
) -> list[list[float]]:
    """Approximate a circular slick as a closed GeoJSON (lon, lat) polygon ring."""
    radius_m = math.sqrt(area_sq_m / math.pi)
    lat_radius = radius_m / 111_320
    lon_radius = radius_m / (111_320 * math.cos(math.radians(center_lat)))
    ring = [
        [
            center_lon + lon_radius * math.cos(2 * math.pi * index / vertices),
            center_lat + lat_radius * math.sin(2 * math.pi * index / vertices),
        ]
        for index in range(vertices)
    ]
    ring.append(ring[0])
    return ring


def export_geojson(
    output_path: Path,
    drift_origin_lat: float,
    drift_origin_lon: float,
    jurisdiction_zone: str,
) -> None:
    """Write the scenario's evidentiary features as RFC 7946 GeoJSON."""
    common_properties: dict[str, Any] = {
        "incident_id": INCIDENT_ID,
        "timestamp": INCIDENT_TIME.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "suspicion_score": 0.90,
        "area_sq_m": SLICK_AREA_SQ_M,
        "jurisdiction_zone": jurisdiction_zone,
        "responding_unit": RESPONDING_UNIT,
    }
    dossier = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {**common_properties, "feature_type": "Oil Slick"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [slick_polygon_coordinates(SLICK_LAT, SLICK_LON, SLICK_AREA_SQ_M)],
                },
            },
            {
                "type": "Feature",
                "properties": {**common_properties, "feature_type": "Backward Drift Track", "hours_back": 6.0},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[SLICK_LON, SLICK_LAT], [drift_origin_lon, drift_origin_lat]],
                },
            },
            {
                "type": "Feature",
                "properties": {**common_properties, "feature_type": "Suspect Dark Vessel", "ais_status": "Inactive", "rf_x_band_intercepted": True},
                "geometry": {"type": "Point", "coordinates": [SUSPECT_LON, SUSPECT_LAT]},
            },
            {
                "type": "Feature",
                "properties": {**common_properties, "feature_type": "MSC Elsa 3 Ground Truth"},
                "geometry": {"type": "Point", "coordinates": [GROUND_TRUTH_LON, GROUND_TRUTH_LAT]},
            },
        ],
    }
    output_path.write_text(json.dumps(dossier, indent=2), encoding="utf-8")


def export_evidence_map(
    output_path: Path,
    drift_origin_lat: float,
    drift_origin_lon: float,
) -> None:
    """Render the scenario as an interactive Folium evidence map."""
    try:
        import folium
        from folium.plugins import PolyLineTextPath
    except ImportError as exc:
        raise RuntimeError("Folium is required for the evidence map. Install it with: pip install folium") from exc

    evidence_map = folium.Map(location=[9.35, 76.08], zoom_start=10, tiles="OpenStreetMap")
    folium.TileLayer("Esri.WorldImagery", name="Esri Satellite").add_to(evidence_map)
    folium.LayerControl().add_to(evidence_map)

    folium.Marker(
        [GROUND_TRUTH_LAT, GROUND_TRUTH_LON],
        popup="MSC Elsa 3 known sinking site (ground truth)",
        icon=folium.Icon(color="blue", icon="anchor", prefix="fa"),
    ).add_to(evidence_map)
    folium.Circle(
        [SLICK_LAT, SLICK_LON],
        radius=math.sqrt(SLICK_AREA_SQ_M / math.pi),
        color="#7a0000",
        fill=True,
        fill_color="#7a0000",
        fill_opacity=0.45,
        popup=f"Oil slick: {SLICK_AREA_SQ_M:,} sq m",
    ).add_to(evidence_map)

    drift_line = folium.PolyLine(
        [[SLICK_LAT, SLICK_LON], [drift_origin_lat, drift_origin_lon]],
        color="#5b0f00",
        weight=4,
        tooltip="6.0-hour backward drift track",
    ).add_to(evidence_map)
    PolyLineTextPath(drift_line, "  ▶  ", repeat=False, offset=45, attributes={"fill": "#5b0f00", "font-weight": "bold"}).add_to(evidence_map)

    folium.Marker(
        [SUSPECT_LAT, SUSPECT_LON],
        popup="SUSPECT DARK VESSEL (Score: 0.90) | AIS: Inactive | RF: X-Band Radar Intercepted (True)",
        icon=folium.Icon(color="red", icon="ship", prefix="fa"),
    ).add_to(evidence_map)
    folium.Marker(
        [KOCHI_BASE_LAT, KOCHI_BASE_LON],
        popup=RESPONDING_UNIT,
        icon=folium.Icon(color="green", icon="shield", prefix="fa"),
    ).add_to(evidence_map)
    folium.PolyLine(
        [[KOCHI_BASE_LAT, KOCHI_BASE_LON], [SUSPECT_LAT, SUSPECT_LON]],
        color="green",
        weight=3,
        dash_array="8, 8",
        tooltip="ICG intercept trajectory",
    ).add_to(evidence_map)
    evidence_map.save(str(output_path))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the MSC Elsa 3 validation scenario.")
    parser.add_argument(
        "--pixel-count", type=int, default=1_000,
        help="Detected slick pixel count used for the area calculation (default: 1000).",
    )
    args = parser.parse_args()
    if args.pixel_count < 0:
        parser.error("--pixel-count must be zero or greater")

    ais_df = build_ais_evidence()
    hulls = [
        {
            "hull_id": 1,
            "label": "MSC ELSA 3",
            "lat": GROUND_TRUTH_LAT,
            "lon": GROUND_TRUTH_LON,
            "timestamp": INCIDENT_TIME,
            "rf_emission_detected": False,
        },
        {
            "hull_id": 2,
            "label": "Suspect Target",
            "lat": SUSPECT_LAT,
            "lon": SUSPECT_LON,
            "timestamp": INCIDENT_TIME,
            "rf_emission_detected": True,
        },
    ]
    ais_matches = match_all_hulls(hulls, ais_df)

    # Environmental parameters are explicit, deterministic scenario inputs.
    drift = simulate_backward_drift(
        slick_lat=SLICK_LAT,
        slick_lon=SLICK_LON,
        detection_time=INCIDENT_TIME,
        current_velocity_kmh=0.60,
        current_direction_deg=45.0,
        wind_speed_kmh=18.0,
        wind_direction_deg=225.0,
        hours_back=6.0,
    )
    zone, within_500m, coast_distance_m = get_jurisdiction_info(
        drift.origin_lat, drift.origin_lon
    )
    error_km = geodesic_distance_km(
        drift.origin_lat, drift.origin_lon, GROUND_TRUTH_LAT, GROUND_TRUTH_LON
    )
    estimated_area_m2 = args.pixel_count * SQUARE_METRES_PER_PIXEL

    print("=" * 78)
    print("COURT-READY EVIDENTIARY DOSSIER - MSC ELSA 3 VALIDATION SCENARIO")
    print("=" * 78)
    print("IMPORTANT: This is a reproducible analytical scenario, not live evidence or an alert.")
    print("Ground-truth source references: [cite: 1, 4] coordinates; [cite: 1, 2, 4] time.")
    print()
    print("INCIDENT GROUND TRUTH")
    print(f"  Sinking coordinate : {GROUND_TRUTH_LAT:.4f}, {GROUND_TRUTH_LON:.4f}")
    print(f"  Incident time (UTC): {INCIDENT_TIME:%Y-%m-%d %H:%M:%S}")
    print()
    print("AIS SCENARIO EVIDENCE (IN MEMORY)")
    for _, record in ais_df.iterrows():
        print(f"  {record['evidence_label']}: MMSI {record['mmsi']} at "
              f"{record['lat']:.4f}, {record['lon']:.4f}")
    print("  Suspect Target: no AIS broadcast in this scenario (dark-vessel hypothesis).")
    print()
    print("SAR HULL DETECTIONS")
    for hull in hulls:
        print(f"  Hull {hull['hull_id']} ({hull['label']}): "
              f"{hull['lat']:.4f}, {hull['lon']:.4f}; "
              f"RF emission detected: {hull['rf_emission_detected']}")
    print("  Matcher outcomes:")
    for match in ais_matches:
        status = "MATCH" if match.has_ais_match else "NO MATCH / SUSPECT"
        hull = next(hull for hull in hulls if hull["hull_id"] == match.hull_id)
        print(f"    Hull {match.hull_id} ({hull['label']}): {status}; "
              f"Suspicion Score: {match.suspicion_score:.2f}; {match.reason}")
        if hull["label"] == "Suspect Target":
            print(f"      Suspect RF emission detected: {hull['rf_emission_detected']}")
    print()
    print("SLICK AND BACKWARD-DRIFT ANALYSIS")
    print(f"  Estimated spill area: {estimated_area_m2:,} square metres "
          f"({args.pixel_count:,} pixels x {SQUARE_METRES_PER_PIXEL} square metres/pixel)")
    print(f"  Drift estimate      : {drift.origin_lat:.6f}, {drift.origin_lon:.6f}")
    print(f"  Backtrack window    : {drift.hours_back:.1f} h; {drift.total_distance_km:.2f} km")
    print(f"  Geodesic error      : {error_km:.3f} km from stated sinking coordinate")
    print()
    print("JURISDICTION AND RESPONSE ROUTING")
    print(f"  Jurisdiction        : {zone}")
    print(f"  Within 500 m coast exclusion: {within_500m} ({coast_distance_m:,.1f} m to model coastline)")
    print("  Route to            : Coast Guard District HQ No. 4 (Kochi)")
    print("  Requested action    : Immediate intercept assessment, subject to authenticated live evidence.")
    print("=" * 78)

    output_dir = Path.cwd()
    geojson_path = output_dir / "msc_elsa_dossier.geojson"
    map_path = output_dir / "msc_elsa_evidence_map.html"
    export_geojson(geojson_path, drift.origin_lat, drift.origin_lon, zone)
    export_evidence_map(map_path, drift.origin_lat, drift.origin_lon)
    print("Geospatial Map Exported: msc_elsa_evidence_map.html")
    print("Forensic GeoJSON Exported: msc_elsa_dossier.geojson")


if __name__ == "__main__":
    main()
