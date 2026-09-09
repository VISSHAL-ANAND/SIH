"""
Indo Marine Watch (IMW) — Endpoint Verification Suite
=====================================================
Tests:
  1. POST /api/process-sar     — SAR upload returns spill, hull, drift
  2. POST /api/analyze-traffic — AIS correlation, dark vessel flagging, RF lock
  3. POST /api/dispatch-alert  — GMDSS Coast Guard dossier with HMAC
  4. GET  /                    — Frontend HTML served
  5. POST /api/analyze-incident — Regression (legacy endpoint still works)
"""

import io
import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app import app
from fastapi.testclient import TestClient


class TestIMWEndpoints(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    # ----------------------------------------------------------------
    # 1. SAR Processing
    # ----------------------------------------------------------------
    def test_01_process_sar(self):
        """POST /api/process-sar returns spill area, hull coords, drift origin."""
        fake_image = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        resp = self.client.post(
            "/api/process-sar",
            files={"file": ("test_chip.png", fake_image, "image/png")},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["status"], "success")
        self.assertIn("incident_id", data)
        self.assertTrue(data["incident_id"].startswith("IMW-"))

        # Coordinates
        self.assertIn("coordinates", data)
        self.assertIn("center_lat", data["coordinates"])
        self.assertIn("bbox", data["coordinates"])

        # Spill
        self.assertEqual(data["spill"]["area_sq_m"], 100000.0)
        self.assertEqual(data["spill"]["shape_classification"]["shape_class"], "linear")

        # Hull
        self.assertTrue(data["hull"]["detected"])
        self.assertEqual(len(data["hull"]["coordinates"]), 2)

        # Drift
        self.assertGreater(data["drift"]["drift_distance_km"], 0.0)
        self.assertIn("origin_coordinates", data["drift"])

        print(f"[Test 01 PASSED] /api/process-sar — Incident: {data['incident_id']}, "
              f"Spill: {data['spill']['area_sq_m']} m², Hull: {data['hull']['coordinates']}")

    # ----------------------------------------------------------------
    # 2. Traffic Analysis
    # ----------------------------------------------------------------
    def test_02_analyze_traffic(self):
        """POST /api/analyze-traffic returns AIS track, blackout point, RF lock."""
        resp = self.client.post("/api/analyze-traffic", json={
            "slick_lat": 9.3764,
            "slick_lon": 75.9758,
            "hull_lat": 9.4200,
            "hull_lon": 76.0200,
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["status"], "success")
        self.assertEqual(data["ais_status"], "INACTIVE / UNMATCHED")
        self.assertTrue(data["is_dark_vessel"])

        # AIS track
        self.assertIsInstance(data["ais_track"], list)
        self.assertGreater(len(data["ais_track"]), 0)
        self.assertIn("sog", data["ais_track"][0])

        # Blackout point
        bp = data["ais_blackout_point"]
        self.assertIsNotNone(bp)
        self.assertEqual(bp["event"], "AIS_DISABLED")

        # RF intercept
        self.assertTrue(data["rf_intercept"]["match"])
        self.assertEqual(data["rf_intercept"]["signature"], "HawkEye 360 X-Band Marine Radar Emitter")

        # Suspect vessel
        self.assertEqual(data["suspect_vessel"]["threat_score"], 0.90)

        print(f"[Test 02 PASSED] /api/analyze-traffic — AIS track: {len(data['ais_track'])} pts, "
              f"Blackout: {bp['lat']},{bp['lon']}, Threat: {data['suspect_vessel']['threat_score']}")

    # ----------------------------------------------------------------
    # 3. Dispatch Alert
    # ----------------------------------------------------------------
    def test_03_dispatch_alert(self):
        """POST /api/dispatch-alert returns GMDSS dossier with HMAC digest."""
        resp = self.client.post("/api/dispatch-alert", json={
            "incident_id": "IMW-TEST0001-2026",
            "slick_centroid": [9.3764, 75.9758],
            "spill_area_sq_m": 100000.0,
            "suspect_vessel": {"name": "UNKNOWN", "mmsi": "---", "threat_score": 0.90},
            "threat_score": 0.90,
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["status"], "dispatched")
        self.assertTrue(data["dispatch_id"].startswith("ICG-DISPATCH-"))
        self.assertEqual(data["urgency"], "DISTRESS")
        self.assertIn("MRCC Mumbai", data["recipient"])
        self.assertIn("hmac_sha256_digest", data)
        self.assertEqual(len(data["hmac_sha256_digest"]), 64)

        print(f"[Test 03 PASSED] /api/dispatch-alert -- {data['dispatch_id']} -> {data['recipient']}, "
              f"Urgency: {data['urgency']}, HMAC: {data['hmac_sha256_digest'][:16]}...")

    # ----------------------------------------------------------------
    # 4. Root serves HTML
    # ----------------------------------------------------------------
    def test_04_root_serves_html(self):
        """GET / returns index.html with IMW content."""
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers.get("content-type", ""))
        self.assertIn("Indo Marine Watch", resp.text)
        print("[Test 04 PASSED] GET / — index.html served with IMW branding.")

    # ----------------------------------------------------------------
    # 5. Legacy endpoint regression
    # ----------------------------------------------------------------
    def test_05_legacy_analyze_incident(self):
        """POST /api/analyze-incident still works (backward compatibility)."""
        resp = self.client.post("/api/analyze-incident", json={
            "scenario": "msc_elsa_3",
            "hours_back": 6.0,
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["incident_id"], "INCIDENT-MSC-ELSA-3-2026")
        self.assertEqual(data["sensor_fusion"]["threat_score"], 0.90)
        print("[Test 05 PASSED] /api/analyze-incident — Legacy endpoint intact.")


if __name__ == "__main__":
    unittest.main()
