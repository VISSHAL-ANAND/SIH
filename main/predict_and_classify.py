"""
SIH26143 - Slick Detection: end-to-end inference (U-Net -> shape classifier)
Owner: VISSHAL

Run this once data/processed/best_unet.pt exists (from RINOSH's GPU run).
Loads the trained model, runs it on the held-out test images, and passes
each predicted mask through the linear-vs-blob shape classifier.

The inference primitive also supports arbitrary image/tile dimensions. SAR
GeoTIFF tiling commonly produces edge tiles that are not divisible by the
U-Net encoder stride, so predict_mask pads those tiles before inference and
crops the prediction back to the exact requested dimensions.
"""

import numpy as np
import torch
import segmentation_models_pytorch as smp

from .shape_classifier import classify_slick_shape, components_to_dicts

CHECKPOINT_PATH = str(__import__("pathlib").Path(__file__).resolve().parent.parent / "data" / "processed" / "best_unet.pt")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
MODEL_STRIDE = 32


def load_model():
    model = smp.Unet(
        encoder_name="resnet34",
        encoder_weights=None,
        in_channels=3,
        classes=2,
    )
    model.load_state_dict(torch.load(CHECKPOINT_PATH, map_location=DEVICE))
    model.to(DEVICE)
    model.eval()
    return model


def predict_mask(model, image_rgb: np.ndarray) -> np.ndarray:
    """image_rgb: (H, W, 3) uint8. Returns (H, W) binary mask, 1 = predicted oil.

    Pads H/W to the model's encoder stride for edge tiles, then removes the
    padding so callers always receive a mask exactly matching the input.
    """
    if image_rgb.ndim != 3 or image_rgb.shape[2] != 3:
        raise ValueError("image_rgb must have shape (H, W, 3)")
    h, w = image_rgb.shape[:2]
    if h == 0 or w == 0:
        return np.zeros((h, w), dtype=np.uint8)

    pad_h = (MODEL_STRIDE - (h % MODEL_STRIDE)) % MODEL_STRIDE
    pad_w = (MODEL_STRIDE - (w % MODEL_STRIDE)) % MODEL_STRIDE
    if pad_h or pad_w:
        image_rgb = np.pad(
            image_rgb,
            ((0, pad_h), (0, pad_w), (0, 0)),
            mode="reflect",
        )

    img = image_rgb.astype(np.float32) / 255.0
    img_t = torch.from_numpy(img).permute(2, 0, 1).unsqueeze(0).to(DEVICE)
    with torch.no_grad():
        logits = model(img_t)
        pred = torch.argmax(logits, dim=1).squeeze(0).cpu().numpy()
    return pred[:h, :w].astype(np.uint8)


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
