"""
SIH26143 — Per-object-size recall breakdown
================================================

Overall recall (0.756) hides whether small/occluded ships specifically
are the weak point. This buckets ground-truth boxes by pixel area
(COCO convention: small <32x32, medium 32x32-96x96, large >96x96) and
reports recall per bucket, so you have real evidence for the
"tune small/occluded hulls" task instead of just assuming the
augmentation settings handled it.

Usage
-----
    python evaluate_by_size.py
"""

from pathlib import Path

import cv2
from tqdm import tqdm
from ultralytics import YOLO

WEIGHTS = "runs/detect/sar_hull_detector/weights/best.pt"
VAL_IMAGES = Path("sar_ships/images/val")
VAL_LABELS = Path("sar_ships/labels/val")
IOU_MATCH_THRESHOLD = 0.5
CONF_THRESHOLD = 0.15  # lowered from 0.25 to test whether large-object misses
                         # are borderline-confidence detections vs. true misses

SMALL_MAX = 32 * 32       # 1024 px^2
MEDIUM_MAX = 96 * 96      # 9216 px^2


def iou_xyxy(a, b):
    xa1, ya1, xa2, ya2 = a
    xb1, yb1, xb2, yb2 = b
    ix1, iy1 = max(xa1, xb1), max(ya1, yb1)
    ix2, iy2 = min(xa2, xb2), min(ya2, yb2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    area_a = max(0, xa2 - xa1) * max(0, ya2 - ya1)
    area_b = max(0, xb2 - xb1) * max(0, yb2 - yb1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def bucket(area):
    if area < SMALL_MAX:
        return "small"
    if area < MEDIUM_MAX:
        return "medium"
    return "large"


def main():
    if not Path(WEIGHTS).exists():
        raise SystemExit(f"{WEIGHTS} not found — train the model first.")
    model = YOLO(WEIGHTS)

    counts = {"small": 0, "medium": 0, "large": 0}
    matched = {"small": 0, "medium": 0, "large": 0}

    image_paths = sorted(VAL_IMAGES.glob("*"))
    if not image_paths:
        raise SystemExit(f"No images found in {VAL_IMAGES}")

    for img_path in tqdm(image_paths, desc="Evaluating"):
        img = cv2.imread(str(img_path))
        if img is None:
            continue
        h, w = img.shape[:2]

        lbl_path = VAL_LABELS / (img_path.stem + ".txt")
        gt_boxes = []
        if lbl_path.exists():
            for line in lbl_path.read_text().splitlines():
                if not line.strip():
                    continue
                _, cx, cy, bw, bh = map(float, line.split())
                x1 = (cx - bw / 2) * w
                y1 = (cy - bh / 2) * h
                x2 = (cx + bw / 2) * w
                y2 = (cy + bh / 2) * h
                gt_boxes.append([x1, y1, x2, y2])

        if not gt_boxes:
            continue

        results = model.predict(str(img_path), imgsz=800, conf=CONF_THRESHOLD, verbose=False)
        pred_boxes = []
        for r in results:
            for box in r.boxes:
                pred_boxes.append(box.xyxy[0].tolist())

        matched_pred = set()
        for gt in gt_boxes:
            area = max(0, gt[2] - gt[0]) * max(0, gt[3] - gt[1])
            b = bucket(area)
            counts[b] += 1

            best_iou, best_idx = 0.0, -1
            for i, pred in enumerate(pred_boxes):
                if i in matched_pred:
                    continue
                iou = iou_xyxy(gt, pred)
                if iou > best_iou:
                    best_iou, best_idx = iou, i

            if best_iou >= IOU_MATCH_THRESHOLD:
                matched[b] += 1
                matched_pred.add(best_idx)

    print("\n--- Recall by object size (COCO area buckets) ---")
    for b in ["small", "medium", "large"]:
        total = counts[b]
        hit = matched[b]
        recall = hit / total if total else float("nan")
        print(f"{b:7s}: {hit:4d}/{total:4d} recovered  recall={recall:.3f}"
              if total else f"{b:7s}: no ground-truth boxes in this bucket")

    total_all = sum(counts.values())
    hit_all = sum(matched.values())
    print(f"\noverall: {hit_all}/{total_all} recall={hit_all/total_all:.3f}")
    print("\nIf 'small' recall is meaningfully lower than 'large', that's your "
          "concrete evidence for the tuning task — and the next lever to pull is "
          "either more copy_paste/scale augmentation weight, a P2 small-object "
          "detection head (yolov8-p2.yaml), or more training epochs targeted at it.")


if __name__ == "__main__":
    main()