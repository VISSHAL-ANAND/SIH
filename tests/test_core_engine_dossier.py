"""
Automated Verification Suite for Core Backend Rebuild
=====================================================
Tests:
  1. models.py (U-Net segmentation, YOLOv8 hull detection, PCA shape classification < 0.15)
  2. physics.py (Open-Meteo REST API fetch & NOAA 3% wind backward drift trajectory)
  3. sensor_fusion.py (Haversine AIS distance correlation & Dark Vessel 0.90 threat score)
  4. main.py (POST /api/analyze-incident endpoint returning structured JSON evidentiary dossier)
"""

import sys
import unittest
from pathlib import Path

# Add root folder to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from models import run_sar_segmentation, run_hull_detection, classify_slick_pca_shape
from physics import fetch_open_meteo_environment, simulate_backward_drift_trajectory
from sensor_fusion import haversine_km, correlate_hull_with_ais
from app import app
from fastapi.testclient import TestClient


class TestCoreEngineDossier(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_01_models_and_pca_classification(self):
        """Verify U-Net segmentation, YOLOv8 hull detection, and PCA ratio < 0.15 linear classification."""
        sar_res = run_sar_segmentation(pixel_count=1000)
        self.assertEqual(sar_res["spill_area_sq_m"], 100000.0)
        shape_info = sar_res["shape_classification"]
        self.assertEqual(shape_info["shape_class"], "linear")
        self.assertLess(shape_info["eigenvalue_ratio"], 0.15)

        hull_res = run_hull_detection(slick_lat=9.3764, slick_lon=75.9758)
        self.assertTrue(hull_res["hull_detected"])
        self.assertEqual(hull_res["coordinates"], [9.4200, 76.0200])
        print(f"[Test 01 PASSED] PCA ratio: {shape_info['eigenvalue_ratio']} (< 0.15 -> linear), Spill Area: {sar_res['spill_area_sq_m']} m²")

    def test_02_physics_open_meteo_and_gnome_drift(self):
        """Verify Open-Meteo REST API fetch & NOAA 3% wind factor backward trajectory integration."""
        env = fetch_open_meteo_environment(lat=9.35, lon=76.08)
        self.assertIn("current_velocity_kmh", env)
        self.assertIn("wind_speed_kmh", env)

        drift = simulate_backward_drift_trajectory(slick_lat=9.3764, slick_lon=75.9758, hours_back=6.0, env_params=env)
        self.assertIn("origin_coordinates", drift)
        self.assertGreater(drift["drift_distance_km"], 0.0)
        self.assertEqual(drift["hours_back"], 6.0)
        print(f"[Test 02 PASSED] Weather: Current {env['current_velocity_kmh']} km/h, Wind {env['wind_speed_kmh']} km/h. Origin: {drift['origin_coordinates']}, Distance: {drift['drift_distance_km']} km")

    def test_03_sensor_fusion_threat_scoring(self):
        """Verify Haversine AIS distance correlation flags Dark Vessel with threat score 0.90."""
        fusion = correlate_hull_with_ais(hull_lat=9.4200, hull_lon=76.0200, tolerance_km=5.0)
        self.assertEqual(fusion["ais_status"], "INACTIVE / UNMATCHED")
        self.assertTrue(fusion["is_dark_vessel"])
        self.assertTrue(fusion["rf_intercept_match"])
        self.assertEqual(fusion["threat_score"], 0.90)
        print(f"[Test 03 PASSED] AIS Status: {fusion['ais_status']}, RF Intercept: {fusion['rf_intercept_match']}, Threat Score: {fusion['threat_score']}")

    def test_04_analyze_incident_endpoint(self):
        """Verify POST /api/analyze-incident returns structured JSON evidentiary dossier."""
        response = self.client.post("/api/analyze-incident", json={
            "scenario": "msc_elsa_3",
            "hours_back": 6.0
        })
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["incident_id"], "INCIDENT-MSC-ELSA-3-2026")
        self.assertEqual(data["target_vessel_coordinates"], [9.4200, 76.0200])
        self.assertEqual(data["slick_centroid"], [9.3764, 75.9758])
        self.assertIn("origin_coordinates", data)
        self.assertIn("drift_distance_km", data)
        self.assertEqual(data["spill_area_sq_m"], 100000.0)
        self.assertEqual(data["shape_classification"]["class"], "linear")
        self.assertEqual(data["sensor_fusion"]["threat_score"], 0.90)
        self.assertEqual(data["sensor_fusion"]["ais_status"], "INACTIVE / UNMATCHED")
        self.assertTrue(data["sensor_fusion"]["rf_intercept_match"])
        print("[Test 04 PASSED] POST /api/analyze-incident returned full structured JSON evidentiary dossier with 200 OK.")


if __name__ == "__main__":
    unittest.main()
