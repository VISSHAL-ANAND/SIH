"""
Automated Verification Suite for Dynamic SAR Image Processing & Decoupled Architecture
========================================================================================
Tests:
  1. Geolocation bounding box calculation & centroid extraction
  2. Dynamic Open-Meteo weather physics fetch for arbitrary global coordinates
  3. Dynamic POST /api/upload-sar endpoint execution with image_overlay & custom coordinates
"""

import sys
import unittest
from pathlib import Path
from io import BytesIO

# Add 'main' folder to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
MAIN_DIR = BASE_DIR / "main"
if str(MAIN_DIR) not in sys.path:
    sys.path.insert(0, str(MAIN_DIR))

from geolocation import compute_image_bounds, extract_geotiff_bounds
from ocean_wind_loader import get_live_weather_physics
from main import app
from fastapi.testclient import TestClient


class TestDynamicSARProcessing(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_01_compute_image_bounds(self):
        """Verify compute_image_bounds creates valid WGS84 bounding box for non-GeoTIFF images."""
        res = compute_image_bounds(center_lat=12.9716, center_lon=77.5946, width_px=512, height_px=512)
        self.assertIn("centroid", res)
        self.assertIn("bounds", res)
        self.assertEqual(res["centroid"], [12.9716, 77.5946])
        bounds = res["bounds"]
        self.assertLess(bounds[0][0], 12.9716)  # south < center_lat
        self.assertGreater(bounds[1][0], 12.9716)  # north > center_lat
        print(f"[Test 01 PASSED] Image bounds generated: {bounds}")

    def test_02_dynamic_weather_physics(self):
        """Verify get_live_weather_physics fetches weather vectors for arbitrary coordinates."""
        weather = get_live_weather_physics(lat=20.85, lon=69.20)
        self.assertIn("current_velocity_kmh", weather)
        self.assertIn("current_direction_deg", weather)
        self.assertIn("wind_speed_kmh", weather)
        self.assertIn("wind_direction_deg", weather)
        self.assertIn("source", weather)
        print(f"[Test 02 PASSED] Dynamic weather fetched: {weather}")

    def test_03_upload_sar_dynamic_endpoint(self):
        """Verify POST /api/upload-sar with custom lat/lon form fields returns image_overlay."""
        dummy_file = BytesIO(b"DUMMY_SAR_IMAGE_BYTES_1234567890")
        files = {"file": ("test_scene.png", dummy_file, "image/png")}
        data = {"latitude": "15.2993", "longitude": "74.1240"}  # Goa Coast

        response = self.client.post("/api/upload-sar", files=files, data=data)
        self.assertEqual(response.status_code, 200)

        res_json = response.json()
        self.assertEqual(res_json["status"], "success")
        self.assertIn("image_overlay", res_json)
        self.assertEqual(res_json["image_overlay"]["centroid"], [15.2993, 74.1240])
        self.assertIn("surrounding_traffic", res_json)
        self.assertIn("geojson", res_json)
        print(f"[Test 03 PASSED] Upload SAR processed dynamically for custom coordinates (15.2993, 74.1240). Image overlay URL: {res_json['image_overlay']['url']}")

    def test_04_upload_sar_missing_coords_error(self):
        """Verify upload-sar returns HTTP 400 when uploading non-GeoTIFF without coordinates."""
        dummy_file = BytesIO(b"DUMMY_SAR_IMAGE_BYTES_PLAIN")
        files = {"file": ("test_plain.jpg", dummy_file, "image/jpeg")}

        response = self.client.post("/api/upload-sar", files=files)
        self.assertEqual(response.status_code, 400)
        self.assertIn("Latitude and Longitude form fields are required", response.json()["detail"])
        print("[Test 04 PASSED] HTTP 400 correctly raised when uploading plain image without coordinates.")


if __name__ == "__main__":
    unittest.main()

