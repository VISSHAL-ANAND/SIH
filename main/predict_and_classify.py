"""
SIH26143 - Slick Detection: End-to-end inference (U-Net -> shape classifier)
Owner: VISSHAL

Run this once data/processed/best_unet.pt exists (from RINOSH's GPU run).
Loads the trained model, runs it on the held-out test images, and passes
each predicted mask through the linear-vs-blob shape classifier.

This is also your "package slick detection as pipeline module" deliverable --
SIMI's integration task (wiring all 4 modules together) can call
`predict_and_classify(image)` directly rather than reaching into U-Net
internals.
"""

import numpy as np
import torch
import segmentation_models_pytorch as smp

from .shape_classifier import classify_slick_shape, components_to_dicts

CHECKPOINT_PATH = str(__import__("pathlib").Path(__file__).resolve().parent.parent / "data" / "processed" / "best_unet.pt")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def load_model():
    model = smp.Unet(
        encoder_name="resnet34",
        encoder_weights=None,   # we're loading trained weights, not ImageNet ones
        in_channels=3,
        classes=2,
    )
    model.load_state_dict(torch.load(CHECKPOINT_PATH, map_location=DEVICE))
    model.to(DEVICE)
    model.eval()
    return model


def predict_mask(model, image_rgb: np.ndarray) -> np.ndarray:
    """image_rgb: (H, W, 3) uint8. Returns (H, W) binary mask, 1 = predicted oil."""
    img = image_rgb.astype(np.float32) / 255.0
    img_t = torch.from_numpy(img).permute(2, 0, 1).unsqueeze(0).to(DEVICE)
    with torch.no_grad():
        logits = model(img_t)
        pred = torch.argmax(logits, dim=1).squeeze(0).cpu().numpy()
    return pred.astype(np.uint8)


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
    test_masks = np.load("data/processed/test_masks.npy")  # ground truth, for comparison
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
    print("\nLinear detections are your leads for RINOSH/ASHMIL's hull-matching --")
    print("pass their centroid coordinates + this image's timestamp/geolocation to")
    print("the AIS matcher to check for a nearby vessel with no matching AIS ping.")


if __name__ == "__main__":
    main()
