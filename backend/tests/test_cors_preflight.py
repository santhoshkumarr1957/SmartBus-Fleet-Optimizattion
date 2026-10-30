"""Tests for CORS preflight and actual requests across development origins.
"""
import unittest
from starlette.testclient import TestClient
from app.main import app
from app.core.config import settings


class TestCORSPreflight(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.test_origins = [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]

    def test_configured_origins_in_settings(self):
        """Verify all local development origins are configured in settings."""
        for origin in self.test_origins:
            self.assertIn(origin, settings.CORS_ORIGINS, f"Origin {origin} not in CORS_ORIGINS")

    def test_options_preflight_buses_live_localhost_5174(self):
        """Test OPTIONS preflight to /api/buses/live with Origin http://localhost:5174."""
        resp = self.client.options(
            "/api/buses/live",
            headers={
                "Origin": "http://localhost:5174",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("access-control-allow-origin"), "http://localhost:5174")
        self.assertIn("GET", resp.headers.get("access-control-allow-methods", ""))
        self.assertIn("content-type", resp.headers.get("access-control-allow-headers", "").lower())

    def test_options_preflight_routes_127_0_0_1_5174(self):
        """Test OPTIONS preflight to /api/routes with Origin http://127.0.0.1:5174."""
        resp = self.client.options(
            "/api/routes",
            headers={
                "Origin": "http://127.0.0.1:5174",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("access-control-allow-origin"), "http://127.0.0.1:5174")

    def test_disallowed_origin_returns_400(self):
        """Verify that arbitrary external origins are rejected with 400."""
        resp = self.client.options(
            "/api/buses/live",
            headers={
                "Origin": "http://malicious-site.example.com",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIsNone(resp.headers.get("access-control-allow-origin"))


if __name__ == "__main__":
    unittest.main()
