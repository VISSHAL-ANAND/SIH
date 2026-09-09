"""
SIH26143 - AI & Shape Analysis Engine
======================================
Provides U-Net SAR slick segmentation, YOLOv8 hull detection,
and PCA shape classification logic (minor/major eigenvalue ratio < 0.15).
"""

import math
import numpy as np
import cv2
from typing import Dict, Any, Tuple, Optional


def classify_slick_pca_shape(binary_mask: Optional[np.ndarray] = None) -> Dict[str, Any]:
    """
    Performs Principal Component Analysis (PCA) on pixel coordinates of connected slick regions.
    Eigenvalue ratio (minor / major) < 0.15 indicates a LINEAR trailing active discharge from a moving vessel.
    Ratio >= 0.15 indicates a static BLOB leak.
    """
    if binary_mask is None:
        # Generate representative linear trailing slick mask for MSC Elsa 3 scenario
        binary_mask = np.zeros((100, 100), dtype=np.uint8)
        # Draw linear trailing slick (long thin line)
        cv2.line(binary_mask, (10, 20), (90, 80), 1, thickness=3)

    ys, xs = np.where(binary_mask > 0)
    if len(xs) < 5:
        return {
            "class": "blob",
            "shape_class": "blob",
            "eigenvalue_ratio": 0.50,
            "description": "Insufficient pixels for PCA"
        }

    coords = np.stack([xs, ys], axis=1).astype(np.float64)
    coords -= coords.mean(axis=0)
    cov = np.cov(coords.T)
    eigvals, eigvecs = np.linalg.eigh(cov)  # ascending order
    minor, major = float(eigvals[0]), float(eigvals[1])

    eigenvalue_ratio = 0.0 if major <= 1e-9 else float(minor / major)
    shape_class = "linear" if eigenvalue_ratio < 0.15 else "blob"

    major_vec = eigvecs[:, 1]
    orientation_deg = float(np.degrees(np.arctan2(major_vec[1], major_vec[0])) % 180)

    return {
        "class": shape_class,
        "shape_class": shape_class,
        "eigenvalue_ratio": round(eigenvalue_ratio, 4),
        "orientation_deg": round(orientation_deg, 2),
        "description": "Linear trailing discharge (ratio < 0.15)" if shape_class == "linear" else "Static circular leak (ratio >= 0.15)"
    }


def run_sar_segmentation(pixel_count: int = 1000) -> Dict[str, Any]:
    """
    Simulates U-Net SAR slick segmentation pipeline.
    Outputs estimated spill area assuming 10m x 10m SAR pixel resolution.
    """
    spill_area_sq_m = float(pixel_count * 100.0)  # 1,000 pixels * 100 m²/pixel = 100,000 m²
    pca_result = classify_slick_pca_shape()

    return {
        "spill_area_sq_m": spill_area_sq_m,
        "pixel_count": pixel_count,
        "resolution_meters_per_pixel": 10.0,
        "shape_classification": pca_result
    }


def run_hull_detection(slick_lat: float = 9.3764, slick_lon: float = 75.9758) -> Dict[str, Any]:
    """
    Simulates YOLOv8 physical vessel hull detection in SAR image.
    Outputs detected hull coordinates near slick centroid.
    """
    hull_lat = round(slick_lat + 0.0436, 4)  # ~9.4200° N
    hull_lon = round(slick_lon + 0.0442, 4)  # ~76.0200° E

    return {
        "hull_detected": True,
        "confidence": 0.94,
        "coordinates": [hull_lat, hull_lon],
        "vessel_class": "vessel_hull",
        "bounding_box_px": [140, 220, 185, 265]
    }
