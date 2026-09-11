"""Tests for the current IMW dynamic SAR/API architecture.

These tests avoid model inference and external network calls so they remain
 deterministic in CI. Real SAR inference is exercised separately by the
 Sentinel-1 geolocation and integration tests.
"""

import unittest

from fastapi.testclient import TestClient

from app import app
from main.geolocation import compute_image_bounds


class TestDynamicSARProcessing(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_01_compute_image_bounds(self):
        """Verify estimated bounds are centered on the supplied coordinates."""
        result = compute_image_bounds(
            center_lat=12.9716,
            center_lon=77.5946,
            width_px=512,
            height_px=512,
        )
        self.assertIn("centroid", result)
        self.assertIn("bounds", result)
        self.assertEqual(result["centroid"], [12.9716, 77.5946])
        bounds = result["bounds"]
        self.assertLess(bounds[0][0], 12.9716)
        self.assertGreater(bounds[1][0], 12.9716)

    def test_02_health_endpoint(self):
        """Verify the canonical API exposes read-only deployment diagnostics."""
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["service"], "Indo Marine Watch")
        self.assertEqual(payload["data_integrity"], "REAL_ONLY")
        self.assertIn("dependencies", payload)

    def test_03_process_sar_requires_file(self):
        """Verify the current SAR endpoint rejects a request without an upload."""
        response = self.client.post("/api/process-sar")
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
