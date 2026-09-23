# Indo Marine Watch (IMW) — Project State / Handoff

Last updated: 2026-09-20

## Project

- SIH 2026 Problem Statement: SIH26143
- Project: Indo Marine Watch (IMW)
- Repository: VISSHAL-ANAND/SIH
- Goal: Sentinel-1 SAR oil-spill detection + independent physical vessel detection + AIS correlation + trajectory/gap analysis + environmental drift reconstruction + evidence fusion for operator-reviewed vessel investigation.

## Core system flow

1. Sentinel-1 SAR acquisition and geolocation
2. SAR preprocessing
3. Pixel-level oil-spill segmentation with U-Net
4. Slick morphology / PCA-based shape analysis
5. Independent physical ship detection from SAR
6. SAR vessel coordinates + verified acquisition timestamp
7. AIS spatial-temporal correlation
8. AIS continuity/gap analysis
9. Vessel trajectory evidence
10. Backward environmental drift/source-zone reconstruction
11. Multi-factor evidence fusion and candidate ranking
12. Investigation dashboard / evidence package
13. RF corroboration is PLANNED, not yet a real integrated tracker
14. Coast Guard response is operator-review only; no automatic transmission

## Completed implementation

- Real Sentinel-1 GeoTIFF tiled pipeline
- Sentinel-1 SAFE annotation geolocation fallback
- Colocated Sentinel-1 annotation XML discovery for local GRD TIFF + XML pairs
- Sentinel-1 acquisition timestamp parsing/hardening
- U-Net oil-slick segmentation pipeline
- PCA/elongation slick shape classification
- SAR physical ship detection with a verified one-class ship checkpoint
- 1-band Sentinel-1 TIFF handling for ship detection
- Global NMS for tiled SAR detections, including suppression of high-overlap/nested duplicate boxes
- Real WGS84 vessel geolocation from Sentinel-1 annotation geolocation grids
- AIS candidate engine using spatial + temporal windows
- AIS candidate metadata and evidence states
- Vessel history / AIS continuity and gap analysis
- Pre/post-event trajectory evidence
- Backward drift analysis and estimated source-zone evidence
- Multi-factor evidence fusion
- Investigation map and candidate investigation panel
- Evidence matrix / confidence / coverage presentation
- Incident package/report/response safeguards
- Operator-review gates
- Test suite previously reached 105 passing tests with 6 warnings
- Real Sentinel-1 SAFE geolocation successfully verified from annotation XML
- Random real Sentinel-1 scene validation produced no slicks and should remain a no-oil result; do not tune the system to force a detection

## Ship-model training status

### Final selected detector: YOLO26-S V2

The original reconstructed YOLO checkpoint was an early SAR ship model:
- checkpoint: best_reconstructed.pt
- one class: ship
- benchmark on 25 OSSDD test chips:
  - Precision: 0.750
  - Recall: 0.203
  - TP: 36 / FP: 12 / FN: 141
- Conclusion: insufficient recall for final IMW deployment.

A persistent YOLO26-S training path was then completed on the OSSDD/OpenSARShip smoke dataset:
- Train images: 500
- Validation images: 100
- Model: YOLO26-S
- Image size: 800
- Planned maximum: 150 epochs
- Patience: 30
- Training environment: Google Colab Tesla T4
- Training outputs/checkpoints were stored under Google Drive so the final checkpoint survived runtime resets.

### V2 final detector

Final selected run:
- Run: imw_yolo26s_ossdd_500x100_v2
- Model: YOLO26-S
- Image size: 800
- Completed at epoch 92
- SAR-oriented augmentation:
  - hsv_h=0
  - hsv_s=0
  - hsv_v=0.20
  - fliplr=0.5
  - flipud=0.5
  - degrees=0
  - shear=0
  - perspective=0
  - scale=0.90
  - mosaic=1.0
  - close_mosaic=15
  - mixup=0.05
  - copy_paste=0

Fresh independent validation of V2:
- Precision: 0.6654
- Recall: 0.5501
- mAP50: 0.5394
- mAP50-95: 0.2169

The V2 checkpoint is the current final detector.

### Other evaluated variants

V3 — 1024px:
- Precision: 0.6163
- Recall: 0.5468
- mAP50: 0.5507
- mAP50-95: 0.2120
- Not selected.

V4 — small-object crop oversampling:
- Precision: 0.6626
- Recall: 0.5160
- mAP50: 0.5076
- mAP50-95: 0.1972
- Not selected.

V5 — YOLO26-S-P2:
- Precision: 0.6071
- Recall: 0.5000
- mAP50: 0.5163
- mAP50-95: 0.1897
- Not selected.

Conclusion:
- V2 remains the final detector.
- No further V6 detector training is planned unless new validation evidence justifies it.
- The model should not be retrained merely to improve a single real-scene result.

## Local demo model

The selected checkpoint has been copied from persistent Google Drive storage into the local repository for offline/demo use:

```
models/imw_yolo26s_v2/best.pt
```

The model is approximately 20.35 MB and was verified locally with:

```
classes = {0: "ship"}
```

Model weights remain ignored by Git via `*.pt`; the source repository does not require the binary to be committed.

The ship-detection module now resolves the model in this order:
1. Explicit `IMW_HULL_CHECKPOINT` environment override when the file exists
2. Local final V2 checkpoint at `models/imw_yolo26s_v2/best.pt`
3. Legacy `best_reconstructed.pt` fallback only when the V2 checkpoint is unavailable

## Real Sentinel-1 validation

A real Sentinel-1 VV GRD measurement TIFF was tested locally and in Colab:

```
s1a-iw-grd-vv-20260621t234859-20260621t234912-065074-0833c9-001.tiff
```

The matching Sentinel-1 annotation XML was also provided:

```
s1a-iw-grd-vv-20260621t234859-20260621t234912-065074-0833c9-001.xml
```

Scene metadata:
- Width: 25256
- Height: 9176
- One band
- uint16
- No GeoTIFF CRS/affine georeferencing
- Sentinel-1 annotation XML contains 126 geolocation grid points
- Scene latitude range: approximately 18.9760 to 20.2285
- Scene longitude range: approximately 89.8860 to 92.4177

Before the geolocation fix, hull detections had no coordinates because the XML was colocated with the TIFF but was not being searched.

The geolocation module was updated to check for a sibling XML matching the TIFF stem before the SAFE-ancestor search.

After the fix:
- 14 raw detections were produced
- Global duplicate suppression reduced them to 13 detections
- All 13 retained detections received real WGS84 latitude/longitude values from Sentinel-1 annotation geolocation interpolation
- Duplicate detections around the same vessel were successfully suppressed

Representative verified detections included:
- 19.475316, 91.113990
- 19.764439, 90.615751
- 19.634039, 90.503390
- 19.881532, 90.351662
- 19.434674, 90.197210
- 19.977213, 90.738630
- 19.549903, 90.394528
- 19.514787, 92.308589
- 19.963233, 90.697290
- 19.737812, 91.674445
- 19.637356, 92.247229
- 19.401648, 91.971280
- 19.369843, 92.307140

These coordinates are SAR-derived physical-hull locations, not AIS-derived locations.

## Current real-data pipeline status

The following chain is now operational:

```
Real Sentinel-1 VV TIFF
        ↓
YOLO26-S V2 tiled ship detection
        ↓
SAR physical hull detections
        ↓
Sentinel-1 annotation geolocation
        ↓
Real WGS84 vessel coordinates
```

The next integration step is:

```
Verified SAR vessel coordinates
        +
Verified Sentinel-1 acquisition timestamp
        ↓
AIS spatial-temporal correlation
        ↓
Candidate vessels
        ↓
Vessel history / trajectory evidence
        ↓
Environmental drift evidence
        ↓
Evidence fusion
```

Do not claim the real Sentinel-1 test has already produced a valid vessel attribution. The AIS correlation stage still needs to be executed against an appropriate real AIS source for this scene.

## AIS sources

### GFW current/recent mode

Set:

```
GFW_API_ACCESS_TOKEN=<authorized-personal-token>
```

The provider is designed to query the GFW 4Wings AIS vessel-presence dataset around detected SAR hulls and convert real hourly presence records into IMW's internal AIS schema.

Authentication and dataset-permission failures must remain explicit.

The current GFW AIS presence product is intended for recent data only, so it should be used for a current/recent Indian-water walkthrough when the authorized token and coverage are appropriate.

### Historical replay mode

The MarineCadastre sample is real data but is geographically unsuitable for presenting as live Indian-water AIS. It can be used for matcher validation/replay when clearly labelled as such.

Previous GFW API attempts returned permission/403 errors. Do not treat the provider as available until a valid authorized token has been verified.

## Evidence / responsibility rules

- AIS gap != proof of intentional AIS shutdown
- AIS gap != proof of wrongdoing
- Drift source zone is estimated/modelled, not a legal attribution radius
- Evidence ranking identifies investigation candidates, not legal responsibility
- responsibility status must remain `NOT_ESTABLISHED` unless independently established outside the system
- machine_generated = true
- legal_responsibility_established = false
- Coast Guard response must be `DRAFT_REQUIRES_OPERATOR_CONFIRMATION`
- transmission status must remain `NOT_SENT` unless an authorized operator actually sends it
- RF must remain `NOT_IMPLEMENTED` / `UNAVAILABLE` until a real source is connected

## RF module — PLANNED, NOT IMPLEMENTED

RF is intended as an additional corroboration layer, not a fabricated source of vessel tracks.

Planned role:
- SAR detects physical vessels.
- AIS reports vessel identity/track.
- RF can provide an independent radio-frequency corroboration signal when a real RF provider/receiver dataset is available.
- RF can help determine whether a radio emitter/track is spatially and temporally compatible with a SAR/AIS candidate.
- RF evidence should enter evidence fusion only when real observations exist.

Never fabricate:
- RF detections
- RF tracks
- emitter identity
- RF-to-vessel attribution

## Repository / local-data policy

Keep large/private/local artifacts outside Git:
- `SAR_DATA/` — local Sentinel-1 TIFF/XML data
- `*.pt`, `*.pth`, `*.h5`, `*.ckpt` — model binaries
- `runs/` — training outputs
- local AIS datasets
- Python virtual environments
- generated benchmark/validation artifacts

Useful source tooling remains tracked:
- `tools/benchmark_ossdd_25.py`
- `tools/validate_ossdd_sample.py`

## Remaining work to finish IMW

### A. AIS integration
1. Verify an authorized AIS provider suitable for the real Sentinel-1 scene.
2. Confirm exact scene timestamp and AIS coverage window.
3. Run SAR hull → AIS candidate correlation.
4. Inspect candidate separation/time differences.
5. Run vessel history and trajectory evidence.
6. Keep coverage gaps explicit.

### B. Environmental / drift integration
1. Verify real environmental observations for the scene/time.
2. Run backward drift/source-zone estimation.
3. Present drift as modelled corroboration, not attribution.

### C. RF
1. Define a real RF data source/provider/receiver.
2. Define RF observation schema and time/location accuracy.
3. Implement RF ingestion.
4. Implement RF-to-candidate correlation.
5. Add RF evidence to fusion only when observed.
6. Add tests and UI status.

### D. End-to-end production hardening
- real-data API integration
- persistence/database
- authentication/authorization
- audit logging
- deployment
- performance optimization
- final end-to-end tests

### E. SIH presentation
- align PPT wording with actual implementation status
- distinguish REAL DATA, UNAVAILABLE, NOT_IMPLEMENTED, and ESTIMATED
- show the independent SAR vessel detector + AIS correlation + drift + evidence fusion as the core novelty
- mention RF as planned corroboration unless implemented and tested before presentation
- do not claim automatic vessel responsibility

## How a new ChatGPT chat should continue

First read this file.

Then inspect the current repository state and tests.

Do not restart completed architecture or detector-training work.

The final YOLO26-S V2 detector is already selected and locally integrated. The real Sentinel-1 ship-detection/geolocation path is already verified.

The immediate engineering priority is now:
1. connect the verified SAR vessel coordinates and acquisition timestamp to an appropriate real AIS source;
2. validate candidate vessel correlation;
3. continue through trajectory/history and environmental evidence;
4. validate the complete incident package/dashboard/report flow;
5. only then consider RF corroboration using a real source;
6. finish production hardening and SIH PPT/demo validation.

Never invent missing data or integrations.
