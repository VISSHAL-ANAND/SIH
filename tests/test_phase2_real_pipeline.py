"""Phase-2 tests for the real-only IMW pipeline adapter."""
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from main.imw_real_pipeline import filter_ais_for_hulls, image_timestamp


def test_filter_ais_normalizes_utc_and_keeps_nearby_records():
    ais = pd.DataFrame([
        {"mmsi": "111", "lat": 10.0, "lon": 76.0,
         "timestamp": pd.Timestamp("2026-08-20 12:00:00"), "vessel_name": "A"},
        {"mmsi": "222", "lat": 20.0, "lon": 80.0,
         "timestamp": pd.Timestamp("2026-08-20 12:00:00"), "vessel_name": "B"},
    ])
    hulls = [{
        "lat": 10.01, "lon": 76.01,
        "timestamp": "2026-08-20T12:00:00Z",
    }]
    result = filter_ais_for_hulls(ais, hulls, radius_km=25, time_hours=1)
    assert list(result["mmsi"]) == ["111"]


def test_image_timestamp_reads_sentinel1_filename(tmp_path: Path):
    path = tmp_path / "S1A_IW_GRDH_1SDV_20260820T031400_20260820T031425_TEST.tif"
    path.write_bytes(b"not-a-real-raster")
    assert image_timestamp(path) == "2026-08-20T03:14:00Z"
