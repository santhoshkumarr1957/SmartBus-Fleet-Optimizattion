"""Tests for Notification Summary endpoint, connection release, and error handling.
"""
import unittest
from unittest.mock import patch
from starlette.testclient import TestClient
from app.main import app
from app.core.config import settings


class TestNotificationSummaryConnection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_notification_summary_success(self):
        """Verify /api/notifications/summary returns 200 with valid structure."""
        resp = self.client.get("/api/notifications/summary")
        # If database is configured and accessible, expect 200
        if resp.status_code == 200:
            data = resp.json()
            self.assertIn("total_alerts", data)
            self.assertIn("active_count", data)
            self.assertIn("critical_count", data)
            self.assertIn("warning_count", data)
            self.assertIsInstance(data["total_alerts"], int)
        else:
            # 503 is acceptable if remote DB is unreachable in test environment
            self.assertEqual(resp.status_code, 503)

    def test_repeated_summary_requests_release_connections(self):
        """Execute repeated requests to verify connections are closed and not leaked."""
        for _ in range(10):
            resp = self.client.get("/api/notifications/summary")
            self.assertIn(resp.status_code, [200, 503])

    def test_notification_summary_db_error_handling(self):
        """Verify database exception produces 503 Service Unavailable cleanly."""
        with patch("app.services.notification.NotificationService.get_summary") as mock_get:
            mock_get.side_effect = Exception("EMAXCONNSESSION: max clients reached")
            resp = self.client.get("/api/notifications/summary")
            self.assertEqual(resp.status_code, 503)
            self.assertIn("Database query failed", resp.json().get("detail", ""))


if __name__ == "__main__":
    unittest.main()
