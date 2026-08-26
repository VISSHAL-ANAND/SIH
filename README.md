# Ship Detection & Attribution — Track (SIH26143)

Hey — this is your corner of the oil-spill project: finding every vessel
hull in a SAR image, independent of AIS, so a spill can actually be traced
back to a ship instead of staying anonymous. Everything below reflects
what's actually built and tested, not just what's planned.

## Install this first
```bash
pip install ultralytics rasterio pyproj gdown pyyaml tqdm opencv-python scikit-learn --break-system-packages
```
Training needs a GPU to be practical — full 100-epoch run took ~4 hours on
an RTX 4060 Laptop GPU (8GB). CPU-only would take a day+; use Colab's free
T4 instead if that's your situation.

---

## What's done vs. what's left

| File | Where it stands | Notes |
|---|---|---|
| `prepare_sar_ship_datasets.py` | Done — dataset built | 6,764 chips (5,604 HRSID + 1,160 SSDD, deduped from ~11 redundant split-ratio copies) |
| `train_ship_detector.py` | Done — model trained | YOLOv8s, mAP50=0.850, precision=0.882, recall=0.756 |
| `evaluate_by_size.py` | Done — used to tune | Confirmed small/occluded-hull recall specifically, not just overall |
| `ship_detection_module.py` | Done — tested | Verified on in-distribution + out-of-distribution imagery |
| `test_geo_conversion.py` | Done — passing | Both plain lat/lon and UTM-reprojection cases pass |
| `runs/detect/sar_hull_detector/weights/best.pt` | Exists locally, **not in git** | Large binary — share via Drive link, don't push |

---

## Step 1 — Get and preprocess the datasets

Using **HRSID** (5,604 SAR chips, COCO-format annotations, TerraSAR-X +
Sentinel-1B) and **SSDD** (1,160 images, VOC-format, the `BBox_SSDD/voc_style`
variant specifically — not the rotated-box or segmentation variants).

1. Grab HRSID from the Google Drive link in `github.com/chaozhong2010/HRSID`'s
   README (the JPG version with inshore/offshore annotations).
2. Grab SSDD from `github.com/TianwenZhang0825/Official-SSDD` — **heads up,
   it's distributed as a `.rar`, not a `.zip`**, even though the Drive
   filename may not say so. Extract with 7-Zip, not Windows' built-in tool
   (which fails silently on RAR content). Use only the `BBox_SSDD/voc_style`
   subfolder.
3. Paste both Google Drive file IDs into `HRSID_GDRIVE_ID` / `SSDD_GDRIVE_ID`
   near the top of `prepare_sar_ship_datasets.py`.
4. Run:
   ```bash
   python prepare_sar_ship_datasets.py --download    # HRSID only, SSDD is manual
   python prepare_sar_ship_datasets.py --preprocess
   python prepare_sar_ship_datasets.py --check        # writes sample_check.png
   ```
   This converts both datasets to a unified YOLO format, dedupes SSDD's
   duplicate split-ratio copies automatically, and splits 85/15 into
   `sar_ships/images/{train,val}` + `sar_ships/labels/{train,val}`.

**One thing to actually look at:** open `sample_check.png` after `--check`
and confirm the boxes sit on real hulls, not empty water/land — especially
in dense harbor scenes, which are genuinely hard to eyeball at small size
but are where a real coordinate bug would show up first.

## Step 2 — Train the hull detector

```bash
python train_ship_detector.py --train
```

YOLOv8s, not Faster-RCNN — picked for training speed given the timeline;
flag this to the team if it affects the architecture diagram or pitch deck.
Config is tuned specifically for small/occluded hulls (mosaic, scale
jitter, copy-paste augmentation, both flips since SAR has no canonical
"up").

**Results on the val split (1,101 images, 2,859 ship instances):**
- mAP50 = 0.850, mAP50-95 = 0.576
- Precision = 0.882, Recall = 0.756 (at conf=0.25)

Ran `evaluate_by_size.py` to check recall **by object size** specifically,
since overall recall hides whether small/occluded ships are the weak point:

| Bucket | conf=0.25 | conf=0.15 (deployed default) |
|---|---|---|
| small | 0.751 | 0.788 |
| medium | 0.887 | 0.912 |
| large | 0.294 | 0.500 |
| overall | 0.803 | 0.839 |

**Deliberately lowered the deployed confidence threshold to 0.15.** This
isn't just recall-chasing — this module feeds ASHMIL's AIS matcher as a
*candidate generator*, not a final verdict, so a few extra false positives
get filtered downstream when they turn out to have valid AIS. A missed
real ship never gets a second chance. Recall matters more than precision
at this stage of the pipeline.

**Known limitation, not hidden:** large-vessel recall (0.500) is still
meaningfully weaker than small/medium even after tuning. Worth flagging
since a real oil-tanker culprit is typically a *large* vessel — this is a
legitimate next-step item, not something papered over.

If it crashes mid-training (laptop dies, etc.), resume with:
```bash
python train_ship_detector.py --resume
```
YOLO checkpoints `last.pt`/`best.pt` after every completed epoch, so you
only lose the current partial epoch, not the whole run.

## Step 3 — Package as a pipeline module

```python
from ship_detection_module import detect_hulls

detections = detect_hulls("scene.tif")
# -> [{"bbox_px": [...], "confidence": 0.91,
#      "lat": 10.234, "lon": 78.912,   # None if no geo metadata
#      "timestamp": "2026-08-20T03:14:00Z"}, ...]
```

Handles both plain image chips (pixel coords only) and georeferenced
GeoTIFF scenes (real lat/lon via `rasterio` + `pyproj`, tested against both
plain-lat/lon and UTM-projected synthetic rasters in
`test_geo_conversion.py` — both pass).

**Tested on:**
- In-distribution HRSID/SSDD val chips — sensible detections, correct box
  localization confirmed by manual inspection.
- **Out-of-distribution real Sentinel-1 imagery** (Strait of Hormuz, pulled
  fresh from the Copernicus Browser — a source completely separate from
  training data) — detection count matched the visually-countable ships
  exactly. This is the strongest evidence the model actually generalizes,
  not just memorizes HRSID/SSDD.

---

## Where this feeds into the rest of the pipeline

`detect_hulls()`'s output is what **ASHMIL's AIS matcher** and
**RATHIMEE's full pipeline wiring** both import directly — each detection's
`lat`/`lon`/`timestamp` gets cross-checked against AIS tracks for that
window; anything with no AIS match is an auto-flagged suspect vessel. So
this track's output isn't just a box to check — it's the independent,
AIS-free detection signal the whole attribution story depends on.

## If you get stuck

- SSDD download comes down as `.zip` but is actually `.rar` → rename the
  extension, extract with 7-Zip, not Windows' built-in tool.
- HRSID's `images/` folder isn't where you expect → the script indexes the
  whole extracted tree by filename instead of assuming a folder name, so
  this shouldn't come up again, but if it does, check `raw/HRSID/` actually
  contains `train2017.json`/`test2017.json` somewhere.
- No GPU for training → Colab's free T4 handles this dataset size fine;
  upload `sar_ships/` (zip it first) and run `train_ship_detector.py` there.
- Need the trained weights without retraining → ask rinosh directly, since
  `best.pt` isn't in git (too large) — share via Drive link instead.