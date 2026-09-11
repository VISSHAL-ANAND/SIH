"""
SIH26143 - Dynamic Georeferencing Module
========================================
Reads affine transforms and CRSs from GeoTIFF files using rasterio.
GeoTIFF pixel coordinates are converted at the PIXEL CENTER and returned
in WGS84. Sentinel-1 GRD measurement TIFFs inside a SAFE product often
carry no CRS/affine transform themselves; for those files this module
reads the matching annotation XML geolocation grid and interpolates the
published line/pixel tie points. Plain images can only use an explicitly
supplied scene center and an assumed ground sampling distance; those
coordinates are therefore marked as estimated by the caller.
"""

import math
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Tuple, Optional, Dict, Any

try:
    import rasterio
    from rasterio.warp import transform as rasterio_transform
    RASTERIO_AVAILABLE = True
except ImportError:
    RASTERIO_AVAILABLE = False


def extract_geotiff_coords(geotiff_path: str | Path, px: float = 0.0, py: float = 0.0) -> Optional[Tuple[float, float]]:
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
            x_crs, y_crs = rasterio.transform.xy(src.transform, py, px, offset="center")
            if src.crs.to_epsg() == 4326:
                return round(float(y_crs), 6), round(float(x_crs), 6)
            lons, lats = rasterio_transform(src.crs, "EPSG:4326", [x_crs], [y_crs])
            return round(float(lats[0]), 6), round(float(lons[0]), 6)
    except Exception as err:
        print(f"[geolocation] Could not parse GeoTIFF transform from {path_obj.name}: {err}")
    return None


def _find_sentinel1_annotation_xml(measurement_path: str | Path) -> Optional[Path]:
    """Find the matching Sentinel-1 GRD annotation XML for a measurement TIFF.

    First searches the TIFF's own SAFE ancestors. For the browser upload
    path, the API removes the temporary TIFF after processing, so an operator
    may set IMW_SENTINEL1_SAFE_ROOT to the local SAFE product root; the same
    original measurement filename is then resolved against its annotation/
    directory without copying or modifying the SAFE product.
    """
    path = Path(measurement_path)
    if path.suffix.lower() not in {".tif", ".tiff"}:
        return None
    stem = path.stem.lower()

    for ancestor in path.parents:
        annotation_dir = ancestor / "annotation"
        if not annotation_dir.is_dir():
            continue
        exact = annotation_dir / f"{stem}.xml"
        if exact.is_file():
            return exact

    safe_root = os.getenv("IMW_SENTINEL1_SAFE_ROOT")
    if safe_root:
        root = Path(safe_root)
        if root.is_dir():
            direct = root / "annotation" / f"{stem}.xml"
            if direct.is_file():
                return direct
            for annotation_dir in root.rglob("annotation"):
                candidate = annotation_dir / f"{stem}.xml"
                if candidate.is_file():
                    return candidate
    return None


def _read_sentinel1_geolocation_grid(annotation_xml: str | Path) -> list[tuple[float, float, float, float]]:
    """Read Sentinel-1 geolocation grid points as (line, pixel, lat, lon)."""
    root = ET.parse(annotation_xml).getroot()
    points: list[tuple[float, float, float, float]] = []
    for point in root.findall(".//geolocationGridPoint"):
        values = [point.findtext(tag) for tag in ("line", "pixel", "latitude", "longitude")]
        if any(value is None for value in values):
            continue
        try:
            points.append(tuple(float(value) for value in values))
        except ValueError:
            continue
    if not points:
        raise ValueError(f"No geolocationGridPoint entries found in {annotation_xml}")
    return points


def _bracket(values: list[float], value: float) -> tuple[float, float]:
    """Return the two grid coordinates bracketing value, clamped at edges."""
    if value <= values[0]:
        return values[0], values[0]
    if value >= values[-1]:
        return values[-1], values[-1]
    for left, right in zip(values, values[1:]):
        if left <= value <= right:
            return left, right
    return values[-1], values[-1]


def sentinel1_annotation_pixel_to_latlon(annotation_xml: str | Path, px: float, py: float) -> Tuple[float, float]:
    """Convert Sentinel-1 image pixel (column=px, line=row=py) to WGS84.

    Uses bilinear interpolation between the surrounding published
    Sentinel-1 geolocation tie points. No scene-center or GSD assumption
    is introduced.
    """
    points = _read_sentinel1_geolocation_grid(annotation_xml)
    lines = sorted({p[0] for p in points})
    pixels = sorted({p[1] for p in points})
    lookup = {(line, pixel): (lat, lon) for line, pixel, lat, lon in points}
    l0, l1 = _bracket(lines, float(py))
    p0, p1 = _bracket(pixels, float(px))

    def value(line: float, pixel: float) -> tuple[float, float]:
        if (line, pixel) not in lookup:
            raise ValueError(f"Incomplete Sentinel-1 geolocation grid: missing ({line}, {pixel})")
        return lookup[(line, pixel)]

    a_lat, a_lon = value(l0, p0)
    b_lat, b_lon = value(l0, p1)
    c_lat, c_lon = value(l1, p0)
    d_lat, d_lon = value(l1, p1)
    tx = 0.0 if p1 == p0 else (float(px) - p0) / (p1 - p0)
    ty = 0.0 if l1 == l0 else (float(py) - l0) / (l1 - l0)
    top_lat = a_lat + tx * (b_lat - a_lat)
    top_lon = a_lon + tx * (b_lon - a_lon)
    bottom_lat = c_lat + tx * (d_lat - c_lat)
    bottom_lon = c_lon + tx * (d_lon - c_lon)
    return round(top_lat + ty * (bottom_lat - top_lat), 8), round(top_lon + ty * (bottom_lon - top_lon), 8)


def extract_sentinel1_coords(measurement_path: str | Path, px: float = 0.0, py: float = 0.0) -> Optional[Tuple[float, float]]:
    """Return real WGS84 coordinates using a matching Sentinel-1 SAFE XML."""
    annotation = _find_sentinel1_annotation_xml(measurement_path)
    if annotation is None:
        return None
    try:
        return sentinel1_annotation_pixel_to_latlon(annotation, px, py)
    except Exception as err:
        print(f"[geolocation] Could not parse Sentinel-1 annotation for {Path(measurement_path).name}: {err}")
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
            return {"centroid": [round((south + north) / 2.0, 6), round((west + east) / 2.0, 6)], "bounds": [[round(south, 6), round(west, 6)], [round(north, 6), round(east, 6)]], "width_px": src.width, "height_px": src.height}
    except Exception as err:
        print(f"[geolocation] Bounds extraction error from {path_obj.name}: {err}")
    return None


def compute_image_bounds(center_lat: float, center_lon: float, width_px: int = 512, height_px: int = 512, meters_per_pixel: float = 10.0) -> Dict[str, Any]:
    """Estimate a plain-image footprint around an explicitly supplied center."""
    width_km = (width_px * meters_per_pixel) / 1000.0
    height_km = (height_px * meters_per_pixel) / 1000.0
    lat_half = (height_km / 2.0) / 111.0
    lon_half = (width_km / 2.0) / (111.0 * max(0.1, math.cos(math.radians(center_lat))))
    south, north = round(center_lat - lat_half, 6), round(center_lat + lat_half, 6)
    west, east = round(center_lon - lon_half, 6), round(center_lon + lon_half, 6)
    return {"centroid": [center_lat, center_lon], "bounds": [[south, west], [north, east]], "width_px": width_px, "height_px": height_px, "geolocation_status": "ESTIMATED", "ground_sample_distance_m": meters_per_pixel}


def pixel_to_latlon(px: float, py: float, center_lat: float, center_lon: float, width_px: int = 512, height_px: int = 512, meters_per_pixel: float = 10.0) -> Tuple[float, float]:
    """Estimate WGS84 position from a plain-image pixel and supplied scene center."""
    east_px = px - (width_px - 1) / 2.0
    south_px = py - (height_px - 1) / 2.0
    east_km = (east_px * meters_per_pixel) / 1000.0
    south_km = (south_px * meters_per_pixel) / 1000.0
    lat_offset = -south_km / 111.0
    lon_offset = east_km / (111.0 * math.cos(math.radians(center_lat)))
    return round(center_lat + lat_offset, 6), round(center_lon + lon_offset, 6)
