"""
SIH26143 - Slick Detection: End-to-end inference (U-Net -> shape classifier)

The production checkpoint is configurable through IMW_SLICK_CHECKPOINT so the
same code can run locally, in CI, or in a deployed environment without
committing large model binaries to Git.
"""

import os
from pathlib import Path

import numpy as np
import torch
import segmentation_models_pytorch as smp

from .shape_classifier import classify_slick_shape, components_to_dicts

DEFAULT_CHECKPOINT_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "best_unet.pt"
CHECKPOINT_PATH = os.getenv("IMW_SLICK_CHECKPOINT", str(DEFAULT_CHECKPOINT_PATH))
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def load_model():
    checkpoint = Path(CHECKPOINT_PATH)
    if not checkpoint.exists():
        raise FileNotFoundError(
            f"Trained slick-segmentation checkpoint not found: {checkpoint}. "
            "Set IMW_SLICK_CHECKPOINT or provide the expected checkpoint."
        )
    model = smp.Unet(
        encoder_name="resnet34",
        encoder_weights=None,
        in_channels=3,
        classes=2,
    )
    state = torch.load(checkpoint, map_location=DEVICE)
    if isinstance(state, dict) and "state_dict" in state:
        state = state["state_dict"]
    model.load_state_dict(state)
    model.to(DEVICE)
    model.eval()
    return model


def predict_mask(model, image_rgb: np.ndarray) -> np.ndarray:
    """image_rgb: (H, W, 3) uint8. Returns (H, W) binary mask, 1 = predicted oil.

    Arbitrary SAR tiles are padded to the U-Net stride before inference and
    cropped back afterwards. This keeps edge tiles valid without loading the
    entire Sentinel-1 scene into RAM.
    """
    img = np.asarray(image_rgb, dtype=np.float32) / 255.0
    h, w = img.shape[:2]
    stride = 32
    padded_h = ((h + stride - 1) // stride) * stride
    padded_w = ((w + stride - 1) // stride) * stride
    if padded_h != h or padded_w != w:
        img = np.pad(img, ((0, padded_h - h), (0, padded_w - w), (0, 0)), mode="edge")

    img_t = torch.from_numpy(img).permute(2, 0, 1).unsqueeze(0).to(DEVICE)
    with torch.inference_mode():
        logits = model(img_t)
        pred = torch.argmax(logits, dim=1).squeeze(0).cpu().numpy().astype(np.uint8)
    del logits, img_t
    return pred[:h, :w]


def predict_and_classify(model, image_rgb: np.ndarray) -> dict:
    """Full pipeline stage: SAR image in -> predicted mask + classified slick components out."""
    mask = predict_mask(model, image_rgb)
    raw_components = classify_slick_shape(mask)
    component_dicts = components_to_dicts(raw_components)
    return {
        "predicted_mask": mask,
        "components": component_dicts,
        "num_slicks_detected": len(component_dicts),
        "num_linear": sum(1 for c in component_dicts if c["shape_class"] == "linear"),
        "num_blob": sum(1 for c in component_dicts if c["shape_class"] == "blob"),
    }


def main():
    print(f"Loading model from {CHECKPOINT_PATH} on {DEVICE}...")
    model = load_model()

    test_images = np.load("data/processed/test_images.npy")
    test_masks = np.load("data/processed/test_masks.npy")
    print(f"Running inference on {len(test_images)} held-out test images...\n")

    linear_count, blob_count = 0, 0
    for i in range(len(test_images)):
        result = predict_and_classify(model, test_images[i])
        linear_count += result["num_linear"]
        blob_count += result["num_blob"]

        if result["num_slicks_detected"] > 0:
            print(f"Image {i}: {result['num_slicks_detected']} slick(s) detected "
                  f"({result['num_linear']} linear, {result['num_blob']} blob)")
            for comp in result["components"]:
                print(f"    -> {comp['shape_class']:6s} | area={comp['area_pixels']:5d}px "
                      f"| elongation={comp['elongation_ratio']:.3f} "
                      f"| centroid=({comp['centroid_x']:.0f},{comp['centroid_y']:.0f})")

    print(f"\nTotals across test set: {linear_count} linear slicks, {blob_count} blob slicks")


if __name__ == "__main__":
    main()
