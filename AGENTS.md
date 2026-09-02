# AGENTS.md — SIH26143 Project Knowledge Base
*Last synced: 2026-09-01. This is the single source of truth for any AI agent (Codex, Copilot, Antigravity/Gemini) working on this repo. Read this file fully before touching any code. Do not explore other files "to understand context" unless this file tells you to — everything you need is here.*

---

## 0. HOW AGENTS SHOULD USE THIS FILE

- **Codex**: read this file first, execute exactly ONE task from `## TASK QUEUE` per session unless told otherwise. Do not re-architect anything marked `REAL` or `DO NOT TOUCH`. Do not "helpfully" fix placeholders that are explicitly marked intentional.
- **Copilot**: use this as background context via `.github/copilot-instructions.md` (copy of this file). Passive autocomplete only — don't let it silently rewrite placeholder logic.
- **Antigravity / Gemini**: use for planning, debugging discussion, and updating this file itself when status changes. This is the tool that should *edit* this document as the ground truth shifts.
- **Golden rule**: if you (agent) are unsure whether something is a bug or intentional, check `## KNOWN PITFALLS (INTENTIONAL — DO NOT "FIX")` before touching it.

---

## 1. PROJECT OVERVIEW

**Project**: SIH26143 — Oil-spill / dark-vessel detection pipeline (Smart India Hackathon).

**Problem**: Vessels that cause oil spills often turn off AIS (Automatic Identification System) to evade detection ("dark vessels"). Existing tools (Cerulean, CleanSeaNet) rely on AIS broadcast to identify the responsible ship — if AIS is off, they can't find it.

**Our core architectural novelty**: Invert the traditional workflow. Don't rely on AIS to find the vessel. Detect every physical vessel hull in the SAR image independently (a separate computer-vision task from slick detection), then cross-check each hull against AIS. AIS confirms *innocence*; it does not establish *existence*. A hull detected near a spill with no matching AIS broadcast is structurally flagged as a dark-vessel suspect.

**Deadline**: Portal submission September 20 (as of Sept 1, ~3 weeks of runway).

**Repo root**: `A:\SIH` (Windows machine).

---

## 2. ARCHITECTURE — 4-STAGE PIPELINE

```
Stage 1: Slick Detection    →  Stage 2: Hull Detection  →  Stage 3: AIS Matching  →  Stage 4: Drift + Jurisdiction
(sih26143_slick_detection)     (sih26143_ship_detection)    (sih26143_ais_matching)   (sih26143_integration)
```

All four stages are wired together in `sih26143_integration/integration_pipeline.py`.

### Module ownership (for honesty in pitch — know who can speak to what)
| Module | Owner | Status |
|---|---|---|
| `sih26143_slick_detection/` | trained by VISSHAL | REAL |
| `sih26143_ship_detection/` | RINOSH | REAL |
| `sih26143_ais_matching/` | you | REAL (data source still being decided) |
| `sih26143_integration/` | absorbed by you from RATHIMEENA (stalled) | REAL except jurisdiction routing |
| Drift simulation | SIMI's track — **status unconfirmed, needs a decision today** | MOCKED |
| Dashboard | SYLVI's track — **status unconfirmed** | NOT BUILT |
| Demo frame curation | originally RATHIMEENA, still open | NOT STARTED |
| Pitch deck | nobody yet | NOT STARTED |

⚠️ Pattern to watch: multiple tracks (integration, AIS, drift, dashboard) have stalled and been silently absorbed by one person. Don't assume a track marked with an owner name is actually being worked on — verify status before depending on it.

---

## 3. WHAT'S REAL vs PLACEHOLDER (ground truth — check before editing)

### `sih26143_slick_detection/` — REAL
| File | What it does | Verified numbers (last known) |
|---|---|---|
| `preprocess.py` | Prepares dataset | 5,810 / 1,615 / 645 split, 24.89% oil pixels |
| `train_unet.py` | Trains U-Net | Checkpoint: `data/processed/best_unet.pt` |
| `shape_classifier.py` | Classifies slick shape (linear vs blob) | Has 3 self-tests, run standalone: `python shape_classifier.py` |
| `predict_and_classify.py` | Runs inference + classification | Last known: 1,463 linear / 1,709 blob |

### `sih26143_ship_detection/` — REAL (RINOSH's)
| File | What it does | Notes |
|---|---|---|
| `ship_detection_module.py` | YOLOv8 hull detector | Trained weights at `runs/detect/sar_hull_detector/weights/best_unet.pt` — **missing on demo machine filesystem; currently falls back to `yolov8n.pt` (0 hulls detected)** |
| `test_geo_conversion.py` | Self-test for pixel→geo conversion | Should print "All geo-conversion tests passed." |
| `evaluate_by_size.py` | Recall by object size | Run once for pitch numbers ("we found X, so we tuned Y") |

### `sih26143_ais_matching/` — REAL logic, data source in flux
| File | What it does | Notes |
|---|---|---|
| `ais_matcher.py` | Matches detected hulls against AIS broadcasts | Uses relative `AIS_CSV_PATH`. MarineCadastre dataset is U.S.-only (zero Indian ocean coverage) — see Pitfall 5. |
| `gfw_ais_loader.py` | Global Fishing Watch API loader | Mid-fix — 403 permission wall on Vessel Presence dataset; GFW SAR Vessel Detections API tested as alternative. |

### `sih26143_integration/` — REAL (4-stage pipeline wired)
| File | What it does | Notes |
|---|---|---|
| `pipeline_contracts.py` | Shared data contracts (`HullDetection`, `AISMatch`, `DriftResult`) | Shared schema across all 4 stages. |
| `integration_pipeline.py` | Wires slick → hull → AIS → drift → jurisdiction | Real end-to-end execution. Timestamps normalized to avoid tz-aware/naive pandas mismatch. Note: previously hit a silent network block (`ConnectionResetError 10054`) fallback, now verified clean when online. |
| `geolocation.py` | Converts pixel coords to lat/lon | REAL when georeferenced; falls back to Gujarat demo-anchor box (lat 20.75–20.95, lon 69.10–69.35) for plain `.jpg` chips. |

### Stage 4 (Drift + Jurisdiction) — REAL (vector math) / PARAMETERIZED (`hours_back`)
- `jurisdiction_lookup.py`: REAL using `shapely` + `geopandas` for Indian EEZ polygon matching (West Coast, East Coast, A&N) and 500m coastal exclusion distance math.
- `DriftResult.jurisdiction_zone` & `DriftResult.within_500m_exclusion` populated dynamically on full pipeline outputs.
- Backward drift simulation (`drift_simulation.py` + `ocean_wind_loader.py`): REAL vector current + wind drift math using NOAA GNOME 3% wind factor rule (`drift_velocity = ocean_current + 0.03 * wind`). Origin lat/lon and distance vary dynamically with weather and centroid inputs.
- `hours_back`: FIXED SIMULATION PARAMETER (defaults to `6.0` hours window in `simulate_backward_drift`), not dynamically calculated from satellite images.

---

## 4. KNOWN PITFALLS (INTENTIONAL — DO NOT "FIX")

An agent seeing these patterns should **not** treat them as bugs to silently patch:

1. **Geolocation fallback returns a labeled mock anchor box** when the SAR image has no georeferencing transform. This is a disclosed approximation, not a bug — our current demo/test images (plain `.jpg`, no geo metadata) will *legitimately* always hit this path. Only a real georeferenced Sentinel-1 GeoTIFF would return genuinely real coordinates.
2. **`ais_matcher.py`'s data source varies by run** (GFW vs MarineCadastre) depending on what's currently accessible — this is a known, temporary state, not a config error.
3. **Drift fallback when offline** — if Open-Meteo network request fails, pipeline logs a warning and falls back gracefully without crashing.
4. **Timezone timestamp mismatch (timezone-naive vs aware bug)**: RINOSH's hull detector outputs ISO strings with timezone offset (`+00:00`/`Z`), while raw AIS CSV timestamps are timezone-naive. `pandas` throws `TypeError` when comparing aware vs naive datetimes — `integration_pipeline.py` explicitly strips `tzinfo` (`.replace(tzinfo=None)`) before time-window filtering. Do not re-introduce timezone-aware datetimes into raw pandas comparisons.
5. **MarineCadastre zero Indian ocean coverage gap**: MarineCadastre dataset only covers U.S. coastal waters (first real record is near Puerto Rico). Running AIS matcher against MarineCadastre on Gujarat demo anchor box will cause every single hull to flag as a "suspect" — this is a dataset coverage limitation, not a pipeline bug. Always disclose this coverage gap during MarineCadastre-framed demos.
6. **Windows PyTorch CUDA vs CPU installation trap**: On Windows, `pip install torch` defaults to CPU-only build unless explicitly installing from the CUDA wheel index (`--index-url https://download.pytorch.org/whl/cu121`).

---

## 5. HARD DECISIONS ALREADY MADE (don't relitigate these)

- **Jurisdiction zones**: use free public data — Marine Regions (EEZ boundaries) + Natural Earth (coastline), via `shapely` + `geopandas`. No paid API, no ICG-specific data source (not realistically available).
- **AIS data source**: try `fetch_sar_vessel_detections()` (GFW) first; if it 403s, time-box troubleshooting to **30 minutes max**, then fall back to the MarineCadastre-validated framing. This integration is a nice-to-have upgrade, not a blocker — the matcher's logic is already proven.
- **Drift simulation fallback**: if SIMI's track is confirmed stalled, the acceptable fallback is a **simplified straight-line backward projection** using average current speed/direction for the region — NOT a full physics simulation. A full sim is not required for a defensible hackathon demo. If even that isn't feasible in time, cut it from the *live* demo and present it as "designed but not implemented — here's the approach" with a diagram.
- **Dashboard fallback**: does not need to be polished. Minimum viable = one static map image (slick + detected hull + red flag on unmatched hull) plus one simple table (hull ID, matched Y/N, suspicion score). Don't let "no dashboard" block anything.
- **RF geolocation (HawkEye 360) was considered and rejected** — access requires an institutional relationship not available to the team. Have this explanation ready for judges.
- **No "look-alike" class in training data** (things that look like oil slicks but aren't, e.g. algae blooms) — mitigated (not solved) by the shape classifier. State this honestly in limitations, don't overclaim.

---

## 6. TASK QUEUE — WORK IN THIS ORDER

Each phase assumes the previous is fully done, not just started. Do not skip ahead (e.g. don't build jurisdiction routing before confirming the pipeline runs clean — that's debugging two unknowns at once).

### PHASE 0 — File Review & Repo-wide Bug Sweep (~1-2 hrs, do first)
- [ ] From `A:\SIH`, run: `Select-String -Path *.py -Pattern "sih26143_|\.\./"` — catch leftover nested-folder-style imports/paths (already found and fixed one in `integration_pipeline.py`; there may be more).
- [ ] Verify every `import`/`from X import Y` resolves to a file that actually exists (case-sensitive).
- [ ] List every hardcoded file path (e.g. `ais_matcher.py`'s `AIS_CSV_PATH`) — flag which need to become relative.
- [ ] Confirm `data/processed/`, `sar_ships/`, `AIS_CSV_PATH/` actually contain the expected files (checkpoints, datasets) — not just that code references them correctly.
- [ ] Re-run and verify each file in the table in Section 3 matches its documented state (self-tests pass, numbers match, checkpoints exist and are recent).
- [ ] Update the task tracker (Notion) so ownership reflects who *actually* built/is maintaining each absorbed track (VISSHAL absorbed ASHMIL's + RATHIMEENA's integration tasks) — not for bookkeeping's sake, but because whoever presents needs to honestly know what they can speak to.
- **Done when**: written list of every remaining path/import issue exists, even unfixed ones.

### PHASE 1 — AIS Data Source Decision (time-boxed, ≤30 min beyond the try)
- [ ] Run `ais_matcher.py` with `fetch_sar_vessel_detections()` (GFW) as the data source.
- [ ] If it 403s: send GFW access-request email (don't block on a reply).
- [ ] Hard stop at 30 minutes — if not working, switch to MarineCadastre-validated framing and move on. Do not let this eat more time.

### PHASE 2 — Drift Simulation Decision (get a real answer TODAY, don't let it slide)
- [ ] Confirm whether SIMI's track is active or stalled.
- [ ] If active: she finishes backward drift sim using her pulled NOAA HYCOM/GFS data, plus wires jurisdiction routing for real.
- [ ] If stalled: decide between (a) you build the simplified straight-line backward-projection version, or (b) cut from live demo, present as "designed, not implemented" with a diagram.

### PHASE 3 — Get Pipeline Running Clean End-to-End
- [ ] Re-run `python integration_pipeline.py`, read full output (not just last line).
- [ ] If it errors: paste full traceback and fix (same process as prior 3 fixes: case mismatch, missing file, stale path).
- [ ] Confirm sane, non-zero suspect counts on test images — a pipeline that always prints 0 suspects needs investigation, not acceptance.
- [ ] Confirm Stage 4 hits the REAL Open-Meteo path (no `[warning] ocean/wind fetch failed` line repeating every run) — if it does, that's a local network/firewall issue to fix, not a state to leave.
- **Done when**: runs on all 5 test images with real (non-mocked, except drift-pending) output at every stage, and the numbers are understood, not just observed.

### PHASE 4 — Fix Known Rough Edges
- [ ] Change `ais_matcher.py`'s `AIS_CSV_PATH` from hardcoded absolute path to relative (e.g. `Path("AIS_CSV_PATH") / "ais-2025-01-01"`).
- [ ] Delete stale `__pycache__` (has leftover bytecode from removed `gfw_ais_loader` module state, if not already cleaned).
- [ ] Consolidate `.venv`, `.venv-1`, `.venv-2` into ONE canonical env; document install steps in README; delete the other two.
- **Done when**: a teammate who's never touched the repo can clone it, follow the README install steps, and run `integration_pipeline.py` with zero path edits.

### PHASE 5 — Build Jurisdiction / ICG-Zone Routing (the one real missing feature, ~1-2 sessions)
- [ ] Download India EEZ boundary data from Marine Regions (marineregions.org — free, shapefile/GeoJSON).
- [ ] Download coastline data from Natural Earth (free) for 500m-exclusion-zone distance calc.
- [ ] `pip install shapely geopandas` (no API keys needed).
- [ ] Write `jurisdiction_lookup.py`:
  ```python
  import geopandas as gpd
  from shapely.geometry import Point

  def load_zones(geojson_path: str) -> gpd.GeoDataFrame:
      return gpd.read_file(geojson_path)

  def find_zone(lat: float, lon: float, zones: gpd.GeoDataFrame) -> str:
      point = Point(lon, lat)  # shapely wants (x=lon, y=lat)
      for _, zone in zones.iterrows():
          if zone.geometry.contains(point):
              return zone["zone_name"]
      return "outside all known zones"

  def distance_to_coastline_m(lat: float, lon: float, coastline: gpd.GeoDataFrame) -> float:
      point = Point(lon, lat)
      # project to a metric CRS first (e.g. EPSG:32644 for this region)
      # before measuring distance in meters, not degrees
      ...
  ```
- [ ] Wire into `integration_pipeline.py` Stage 4 — replace:
  ```python
  jurisdiction_zone="[NOT BUILT -- ICG-zone routing pending]",
  within_500m_exclusion=False,
  ```
  with real `find_zone()` / `distance_to_coastline_m() < 500` calls.
- [ ] Self-test with one known point clearly inside a zone and one clearly outside before trusting on real data.
- **Done when**: `DriftResult` shows a real zone name and real true/false exclusion flag on actual pipeline output.

### PHASE 6 — Full Pipeline Integration (once drift is real or deliberately cut)
- [ ] Wire real/simplified drift sim into `integration_pipeline.py`, replacing the mock (same swap pattern as hull detection and AIS matching).
- [ ] Run full 4-stage pipeline end to end on real test images.
- [ ] Pick one image, manually verify every number in the chain (slick → hull → AIS → origin point) is sane — this is your dry run for the pitch walkthrough.

### PHASE 7 — Swap in Real Data
- [ ] Download a real day of AIS data from MarineCadastre for your demo region/date; point `AIS_CSV_PATH` at it; use `ais_matcher.load_ais_data()` instead of `generate_synthetic_ais()`.
- [ ] (If time allows) get one real georeferenced Sentinel-1 GeoTIFF from Copernicus for the demo region/date; run through full pipeline; confirm hull/slick lat/lon comes back genuinely real (not the demo-anchor fallback).
- **Done when**: at least one full run uses real AIS + ideally one real georeferenced SAR scene.

### PHASE 8 — Validate Against a Real Incident
- [ ] Find a publicly reported real oil-spill incident (known date/location, ideally named vessel) via NOAA ERMA or news coverage.
- [ ] Run pipeline against SAR imagery from that date/location.
- [ ] Check: spill flagged in right place? Drift origin near real vessel's likely position? AIS matching correct?
- [ ] Write up honestly, including mismatches — a partial match with honest analysis beats an unvalidated "trust us."
- **Done when**: one written case study comparing pipeline output to real-world ground truth exists.

### PHASE 9 — Dashboard (minimum viable if behind)
- [ ] If SYLVI's track is behind: build the minimum viable version — one static map image (slick + hull + red flag on unmatched) + one simple table (hull ID, matched Y/N, suspicion score). Nothing more is required.

### PHASE 10 — Demo Frame Curation
- [ ] Run full pipeline across all 645 test images.
- [ ] Pick 2-3 frames with the clearest story: visibly linear slick, detected hull nearby, hull unmatched.
- [ ] Script the exact 60-90 second walkthrough: *"Here's the slick. Here's the shape — linear, so likely a moving vessel. Here's the hull our detector found nearby. Here's the AIS check — no broadcast found within our tolerance. That's our suspect."*
- [ ] Rehearse at least twice before the actual pitch.

### PHASE 11 — Pitch Deck
Structure:
1. Problem — dark vessels evading detection during oil spills.
2. Why existing tools miss this — Cerulean/CleanSeaNet rely on AIS; if AIS is off, they can't find the ship.
3. Our approach — detect hulls independently of AIS; AIS only rules out innocent ships.
4. Architecture diagram — the 4-stage pipeline.
5. What's real — be specific: trained model, real numbers (1,463/1,709 linear/blob split), validated against real AIS records.
6. Live demo — the curated walkthrough from Phase 10.
7. Honest limitations / future work — no look-alike class (mitigated not solved), AIS data source status, drift simulation status (real or designed-not-built).
8. Validation — cite Global Fishing Watch's own SAR+AIS dark-vessel detection at global scale as independent proof the approach works.

### PHASE 12 — Rehearsal & Final Polish
- [ ] Full team run-through at least twice with the actual demo, not a description of it.
- [ ] Confirm every presenting team member can actually speak to their assigned part — don't let it silently become a one-person show.
- [ ] Prepare a tight answer for: "How do you get lat/lon on non-georeferenced images?" (the demo-anchor explanation).
- [ ] Prepare a tight answer for: "Why not RF geolocation?" (HawkEye 360 institutional-access explanation).
- [ ] Full timed dry-run before the actual presentation.

---

## 7. QUICK REFERENCE — PHASE DEPENDENCY ORDER

```
Phase 0  → repo-wide review, find remaining path/import bugs
Phase 1  → AIS data source decision (time-boxed)
Phase 2  → drift simulation decision (today, not another stalled day)
Phase 3  → confirm pipeline runs clean end-to-end
Phase 4  → fix hardcoded paths, duplicate venvs
Phase 5  → build jurisdiction/ICG-zone routing (the one real gap)
Phase 6  → full integration once drift resolved
Phase 7  → swap in real AIS + ideally real SAR data
Phase 8  → validate against a real incident
Phase 9  → dashboard (parallel-safe with 10 & 11)
Phase 10 → demo frame curation (parallel-safe with 9 & 11)
Phase 11 → pitch deck (parallel-safe with 9 & 10)
Phase 12 → rehearsal, last
```

Phases 9, 10, 11 can run in parallel if team bandwidth allows — they don't depend on each other. Everything before Phase 9 is sequential.

---

## 8. RISK NOTE FOR WHOEVER IS DIRECTING AGENTS

The biggest risk to this plan is not technical difficulty — it's the same silent-stall pattern that already hit integration and AIS matching happening again on drift (Phase 2), dashboard (Phase 9), demo curation (Phase 10), or pitch deck (Phase 11). Before starting Phase 2, get an honest, explicit status from SIMI and SYLVI's tracks rather than assuming "assigned" means "in progress."

---

## 9. CHANGELOG (Antigravity/Gemini updates this section when status changes)

- 2026-09-02: Hull Detector Re-verification Audit: Re-ran `integration_pipeline.py` on all 5 test images. Confirmed `[warning] Trained weights ... best_unet.pt not found locally` persists because `runs/detect/sar_hull_detector/weights/best_unet.pt` does not exist on disk. Recorded actual hull counts: `test_0`: 0 hulls, `test_1`: 0 hulls, `test_2`: 0 hulls, `test_3`: 0 hulls, `test_4`: 0 hulls (0 total hulls detected due to `yolov8n.pt` COCO fallback).
- 2026-09-02: Pipeline Audit & Network Verification: Re-ran full pipeline on all 5 test images. Confirmed live Open-Meteo ocean/wind fetch executed with 0 warnings. Disclosed that previous "REAL end-to-end" claim ran on silent fallback due to local network socket block (`ConnectionResetError 10054`), demonstrating that the offline fallback mechanism works as designed. Noted hull detector status: trained weights file `runs/detect/sar_hull_detector/weights/best_unet.pt` is missing on demo machine filesystem, forcing pipeline to use `yolov8n.pt` COCO fallback (detecting 0 hulls on SAR chips).
- 2026-09-02: Drift Simulation Audit & Verification: Verified `drift_simulation.py` vector current/wind physics math (`simulate_backward_drift()`) is REAL and varies dynamically with weather & centroid inputs. Clarified that `hours_back` is a FIXED SIMULATION PARAMETER (default 6.0 hours).
- 2026-09-01: Initial knowledge file compiled from PROJECT_STATUS.md + execution plan roadmap.
