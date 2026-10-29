"""Tests for Python Datetime and Timezone Handling in Reassignment & Live Telemetry.

Validates:
1. _to_utc helper with None, timezone-naive, timezone-aware UTC, and timezone-aware offset timestamps.
2. Elapsed-time calculations with timezone-aware UTC created_at.
3. Elapsed-time calculations with timezone-naive created_at.
4. Elapsed-time calculations with non-UTC timezone-aware created_at (e.g., IST +05:30).
5. Safe handling when created_at is None.
6. Preserved transfer timeout lifecycle (< 180s = IN_PROGRESS, >= 180s = IDLE).
7. get_live_buses integration with both naive and aware database execution records.
"""
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.bus import Bus
from app.models.route import Route
from app.models.bus_position import BusPosition
from app.models.passenger_load import PassengerLoad
from app.models.reallocation_execution import ReallocationExecution
from app.api.routes.buses import _to_utc, get_live_buses
from app.services.load_intelligence import _to_utc as li_to_utc, LoadIntelligenceService


class TestDatetimeTimezoneHandling(unittest.TestCase):
    def setUp(self):
        # Create an in-memory SQLite database for isolated test execution
        self.engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.db = self.SessionLocal()

        # Seed baseline route and bus
        self.route1 = Route(
            id=1,
            route_number="101",
            name="Corridor 101",
            origin="Gandhipuram",
            destination="Airport",
            is_active=True,
        )
        self.route2 = Route(
            id=2,
            route_number="202",
            name="Corridor 202",
            origin="Saibaba",
            destination="Junction",
            is_active=True,
        )
        self.bus = Bus(
            id=1,
            bus_number="202A",
            license_plate="TN-38-N-2021",
            capacity=60,
            status="ACTIVE",
            current_route_id=2,
        )
        self.pos = BusPosition(
            id=1,
            bus_id=1,
            latitude=11.0168,
            longitude=76.9558,
            speed=25.0,
            heading=90.0,
        )
        self.load = PassengerLoad(
            id=1,
            bus_id=1,
            current_load=20,
            capacity=60,
            load_factor=0.33,
        )
        self.db.add_all([self.route1, self.route2, self.bus, self.pos, self.load])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    # -------------------------------------------------------------------------
    # Unit tests for _to_utc helper function
    # -------------------------------------------------------------------------
    def test_to_utc_none_returns_none(self):
        """_to_utc(None) returns None safely without raising an exception."""
        self.assertIsNone(_to_utc(None))
        self.assertIsNone(li_to_utc(None))

    def test_to_utc_naive_timestamp(self):
        """_to_utc on a naive timestamp assigns timezone.utc preserving components."""
        naive_dt = datetime(2026, 10, 25, 14, 30, 0)
        utc_dt = _to_utc(naive_dt)

        self.assertIsNotNone(utc_dt)
        self.assertIsNotNone(utc_dt.tzinfo)
        self.assertEqual(utc_dt.tzinfo, timezone.utc)
        self.assertEqual(utc_dt.year, 2026)
        self.assertEqual(utc_dt.month, 10)
        self.assertEqual(utc_dt.day, 25)
        self.assertEqual(utc_dt.hour, 14)
        self.assertEqual(utc_dt.minute, 30)

    def test_to_utc_aware_utc_timestamp(self):
        """_to_utc on an already UTC aware timestamp preserves timezone and time."""
        aware_utc = datetime(2026, 10, 25, 14, 30, 0, tzinfo=timezone.utc)
        result = _to_utc(aware_utc)

        self.assertIsNotNone(result)
        self.assertEqual(result.tzinfo, timezone.utc)
        self.assertEqual(result, aware_utc)

    def test_to_utc_aware_offset_timestamp(self):
        """_to_utc on an offset-aware timestamp (e.g. IST +05:30) correctly converts to UTC."""
        ist_tz = timezone(timedelta(hours=5, minutes=30))
        # 20:00 IST = 14:30 UTC
        ist_dt = datetime(2026, 10, 25, 20, 0, 0, tzinfo=ist_tz)
        utc_dt = _to_utc(ist_dt)

        self.assertIsNotNone(utc_dt)
        self.assertEqual(utc_dt.tzinfo, timezone.utc)
        self.assertEqual(utc_dt.hour, 14)
        self.assertEqual(utc_dt.minute, 30)

    # -------------------------------------------------------------------------
    # Elapsed-time calculation tests in get_live_buses
    # -------------------------------------------------------------------------
    def test_elapsed_time_with_timezone_aware_recent_execution(self):
        """A timezone-aware UTC execution dispatched 30 seconds ago evaluates as IN_PROGRESS."""
        recent_time = datetime.now(timezone.utc) - timedelta(seconds=30)
        execution = ReallocationExecution(
            id=1,
            recommendation_id="REC-TEST-1",
            bus_id=1,
            bus_number="202A",
            source_route_id=2,
            source_route_number="202",
            target_route_id=1,
            target_route_number="101",
            status="EXECUTED",
            created_at=recent_time,
        )
        self.db.add(execution)
        self.db.commit()

        live_buses = get_live_buses(self.db)
        self.assertEqual(len(live_buses), 1)
        bus_state = live_buses[0]

        self.assertTrue(bus_state.is_transferring)
        self.assertEqual(bus_state.transfer_status, "IN_PROGRESS")
        self.assertEqual(bus_state.target_route_id, 1)

    def test_elapsed_time_with_timezone_naive_recent_execution(self):
        """A timezone-naive execution dispatched 30 seconds ago (SQLite UTC style) evaluates as IN_PROGRESS."""
        # Naive datetime representing UTC 30s ago
        now_utc = datetime.now(timezone.utc)
        recent_naive = (now_utc - timedelta(seconds=30)).replace(tzinfo=None)

        execution = ReallocationExecution(
            id=1,
            recommendation_id="REC-TEST-2",
            bus_id=1,
            bus_number="202A",
            source_route_id=2,
            source_route_number="202",
            target_route_id=1,
            target_route_number="101",
            status="EXECUTED",
            created_at=recent_naive,
        )
        self.db.add(execution)
        self.db.commit()

        live_buses = get_live_buses(self.db)
        self.assertEqual(len(live_buses), 1)
        bus_state = live_buses[0]

        self.assertTrue(bus_state.is_transferring)
        self.assertEqual(bus_state.transfer_status, "IN_PROGRESS")
        self.assertEqual(bus_state.target_route_id, 1)

    def test_elapsed_time_with_offset_aware_recent_execution(self):
        """An offset-aware timestamp (+05:30) dispatched 45 seconds ago evaluates as IN_PROGRESS."""
        ist_tz = timezone(timedelta(hours=5, minutes=30))
        recent_ist = datetime.now(ist_tz) - timedelta(seconds=45)

        execution = ReallocationExecution(
            id=1,
            recommendation_id="REC-TEST-3",
            bus_id=1,
            bus_number="202A",
            source_route_id=2,
            source_route_number="202",
            target_route_id=1,
            target_route_number="101",
            status="EXECUTED",
            created_at=recent_ist,
        )
        self.db.add(execution)
        self.db.commit()

        live_buses = get_live_buses(self.db)
        self.assertEqual(len(live_buses), 1)
        bus_state = live_buses[0]

        self.assertTrue(bus_state.is_transferring)
        self.assertEqual(bus_state.transfer_status, "IN_PROGRESS")
        self.assertEqual(bus_state.target_route_id, 1)

    def test_elapsed_time_timeout_expired(self):
        """An execution created 200 seconds ago (beyond 180s threshold) evaluates as IDLE."""
        old_time = datetime.now(timezone.utc) - timedelta(seconds=200)

        execution = ReallocationExecution(
            id=1,
            recommendation_id="REC-TEST-4",
            bus_id=1,
            bus_number="202A",
            source_route_id=2,
            source_route_number="202",
            target_route_id=1,
            target_route_number="101",
            status="EXECUTED",
            created_at=old_time,
        )
        self.db.add(execution)
        self.db.commit()

        live_buses = get_live_buses(self.db)
        self.assertEqual(len(live_buses), 1)
        bus_state = live_buses[0]

        self.assertFalse(bus_state.is_transferring)
        self.assertEqual(bus_state.transfer_status, "IDLE")

    def test_execution_with_null_created_at_handled_safely(self):
        """An execution record with created_at=None does not crash and leaves transfer status IDLE."""
        fake_exec = ReallocationExecution(
            id=1,
            recommendation_id="REC-TEST-5",
            bus_id=1,
            bus_number="202A",
            source_route_id=2,
            source_route_number="202",
            target_route_id=1,
            target_route_number="101",
            status="EXECUTED",
        )
        self.assertIsNone(fake_exec.created_at)
        self.assertIsNone(_to_utc(fake_exec.created_at))

        orig_query = self.db.query

        def query_interceptor(model, *args, **kwargs):
            q = orig_query(model, *args, **kwargs)
            if model is ReallocationExecution:
                mock_q = MagicMock()
                mock_q.order_by.return_value.limit.return_value.all.return_value = [fake_exec]
                return mock_q
            return q

        with patch.object(self.db, "query", side_effect=query_interceptor):
            live_buses = get_live_buses(self.db)
            self.assertEqual(len(live_buses), 1)
            bus_state = live_buses[0]

            self.assertFalse(bus_state.is_transferring)
            self.assertEqual(bus_state.transfer_status, "IDLE")

    def test_load_intelligence_service_transfer_detection_parity(self):
        """LoadIntelligenceService uses consistent UTC handling and detects active transfers identically."""
        recent_time = datetime.now(timezone.utc) - timedelta(seconds=30)
        execution = ReallocationExecution(
            id=1,
            recommendation_id="REC-TEST-6",
            bus_id=1,
            bus_number="202A",
            source_route_id=2,
            source_route_number="202",
            target_route_id=1,
            target_route_number="101",
            status="EXECUTED",
            created_at=recent_time,
        )
        self.db.add(execution)
        self.db.commit()

        intelligence = LoadIntelligenceService.get_bus_intelligence(self.db)
        self.assertEqual(len(intelligence), 1)
        bus_intel = intelligence[0]

        self.assertTrue(bus_intel.is_transferring)
        self.assertEqual(bus_intel.transfer_status, "IN_PROGRESS")
        self.assertEqual(bus_intel.target_route_id, 1)


if __name__ == "__main__":
    unittest.main()
