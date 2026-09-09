# SIH26143 — Demo Frame Curation & Live Pitch Walkthrough
*Curated Demo Payload & Script for Hackathon Presentation*

---

## Executive Overview

This document contains the curated demo frames and the exact 60-90 second presentation walkthrough script for **SIH26143**. Each frame demonstrates the complete 4-stage pipeline execution: **SAR Slick Detection -> Hull Geolocation -> AIS Transponder Cross-Check -> Backward Drift Trajectory & Jurisdiction Routing**.

---

## Curated Demo Frames

### 🎬 Frame 1: `test_1` — Linear Slick & Unmatched Dark Vessel Suspect (Primary Demo Payload)

* **SAR Scene ID**: `test_1`
* **Stage 1 (Slick Segmentation)**:
  * **Slick Count**: 1 Slick Component
  * **Classification**: **Linear Slick** ($\text{PCA Elongation} > 3.0$). Indicates an active discharge from a vessel moving through open water.
  * **Centroid Coordinates**: $(20.8856^\circ\text{ N}, 69.1942^\circ\text{ E})$
* **Stage 2 (Hull Detection)**:
  * **Detected Hull**: Hull #0 (Bounding box `[260, 240, 300, 280]`, Confidence `0.91`)
  * **Geographic Position**: $20.826577^\circ\text{ N}, 69.226993^\circ\text{ E}$ (~6.5 km from slick centroid)
* **Stage 3 (AIS Cross-Check)**:
  * **Matched Records**: 0 AIS Broadcasts within 5.0 km / 2.0 hours (cross-checked against 7.33M real AIS records).
  * **Status**: **FLAGGED SUSPECT**
  * **Suspicion Score**: **`0.90`** (High Risk Dark Vessel)
  * **Alert Reason**: *"No AIS transponder broadcasts found within 2.0 hours of SAR detection time."*
* **Stage 4 (Drift & Jurisdiction)**:
  * **Backward Drift Origin (6.0h back)**: $(20.885638^\circ\text{ N}, 69.194261^\circ\text{ E})$
  * **Jurisdiction Zone**: `Indian EEZ (West Coast - ICG Regional HQ West / Gandhinagar & Mumbai)`
  * **Coastal Exclusion Zone (<500m)**: `False` (Open waters, 104 km offshore)

---

### 🎬 Frame 2: `test_2` — Parallel Linear Slick Tracks & Suspect Alert

* **SAR Scene ID**: `test_2`
* **Stage 1 (Slick Segmentation)**:
  * **Slick Count**: 2 Slick Components
  * **Classification**: **2 Linear Slicks** (Parallel discharge trajectory)
* **Stage 2 & 3 (Hull & AIS)**:
  * **Detected Hull**: Hull #0 at $(20.826577^\circ\text{ N}, 69.226993^\circ\text{ E})$
  * **AIS Match**: 0 Transponder Broadcasts matched $\rightarrow$ **Suspicion Score `0.90`**
* **Stage 4 (Drift & Zone)**:
  * **Origin Comp #1**: $(20.873851^\circ\text{ N}, 69.211155^\circ\text{ E})$
  * **Origin Comp #2**: $(20.869500^\circ\text{ N}, 69.196462^\circ\text{ E})$
  * **Jurisdiction**: `Indian EEZ (West Coast)`

---

### 🎬 Frame 3: `test_3` — Multi-Slick Cluster in High-Density Corridor

* **SAR Scene ID**: `test_3`
* **Stage 1 (Slick Segmentation)**:
  * **Slick Count**: 3 Slick Components (3 Linear Slicks)
* **Stage 2 & 3 (Hull & AIS)**:
  * **Detected Hull**: Hull #0 at $(20.826577^\circ\text{ N}, 69.226993^\circ\text{ E})$
  * **AIS Match**: Unmatched $\rightarrow$ **Suspicion Score `0.90`**
* **Stage 4 (Drift & Zone)**:
  * **Origin Comp #1**: $(20.885375^\circ\text{ N}, 69.211601^\circ\text{ E})$
  * **Origin Comp #2**: $(20.882657^\circ\text{ N}, 69.207715^\circ\text{ E})$
  * **Origin Comp #3**: $(20.865081^\circ\text{ N}, 69.202161^\circ\text{ E})$
  * **Jurisdiction**: `Indian EEZ (West Coast)`

---

## 🎙️ Live 60–90 Second Pitch Script

> **[0:00 - 0:15] The Problem & The Inversion**
> *"Judges, current oil spill detection tools like CleanSeaNet or Cerulean ask: 'Which AIS-broadcasting ship was near this slick?' But dark vessels intentionally turn AIS off to dump oil undetected. Our platform inverts that workflow. We don't rely on AIS to find the vessel — we detect physical hulls in SAR imagery independently, then use AIS only to confirm innocence."*

> **[0:15 - 0:45] Live Walkthrough on Frame `test_1`**
> *"Here is frame `test_1`. Stage 1 runs our U-Net model and PCA shape classifier — it detects a linear slick, meaning a moving vessel was actively discharging oil. Stage 2 scans the SAR scene for physical hulls and georeferences Hull #0 off the Gujarat coast. Stage 3 cross-checks Hull #0 against 7.3 million real AIS records. Zero transponder pings were found within 5km and 2 hours. That gives us a structural Dark Vessel Alert with a suspicion score of 0.90."*

> **[0:45 - 1:15] Stage 4 Drift & Jurisdiction Impact**
> *"Stage 4 takes live Open-Meteo ocean current and wind vectors and simulates backward drift using NOAA's 3% wind rule. It pinpoints the spill's origin 6 hours ago to $(20.8856^\circ\text{ N}, 69.1942^\circ\text{ E})$, inside the Indian EEZ under Coast Guard Regional HQ West jurisdiction. In under 15 seconds, enforcement agencies get actionable evidence on non-compliant vessels."*

