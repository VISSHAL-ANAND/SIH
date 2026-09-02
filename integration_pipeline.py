"""
SIH26143 - Pipeline Integration v3: Wire all 4 modules together
Owner: VISSHAL (took over from RATHIMEENA)
Updated 2026-09-01: drift simulation is now wired in for real (ocean_wind_loader
+ drift_simulation.py, using geolocation.py for slick pixel->latlon). All 4
stages are genuinely connected now -- nothing left mocked in the happy path.

WHAT'S REAL VS MOCKED NOW:
  - Slick detection : REAL (VISSHAL's trained U-Net + shape classifier)
  - Hull detection  : REAL (RINOSH's trained YOLOv8 detector, geo-verified)
  - AIS matching    : REAL (VISSHAL's spatial-temporal matcher)
  - Drift simulation: REAL (Open-Meteo current/wind + 3%-wind-factor backward
                       sim). Falls back to a labeled mock per-image ONLY if
                       the live Open-Meteo fetch fails (e.g. no network) --
                       treat that as a bug to fix, not a normal outcome.
  - Jurisdiction/ICG-zone routing: STILL NOT BUILT. drift_simulation.py gives
    an origin point, not a zone -- jurisdiction_zone/within_500m_exclusion on
    DriftResult are still placeholders until that logic exists.

IMPORTANT GEO CAVEAT (be upfront about this in the pitch):
RINOSH's hull detector returns REAL lat/lon only when given a georeferenced
raster (GeoTIFF with a valid transform). Our current demo/training images
(the Kaggle SOS chips) are plain .jpg with NO geo metadata -- so on THOSE
images, lat/lon will legitimately come back None. This script falls back to
geolocation.py's demo-anchor approximation ONLY when RINOSH's real
conversion returns None -- it never overwrites a genuine geo-referenced
coordinate. If you get a real georeferenced Sentinel-1 scene before the
demo, run it through and you'll get genuinely real coordinates instead of
the anchor approximation.
"""

from datetime import datetime

import numpy as np
from PIL import Image

from pipeline_contracts import (
    SlickComponent, SlickDetectionResult,
    HullDetection, HullDetectionResult,
    AISMatch as ContractAISMatch, AISMatchResult,
    DriftResult, DriftSimResult,
    PipelineOutput,
)
from geolocation import EXAMPLE_DEMO_ANCHOR, pixel_to_latlon
from jurisdiction_lookup import get_jurisdiction_info


# -----------------------------------------------------------------------------
# STAGE 1: Slick Detection -- REAL
# -----------------------------------------------------------------------------
def run_slick_detection(image_id: str, image_rgb: np.ndarray, model) -> SlickDetectionResult:
    from predict_and_classify import predict_and_classify

    result = predict_and_classify(model, image_rgb)
    components = [
        SlickComponent(
            component_id=c["component_id"], area_pixels=c["area_pixels"],
            centroid_x=c["centroid_x"], centroid_y=c["centroid_y"],
            bbox=tuple(c["bbox"]), elongation_ratio=c["elongation_ratio"],
            shape_class=c["shape_class"], aspect_ratio=c["aspect_ratio"],
            orientation_deg=c["orientation_deg"],
        )
        for c in result["components"]
    ]
    return SlickDetectionResult(
        image_id=image_id, components=components,
        num_linear=result["num_linear"], num_blob=result["num_blob"],
    )


# -----------------------------------------------------------------------------
# STAGE 2: Hull Detection -- REAL, calls RINOSH's actual trained YOLOv8 detector
# -----------------------------------------------------------------------------
def run_hull_detection(image_id: str, image_path: str) -> HullDetectionResult:
    """
    Calls RINOSH's real detect_hulls(). Note this needs an actual FILE PATH,
    not an in-memory array -- his geotransform reading requires a real
    raster file (rasterio.open() can't read a numpy array). If you're
    working from the .npy test arrays, save each image to a temp file first
    (see main() below for how).
    """
    from ship_detection_module import detect_hulls

    raw_detections = detect_hulls(image_path)

    hulls = []
    for i, d in enumerate(raw_detections):
        x1, y1, x2, y2 = d["bbox_px"]
        lat, lon = d["lat"], d["lon"]

        used_demo_anchor = False
        if lat is None or lon is None:
            # fallback: no real geo metadata on this image -- use the demo
            # anchor so downstream AIS matching still has something to test
            # against. NEVER present this as a real coordinate in the pitch.
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            lat, lon = pixel_to_latlon(cx, cy, EXAMPLE_DEMO_ANCHOR)
            used_demo_anchor = True

        hulls.append(HullDetection(
            hull_id=i,
            bbox=(int(x1), int(y1), int(x2), int(y2)),
            centroid_x=(x1 + x2) / 2,
            centroid_y=(y1 + y2) / 2,
            confidence=d["confidence"],
            timestamp=d["timestamp"],
            lat=lat, lon=lon,
        ))
        if used_demo_anchor:
            print(f"    [note] hull {i}: no geo metadata on source image, "
                  f"using demo-anchor approximation for lat/lon")

    return HullDetectionResult(image_id=image_id, hulls=hulls)


# -----------------------------------------------------------------------------
# STAGE 3: AIS Matching -- REAL, calls VISSHAL's actual matcher
# -----------------------------------------------------------------------------
def run_ais_matching(image_id: str, hull_result: HullDetectionResult, ais_df) -> AISMatchResult:
    from ais_matcher import match_all_hulls

    hull_dicts = []
    for h in hull_result.hulls:
        if h.timestamp:
            ts = datetime.fromisoformat(h.timestamp.replace("Z", "+00:00"))
            ts = ts.replace(tzinfo=None)  # AIS data (real MarineCadastre + our
                                            # synthetic generator) is naive --
                                            # strip tz to keep comparisons valid
        else:
            ts = datetime.now()
        hull_dicts.append({"hull_id": h.hull_id, "lat": h.lat, "lon": h.lon, "timestamp": ts})

    raw_results = match_all_hulls(hull_dicts, ais_df)
    matches = [
        ContractAISMatch(
            hull_id=r.hull_id, has_ais_match=r.has_ais_match,
            matched_mmsi=r.matched_mmsi, suspicion_score=r.suspicion_score,
            reason=r.reason,
        )
        for r in raw_results
    ]
    return AISMatchResult(image_id=image_id, matches=matches)


# -----------------------------------------------------------------------------
# STAGE 4: Drift Simulation -- REAL, calls ocean_wind_loader + drift_simulation
# -----------------------------------------------------------------------------
def run_drift_simulation(image_id: str, slick_result: SlickDetectionResult,
                          detection_time: datetime,
                          image_anchor: tuple = EXAMPLE_DEMO_ANCHOR) -> DriftSimResult:
    """
    For each detected slick component, converts its pixel centroid to a
    lat/lon (via geolocation.py's demo-anchor approximation -- see that
    module's caveats), pulls real ocean current + wind data for the image's
    date/location, and runs the backward drift simulation to estimate the
    slick's likely origin point.

    jurisdiction_zone / within_500m_exclusion remain placeholders -- that's
    SIMI's separate, not-yet-built task (ICG zone lookup), not something
    drift_simulation.py computes.

    Falls back to a clearly-labeled mock per-component if the live
    Open-Meteo fetch fails (e.g. no network), so a demo run doesn't crash
    outright -- but this should be treated as a real failure to fix, not a
    normal path.
    """
    from ocean_wind_loader import fetch_currents_and_wind
    from drift_simulation import simulate_backward_drift

    anchor_lat, anchor_lon = image_anchor
    date_str = detection_time.strftime("%Y-%m-%d")

    weather_row = None
    try:
        weather = fetch_currents_and_wind(
            lat=anchor_lat, lon=anchor_lon, start_date=date_str, end_date=date_str,
        )
        weather["diff"] = (weather["time"] - detection_time).abs()
        weather_row = weather.loc[weather["diff"].idxmin()]
    except Exception as e:
        print(f"    [warning] ocean/wind fetch failed for {image_id} ({e}) -- "
              f"falling back to mocked drift estimates. Fix network access "
              f"before treating this as demo-ready.")

    estimates = []
    for comp in slick_result.components:
        slick_lat, slick_lon = pixel_to_latlon(comp.centroid_x, comp.centroid_y, image_anchor)

        if weather_row is None:
            zone, within_500m, _ = get_jurisdiction_info(slick_lat, slick_lon)
            estimates.append(DriftResult(
                slick_component_id=comp.component_id,
                estimated_origin_lat=slick_lat, estimated_origin_lon=slick_lon,
                estimated_origin_time_offset_hours=6.0,
                jurisdiction_zone=zone,
                within_500m_exclusion=within_500m,
            ))
            continue

        result = simulate_backward_drift(
            slick_lat=slick_lat, slick_lon=slick_lon,
            detection_time=detection_time,
            current_velocity_kmh=weather_row["current_velocity_kmh"],
            current_direction_deg=weather_row["current_direction_deg"],
            wind_speed_kmh=weather_row["wind_speed_kmh"],
            wind_direction_deg=weather_row["wind_direction_deg"],
        )

        zone, within_500m, _ = get_jurisdiction_info(result.origin_lat, result.origin_lon)

        estimates.append(DriftResult(
            slick_component_id=comp.component_id,
            estimated_origin_lat=result.origin_lat,
            estimated_origin_lon=result.origin_lon,
            estimated_origin_time_offset_hours=result.hours_back,
            jurisdiction_zone=zone,
            within_500m_exclusion=within_500m,
        ))

    return DriftSimResult(image_id=image_id, drift_estimates=estimates)


# -----------------------------------------------------------------------------
# FULL PIPELINE
# -----------------------------------------------------------------------------
def run_full_pipeline(image_id: str, image_rgb: np.ndarray, image_path: str,
                       slick_model, ais_df, image_anchor: tuple = EXAMPLE_DEMO_ANCHOR) -> PipelineOutput:
    slicks = run_slick_detection(image_id, image_rgb, slick_model)
    hulls = run_hull_detection(image_id, image_path)
    ais = run_ais_matching(image_id, hulls, ais_df)

    # Reuse the first hull's timestamp as the image's acquisition/detection
    # time (same source Stage 3 already parses from) -- falls back to now()
    # if no hulls were detected or none carried a timestamp.
    if hulls.hulls and hulls.hulls[0].timestamp:
        detection_time = datetime.fromisoformat(
            hulls.hulls[0].timestamp.replace("Z", "+00:00")
        ).replace(tzinfo=None)
    else:
        detection_time = datetime.now()

    drift = run_drift_simulation(image_id, slicks, detection_time, image_anchor)

    return PipelineOutput(image_id=image_id, slicks=slicks, hulls=hulls,
                           ais_matches=ais, drift=drift)


def main():
    import tempfile
    from pathlib import Path

    from predict_and_classify import load_model
    from ais_matcher import generate_synthetic_ais

    print("Loading slick detection model...")
    slick_model = load_model()

    print("Loading AIS data (synthetic for this test run -- swap for real "
          "MarineCadastre CSV via ais_matcher.load_ais_data() when ready)...")
    ais_df = generate_synthetic_ais()

    # Path fixed 2026-09-01 (Phase 0 sweep): this script lives flat in A:\SIH,
    # not nested inside its own subfolder, so it must NOT use "../" -- that
    # pointed one level ABOVE the project root, which doesn't exist. Path is
    # relative to A:\SIH itself.
    test_images = np.load("data/processed/test_images.npy")
    n = min(5, len(test_images))
    print(f"Running full pipeline on {n} test images...\n")

    for i in range(n):
        image_id = f"test_{i}"
        # Use the OS temp dir instead of a hardcoded "/tmp/..." path -- "/tmp"
        # is a Unix convention and is not reliable on Windows (the dev
        # machine here is A:\SIH). tempfile.gettempdir() resolves correctly
        # on both platforms.
        temp_path = str(Path(tempfile.gettempdir()) / f"{image_id}.jpg")
        Image.fromarray(test_images[i]).save(temp_path)

        output = run_full_pipeline(image_id, test_images[i], temp_path, slick_model, ais_df)
        suspects = output.top_suspects()

        print(f"{image_id}: {len(output.slicks.components)} slick(s) "
              f"({output.slicks.num_linear} linear, {output.slicks.num_blob} blob), "
              f"{len(output.hulls.hulls)} hull(s) detected, "
              f"{len(suspects)} suspect(s) flagged")
        for s in suspects:
            print(f"    -> SUSPECT hull {s['hull_id']}: suspicion={s['suspicion_score']} | {s['reason']}")


if __name__ == "__main__":
    main()