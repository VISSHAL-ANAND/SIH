"""
SIH26143 — SAR hull-detection model (YOLOv8)
================================================

Trains a YOLOv8 detector on the sar_ships/ dataset produced by
prepare_sar_ship_datasets.py, tuned with small/occluded-object settings
since that's flagged as the highest-value detection case for this track.

Usage
-----
    pip install ultralytics --quiet

    # Train
    python train_ship_detector.py --train

    # Quick inference test on one image (prints bbox + confidence)
    python train_ship_detector.py --predict path/to/image.jpg

    # Validate metrics (mAP, precision/recall) on the val split
    python train_ship_detector.py --val
"""

import argparse
from pathlib import Path

DATA_YAML = "sar_ships/data.yaml"
RUN_NAME = "sar_hull_detector"
MODEL_SIZE = "yolov8s.pt"   # yolov8n = fastest/smallest, yolov8s = better
                             # small-object recall, yolov8m if you have time/GPU


def train():
    from ultralytics import YOLO

    model = YOLO(MODEL_SIZE)

    model.train(
        data=DATA_YAML,
        imgsz=800,              # matches HRSID/SSDD native chip size
        epochs=100,
        patience=20,            # early stop if val mAP plateaus
        batch=16,                # lower to 8 if you hit GPU OOM
        name=RUN_NAME,

        # --- settings that matter for small / partially-occluded hulls ---
        mosaic=1.0,              # keep mosaic on — helps small-object recall
        close_mosaic=10,         # disable mosaic for the last 10 epochs (stabilizes)
        scale=0.5,               # random scale augmentation — exposes the model
                                  # to smaller apparent ship sizes during training
        copy_paste=0.3,          # paste ships onto other backgrounds — directly
                                  # increases occluded/near-clutter examples
        hsv_v=0.3,                # SAR "brightness" (intensity) jitter, no color
                                  # channel to speak of so keep hsv_h/hsv_s low
        hsv_h=0.0,
        hsv_s=0.0,
        fliplr=0.5,
        flipud=0.5,               # SAR has no canonical "up" — both flips are valid

        # small-object detection benefits from anchor-free YOLOv8's P2 head;
        # if recall on tiny hulls is still poor after this run, switch to a
        # P2-enabled config (yolov8-p2.yaml) for a dedicated small-object head
    )

    print(f"\nTraining complete. Best weights: runs/detect/{RUN_NAME}/weights/best_unet.pt")
    print("Copy that to data/processed/ (or wherever your pipeline module expects it).")


def validate():
    from ultralytics import YOLO
    weights = f"runs/detect/{RUN_NAME}/weights/best_unet.pt"
    if not Path(weights).exists():
        raise SystemExit(f"{weights} not found — run --train first.")
    model = YOLO(weights)
    metrics = model.val(data=DATA_YAML, imgsz=800)
    print(f"\nmAP50: {metrics.box.map50:.3f}   mAP50-95: {metrics.box.map:.3f}")
    print("If mAP50 on small objects specifically looks weak, check per-class "
          "breakdown with model.val(..., plots=True) and inspect runs/detect/val/.")


def predict(image_path: str):
    """
    Quick single-image test. In your final pipeline module (next task),
    wrap this in a function that also converts pixel bbox -> geo-coordinates
    using the SAR scene's geotransform/metadata, and attaches a timestamp.
    """
    from ultralytics import YOLO
    weights = f"runs/detect/{RUN_NAME}/weights/best_unet.pt"
    if not Path(weights).exists():
        raise SystemExit(f"{weights} not found — run --train first.")
    model = YOLO(weights)
    results = model.predict(image_path, imgsz=800, conf=0.25, iou=0.45)

    for r in results:
        print(f"\n{image_path}: {len(r.boxes)} hulls detected")
        for box in r.boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            conf = box.conf.item()
            print(f"  bbox=({x1:.0f},{y1:.0f},{x2:.0f},{y2:.0f})  confidence={conf:.2f}")
        r.save(filename=f"predicted_{Path(image_path).stem}.jpg")
    print("\nAnnotated image saved.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--train", action="store_true")
    p.add_argument("--val", action="store_true")
    p.add_argument("--predict", type=str, default=None, metavar="IMAGE_PATH")
    args = p.parse_args()

    if args.train:
        train()
    if args.val:
        validate()
    if args.predict:
        predict(args.predict)
    if not any([args.train, args.val, args.predict]):
        print(__doc__)
