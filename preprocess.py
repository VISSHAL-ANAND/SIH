"""
SIH26143 - Slick Detection: Dataset Preprocessing
Owner: VISSHAL
Task: Collect & preprocess Sentinel-1 SAR oil-spill dataset

Dataset: MKLab Oil Spill Detection Dataset (Zenodo, DOI 10.5281/zenodo.6552722)
  https://zenodo.org/records/6552722

Download manually first (Zenodo doesn't like scripted bulk downloads without an
API token, and the file is a few GB), then point RAW_DIR below at the extracted
folder. Expected structure after extraction:

    raw/
      train/
        images/   *.jpg  (SAR images)
        labels/   *.png  (color-coded segmentation masks)
      test/
        images/
        labels/

Mask color code (from the dataset's own class definitions):
    Black   (0,0,0)     -> Background / Sea Surface
    Cyan    (0,255,255) -> Oil Spill        <-- the class you actually care about
    Red     (255,0,0)   -> Look-alike       <-- the class that causes false positives
    Brown   (153,76,0)  -> Ship
    Green   (0,153,0)   -> Land

This script:
  1. Resizes all images/masks to a fixed size (default 256x256 - fast enough
     for a 3-day sprint, bump to 512 later if you have time).
  2. Converts the RGB masks into a single-channel class-index mask.
  3. Splits into train/val (the dataset's own test/ folder becomes your held-out test set).
  4. Saves everything as .npy arrays so training doesn't re-decode images every epoch.
"""

import os
import glob
import numpy as np
from PIL import Image

# ---- CONFIG ----------------------------------------------------------------
RAW_DIR = "../data/raw"              # point this at your extracted Zenodo download
OUT_DIR = "../data/processed"
IMG_SIZE = 256
VAL_SPLIT = 0.15
SEED = 42

CLASS_COLORS = {
    (0, 0, 0): 0,        # Background / Sea Surface
    (0, 255, 255): 1,    # Oil Spill  <- primary target class
    (255, 0, 0): 2,      # Look-alike
    (153, 76, 0): 3,     # Ship
    (0, 153, 0): 4,      # Land
}
NUM_CLASSES = len(CLASS_COLORS)
CLASS_NAMES = ["background", "oil_spill", "look_alike", "ship", "land"]


def rgb_mask_to_class_index(mask_rgb: np.ndarray) -> np.ndarray:
    """Convert an (H, W, 3) color mask into an (H, W) class-index mask."""
    h, w, _ = mask_rgb.shape
    class_mask = np.zeros((h, w), dtype=np.uint8)
    for color, idx in CLASS_COLORS.items():
        matches = np.all(mask_rgb == np.array(color), axis=-1)
        class_mask[matches] = idx
    return class_mask


def load_split(split_dir: str):
    img_paths = sorted(glob.glob(os.path.join(split_dir, "images", "*")))
    lbl_paths = sorted(glob.glob(os.path.join(split_dir, "labels", "*")))
    assert len(img_paths) == len(lbl_paths), (
        f"Mismatch: {len(img_paths)} images vs {len(lbl_paths)} labels in {split_dir}. "
        "Check filenames line up between images/ and labels/."
    )

    images, masks = [], []
    for img_p, lbl_p in zip(img_paths, lbl_paths):
        img = Image.open(img_p).convert("RGB").resize((IMG_SIZE, IMG_SIZE), Image.BILINEAR)
        lbl = Image.open(lbl_p).convert("RGB").resize((IMG_SIZE, IMG_SIZE), Image.NEAREST)

        img_arr = np.array(img, dtype=np.uint8)
        lbl_arr = rgb_mask_to_class_index(np.array(lbl, dtype=np.uint8))

        images.append(img_arr)
        masks.append(lbl_arr)

    return np.stack(images), np.stack(masks)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    rng = np.random.default_rng(SEED)

    print("Loading train split...")
    train_imgs, train_masks = load_split(os.path.join(RAW_DIR, "train"))

    print("Loading test split (held out, do not touch until final eval)...")
    test_imgs, test_masks = load_split(os.path.join(RAW_DIR, "test"))

    # carve a val set out of train
    n = len(train_imgs)
    idx = rng.permutation(n)
    n_val = int(n * VAL_SPLIT)
    val_idx, tr_idx = idx[:n_val], idx[n_val:]

    np.save(os.path.join(OUT_DIR, "train_images.npy"), train_imgs[tr_idx])
    np.save(os.path.join(OUT_DIR, "train_masks.npy"), train_masks[tr_idx])
    np.save(os.path.join(OUT_DIR, "val_images.npy"), train_imgs[val_idx])
    np.save(os.path.join(OUT_DIR, "val_masks.npy"), train_masks[val_idx])
    np.save(os.path.join(OUT_DIR, "test_images.npy"), test_imgs)
    np.save(os.path.join(OUT_DIR, "test_masks.npy"), test_masks)

    print(f"Train: {len(tr_idx)} | Val: {len(val_idx)} | Test: {len(test_imgs)}")
    print("Class pixel counts (train) — check for severe imbalance:")
    unique, counts = np.unique(train_masks[tr_idx], return_counts=True)
    for u, c in zip(unique, counts):
        print(f"  {CLASS_NAMES[u]:12s}: {c:,}")
    print(f"\nSaved processed arrays to {OUT_DIR}/")


if __name__ == "__main__":
    main()
