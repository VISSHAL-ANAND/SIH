"""
SIH26143 - Dynamic Georeferencing Module
========================================
Reads affine transform matrices and Coordinate Reference Systems (CRS)
directly from uploaded GeoTIFF files using rasterio.
For plain JPG/PNG images, accepts explicit user-provided centroid coordinates.
"""

import math
from pathlib import Path
from typing import Tuple, Optional, Dict, Any

try:
    import rasterio
    from rasterio.warp import transform as rasterio_transform
    RASTERIO_AVAILABLE = True
except ImportError:
    RASTERIO_AVAILABLE = False


def extract_geotiff_coords(geotiff_path: str | Path, px: float = 0.0, py: float = 0.0) -> Optional[Tuple[float, float]]:
    """
    Convert pixel (column, row) to the geographic center of that pixel and
    return WGS84 (latitude, longitude).

    rasterio.transform.xy(..., offset="center") is used deliberately: a
    detection centroid represents a pixel center, not the outer corner of a
    raster cell. This matters when the dashboard displays coordinates as
    investigation evidence.
    """
    if not RASTERIO_AVAILABLE:
        return None

    path_obj = Path(geotiff_path)
    if not path_obj.exists() or path_obj.suffix.lower() not in ('.tif', '.tiff'):
        return None

    try:
        with rasterio.open(str(path_obj)) as src:
            if src.transform is None or src.crs is None:
                return None

            x_crs, y_crs = rasterio.transform.xy(
                src.transform, py, px, offset="center"
            )

            if src.crs.to_epsg() == 4326:
                return round(float(y_crs), 6), round(float(x_crs), 6)

            lons, lats = rasterio_transform(
                src.crs, "EPSG:4326", [x_crs], [y_crs]
            )
            return round(float(lats[0]), 6), round(float(lons[0]), 6)
    except Exception as err:
        print(f"[geolocation] Could not parse GeoTIFF transform from {path_obj.name}: {err}")

    return None


def extract_geotiff_bounds(geotiff_path: str | Path) -> Optional[Dict[str, Any]]:
    """Extract WGS84 bounds and raster dimensions from a GeoTIFF."""
    if not RASTERIO_AVAILABLE:
        return None

    path_obj = Path(geotiff_path)
    if not path_obj.exists() or path_obj.suffix.lower() not in ('.tif', '.tiff'):
        return None

    try:
        with rasterio.open(str(path_obj)) as src:
            bounds = src.bounds
            w, h = src.width, src.height
            xs = [bounds.left, bounds.right, bounds.right, bounds.left]
            ys = [bounds.bottom, bounds.bottom, bounds.top, bounds.top]

            if src.crs and src.crs.to_epsg() != 4326:
                lons, lats = rasterio_transform(src.crs, "EPSG:4326", xs, ys)
            else:
                lons, lats = xs, ys

            south, north = min(lats), max(lats)
            west, east = min(lons), max(lons)
            centroid_lat = round((south + north) / 2.0, 6)
            centroid_lon = round((west + east) / 2.0, 6)

            return {
                "centroid": [centroid_lat, centroid_lon],
                "bounds": [[round(south, 6), round(west, 6)], [round(north, 6), round(east, 6)]],
                "width_px": w,
                "height_px": h,
                "crs": str(src.crs),
                "geolocation_status": "REAL",
            }
    except Exception as err:
        print(f"[geolocation] Bounds extraction error from {path_obj.name}: {err}")

    return None


def compute_image_bounds(
    center_lat: float,
    center_lon: float,
    width_px: int = 512,
    height_px: int = 512,
    meters_per_pixel: float = 10.0
) -> Dict[str, Any]:
    """Compute an estimated bounding box for a plain image with known centroid."""
    width_km = (width_px * meters_per_pixel) / 1000.0
    height_km = (height_px * meters_per_pixel) / 1000.0

    lat_half = (height_km / 2.0) / 111.0
    lon_half = (width_km / 2.0) / (111.0 * max(0.1, math.cos(math.radians(center_lat))))

    south = round(center_lat - lat_half, 6)
    north = round(center_lat + lat_half, 6)
    west = round(center_lon - lon_half, 6)
    east = round(center_lon + lon_half, 6)

    return {
        "centroid": [center_lat, center_lon],
        "bounds": [[south, west], [north, east]],
        "width_px": width_px,
        "height_px": height_px,
        "geolocation_status": "ESTIMATED",
    }


def pixel_to_latlon(
    px: float,
    py: float,
    center_lat: float,
    center_lon: float,
    meters_per_pixel: float = 10.0
) -> Tuple[float, float]:
    """Approximate a pixel location relative to an explicitly supplied image center."""
    east_km = (px * meters_per_pixel) / 1000.0
    south_km = (py * meters_per_pixel) / 1000.0
    lat_offset = -south_km / 111.0
    lon_offset = east_km / (111.0 * math.cos(math.radians(center_lat)))
    return round(center_lat + lat_offset, 6), round(center_lon + lon_offset, 6)
