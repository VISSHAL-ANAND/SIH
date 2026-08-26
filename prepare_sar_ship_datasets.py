"""
SIH26143 — SAR ship-chip preprocessing for HRSID + SSDD  (v2 — robust paths)
==============================================================================

Run this in an environment WITH internet access (Colab, Kaggle, or your
local machine) — not in a network-isolated sandbox.

CHANGELOG vs v1
----------------
- HRSID: no longer assumes a folder literally named "images/". Instead it
  indexes every file under raw/HRSID by filename once, then looks each
  COCO annotation's file_name up in that index. Handles whatever nested
  folder layout your HRSID zip actually extracted to.
- SSDD (VOC path): skips <object> entries with a missing/malformed
  <bndbox> instead of crashing (some SSDD releases include "difficult"
  or non-bbox entries). Prints a summary of how many were skipped.
- Both converters now print a per-dataset summary (images found / labels
  written / skipped) so a silent zero-conversion doesn't slip through.

Usage
-----
    pip install gdown pillow opencv-python pyyaml tqdm scikit-learn --quiet

    python prepare_sar_ship_datasets.py --download     # only if you haven't
    python prepare_sar_ship_datasets.py --preprocess
    python prepare_sar_ship_datasets.py --check
"""

import argparse
import json
import os
import random
import shutil
import zipfile
from pathlib import Path

import cv2
import yaml
from tqdm import tqdm

# --------------------------------------------------------------------------
# CONFIG — edit these
# --------------------------------------------------------------------------

RAW_DIR = Path("raw")
OUT_DIR = Path("sar_ships")
VAL_FRACTION = 0.15
RANDOM_SEED = 42

HRSID_GDRIVE_ID = "1NY3ovgc-woDlNoQdyqzRB3t9McOBH5Ms"
SSDD_GDRIVE_ID = "1glNJUGotrbEyk43twwB9556AdngJsynZ"  # NOTE: this is a .rar,
                                                         # extract it manually
                                                         # (see README chat)

CLASS_NAMES = ["ship"]

random.seed(RANDOM_SEED)


# --------------------------------------------------------------------------
# 1. DOWNLOAD
# --------------------------------------------------------------------------

def download():
    RAW_DIR.mkdir(exist_ok=True)
    try:
        import gdown
    except ImportError:
        raise SystemExit("Run: pip install gdown")

    if "PASTE" not in HRSID_GDRIVE_ID:
        hrsid_zip = RAW_DIR / "hrsid.zip"
        if not hrsid_zip.exists():
            gdown.download(id=HRSID_GDRIVE_ID, output=str(hrsid_zip), quiet=False)
        with zipfile.ZipFile(hrsid_zip) as z:
            z.extractall(RAW_DIR / "HRSID")
    else:
        print("[skip] Set HRSID_GDRIVE_ID before downloading HRSID.")

    print("SSDD is distributed as a .rar — download + extract it manually "
          "(gdown/zipfile can't open .rar), then place its BBox_SSDD/voc_style "
          "contents under raw/SSDD/.")


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def build_filename_index(root: Path) -> dict:
    """Map every file's basename -> full path, for one recursive walk."""
    index = {}
    for dirpath, _, filenames in os.walk(root):
        for f in filenames:
            index.setdefault(f, Path(dirpath) / f)
    return index


# --------------------------------------------------------------------------
# 2. HRSID -> YOLO
# --------------------------------------------------------------------------

def convert_hrsid(hrsid_root: Path, images_out: Path, labels_out: Path):
    ann_files = list(hrsid_root.rglob("train2017.json")) + list(hrsid_root.rglob("test2017.json"))
    if not ann_files:
        print(f"[HRSID] No train2017.json / test2017.json found anywhere under {hrsid_root}. "
              f"Check the extracted zip contents.")
        return []

    print(f"[HRSID] Indexing files under {hrsid_root} (one-time walk)...")
    file_index = build_filename_index(hrsid_root)
    print(f"[HRSID] Indexed {len(file_index)} files.")

    written = []
    for jf in ann_files:
        coco = json.loads(jf.read_text())
        images_by_id = {im["id"]: im for im in coco["images"]}
        anns_by_img = {}
        for a in coco["annotations"]:
            anns_by_img.setdefault(a["image_id"], []).append(a)

        found, missing, no_boxes = 0, 0, 0
        for img_id, im in tqdm(images_by_id.items(), desc=f"HRSID {jf.name}"):
            fname = im["file_name"]
            src = file_index.get(fname) or file_index.get(Path(fname).name)
            if src is None:
                missing += 1
                continue
            w, h = im["width"], im["height"]

            lines = []
            for a in anns_by_img.get(img_id, []):
                x, y, bw, bh = a["bbox"]
                cx = (x + bw / 2) / w
                cy = (y + bh / 2) / h
                nw, nh = bw / w, bh / h
                lines.append(f"0 {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")

            if not lines:
                no_boxes += 1

            stem = Path(fname).stem
            shutil.copy(src, images_out / f"hrsid_{stem}.jpg")
            (labels_out / f"hrsid_{stem}.txt").write_text("\n".join(lines))
            written.append(f"hrsid_{stem}")
            found += 1

        print(f"[HRSID] {jf.name}: {found} images converted, {missing} not found on disk, "
              f"{no_boxes} had zero ship boxes.")

    return written


# --------------------------------------------------------------------------
# 3. SSDD -> YOLO
# --------------------------------------------------------------------------

def convert_ssdd(ssdd_root: Path, images_out: Path, labels_out: Path):
    written = []

    # Case A: already YOLO-style (images/ + labels/ siblings)
    yolo_label_dirs = list(ssdd_root.rglob("labels"))
    if yolo_label_dirs:
        for lbl_dir in yolo_label_dirs:
            img_dir_candidate = lbl_dir.parent / "images"
            if not img_dir_candidate.exists():
                continue
            for lbl in tqdm(list(lbl_dir.glob("*.txt")), desc="SSDD (YOLO source)"):
                img = img_dir_candidate / (lbl.stem + ".jpg")
                if not img.exists():
                    img = img_dir_candidate / (lbl.stem + ".png")
                if not img.exists():
                    continue
                stem = lbl.stem
                shutil.copy(img, images_out / f"ssdd_{stem}{img.suffix}")
                shutil.copy(lbl, labels_out / f"ssdd_{stem}.txt")
                written.append(f"ssdd_{stem}")
        if written:
            return written

    # Case B: VOC-style XML annotations
    import xml.etree.ElementTree as ET
    xml_files = list(ssdd_root.rglob("*.xml"))
    if not xml_files:
        print(f"[SSDD] No .xml files found under {ssdd_root} either. Check the folder you copied in.")
        return []

    print(f"[SSDD] Indexing files under {ssdd_root} (one-time walk)...")
    file_index = build_filename_index(ssdd_root)
    print(f"[SSDD] Indexed {len(file_index)} files. Parsing {len(xml_files)} XML annotations...")

    skipped_no_image, skipped_bad_object, converted, zero_box, duplicates = 0, 0, 0, 0, 0
    seen_stems = set()
    for xf in tqdm(xml_files, desc="SSDD (VOC source)"):
        try:
            tree = ET.parse(xf)
            root = tree.getroot()
            fname_el = root.find("filename")
            size_el = root.find("size")
            if fname_el is None or size_el is None:
                skipped_no_image += 1
                continue
            fname = fname_el.text
            w = int(size_el.find("width").text)
            h = int(size_el.find("height").text)
        except Exception:
            skipped_no_image += 1
            continue

        src_img = file_index.get(fname) or file_index.get(Path(fname).name)
        if src_img is None:
            skipped_no_image += 1
            continue

        stem = Path(fname).stem
        if f"ssdd_{stem}" in seen_stems:
            duplicates += 1
            continue
        seen_stems.add(f"ssdd_{stem}")

        lines = []
        for obj in root.findall("object"):
            bb = obj.find("bndbox")
            if bb is None:
                skipped_bad_object += 1
                continue
            xmin_el, ymin_el = bb.find("xmin"), bb.find("ymin")
            xmax_el, ymax_el = bb.find("xmax"), bb.find("ymax")
            if None in (xmin_el, ymin_el, xmax_el, ymax_el):
                skipped_bad_object += 1
                continue
            try:
                xmin, ymin = float(xmin_el.text), float(ymin_el.text)
                xmax, ymax = float(xmax_el.text), float(ymax_el.text)
            except (TypeError, ValueError):
                skipped_bad_object += 1
                continue

            cx, cy = (xmin + xmax) / 2 / w, (ymin + ymax) / 2 / h
            bw, bh = (xmax - xmin) / w, (ymax - ymin) / h
            lines.append(f"0 {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")

        if not lines:
            zero_box += 1

        shutil.copy(src_img, images_out / f"ssdd_{stem}{src_img.suffix}")
        (labels_out / f"ssdd_{stem}.txt").write_text("\n".join(lines))
        written.append(f"ssdd_{stem}")
        converted += 1

    print(f"[SSDD] {converted} unique images converted, {duplicates} duplicate XML entries skipped "
          f"(same image across multiple split ratios), {skipped_no_image} skipped (no matching image/xml), "
          f"{skipped_bad_object} malformed <object> entries skipped, {zero_box} images had zero boxes.")

    return written


# --------------------------------------------------------------------------
# 4. SPLIT + data.yaml
# --------------------------------------------------------------------------

def preprocess():
    for sub in ["images/train", "images/val", "labels/train", "labels/val"]:
        (OUT_DIR / sub).mkdir(parents=True, exist_ok=True)

    tmp_images = OUT_DIR / "_tmp_images"
    tmp_labels = OUT_DIR / "_tmp_labels"
    tmp_images.mkdir(exist_ok=True)
    tmp_labels.mkdir(exist_ok=True)

    stems = []
    hrsid_root = RAW_DIR / "HRSID"
    ssdd_root = RAW_DIR / "SSDD"
    if hrsid_root.exists():
        stems += convert_hrsid(hrsid_root, tmp_images, tmp_labels)
    else:
        print(f"[skip] {hrsid_root} does not exist.")
    if ssdd_root.exists():
        stems += convert_ssdd(ssdd_root, tmp_images, tmp_labels)
    else:
        print(f"[skip] {ssdd_root} does not exist.")

    if not stems:
        raise SystemExit("No images converted — check the [HRSID]/[SSDD] messages above "
                          "for what went wrong before re-running.")

    before = len(stems)
    stems = list(dict.fromkeys(stems))  # dedupe, preserve order
    if len(stems) != before:
        print(f"[dedupe] Removed {before - len(stems)} duplicate stems before splitting.")

    random.shuffle(stems)
    n_val = max(1, int(len(stems) * VAL_FRACTION))
    val_stems, train_stems = set(stems[:n_val]), set(stems[n_val:])

    for stem in tqdm(stems, desc="Splitting train/val"):
        split = "val" if stem in val_stems else "train"
        img_src = next(tmp_images.glob(f"{stem}.*"))
        lbl_src = tmp_labels / f"{stem}.txt"
        shutil.move(str(img_src), OUT_DIR / f"images/{split}/{img_src.name}")
        shutil.move(str(lbl_src), OUT_DIR / f"labels/{split}/{lbl_src.name}")

    shutil.rmtree(tmp_images)
    shutil.rmtree(tmp_labels)

    data_yaml = {
        "path": str(OUT_DIR.resolve()),
        "train": "images/train",
        "val": "images/val",
        "nc": len(CLASS_NAMES),
        "names": CLASS_NAMES,
    }
    (OUT_DIR / "data.yaml").write_text(yaml.safe_dump(data_yaml, sort_keys=False))

    print(f"\nDone. {len(train_stems)} train / {len(val_stems)} val chips.")
    print(f"Dataset config written to {OUT_DIR/'data.yaml'}")
    print("Train with e.g.: yolo detect train model=yolov8n.pt "
          f"data={OUT_DIR/'data.yaml'} imgsz=800 epochs=100")


# --------------------------------------------------------------------------
# 5. SANITY CHECK
# --------------------------------------------------------------------------

def check(n=6):
    img_dir = OUT_DIR / "images/train"
    lbl_dir = OUT_DIR / "labels/train"
    imgs = list(img_dir.glob("*"))[:n]
    if not imgs:
        raise SystemExit("No images found — run --preprocess first.")

    tiles = []
    for img_path in imgs:
        img = cv2.imread(str(img_path))
        h, w = img.shape[:2]
        lbl_path = lbl_dir / (img_path.stem + ".txt")
        if lbl_path.exists():
            for line in lbl_path.read_text().splitlines():
                if not line.strip():
                    continue
                _, cx, cy, bw, bh = map(float, line.split())
                x1 = int((cx - bw / 2) * w)
                y1 = int((cy - bh / 2) * h)
                x2 = int((cx + bw / 2) * w)
                y2 = int((cy + bh / 2) * h)
                cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 2)
        tiles.append(cv2.resize(img, (300, 300)))

    grid = cv2.hconcat(tiles)
    cv2.imwrite("sample_check.png", grid)
    print("Wrote sample_check.png — open it and confirm boxes sit on ships, "
          "not land/noise.")


# --------------------------------------------------------------------------

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--download", action="store_true")
    p.add_argument("--preprocess", action="store_true")
    p.add_argument("--check", action="store_true")
    args = p.parse_args()

    if args.download:
        download()
    if args.preprocess:
        preprocess()
    if args.check:
        check()
    if not any([args.download, args.preprocess, args.check]):
        print(__doc__)