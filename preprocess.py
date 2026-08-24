"""
SIH26143 - Slick Detection: Dataset Preprocessing (v2)
Owner: VISSHAL
Task: Collect & preprocess SAR oil-spill dataset

DATASET (updated 2026-08-24): Zenodo kept 502/504'ing, so we pivoted to the
Kaggle mirror: bakhtiyar2222/deep-sar-oil-spill-segmentation-refined
(the "SOS" dataset, built on Zhu et al. 2021).

This is a DIFFERENT structure/label scheme than the original 5-class MKLab
plan -- confirmed from VISSHAL's actual download:

    archive/
      images/[images/]train/*.jpg   (or .png)
      images/[images/]val/*.jpg
      masks/masks/train/*.png
      masks/masks/val/*.png

  - Only train/val exist (no separate held-out test folder in this dataset).
    We carve a small test slice out of train ourselves so we still have a
    truly held-out set for final eval.
  - Masks are BINARY: white = oil spill, black = everything else (sea,
    look-alike, land, ship all lumped as "not oil"). We lose the
    look-alike-as-its-own-class signal the original 5-class plan had --
    see the NOTE printed at the end of main() for how we compensate for
    that later in the pipeline instead.

The script auto-detects whether "images/" has an extra nested "images/"
folder inside it (Kaggle zips are inconsistent about this) so you shouldn't
need to hand-edit paths even if your folder layout differs slightly from
someone else's download of the same dataset.
"""

import os
import glob
import numpy as np
from PIL import Image

# ---- CONFIG ----------------------------------------------------------------
RAW_DIR = "archive"   # point this at the extracted Kaggle "archive" folder
OUT_DIR = "data/processed"
IMG_SIZE = 256
TEST_SPLIT_FROM_TRAIN = 0.10   # carve a held-out test set since the dataset has none
SEED = 42

CLASS_NAMES = ["background", "oil_spill"]  # binary: 0 = not oil, 1 = oil
NUM_CLASSES = 2


def _find_split_dir(base: str, split: str) -> str:
    """Handle the images/images/train vs images/train inconsistency."""
    nested = os.path.join(base, os.path.basename(base), split)
    direct = os.path.join(base, split)
    if os.path.isdir(nested):
        return nested
    if os.path.isdir(direct):
        return direct
    raise FileNotFoundError(
        f"Couldn't find a '{split}' folder under {base} (checked {nested} and {direct}). "
        "Open the folder yourself and check the actual nesting, then edit _find_split_dir "
        "or just hardcode the path here."
    )


def load_split(images_base: str, masks_base: str, split: str):
    img_dir = _find_split_dir(images_base, split)
    mask_dir = _find_split_dir(masks_base, split)

    img_paths = {os.path.splitext(os.path.basename(p))[0]: p
                 for p in glob.glob(os.path.join(img_dir, "*"))}
    mask_paths = {os.path.splitext(os.path.basename(p))[0]: p
                  for p in glob.glob(os.path.join(mask_dir, "*"))}

    common_keys = sorted(set(img_paths) & set(mask_paths))
    missing_images = set(mask_paths) - set(img_paths)
    missing_masks = set(img_paths) - set(mask_paths)
    if missing_images or missing_masks:
        print(f"  [warning] {len(missing_images)} masks with no matching image, "
              f"{len(missing_masks)} images with no matching mask -- skipping those.")
    if not common_keys:
        raise RuntimeError(
            f"No matching image/mask filename pairs found in {img_dir} and {mask_dir}. "
            "Check that filenames correspond 1:1 between the two folders (extension can differ)."
        )

    images, masks = [], []
    for key in common_keys:
        img = Image.open(img_paths[key]).convert("RGB").resize((IMG_SIZE, IMG_SIZE), Image.BILINEAR)
        lbl = Image.open(mask_paths[key]).convert("L").resize((IMG_SIZE, IMG_SIZE), Image.NEAREST)

        img_arr = np.array(img, dtype=np.uint8)
        # binarize: anything above mid-gray counts as oil_spill (1), else background (0)
        lbl_arr = (np.array(lbl, dtype=np.uint8) > 127).astype(np.uint8)

        images.append(img_arr)
        masks.append(lbl_arr)

    return np.stack(images), np.stack(masks)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    rng = np.random.default_rng(SEED)

    images_base = os.path.join(RAW_DIR, "images")
    masks_base = os.path.join(RAW_DIR, "masks")

    print("Loading train split...")
    train_imgs, train_masks = load_split(images_base, masks_base, "train")

    print("Loading val split...")
    val_imgs, val_masks = load_split(images_base, masks_base, "val")

    # carve a held-out test slice out of train (dataset ships without one)
    n = len(train_imgs)
    idx = rng.permutation(n)
    n_test = int(n * TEST_SPLIT_FROM_TRAIN)
    test_idx, tr_idx = idx[:n_test], idx[n_test:]

    np.save(os.path.join(OUT_DIR, "train_images.npy"), train_imgs[tr_idx])
    np.save(os.path.join(OUT_DIR, "train_masks.npy"), train_masks[tr_idx])
    np.save(os.path.join(OUT_DIR, "val_images.npy"), val_imgs)
    np.save(os.path.join(OUT_DIR, "val_masks.npy"), val_masks)
    np.save(os.path.join(OUT_DIR, "test_images.npy"), train_imgs[test_idx])
    np.save(os.path.join(OUT_DIR, "test_masks.npy"), train_masks[test_idx])

    print(f"Train: {len(tr_idx)} | Val: {len(val_imgs)} | Test (held out from train): {len(test_idx)}")

    total_pixels = train_masks[tr_idx].size
    oil_pixels = int(train_masks[tr_idx].sum())
    print(f"\nOil spill pixels: {oil_pixels:,} / {total_pixels:,} "
          f"({100 * oil_pixels / total_pixels:.2f}% of all train pixels)")
    print(f"Saved processed arrays to {OUT_DIR}/")

    print("\nNOTE: this dataset has no separate 'look-alike' class (unlike the "
          "original MKLab plan) -- everything non-oil is lumped together, "
          "which means the model can't be directly taught to distinguish real "
          "spills from look-alikes at THIS stage. That distinction now needs "
          "to happen downstream instead -- e.g. in the linear-vs-blob shape "
          "classifier (tomorrow's task) or by cross-referencing with hull "
          "detection/AIS matching. Flag this to the team so it's a conscious "
          "design choice, not a silently dropped feature.")


if __name__ == "__main__":
    main()