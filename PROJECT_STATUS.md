# Indo Marine Watch — Project Status

**Updated:** 2026-09-10

## Executive status

The repository now has one canonical application entry point: `app.py`. The previous duplicate FastAPI applications and simulated/mock API adapters have been removed from the active branch.

The current system is an investigation-oriented pipeline, not an automatic attribution or dispatch system.

## Canonical pipeline

```text
SAR image / GeoTIFF
    -> U-Net slick segmentation
    -> explainable slick geometry classification
    -> YOLO physical-hull detection
    -> WGS84 geolocation when real raster metadata exists
    -> real AIS correlation / coverage assessment
    -> candidate ranking + vessel history + trajectory evidence
    -> environmental current/wind evidence
    -> backward drift source-zone estimate
    -> incident package / evidence matrix / timeline
    -> operator-reviewed report
    -> operator-reviewed Coast Guard response draft (never auto-sent)
```

## Evidence integrity

- No synthetic SAR result is used by the canonical API.
- No synthetic AIS/RF track is used by the canonical API.
- Missing AIS is represented as an unavailable/coverage state rather than a fabricated dark-vessel event.
- AIS gaps do **not** prove intentional shutdown, spoofing, or legal responsibility.
- RF corroboration is explicitly `NOT_IMPLEMENTED` until a real provider is connected.
- Environmental retrieval uses the Open-Meteo Marine + Forecast/Historical Forecast APIs when available.
- Drift output is labelled as estimated/modelled evidence and is not a legal attribution radius.
- Coast Guard response output is `DRAFT_REQUIRES_OPERATOR_CONFIRMATION` with transmission `NOT_SENT`.

## Component status

| Component | Status | Notes |
|---|---|---|
| SAR slick inference | READY | Real trained U-Net inference path; checkpoint required at runtime |
| Slick shape classifier | READY | Deterministic PCA/geometry classifier |
| Physical hull detection | READY | YOLO inference; no generic-model fallback |
| GeoTIFF geolocation | READY | Pixel-centre coordinates transformed to WGS84 |
| Plain-image geolocation | READY WITH LIMITATION | Requires explicit operator centre; marked estimated |
| AIS matcher | READY | Spatial + temporal matching against configured real records |
| AIS candidate ranking | READY | Transparent spatial/temporal/continuity/trajectory scoring |
| Vessel history | READY | Explicit continuity and gap states |
| Environmental provider | READY | Current/wind vectors + historical replay routing |
| Drift analysis | READY | Modelled backward source-zone estimate with assumptions |
| RF corroboration | NOT IMPLEMENTED | Honest capability boundary; no fabricated RF evidence |
| Incident report | READY | Deterministic report from canonical incident package |
| Coast Guard response | READY AS DRAFT | Operator confirmation required; no automatic transmission |
| Dashboard | READY FOR DEMO | Static dashboard wired to canonical incident state |
| CI contract suite | CONFIGURED | GitHub Actions runs the selected IMW contracts |

## AIS limitation

The checked-in MarineCadastre sample is real data but is not an Indian-water feed. It can validate matcher behaviour at scale, but it must not be presented as live Indian AIS coverage during the SIH pitch.

Global Fishing Watch remains a future provider integration until valid API access is available. The code must keep reporting unavailable coverage rather than substituting synthetic positions.

## Runtime prerequisites

Required model files:

```text
data/processed/best_unet.pt
runs/detect/sar_hull_detector/weights/best_unet.pt
```

Real AIS data, when used, is expected at the configured `AIS_CSV_PATH` location in `main/ais_matcher.py`.

## Repository cleanup completed

Removed from the active branch:

- duplicate root and nested FastAPI applications
- root simulated `models.py`, `physics.py`, and `sensor_fusion.py`
- obsolete simulated C2/database/traffic subsystem
- obsolete alternate integration/evaluator pipeline
- obsolete drift/environment loaders superseded by `environmental_provider.py`
- stale mock endpoint/core-engine tests
- temporary screenshots/test images
- empty root Copilot instructions
- generated legacy MSC Elsa evidence artifacts
- development file dump

The remaining `main/` modules are supporting components for the canonical pipeline or explicit validation/contract code.

## Next engineering priorities

1. Validate the current CI run and fix any dependency/runtime issues it exposes.
2. Test one real georeferenced Sentinel-1 scene end-to-end with the trained checkpoints.
3. Secure an appropriate Indian/global AIS source for the pitch, without fabricating coverage.
4. Curate the final SIH demonstration scenario and evidence trail.
5. Keep all attribution language at the level of evidence/candidate ranking until independently confirmed by an operator.
