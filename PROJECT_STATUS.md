# SIH26143 — Project Status & Knowledge Document
*Compiled 2026-09-01. This is the real, honest state of the project — what's actually built and tested vs. what's still planned.*

---

## 1. The Problem & The Idea

**Official problem statement (SIH26143, National Technical Research Organisation):** Leverage satellite imagery to detect oil spills at sea and correlate with AIS data to identify the vessel responsible for the spill.

**Why the obvious approach isn't good enough:** Existing tools (EMSA CleanSeaNet, SkyTruth Cerulean) already do "detect the slick, then check which AIS-broadcasting ships were nearby." That approach has a fundamental blind spot: it only works if the polluting vessel's AIS was actually on. A ship that turns AIS off specifically to dump oil undetected — the exact scenario this problem statement cares about — defeats that whole approach by design.

**Our actual novelty:** Don't rely on AIS to find the vessel. Detect every physical hull in the SAR image independently (a separate computer-vision task from slick detection), then cross-check each hull against AIS. A hull with **no matching AIS broadcast** isn't a heuristic guess — it's a structural fact: something is out there that isn't identifying itself. That inversion (AIS confirms *innocence*, it doesn't establish *existence*) is the same trick real anti-dark-fishing organizations (Global Fishing Watch, Windward) use, and it's what separates this from a Cerulean clone.

---

## 2. Architecture — Four Pipeline Stages

```
SAR Image
   │
   ├──► [1] SLICK DETECTION ──────► oil slick mask + linear/blob shape classification
   │
   ├──► [2] HULL DETECTION ───────► every vessel hull in the image, independent of AIS
   │
   ├──► [3] AIS MATCHING ─────────► for each hull: matched vessel, OR flagged as suspect
   │
   └──► [4] DRIFT SIMULATION ─────► backward-simulate slick origin + jurisdiction zone
                                          │
                                          ▼
                              Ranked suspect list + evidence
                              (the actual demo payload)
```

---

## 3. Team & Current Assignments

| Person | Track | Notion Status |
|---|---|---|
| **VISSHAL** (you) | Slick detection (original) + took over hull-detection integration, AIS matching build, and pipeline integration when others stalled | 4/4 original tasks Done, plus absorbed work below |
| **RINOSH** | Hull/ship detection (YOLOv8) | 4/4 Done |
| **ASHMIL** | AIS matching (original assignment) | 0/4 in Notion — **VISSHAL built this instead** |
| **RATHIMEENA** | Pipeline integration + demo curation + pitch deck | 0/5 in Notion — **VISSHAL partially absorbed this** (contracts + wiring done; demo curation + pitch deck still open) |
| **SIMI** | Drift simulation + jurisdiction routing | 2/4 Done, 1 In Progress |
| **SYLVI** | Dashboard | 0/4 Done, 1 In Progress |

**Honest note on the Notion board:** it currently under-represents real progress, because VISSHAL built real AIS matching and pipeline integration under ASHMIL's and RATHIMEENA's task names without updating their Notion entries yet. Worth fixing so the board reflects reality.

---

## 4. What's Actually Real vs. Mocked vs. Blocked — Component by Component

### ✅ Stage 1: Slick Detection — REAL, fully tested, done
- **Dataset:** Zenodo repeatedly 502/504'd, pivoted to Kaggle `bakhtiyar2222/deep-sar-oil-spill-segmentation-refined` (binary masks, no look-alike class — a real, disclosed limitation).
- **Real numbers:** 5,810 train / 1,615 val / 645 test images. Oil pixels = 24.89% of all pixels (much higher than the ~3% originally assumed — this dataset is patch-cropped to be oil-enriched, not raw full scenes).
- **Model:** U-Net with pretrained ResNet34 encoder (transfer learning — training from scratch wasn't feasible in the sprint window). Class weights recalibrated from `[0.4, 3.5]` to `[0.5, 1.5]` after seeing the real pixel ratio.
- **Training:** VISSHAL's laptop had no GPU (would've taken 6+ hours on CPU); ran on a friend's RTX 4060 instead (~15 min).
- **Shape classifier:** Rule-based PCA-elongation classifier (not a trained model — deterministic, explainable, zero training time). Self-tested on synthetic shapes first, then run on real predictions: **1,463 linear slicks, 1,709 blob slicks** across the test set (~46/54 split — genuinely discriminating, not defaulting to one class).
- **Known limitation, disclosed honestly:** since the dataset has no separate look-alike class, this shape classifier is now doing double duty as a partial false-positive filter — not a full substitute for a trained look-alike detector. Say this plainly in the pitch.

### ✅ Stage 2: Hull Detection — REAL, built by RINOSH, independently verified
- YOLOv8 trained on HRSID + SSDD datasets, with deliberate small/occluded-object tuning (mosaic augmentation, copy-paste, scale augmentation) since small hulls near slicks are the highest-value detections.
- Evidence-based evaluation: `evaluate_by_size.py` breaks down recall by object size (small/medium/large) rather than assuming augmentation settings worked.
- **Real geo-conversion:** pixel → lat/lon using rasterio + pyproj, handling both plain lat/lon rasters and UTM-projected rasters (the realistic Sentinel-1 case). VISSHAL independently re-ran and verified this math against hand-computed expected values — both test cases passed.
- **Known limitation:** real lat/lon only comes through when the input is a georeferenced raster (GeoTIFF). The current demo/training images are plain `.jpg` with no geo metadata, so on those, lat/lon legitimately returns `None` — a `geolocation.py` demo-anchor approximation (Gujarat coast box) fills the gap for demo purposes only. Never present the demo-anchor coordinates as real in the pitch.

### ✅ Stage 3: AIS Matching — REAL, built by VISSHAL (ASHMIL's original task), tested
- Spatial-temporal matcher: haversine distance + time-window tolerance. No match within tolerance → flagged as suspect with a real suspicion score, not a guess.
- Self-tested on synthetic data first (correctly matched a nearby ping, correctly flagged a distant point).
- **Validated against real government AIS data:** MarineCadastre.gov, 7,337,208 real records loaded and correctly matched/flagged.
- **Critical geographic issue found and being fixed:** MarineCadastre only covers U.S. coastal waters (confirmed — first real record was near Puerto Rico). Zero coverage of Indian waters, where the demo is anchored. Every hull would trivially come back "suspect" against this data — not a real finding, just a coverage gap.
- **In-progress fix:** swapping to Global Fishing Watch's API for genuine global coverage. Hit three real bugs in a row (wrong request body format ×2, wrong dataset ID) — each found through actual testing, not guessing blind, and fixed by checking against GFW's own confirmed working examples. Currently blocked on a **403 "Insufficient permissions"** for the AIS Vessel Presence dataset — this is a genuine access-tier restriction on GFW's side (confirmed: another real user hit the identical wall), not a code bug. Currently trying GFW's SAR Vessel Detections dataset as an alternative, which may have different access rules and is arguably even more relevant (it already includes GFW's own `matched=true/false` dark-vessel flag, built from the same Sentinel-1 source this project uses).
- **Safe fallback built in:** the script tries GFW first, and automatically falls back to MarineCadastre with a loud honest warning if GFW isn't available — so nothing breaks while the access issue gets sorted.

### ⏳ Stage 4: Drift Simulation — MOCKED in the pipeline, partially built by SIMI
- NOAA HYCOM (currents) + GFS (wind) data pull: Done.
- Backward drift simulation itself: In Progress, not finished.
- Jurisdiction routing (ICG zones, 500m exclusion): marked Done in Notion, not yet verified integrated.
- Validation against a real spill case (MSC ELSA 3): Not Started.
- **In `integration_pipeline.py` right now:** this stage is a placeholder mock (fixed dummy origin point, no real current/wind modeling) so the full pipeline can run end-to-end today. Needs SIMI's real simulation wired in to replace it.

### 🔧 Integration — Partially done by VISSHAL (RATHIMEENA's original task)
- `pipeline_contracts.py`: the data contract every module speaks (slick detection, hull detection, AIS matching, drift simulation). Verified working.
- `integration_pipeline.py`: **3 of 4 stages genuinely wired together and tested** (slick → hull → AIS). Drift remains mocked.
- Found and fixed a real bug during integration testing: RINOSH's timestamps are timezone-aware, AIS data is naive — pandas refused to compare them until normalized.
- **Still open from RATHIMEENA's original task list:** demo frame curation (picking the 2-3 SAR frames that best show a hull-with-no-AIS-match for the live walkthrough), and the pitch deck itself.

### 🔲 Dashboard — barely started (SYLVI)
- Wireframe in progress. Map view, ranked suspect list, and UI polish all not started.
- No visual demo surface exists yet — currently the only way to see pipeline output is console text.

---

## 5. Key Decisions & Pivots (so nobody re-litigates settled choices)

1. **Dataset switch:** MKLab/Zenodo (5-class, oil/look-alike/land/ship/sea) → Kaggle SOS (binary, oil/not-oil) after Zenodo's server kept failing. Traded away the look-alike class; compensated partially with the shape classifier.
2. **Training hardware:** VISSHAL's laptop (CPU-only) → friend's RTX 4060, after discovering a plain `pip install torch` defaults to the CPU-only build on Windows (needed the CUDA-specific install index).
3. **Team roles reshuffled mid-sprint:** original RATHIMEENA (drift sim) and SIMI (integration/pitch) roles got swapped at some point; Notion board still needs updating to reflect who actually owns what now.
4. **AIS data source switch:** MarineCadastre (real, but zero Indian coverage) → Global Fishing Watch (real global coverage), currently blocked on a dataset permission wall, being worked around via their SAR-detections dataset instead.
5. **Multiple team members' work absorbed by VISSHAL** when their tasks sat at 0% while the clock kept moving: AIS matching (ASHMIL's), and partial pipeline integration (RATHIMEENA's).

---

## 6. What's Genuinely Left To Do

**High priority (blocks a working demo):**
- Resolve the GFW access issue OR make peace with the honest "validated on real government-scale data, production would use GFW" framing and move on.
- SIMI: finish the real backward drift simulation (currently mocked).
- Demo frame curation: pick the actual 2-3 SAR frames for the live walkthrough.
- Pitch deck: not started.

**Medium priority (strengthens the demo, not blocking):**
- SYLVI: dashboard — even a simple map + suspect list would beat console-only output for a live demo.
- Real georeferenced Sentinel-1 scene (if time allows) — would upgrade the geo story from "disclosed approximation" to "genuinely real" for at least one demo frame.

**Already solid, don't need more time sunk here:**
- Slick detection (done, tested).
- Hull detection (done, tested).
- AIS matcher logic itself (done, tested — only the *data source* is the open question, not the matching algorithm).

---

## 7. Repo / File Map

```
sih26143_slick_detection/
  preprocess.py              — dataset prep (Kaggle SOS)
  train_unet.py               — U-Net training
  shape_classifier.py         — linear-vs-blob classifier
  predict_and_classify.py     — inference pipeline module

sih26143_ship_detection/  (RINOSH)
  prepare_sar_ship_datasets.py
  train_ship_detector.py
  ship_detection_module.py    — callable hull detector, real geo-conversion
  test_geo_conversion.py
  evaluate_by_size.py

sih26143_ais_matching/  (VISSHAL, took over from ASHMIL)
  ais_matcher.py               — core matching logic + real MarineCadastre loader
  gfw_ais_loader.py            — GFW integration (in progress, access-blocked)

sih26143_integration/  (VISSHAL, took over from RATHIMEENA)
  pipeline_contracts.py        — shared data contract
  integration_pipeline.py      — wires 3 of 4 stages together
  geolocation.py                — demo-anchor lat/lon fallback
```

---

## 8. Timeline Reality Check

The original compressed sprint plan targeted Aug 23–25. Today is **September 1** — a week past that internal deadline. This document doesn't know what your actual hard external deadline is (the official SIH portal deadline was 20 September for idea submission, per the original problem statement page) — worth confirming that's still the real constraint you're working against, since it changes how much runway is actually left for the open items above.
