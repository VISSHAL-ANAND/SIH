"""
SIH26143 - Pipeline Integration v2: Wire all 4 modules together
Owner: VISSHAL (took over from RATHIMEENA)
Updated 2026-08-26: RINOSH's real hull detector + VISSHAL's real AIS matcher
are now wired in. Only drift simulation remains mocked.

WHAT'S REAL VS MOCKED NOW:
  - Slick detection : REAL (VISSHAL's trained U-Net + shape classifier)
  - Hull detection  : REAL (RINOSH's trained YOLOv8 detector, geo-verified)
  - AIS matching    : REAL (VISSHAL's spatial-temporal matcher)
  - Drift simulation: MOCKED. SIMI's real simulation isn't built yet.

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

import sys
from datetime import datetime

import numpy as np
from PIL import Image

sys.path.append("../sih26143_slick_detection")
sys.path.append("../sih26143_ship_detection")
sys.path.append("../sih26143_ais_matching")

from pipeline_contracts import (
    SlickComponent, SlickDetectionResult,
    HullDetection, HullDetectionResult,
    AISMatch as ContractAISMatch, AISMatchResult,
    DriftResult, DriftSimResult,
    PipelineOutput,
)
from geolocation import EXAMPLE_DEMO_ANCHOR, pixel_to_latlon


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
# STAGE 4: Drift Simulation -- STILL MOCKED, SIMI's real sim isn't built yet
# -----------------------------------------------------------------------------
def run_drift_simulation(image_id: str, slick_result: SlickDetectionResult) -> DriftSimResult:
    """MOCK -- REPLACE WITH REAL BACKWARD DRIFT SIMULATION once SIMI builds it."""
    estimates = [
        DriftResult(
            slick_component_id=comp.component_id,
            estimated_origin_lat=0.0, estimated_origin_lon=0.0,
            estimated_origin_time_offset_hours=6.0,
            jurisdiction_zone="[MOCK -- not yet computed]",
            within_500m_exclusion=False,
        )
        for comp in slick_result.components
    ]
    return DriftSimResult(image_id=image_id, drift_estimates=estimates)


# -----------------------------------------------------------------------------
# FULL PIPELINE
# -----------------------------------------------------------------------------
def run_full_pipeline(image_id: str, image_rgb: np.ndarray, image_path: str,
                       slick_model, ais_df) -> PipelineOutput:
    slicks = run_slick_detection(image_id, image_rgb, slick_model)
    hulls = run_hull_detection(image_id, image_path)
    ais = run_ais_matching(image_id, hulls, ais_df)
    drift = run_drift_simulation(image_id, slicks)

    return PipelineOutput(image_id=image_id, slicks=slicks, hulls=hulls,
                           ais_matches=ais, drift=drift)


def main():
    from predict_and_classify import load_model
    from ais_matcher import generate_synthetic_ais

    print("Loading slick detection model...")
    slick_model = load_model()

    print("Loading AIS data (synthetic for this test run -- swap for real "
          "MarineCadastre CSV via ais_matcher.load_ais_data() when ready)...")
    ais_df = generate_synthetic_ais()

    test_images = np.load("../sih26143_slick_detection/data/processed/test_images.npy")
    n = min(5, len(test_images))
    print(f"Running full pipeline on {n} test images...\n")

    for i in range(n):
        image_id = f"test_{i}"
        temp_path = f"/tmp/{image_id}.jpg"
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
