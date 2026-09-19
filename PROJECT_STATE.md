# Indo Marine Watch (IMW) — Project State / Handoff

Last updated: 2026-09-19

## Project
- SIH 2026 Problem Statement: SIH26143
- Project: Indo Marine Watch (IMW)
- Repository: VISSHAL-ANAND/SIH
- Goal: Sentinel-1 SAR oil-spill detection + physical vessel detection + AIS correlation + trajectory/gap analysis + drift reconstruction + evidence fusion for operator-reviewed vessel investigation.

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
- SAR acquisition timestamp parsing/hardening
- U-Net oil-slick segmentation pipeline
- PCA/elongation slick shape classification
- SAR physical ship detection with a verified one-class ship checkpoint
- 1-band Sentinel-1 TIFF handling for ship detection
- Global NMS and SAR ship geolocation
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
- Test suite reached 105 passing tests with 6 warnings
- Real Sentinel-1 SAFE geolocation was successfully verified from annotation XML
- Random real Sentinel-1 scene validation produced no slicks and should remain a no-oil result; do not tune the system to force a detection.

## Ship-model training status
The original YOLO checkpoint was an early SAR ship model:
- reconstructed checkpoint: best_reconstructed.pt
- one class: ship
- epoch 4 of 100 at checkpoint time
- benchmark on 25 OSSDD test chips:
  Precision 0.750
  Recall 0.203
  TP 36 / FP 12 / FN 141
Conclusion: insufficient recall for final IMW deployment.

A new training path was started:
- Dataset: OSSDD / OpenSARShip on Hugging Face
- Model: YOLO26-S
- Smoke dataset: 500 train / 100 validation images
- img size: 800
- planned training: 150 epochs, patience 30
- smoke run reached 55 epochs and early-stopped
- best epoch: 25
- smoke validation:
  Precision 0.658
  Recall 0.516
  mAP50 0.517
  mAP50-95 0.199
These smoke metrics are NOT final model metrics because only 500/100 images were used.

IMPORTANT CURRENT TRAINING STATE:
- The Colab runtime reset and the smoke-test checkpoint was NOT found in Google Drive.
- Therefore the smoke checkpoint is presumed lost.
- Before retraining, use Google Drive-backed persistent paths for repository/training outputs/checkpoints.
- Never rely on /content alone for long training.

## Current next training plan
1. Start clean Colab T4 runtime.
2. Mount Google Drive.
3. Keep repo and training outputs under /content/drive/MyDrive/IMW_training/.
4. Install/verify ultralytics, webdataset, huggingface_hub, rasterio, pillow.
5. Reclone VISSHAL-ANAND/SIH into persistent Drive storage if needed.
6. Recreate 500/100 smoke dataset.
7. Run YOLO26-S smoke training with checkpoints saved directly to Drive.
8. Verify best.pt and last.pt exist on Drive.
9. Only after the pipeline is persistent, prepare the full OSSDD train/validation dataset.
10. Train the full SAR ship detector.
11. Benchmark on the same 25-chip OSSDD test protocol.
12. Compare against the existing early checkpoint.
13. Test the resulting detector on the user's real Sentinel-1 GRD SAFE.
14. Validate detection quality visually and quantitatively before deployment.

## RF module — PLANNED, NOT IMPLEMENTED
RF is intended as an additional corroboration layer, not a fabricated source of vessel tracks.

Planned role:
- SAR detects physical vessels.
- AIS reports vessel identity/track.
- RF can provide an independent radio-frequency corroboration signal when a real RF provider/receiver dataset is available.
- RF should help identify whether a radio emitter/track is spatially and temporally compatible with a SAR/AIS candidate.
- RF must remain NOT_IMPLEMENTED / UNAVAILABLE until a real RF source is connected.
- Never fabricate RF detections, RF tracks, emitter identity, or RF-to-vessel attribution.
- RF evidence should enter evidence fusion only when real observations exist.

## Evidence / responsibility rules
- AIS gap != proof of intentional AIS shutdown
- AIS gap != proof of wrongdoing
- Drift source zone is estimated/modelled, not a legal attribution radius
- Evidence ranking identifies investigation candidates, not legal responsibility
- responsibility status must remain NOT_ESTABLISHED unless independently established outside the system
- machine_generated = true
- legal_responsibility_established = false
- Coast Guard response must be DRAFT_REQUIRES_OPERATOR_CONFIRMATION
- transmission status must remain NOT_SENT unless an authorized operator actually sends it.

## PPT technical-approach accuracy
The PPT currently shows:
SAR evidence + AIS evidence + movement evidence + correlation logic + evidence fusion.
It also visually mentions RF.

RF should be labelled as:
PLANNED / OPTIONAL CORROBORATION
until the real RF source and integration are implemented.

Do not claim:
- live RF tracking
- live RF vessel identification
- real RF correlation
- automatic vessel responsibility
unless the corresponding real integration has been completed and tested.

## Remaining work to finish IMW
A. Ship detector
- persistent full OSSDD training
- full test benchmark
- real Sentinel-1 validation
- tune only using justified validation evidence
- select final checkpoint

B. RF
- define real RF data source/provider/receiver
- define RF observation schema and time/location accuracy
- implement RF ingestion
- implement RF-to-candidate correlation
- add RF evidence to fusion only when observed
- add tests and UI status

C. AIS / environmental production integration
- verify the intended Indian-water AIS provider and access
- connect real environmental wind/current provider
- retain replay/local fallbacks only as clearly labelled test/replay modes

D. End-to-end production hardening
- real-data API integration
- persistence/database
- authentication/authorization
- audit logging
- deployment
- performance optimization
- final end-to-end tests

E. SIH presentation
- align PPT wording with actual implementation status
- distinguish REAL DATA, UNAVAILABLE, NOT_IMPLEMENTED, and ESTIMATED
- show the independent SAR vessel detector + AIS correlation + drift + evidence fusion as the core novelty
- mention RF as planned corroboration unless implemented before final presentation

## How a new ChatGPT chat should continue
First read this file.
Then inspect the current repository state and tests.
Do not restart completed architecture work.
Do not invent missing integrations.
The immediate engineering priority is persistent YOLO26-S SAR ship-detector training, followed by full OSSDD evaluation and real Sentinel-1 validation.
After that, implement the RF corroboration layer using a real data source, then production hardening and final SIH PPT/demo validation.
