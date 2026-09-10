"""
SIH26143 - Dynamic Georeferencing Module
========================================
Reads affine transforms and CRSs from GeoTIFF files using rasterio.
GeoTIFF pixel coordinates are converted at the PIXEL CENTER and returned
in WGS84. Plain images can only use an explicitly supplied scene center and
an assumed ground sampling distance; those coordinates are therefore marked
as estimated by the caller.
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


def extract_geotiff_coords(
    geotiff_path: str | Path,
    px: float = 0.0,
    py: float = 0.0,
) -> Optional[Tuple[float, float]]:
    """Return WGS84 (lat, lon) for the CENTER of raster pixel (px, py)."""
    if not RASTERIO_AVAILABLE:
        return None

    path_obj = Path(geotiff_path)
    if not path_obj.exists() or path_obj.suffix.lower() not in (".tif", ".tiff"):
        return None

    try:
        with rasterio.open(str(path_obj)) as src:
            if src.transform is None or src.crs is None or src.transform.is_identity:
                return None

            # rasterio.transform.xy uses row, col and defaults to pixel center.
            x_crs, y_crs = rasterio.transform.xy(src.transform, py, px, offset="center")
            if src.crs.to_epsg() == 4326:
                return round(float(y_crs), 6), round(float(x_crs), 6)

            lons, lats = rasterio_transform(src.crs, "EPSG:4326", [x_crs], [y_crs])
            return round(float(lats[0]), 6), round(float(lons[0]), 6)
    except Exception as err:
        print(f"[geolocation] Could not parse GeoTIFF transform from {path_obj.name}: {err}")

    return None


def extract_geotiff_bounds(geotiff_path: str | Path) -> Optional[Dict[str, Any]]:
    """Extract GeoTIFF bounds and WGS84 centroid."""
    if not RASTERIO_AVAILABLE:
        return None

    path_obj = Path(geotiff_path)
    if not path_obj.exists() or path_obj.suffix.lower() not in (".tif", ".tiff"):
        return None

    try:
        with rasterio.open(str(path_obj)) as src:
            bounds = src.bounds
            xs = [bounds.left, bounds.right, bounds.right, bounds.left]
            ys = [bounds.bottom, bounds.bottom, bounds.top, bounds.top]

            if src.crs and src.crs.to_epsg() != 4326:
                lons, lats = rasterio_transform(src.crs, "EPSG:4326", xs, ys)
            else:
                lons, lats = xs, ys

            south, north = min(lats), max(lats)
            west, east = min(lons), max(lons)
            return {
                "centroid": [round((south + north) / 2.0, 6), round((west + east) / 2.0, 6)],
                "bounds": [[round(south, 6), round(west, 6)], [round(north, 6), round(east, 6)]],
                "width_px": src.width,
                "height_px": src.height,
            }
    except Exception as err:
        print(f"[geolocation] Bounds extraction error from {path_obj.name}: {err}")

    return None


def compute_image_bounds(
    center_lat: float,
    center_lon: float,
    width_px: int = 512,
    height_px: int = 512,
    meters_per_pixel: float = 10.0,
) -> Dict[str, Any]:
    """Estimate a plain-image footprint around an explicitly supplied center."""
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
        "ground_sample_distance_m": meters_per_pixel,
    }


def pixel_to_latlon(
    px: float,
    py: float,
    center_lat: float,
    center_lon: float,
    width_px: int = 512,
    height_px: int = 512,
    meters_per_pixel: float = 10.0,
) -> Tuple[float, float]:
    """Estimate WGS84 position from a plain-image pixel and supplied scene center."""
    east_px = px - (width_px - 1) / 2.0
    south_px = py - (height_px - 1) / 2.0
    east_km = (east_px * meters_per_pixel) / 1000.0
    south_km = (south_px * meters_per_pixel) / 1000.0
    lat_offset = -south_km / 111.0
    lon_offset = east_km / (111.0 * math.cos(math.radians(center_lat)))
    return round(center_lat + lat_offset, 6), round(center_lon + lon_offset, 6)
