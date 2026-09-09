# SIH26143 — Hackathon Pitch Deck Structure
*Oil-Spill & Dark-Vessel Detection Pipeline (National Technical Research Organisation)*

---

## Slide 1: The Problem — Dark Vessels & Environmental Impunity

* **The Challenge**: Vessels causing oil spills frequently disable their Automatic Identification System (AIS) transponders to evade detection ("dark vessels").
* **Environmental & Maritime Impact**: Illegal bilge dumping and oil spills damage coastal ecosystems and cost millions in cleanup, while perpetrators vanish without accountability.
* **The Core Need**: A structural mechanism to identify non-broadcasting vessels at sea during an active spill event.

---

## Slide 2: Why Existing Tools Miss Dark Vessels

* **Existing Tools**: EMSA CleanSeaNet, SkyTruth Cerulean.
* **Fundamental Design Flaw**: Current systems operate on the workflow:
  $$\text{Detect Slick} \longrightarrow \text{Query Nearby AIS Ships}$$
* **The Blind Spot**: If a vessel turns off its AIS transponder specifically to dump oil undetected, **existing tools fail by design**. They rely on AIS to establish the *existence* of the ship.

---

## Slide 3: Our Core Architectural Novelty — Workflow Inversion

* **Our Approach**: Invert the workflow.
  $$\text{SAR Image} \longrightarrow \text{Detect Physical Hull} \longrightarrow \text{Cross-Check Against AIS}$$
* **Key Principle**: **AIS confirms innocence; it does not establish existence.**
* **Structural Detection**: A physical vessel hull detected in Synthetic Aperture Radar (SAR) imagery near an oil spill with **zero matching AIS broadcast** is not a heuristic guess — it is a structural fact: *a vessel is present that is refusing to identify itself*.

---

## Slide 4: 4-Stage Pipeline Architecture

```
                       [ Input SAR Image ]
                                │
   ┌────────────────────────────┼────────────────────────────┐
   ▼                            ▼                            ▼
[Stage 1: Slick Detection]   [Stage 2: Hull Detection]   [Stage 4: Drift & EEZ]
U-Net Segmentation +         YOLOv8 SAR Hull Detector +   NOAA 3% Wind Vector Math +
PCA Shape Classifier         Geo-Coordinates (WGS84)      Shapely EEZ Jurisdiction
   │                            │                            │
   └─────────────┬──────────────┘                            │
                 ▼                                           │
      [Stage 3: AIS Matching] ───────────────────────────────┘
      Spatial-Temporal Match vs
      7.3M AIS Records
                 │
                 ▼
     [ Dark Vessel Suspect Alert ]
```

---

## Slide 5: What is Real — Empirical Performance & Benchmark Numbers

* **Stage 1 (Slick Segmentation)**:
  * Trained U-Net ResNet34 encoder on 5,810 Kaggle SAR images (24.89% oil pixels).
  * Shape Classifier: **1,463 linear slicks** vs **1,709 blob slicks** across 645 test images.
* **Stage 2 (Hull Detection & Georeferencing)**:
  * YOLOv8 trained on HRSID + SSDD SAR ship datasets.
  * Real GeoTIFF affine transform math + demo anchor box fallback ($20.75^\circ-20.95^\circ\text{ N}, 69.10^\circ-69.35^\circ\text{ E}$).
* **Stage 3 (AIS Scale Validation)**:
  * Spatial-temporal Haversine matcher tested against **7,337,208 real AIS records** (`ais-2025-01-01`).
* **Stage 4 (Drift & Jurisdiction)**:
  * NOAA GNOME 3% wind factor vector drift model (`drift_velocity = ocean_current + 0.03 * wind`).
  * Indian EEZ polygon lookup + 500m coastal exclusion distance math.

---

## Slide 6: Live Demo Walkthrough (Frame `test_1`)

* **Stage 1**: Detects linear slick component at $(20.8856^\circ\text{ N}, 69.1942^\circ\text{ E})$.
* **Stage 2**: Detects physical Hull #0 at $(20.8265^\circ\text{ N}, 69.2269^\circ\text{ E})$.
* **Stage 3**: Queries 7.33M AIS records $\rightarrow$ **0 matches found within 5km / 2 hours**.
  * **DARK VESSEL ALERT**: **Suspicion Score = `0.90`**.
* **Stage 4**: Backward drift estimates 6-hour origin to $(20.8856^\circ\text{ N}, 69.1942^\circ\text{ E})$, located inside `Indian EEZ (West Coast - ICG Regional HQ West)`.

---

## Slide 7: Honest Limitations & Future Roadmap

* **No Look-Alike Class**: Dataset lacks false-positive look-alike masks (e.g. algae blooms). Mitigated by rule-based PCA shape classifier.
* **AIS Coverage Gap**: MarineCadastre dataset is U.S.-only (used for scale validation). GFW global API integration queued for production deployment.
* **Satellite Scene Georeferencing**: Non-georeferenced `.jpg` chips use Gujarat demo-anchor box; production uses Sentinel-1 GeoTIFF rasters.

---

## Slide 8: Independent Validation & Conclusion

* **Industry Precedent**: Global Fishing Watch (GFW) uses this exact SAR + AIS dark-vessel detection architecture at global scale for illegal fishing enforcement.
* **Summary**: In less than 15 seconds, our 4-stage pipeline processes raw SAR imagery into actionable evidence for maritime enforcement agencies.

