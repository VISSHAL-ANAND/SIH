# Ship Detection & Attribution — Track (SIH26143)

Hey — this is your corner of the oil-spill project: finding the actual slick
in a SAR image before anyone can figure out who caused it. Everything below
is set up so you can just run it, not go hunting for what's missing.

## Install this first
```bash
pip install ultralytics rasterio pyproj gdown pyyaml tqdm opencv-python scikit-learn --break-system-packages
```
You'll also want a GPU if you can get one (Colab's free T4 is fine). CPU
works too, just slower — see the note in step 2 below.

---

## What's done vs. what's left

| File | Where it stands | Built |
|---|---|---|
| `src/preprocess.py` | Ready — just point it at the dataset | 2026-08-23 18:21 UTC |
| `src/train_unet.py` | Ready — run it after preprocessing | 2026-08-23 18:21 UTC |
| `data/processed/best_unet.pt` | Doesn't exist yet — this is what running the scripts produces | not yet |

---

## Step 1 — Get the dataset

We're using the **MKLab Oil Spill Detection Dataset** on Zenodo. It's the one
most teams working this exact problem end up using, because it's the only
public dataset that separates a real "Oil Spill" from a "Look-alike" — which
matters a lot, since look-alikes are the main source of false positives in
this kind of project.

1. Grab it here: https://zenodo.org/records/6552722 (free account, few GB — Zenodo doesn't allow scripted bulk downloads, so this part's manual)
2. Unzip it into `data/raw/` so it looks like this:
   ```
   data/raw/train/images/*.jpg
   data/raw/train/labels/*.png
   data/raw/test/images/*.jpg
   data/raw/test/labels/*.png
   ```
3. Run the preprocessing script:
   ```bash
   cd src
   python preprocess.py
   ```
   This resizes everything, turns the color masks into class-index masks, and
   splits it into train/val/test as `.npy` files.

   **One thing to actually look at:** the script prints out how many pixels
   belong to each class. If "oil_spill" is only 2-3% of all pixels, that's a
   real imbalance problem worth flagging to the team — not something to just
   shrug off.

## Step 2 — Train the baseline model

```bash
cd src
python train_unet.py
```

This isn't training from scratch — it uses a ResNet34 encoder that's already
pretrained on ImageNet, and just fine-tunes it for our classes. Given we've
got 3 days, not 3 weeks, training from zero simply wouldn't converge to
anything usable in time. This will.

On a GPU, expect well under an hour for 15 epochs. Stuck on CPU only? Drop
`EPOCHS` down to 5-8 in the script just to get a working checkpoint today,
then re-run it properly once someone gets you GPU time.

**Watch "Oil Spill IoU" in the console, not the accuracy number.** Accuracy
will look great even if the model just learns to predict "background"
everywhere, because most of any SAR frame genuinely is open sea. Oil Spill
IoU is the number that tells you if it's actually working.

---

## Where this feeds into tomorrow

Once you've got `data/processed/best_unet.pt`, that's the input for your Aug
24 task — the linear-vs-blob shape classifier. A **linear** slick shape
usually means a moving vessel discharge (which is a real lead for
RINOSH/ASHMIL's suspect-matching work); a **blob** shape usually means a
static leak, less tied to one passing ship. So today's work isn't just a
box to check — it's what tomorrow's differentiation piece actually runs on.

## If you get stuck today

- Zenodo download being annoying → ask around, someone on the team may
  already have it downloaded.
- No GPU → Colab's free tier handles this dataset size fine. Just upload
  the `.npy` files from `data/processed/` and run `train_unet.py` there.


# Pipeline Integration — taken over from RATHIMEENA by VISSHAL

## Install this first
```bash
pip install torch torchvision segmentation-models-pytorch opencv-python-headless scipy numpy pillow pandas ultralytics rasterio pyproj
```

## What's done vs. what's left

| File | Where it stands | Built |
|---|---|---|
| `pipeline_contracts.py` | Ready — data contract, now includes real RINOSH + real AIS formats | 2026-08-27 10:56 UTC |
| `integration_pipeline.py` | Ready — 3 of 4 stages REAL and verified, drift still mocked | 2026-08-27 10:56 UTC |

## What's real vs. mocked right now

- **Slick detection** — REAL (VISSHAL's trained U-Net + shape classifier)
- **Hull detection** — REAL (RINOSH's trained YOLOv8 detector — geo-conversion
  math independently verified against hand-computed values, both plain
  lat/lon and UTM-projected cases passed)
- **AIS matching** — REAL (VISSHAL's spatial-temporal matcher — self-tested)
- **Drift simulation** — still MOCKED, SIMI's real simulation isn't built yet

Only drift/jurisdiction routing remains fake. Three of four pipeline stages
are now genuinely connected, not staged.

## Important: the geo caveat

RINOSH's detector returns REAL lat/lon only when given a georeferenced
raster (GeoTIFF with a valid transform). Our current demo/training images
(Kaggle SOS chips) are plain `.jpg` with no geo metadata — so on those,
lat/lon legitimately comes back `None`. The pipeline falls back to
`geolocation.py`'s demo-anchor approximation ONLY in that case — it never
overwrites a real coordinate. If you get one real georeferenced Sentinel-1
scene before the demo, running it through will produce genuinely real
coordinates instead of the anchor guess. Be upfront about this distinction
if a judge asks how coordinates are derived — don't imply real geocoding on
data that doesn't have it.

## How to run it

1. Make sure `sih26143_slick_detection`, `sih26143_ship_detection`, and
   `sih26143_ais_matching` folders are all siblings of this one (same
   parent directory) — the imports assume that layout.
2. RINOSH's `best_unet.pt` needs to exist at
   `sih26143_ship_detection/runs/detect/sar_hull_detector/weights/best_unet.pt`
3. Real AIS data: point `ais_matcher.py`'s `AIS_CSV_PATH` at a real
   MarineCadastre download, or the pipeline defaults to synthetic AIS data
   for testing (fine for verifying wiring, NOT for the actual pitch).
4. Run:
```bash
python integration_pipeline.py
```

## Verified through actual testing, not just written

- RINOSH's geo-conversion math: independently re-run, both test cases
  (plain lat/lon, UTM reprojection) passed against hand-computed expected
  values.
- Integration wiring: tested with a stub matching his exact documented
  output format (since his trained weights aren't available in this
  environment) — caught and fixed a real timezone bug (his ISO timestamps
  are UTC-aware, AIS data is naive) before it could break on demo day.

## Still open
- Drift simulation (SIMI's task) — the last mock.
- Real AIS data hasn't been run through yet — only synthetic, for wiring
  verification.
- A real georeferenced Sentinel-1 scene would upgrade the geo story from
  "disclosed approximation" to "genuinely real," if there's time to get one.

# Drift Simulation — taken over from SIMI by VISSHAL

## Install this first
```bash
pip install requests pandas
```

## What's done vs. what's left

| File | Where it stands | Built |
|---|---|---|
| `ocean_wind_loader.py` | Ready — real data source, parsing verified | 2026-08-31 09:46 UTC |
| `drift_simulation.py` | Ready — physics self-tests all pass | 2026-08-31 09:46 UTC |
| Jurisdiction routing (ICG zones/500m exclusion) | NOT built — the "Done" status on Notion for this doesn't reflect real work | not yet |
| Validation against a real spill case | NOT built | not yet |

## Data source: Open-Meteo instead of raw HYCOM/GFS

Raw HYCOM (currents) and GFS (wind) access means dealing with THREDDS/
OPeNDAP servers or NOMADS GRIB files — real, but genuinely painful to
integrate correctly under time pressure. **Open-Meteo** provides the same
type of real data through a free, keyless JSON REST API, sourced from real
models including NOAA GFS (wind) and Copernicus Marine/MeteoFrance SMOC
(ocean currents). No API key needed, free for non-commercial use.

**Be honest about this in the pitch:** "We use Open-Meteo's API layer over
real NOAA/Copernicus models rather than raw HYCOM/GFS file access, for
integration speed within the hackathon window. The underlying data is
real; the access method is simplified."

## The physical model: the "3% wind factor" rule

This is a real, established approximation used in actual operational spill
models — including NOAA's own GNOME tool, which the original task
explicitly referenced. Surface drift velocity ≈ ocean current + (3% of
wind speed, in wind direction). This is a genuine simplification (real
Ekman transport physics is more complex), but the 3% factor itself is not
invented for this project — it's a widely-cited real approximation.

## How to run it

```python
from ocean_wind_loader import fetch_currents_and_wind
from drift_simulation import simulate_backward_drift
from datetime import datetime

# 1. Get real current + wind data for your demo region/date
data = fetch_currents_and_wind(
    lat=20.85, lon=69.20,  # Gujarat demo anchor
    start_date="2026-08-20", end_date="2026-08-20",
)
print(data)

# 2. Pick the hour closest to your slick's detection time, then run the
#    backward simulation
row = data.iloc[12]  # e.g. noon
result = simulate_backward_drift(
    slick_lat=20.85, slick_lon=69.20,
    detection_time=datetime(2026, 8, 20, 12, 0, 0),
    current_velocity_kmh=row["current_velocity_kmh"],
    current_direction_deg=row["current_direction_deg"],
    wind_speed_kmh=row["wind_speed_kmh"],
    wind_direction_deg=row["wind_direction_deg"],
    hours_back=6.0,
)
print(f"Estimated origin: {result.origin_lat}, {result.origin_lon}")
```

## Verified through actual testing

- `ocean_wind_loader.py`: parsing logic checked against Open-Meteo's own
  documented example JSON response — passed.
- `drift_simulation.py`: three physics self-tests — pure northward current
  correctly places origin to the south, pure eastward current correctly
  places origin to the west, wind has a real but appropriately small
  (3%-scale) effect relative to current. All passed.

## Honest limitations (say these in the pitch, don't hide them)
- Assumes current/wind conditions were roughly constant during the
  backward window — real conditions vary hour to hour. A more
  sophisticated version would use the actual historical time series for
  each backward step instead of one snapshot.
- Doesn't model oil weathering (evaporation, emulsification) which
  changes real drift behavior over time.
- Still explicitly a "simplified" simulation, as the original task asked
  for — not a claim of GNOME/OSERIT-grade accuracy, only similarity in
  general approach.
- I could not test the live network calls to Open-Meteo myself (not
  reachable from my sandbox) — the parsing logic is verified against their
  real documented example, but run it live on your machine to confirm.
- Jurisdiction routing and real-spill validation (SIMI's other two tasks)
  are NOT built yet — only the two most foundational pieces are done.