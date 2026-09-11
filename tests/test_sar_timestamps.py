from pathlib import Path

import pytest

from main.imw_real_pipeline import image_timestamp
from main.ship_detection_module import _try_extract_timestamp


def test_sentinel1_filename_timestamp_is_acquisition_time():
    path = Path("s1a-iw-grd-vv-20260621t234859-20260621t234912-065074-0833c9-001.tiff")
    expected = "2026-06-21T23:48:59Z"
    assert image_timestamp(path) == expected
    assert _try_extract_timestamp(str(path)) == expected


def test_file_mtime_is_not_used_as_sar_acquisition_time(tmp_path):
    path = tmp_path / "sentinel_scene.tiff"
    path.write_bytes(b"test")
    # A non-Sentinel filename has no trustworthy acquisition timestamp.
    assert image_timestamp(path) is None


def test_pipeline_rejects_unverified_acquisition_time(tmp_path):
    path = tmp_path / "scene.tiff"
    path.write_bytes(b"test")
    with pytest.raises(ValueError, match="acquisition time could not be verified"):
        from main.imw_real_pipeline import run_real_pipeline
        run_real_pipeline(path, use_ais=False)
