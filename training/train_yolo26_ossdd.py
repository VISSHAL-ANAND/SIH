"""Train the IMW SAR ship detector with YOLO26 on OSSDD.

Run this on a CUDA cloud GPU after prepare_ossdd_yolo.py has created
ossdd_yolo/data.yaml.
"""

from pathlib import Path

from ultralytics import YOLO

DATA = "ossdd_yolo/data.yaml"
RUN = "imw_yolo26s_ossdd"


def main() -> None:
    if not Path(DATA).exists():
        raise SystemExit(
            f"Missing {DATA}. Run training/prepare_ossdd_yolo.py first."
        )

    # Start from the official YOLO26-S pretrained checkpoint rather than the
    # current epoch-4 SAR checkpoint. Ultralytics publishes pretrained weights.
    model = YOLO("yolo26s.pt")

    model.train(
        data=DATA,
        imgsz=800,
        epochs=150,
        patience=30,
        batch=-1,
        device=0,
        workers=8,
        cache=False,
        amp=True,
        project="runs/detect",
        name=RUN,
        pretrained=True,
        # SAR has no meaningful RGB hue/saturation; use intensity variation only.
        hsv_h=0.0,
        hsv_s=0.0,
        hsv_v=0.20,
        # Orientation is arbitrary in SAR chips.
        fliplr=0.5,
        flipud=0.5,
        degrees=0.0,
        shear=0.0,
        perspective=0.0,
        # Keep strong scale/mosaic augmentation for small ships, then close it.
        scale=0.90,
        mosaic=1.0,
        close_mosaic=15,
        mixup=0.05,
        copy_paste=0.0,
        plots=True,
        save=True,
        val=True,
    )

    best = Path("runs/detect") / RUN / "weights" / "best.pt"
    print(f"\nBEST MODEL: {best}")


if __name__ == "__main__":
    main()
