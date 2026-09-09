"""
SIH26143 — Geo-coordinate conversion sanity test
=====================================================

ship_detection_module.py's lat/lon conversion has never actually run,
since our only test image (a plain HRSID jpg) had no geo metadata.
This creates a small synthetic georeferenced GeoTIFF with a KNOWN
transform, so we can verify the pixel->lat/lon math independently of
whether the detector finds anything in it.

Usage
-----
    pip install rasterio pyproj numpy --quiet
    python -m tests.test_geo_conversion
"""

import numpy as np
from pathlib import Path

from main.ship_detection_module import _pixel_to_latlon, _try_read_geotransform


TEST_DIR = Path(__file__).resolve().parent


def make_synthetic_geotiff(path: str):
    """
    A tiny 100x100 raster in plain EPSG:4326 (lat/lon), with a known,
    hand-computable transform: top-left corner at (lon=80.000, lat=13.000),
    0.0001 degrees per pixel (~11m at the equator).
    """
    import rasterio
    from rasterio.transform import from_origin

    transform = from_origin(80.000, 13.000, 0.0001, 0.0001)
    data = np.zeros((100, 100), dtype=np.uint8)

    with rasterio.open(
        path, "w",
        driver="GTiff",
        height=100, width=100, count=1,
        dtype=data.dtype,
        crs="EPSG:4326",
        transform=transform,
    ) as dst:
        dst.write(data, 1)

    return transform


def make_synthetic_utm_geotiff(path: str):
    """
    Same idea but in a projected CRS (UTM zone 44N, covers south India),
    to verify the pyproj reprojection branch specifically — this is the
    realistic case for actual Sentinel-1 GRD products, which are usually
    delivered in a UTM projection, not raw lat/lon.
    """
    import rasterio
    from rasterio.transform import from_origin

    # Arbitrary UTM 44N origin roughly near Chennai, 10m pixel spacing
    # (typical Sentinel-1 GRD resolution)
    transform = from_origin(400000.0, 1450000.0, 10.0, 10.0)
    data = np.zeros((100, 100), dtype=np.uint8)

    with rasterio.open(
        path, "w",
        driver="GTiff",
        height=100, width=100, count=1,
        dtype=data.dtype,
        crs="EPSG:32644",  # WGS 84 / UTM zone 44N
        transform=transform,
    ) as dst:
        dst.write(data, 1)


def main():
    print("=== Test 1: plain lat/lon (EPSG:4326) raster ===")
    latlon_path = TEST_DIR / "test_synthetic_latlon.tif"
    make_synthetic_geotiff(str(latlon_path))
    transform, crs = _try_read_geotransform(str(latlon_path))
    if transform is None:
        raise SystemExit("FAILED: geotransform wasn't read at all — check rasterio install.")

    # Pixel (0,0) is a full pixel wide/tall — rasterio.transform.xy() returns
    # the pixel CENTER by default (which is what we want, since detect_hulls
    # converts box centers), so this should be half a pixel in from the
    # (80.000, 13.000) corner: (80.00005, 12.99995).
    lat, lon = _pixel_to_latlon(transform, crs, 0, 0)
    print(f"pixel (0,0)     -> lat={lat:.6f}, lon={lon:.6f}  (expected lat=12.999950, lon=80.000050)")
    assert abs(lat - 12.99995) < 1e-6 and abs(lon - 80.00005) < 1e-6, "MISMATCH on origin pixel!"

    # Pixel (100,100) center: 100 pixels right/down from the corner, plus
    # the same half-pixel center offset.
    lat, lon = _pixel_to_latlon(transform, crs, 100, 100)
    print(f"pixel (100,100) -> lat={lat:.6f}, lon={lon:.6f}  (expected lat=12.989950, lon=80.010050)")
    assert abs(lat - 12.98995) < 1e-6 and abs(lon - 80.01005) < 1e-6, "MISMATCH on offset pixel!"
    print("PASSED\n")

    print("=== Test 2: projected UTM raster (realistic Sentinel-1 case) ===")
    utm_path = TEST_DIR / "test_synthetic_utm.tif"
    make_synthetic_utm_geotiff(str(utm_path))
    transform, crs = _try_read_geotransform(str(utm_path))
    if transform is None:
        raise SystemExit("FAILED: UTM geotransform wasn't read.")

    lat, lon = _pixel_to_latlon(transform, crs, 0, 0)
    print(f"pixel (0,0) reprojected to WGS84 -> lat={lat:.6f}, lon={lon:.6f}")
    # Sanity range check only (exact value depends on UTM zone math) —
    # this UTM 44N origin should land roughly in south India, NOT at (0,0)
    # or some wildly wrong coordinate like (90, 0).
    assert 8.0 < lat < 20.0 and 75.0 < lon < 85.0, \
        f"Reprojected coordinate ({lat}, {lon}) is outside the expected south-India range — reprojection is broken."
    print("PASSED — reprojection lands in the expected geographic range.\n")

    print("All geo-conversion tests passed. The lat/lon code path in "
          "ship_detection_module.py is now verified, not just assumed working.")


if __name__ == "__main__":
    main()