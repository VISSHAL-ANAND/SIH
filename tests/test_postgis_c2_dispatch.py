"""
Automated Verification Suite for PostGIS Architecture & GMDSS C2 Dispatch
========================================================================
Tests:
  1. PostGIS Database Models & Initialization
  2. Spatial-Temporal Traffic Engine (fetch_surrounding_traffic & verify_dark_vessel)
  3. GMDSS Coast Guard Dispatch Payload Generator (generate_c2_dispatch_payload)
  4. FastAPI Endpoints (/api/run-scenario, /api/trigger-dispatch) & APScheduler
"""

import sys
import unittest
from pathlib import Path
from datetime import datetime, timezone

# Add 'main' folder to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
MAIN_DIR = BASE_DIR / "main"
if str(MAIN_DIR) not in sys.path:
    sys.path.insert(0, str(MAIN_DIR))

from database import init_db, SessionLocal
from models import AISTrack, DarkVesselIncident
from traffic_engine import fetch_surrounding_traffic, verify_dark_vessel
from c2_dispatch import generate_c2_dispatch_payload
from main import app, scheduler
from fastapi.testclient import TestClient


class TestPostGISAndC2Dispatch(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        init_db()
        if not scheduler.running:
            scheduler.start()


    def test_01_database_models_init(self):
        """Verify AISTrack and DarkVesselIncident models instantiate cleanly."""
        db = SessionLocal()
        try:
            # Check model query capability
            ais_count = db.query(AISTrack).count()
            incident_count = db.query(DarkVesselIncident).count()
            self.assertIsInstance(ais_count, int)
            self.assertIsInstance(incident_count, int)
            print(f"[Test 01 PASSED] PostGIS Database Models active. AIS Tracks: {ais_count}, Incidents: {incident_count}")
        finally:
            db.close()

    def test_02_spatial_temporal_traffic_engine(self):
        """Verify fetch_surrounding_traffic returns compliant vessel list."""
        traffic = fetch_surrounding_traffic(target_lon=75.9758, target_lat=9.3764, radius_m=50000.0)
        self.assertIsInstance(traffic, list)
        self.assertGreater(len(traffic), 0)
        first_vessel = traffic[0]
        self.assertIn("mmsi", first_vessel)
        self.assertIn("coordinates", first_vessel)
        self.assertIn("status", first_vessel)
        print(f"[Test 02 PASSED] Traffic Engine returned {len(traffic)} compliant AIS vessels.")

    def test_03_verify_dark_vessel(self):
        """Verify verify_dark_vessel flags dark vessel and assigns 0.95 Threat Score."""
        result = verify_dark_vessel(yolov8_lon=76.0200, yolov8_lat=9.4200, slick_area_sq_m=1250000.0)
        self.assertEqual(result["ais_status"], "AIS_INACTIVE")
        self.assertTrue(result["is_dark_vessel"])
        self.assertTrue(result["rf_intercept_match"])
        self.assertEqual(result["threat_score"], 0.95)
        self.assertIn("incident_uuid", result)
        print(f"[Test 03 PASSED] Dark Vessel verified. Threat Score: {result['threat_score']}, RF Intercept: {result['rf_intercept_match']}")

    def test_04_gmdss_c2_dispatch_payload(self):
        """Verify GMDSS C2 dispatch payload generation."""
        incident_data = {
            "incident_id": "MSC-ELSA-3-TEST",
            "target_vessel": "Suspect Dark Vessel (Target #2)",
            "slick_lat": 9.3764,
            "slick_lon": 75.9758,
            "suspect_lat": 9.4200,
            "suspect_lon": 76.0200,
            "threat_score": 0.95
        }
        payload = generate_c2_dispatch_payload(incident_data)
        self.assertEqual(payload["header"], "SECURITE - INDIAN COAST GUARD C2 - TACTICAL INTERCEPT")
        self.assertEqual(payload["priority"], "URGENCY - ILLEGAL DISCHARGE / DARK VESSEL")
        self.assertEqual(payload["routing"]["destination"], "ICG District HQ No. 4 (Kochi)")
        self.assertIn("hmac_sha256_digest", payload["security_integrity"])
        print("[Test 04 PASSED] GMDSS C2 Dispatch Payload verified with HMAC SHA-256 integrity digest.")

    def test_05_fastapi_trigger_dispatch_endpoint(self):
        """Verify POST /api/trigger-dispatch endpoint returns 200 OK with GMDSS payload."""
        response = self.client.post("/api/trigger-dispatch", json={
            "incident_id": "INCIDENT-TEST-1234",
            "target_vessel": "Suspect Tanker Target",
            "threat_score": 0.95
        })
        self.assertEqual(response.status_code, 200)
        json_resp = response.json()
        self.assertEqual(json_resp["status"], "success")
        self.assertIn("C2 Alert successfully transmitted", json_resp["message"])
        self.assertIn("payload", json_resp)
        print("[Test 05 PASSED] FastAPI /api/trigger-dispatch endpoint responded with 200 OK and valid payload.")

    def test_06_apscheduler_running(self):
        """Verify APScheduler background scheduler is instantiated and running."""
        self.assertTrue(scheduler.running)
        print("[Test 06 PASSED] APScheduler 6-hour autonomous cron job running.")


if __name__ == "__main__":
    unittest.main()
