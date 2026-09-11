"""
SIH26143 - Slick Detection: Linear-vs-Blob Shape Classifier
Owner: VISSHAL
Task: Build linear-vs-blob slick shape classifier

WHY THIS MATTERS MORE THAN ORIGINALLY PLANNED:
The dataset we ended up using (Kaggle SOS) has no separate "look-alike"
class -- unlike the original 5-class MKLab plan, the U-Net can't be trained
to directly tell a real spill apart from a look-alike (wind slicks, algae,
biogenic films, etc). This classifier is now doing double duty:
  1. Its original job: is this slick shape consistent with a MOVING VESSEL
     discharge (linear/trailing) vs a STATIC LEAK (blob)? Feeds directly into
     RINOSH/ASHMIL's hull-matching -- a linear slick is a real lead, a blob
     is not tied to a passing ship.
  2. An informal false-positive filter: look-alikes (wind streaks, current
     boundaries) tend to be very thin, very long, and low-density -- often
     distinguishable from genuine linear discharge trails on shape alone.
     This is NOT a substitute for a trained look-alike classifier, just a
     partial mitigation -- flag this honestly in the pitch, don't oversell it.

APPROACH: rule-based / geometric, not a trained model. Deliberately chosen
for a 3-day sprint: zero training time, fully deterministic, and -- useful
for judges -- fully explainable ("flagged linear because elongation_ratio
was 0.08, meaning 92% of the shape's spread is along one axis").

Method: PCA on the (y, x) pixel coordinates of each connected slick region.
  - eigenvalue ratio (minor/major) near 0  -> all the spread is along one
    direction -> LINEAR (a trail)
  - eigenvalue ratio near 1                -> spread is roughly equal in
    every direction -> BLOB (roughly circular/compact)
This is scale- and rotation-invariant, so it doesn't matter which way the
slick is oriented in the image or how big it is.
"""

import numpy as np
import cv2
from dataclasses import dataclass, asdict


MIN_COMPONENT_AREA = 20        # pixels -- ignore specks smaller than this (noise, not slicks)
LINEAR_THRESHOLD = 0.15        # eigenvalue ratio below this -> classified as linear
MAX_PCA_POINTS = 100_000       # cap expensive PCA work for very large real-SAR components


@dataclass
class SlickComponent:
    component_id: int
    area_pixels: int
    centroid_x: float
    centroid_y: float
    bbox: tuple            # (x_min, y_min, x_max, y_max) in pixel coords
    elongation_ratio: float  # 0 = perfectly linear, 1 = perfectly circular
    shape_class: str        # "linear" or "blob"
    aspect_ratio: float     # corroborating signal from oriented bounding box
    orientation_deg: float  # angle of the dominant axis, useful for drift-direction sanity checks
    spill_area_sq_meters: float = 0.0  # assumes 10 m × 10 m SAR pixels


def _pca_elongation(ys: np.ndarray, xs: np.ndarray):
    """Returns (elongation_ratio, orientation_deg) from PCA on pixel coordinates."""
    coords = np.stack([xs, ys], axis=1).astype(np.float64)
    coords -= coords.mean(axis=0)
    cov = np.cov(coords.T)
    eigvals, eigvecs = np.linalg.eigh(cov)  # ascending order
    minor, major = eigvals[0], eigvals[1]
    ratio = 0.0 if major <= 1e-9 else float(minor / major)

    # orientation of the dominant (major) axis, in degrees, 0-180
    major_vec = eigvecs[:, 1]
    orientation = float(np.degrees(np.arctan2(major_vec[1], major_vec[0])) % 180)

    return ratio, orientation


def _component_coordinates(labels: np.ndarray, label_id: int, stats: np.ndarray):
    """Return representative coordinates without repeatedly scanning a huge frame.

    Real Sentinel-1 scenes can contain hundreds of millions of pixels. The old
    implementation called ``np.where(labels == label_id)`` for every component,
    forcing a full-frame scan and creating enormous temporary arrays. For large
    components we instead inspect a strided view of that component's bounding
    box, capped at MAX_PCA_POINTS. Small components still use every pixel.
    """
    x0 = int(stats[label_id, cv2.CC_STAT_LEFT])
    y0 = int(stats[label_id, cv2.CC_STAT_TOP])
    width = int(stats[label_id, cv2.CC_STAT_WIDTH])
    height = int(stats[label_id, cv2.CC_STAT_HEIGHT])
    area = int(stats[label_id, cv2.CC_STAT_AREA])

    if width <= 0 or height <= 0:
        return np.empty(0, dtype=np.int64), np.empty(0, dtype=np.int64)

    bbox_pixels = width * height
    step = max(1, int(np.ceil(np.sqrt(max(area, bbox_pixels) / MAX_PCA_POINTS))))

    # Keep the operation bounded by sampling the component's bounding box.
    crop = labels[y0:y0 + height:step, x0:x0 + width:step]
    ys, xs = np.where(crop == label_id)
    return ys.astype(np.int64) * step + y0, xs.astype(np.int64) * step + x0


def classify_slick_shape(binary_mask: np.ndarray) -> list[SlickComponent]:
    """
    Takes a binary mask (H, W) with 1 = oil, 0 = background -- e.g. the
    output of the U-Net from train_unet.py -- and returns one SlickComponent
    per connected slick region found in it, each classified as linear or blob.

    Multiple components are common: a single SAR frame can contain several
    separate slicks (or a slick plus unrelated noise blobs the U-Net
    misfired on -- MIN_COMPONENT_AREA filters most of that out).
    """
    mask_u8 = (binary_mask > 0).astype(np.uint8)
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask_u8, connectivity=8)

    results = []
    for label_id in range(1, num_labels):  # 0 = background
        area = stats[label_id, cv2.CC_STAT_AREA]
        if area < MIN_COMPONENT_AREA:
            continue

        ys, xs = _component_coordinates(labels, label_id, stats)
        if len(xs) < 2:
            continue
        elongation_ratio, orientation = _pca_elongation(ys, xs)
        shape_class = "linear" if elongation_ratio < LINEAR_THRESHOLD else "blob"
        spill_area_sq_meters = float(area * 100.0)  # 10 m/pixel SAR resolution

        x_min = stats[label_id, cv2.CC_STAT_LEFT]
        y_min = stats[label_id, cv2.CC_STAT_TOP]
        w = stats[label_id, cv2.CC_STAT_WIDTH]
        h = stats[label_id, cv2.CC_STAT_HEIGHT]

        # Corroborating signal: oriented bounding box aspect ratio.
        # Use the representative points for large components to avoid another
        # full-resolution allocation while retaining the same geometry signal.
        points = np.stack([xs, ys], axis=1).astype(np.float32)
        rect = cv2.minAreaRect(points)
        (rw, rh) = rect[1]
        aspect_ratio = float(max(rw, rh) / max(min(rw, rh), 1e-6))

        results.append(SlickComponent(
            component_id=label_id,
            area_pixels=int(area),
            centroid_x=float(centroids[label_id][0]),
            centroid_y=float(centroids[label_id][1]),
            bbox=(int(x_min), int(y_min), int(x_min + w), int(y_min + h)),
            elongation_ratio=round(elongation_ratio, 4),
            shape_class=shape_class,
            aspect_ratio=round(aspect_ratio, 2),
            orientation_deg=round(orientation, 1),
            spill_area_sq_meters=spill_area_sq_meters,
        ))

    return results


def components_to_dicts(components: list[SlickComponent]) -> list[dict]:
    """Convenience for SIMI's pipeline integration / JSON output for the dashboard."""
    return [asdict(c) for c in components]


# -----------------------------------------------------------------------------
# Self-test with synthetic shapes -- run this file directly to verify the
# classifier is working correctly BEFORE plugging it into the real U-Net
# output. A stripe should classify as linear, a circle as blob.
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    print("Running self-test with synthetic shapes...\n")

    # Synthetic 1: a diagonal linear stripe (simulates a vessel discharge trail)
    stripe_mask = np.zeros((200, 200), dtype=np.uint8)
    for i in range(20, 180):
        stripe_mask[i, i - 2:i + 2] = 1
    result = classify_slick_shape(stripe_mask)
    print("Test 1 - Diagonal stripe (expect: linear)")
    for c in result:
        print(f"  shape_class={c.shape_class}  elongation_ratio={c.elongation_ratio}  "
              f"aspect_ratio={c.aspect_ratio}  orientation_deg={c.orientation_deg}")
    assert result[0].shape_class == "linear", "FAILED: stripe should classify as linear"
    print("  PASSED\n")

    # Synthetic 2: a filled circle (simulates a static leak)
    blob_mask = np.zeros((200, 200), dtype=np.uint8)
    yy, xx = np.ogrid[:200, :200]
    circle = (yy - 100) ** 2 + (xx - 100) ** 2 <= 40 ** 2
    blob_mask[circle] = 1
    result = classify_slick_shape(blob_mask)
    print("Test 2 - Filled circle (expect: blob)")
    for c in result:
        print(f"  shape_class={c.shape_class}  elongation_ratio={c.elongation_ratio}  "
              f"aspect_ratio={c.aspect_ratio}  orientation_deg={c.orientation_deg}")
    assert result[0].shape_class == "blob", "FAILED: circle should classify as blob"
    print("  PASSED\n")

    # Synthetic 3: two separate components in one mask (tests multi-component handling)
    multi_mask = np.zeros((200, 200), dtype=np.uint8)
    multi_mask[10:15, 10:100] = 1              # a horizontal linear streak
    yy, xx = np.ogrid[:200, :200]
    circle2 = (yy - 150) ** 2 + (xx - 150) ** 2 <= 25 ** 2
    multi_mask[circle2] = 1                     # a separate blob elsewhere
    result = classify_slick_shape(multi_mask)
    print(f"Test 3 - Two separate components (expect: 2 components, one linear one blob)")
    for c in result:
        print(f"  component_id={c.component_id}  shape_class={c.shape_class}  "
              f"elongation_ratio={c.elongation_ratio}  area={c.area_pixels}")
    assert len(result) == 2, f"FAILED: expected 2 components, got {len(result)}"
    classes = {c.shape_class for c in result}
    assert classes == {"linear", "blob"}, f"FAILED: expected one linear one blob, got {classes}"
    print("  PASSED\n")

    print("All self-tests passed. Classifier is ready to run on real U-Net output.")
