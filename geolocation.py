"""
SIH26143 - Geolocation helper: demo-anchor pixel->lat/lon approximation
=========================================================================

WHY THIS FILE EXISTS: ship_detection_module.py's real geo-conversion only
works on georeferenced rasters (GeoTIFF with a valid transform). Our actual
demo/training images (Kaggle SOS chips, HRSID/SSDD chips) are plain jpg/png
with NO geo metadata -- so on those, lat/lon legitimately comes back None
from the real pipeline.

This module is the FALLBACK used ONLY in that case, so the rest of the
pipeline (AIS matching, drift simulation) still has *something* to run
against during development/demo. It is NOT real geolocation -- it assumes
a fixed anchor point (top-left corner of the image) and a fixed, made-up
meters-per-pixel scale, then offsets from there.

BE HONEST IN THE PITCH: any lat/lon that came from this module (not from a
real georeferenced raster) should be labeled as a demo-anchor approximation,
never presented as a genuine geocoded position. integration_pipeline.py
already enforces this -- it only calls pixel_to_latlon() when the real
conversion returned None, and never overwrites a real coordinate.

If you get a real georeferenced Sentinel-1 scene before the demo, that
image's hull/slick coordinates will come from ship_detection_module.py's
real rasterio-based conversion instead, and this file won't be touched
for that image at all.
"""

import math

# Gujarat demo anchor (lat, lon) -- matches the anchor used in
# ocean_wind_loader.py's example and drift_simulation.py's self-tests.
EXAMPLE_DEMO_ANCHOR = (20.85, 69.20)

# Made-up but documented scale: how many meters one pixel represents in our
# demo chips. This is NOT derived from any real sensor resolution -- pick a
# number and be upfront about it. Sentinel-1 GRD is ~10m/pixel in reality,
# so 10.0 is a reasonable "as if this were a real Sentinel-1 chip" stand-in.
METERS_PER_PIXEL = 10.0


def pixel_to_latlon(px: float, py: float, anchor: tuple = EXAMPLE_DEMO_ANCHOR) -> tuple:
    """
    Approximate a pixel (x, y) position as a lat/lon, treating `anchor` as
    the lat/lon of pixel (0, 0) (top-left corner of the image) and walking
    METERS_PER_PIXEL meters per pixel right (+x) and down (+y).

    This mirrors the same lat/lon-offset math used in drift_simulation.py's
    _km_to_latlon_offset, just starting from a pixel offset instead of a
    current/wind-driven displacement.

    Parameters
    ----------
    px, py : pixel coordinates within the image (e.g. a detected hull or
             slick centroid)
    anchor : (lat, lon) of pixel (0, 0). Defaults to the Gujarat demo anchor.

    Returns
    -------
    (lat, lon) tuple -- APPROXIMATE, not real geocoding. See module docstring.
    """
    anchor_lat, anchor_lon = anchor

    east_km = (px * METERS_PER_PIXEL) / 1000.0
    south_km = (py * METERS_PER_PIXEL) / 1000.0  # +y in image space = south

    lat_offset = -south_km / 111.0  # moving south = decreasing latitude
    lon_offset = east_km / (111.0 * math.cos(math.radians(anchor_lat)))

    return round(anchor_lat + lat_offset, 6), round(anchor_lon + lon_offset, 6)


# -----------------------------------------------------------------------------
# Self-test: sanity-check the offset directions with simple, hand-verifiable
# inputs before trusting it anywhere in the pipeline.
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    print("Running self-test with known simple inputs...\n")

    # Pixel (0, 0) should return the anchor itself, unchanged.
    lat, lon = pixel_to_latlon(0, 0)
    print(f"pixel (0,0)       -> ({lat}, {lon})  (expected == anchor {EXAMPLE_DEMO_ANCHOR})")
    assert (lat, lon) == EXAMPLE_DEMO_ANCHOR, "FAILED: pixel (0,0) should equal the anchor exactly"
    print("  PASSED\n")

    # Moving right (+x) only should increase longitude, leave latitude unchanged.
    lat, lon = pixel_to_latlon(1000, 0)
    print(f"pixel (1000,0)    -> ({lat}, {lon})  (expect lon > anchor lon, lat == anchor lat)")
    assert lon > EXAMPLE_DEMO_ANCHOR[1], "FAILED: moving +x should increase longitude"
    assert abs(lat - EXAMPLE_DEMO_ANCHOR[0]) < 1e-9, "FAILED: moving +x should not change latitude"
    print("  PASSED\n")

    # Moving down (+y) only should decrease latitude (moving south), leave longitude unchanged.
    lat, lon = pixel_to_latlon(0, 1000)
    print(f"pixel (0,1000)    -> ({lat}, {lon})  (expect lat < anchor lat, lon == anchor lon)")
    assert lat < EXAMPLE_DEMO_ANCHOR[0], "FAILED: moving +y (down) should decrease latitude"
    assert abs(lon - EXAMPLE_DEMO_ANCHOR[1]) < 1e-9, "FAILED: moving +y should not change longitude"
    print("  PASSED\n")

    print("All self-tests passed. This is still an APPROXIMATION -- see the")
    print("module docstring before using its output anywhere near a claim of")
    print("real geocoding in the pitch.")