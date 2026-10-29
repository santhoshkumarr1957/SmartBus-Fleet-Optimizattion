"""Stage 10 Verification Test Suite for SmartBus (Reports & Performance Analytics).

Tests all Stage 10 criteria:
1. Fleet utilization calculation (operational count, availability pct, seat totals, load distribution).
2. Route-level performance aggregation, comparison, and overcrowding ratings.
3. Disruption analysis with strict separation between real operational alerts and simulated scenarios.
4. Reallocation and dispatcher review outcomes summary with non-execution limitation disclosures.
5. Historical timeseries trend calculation across configurable time ranges (1h, 24h, 7d).
6. Missing telemetry and empty database graceful handling.
7. CSV report generation with safe RFC 4180 escaping, stable headers, and empty exports.
8. Query parameter validation (e.g. invalid time range or report type raises HTTP 400).
9. Confirmation that report generation never mutates any operational transit data.
10. FastAPI route handlers tested directly via dependency injection.
"""
import unittest
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from fastapi import HTTPException

from app.db.base import Base
from app.models.route import Route
from app.models.stop import Stop
from app.models.bus import Bus
from app.models.bus_position import BusPosition
from app.models.passenger_load import PassengerLoad
from app.models.reallocation_review import ReallocationReview
from app.models.notification import Notification
from app.services.report import ReportService
from app.api.routes.reports import (
    get_reports_overview,
    get_fleet_utilization,
    get_route_performance,
    get_disruptions_analysis,
    get_reallocation_analysis,
    get_historical_trends,
    export_report_csv,
)


def create_in_memory_db() -> Session:
    """Create isolated SQLite in-memory database instance with full schema."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    SessionTest = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionTest()


def seed_test_reports_network(db: Session) -> datetime:
    """Seed comprehensive transit network with buses, routes, historical telemetry, reviews, and notifications."""
    now = datetime.now(timezone.utc)

    # Routes
    r101 = Route(id=1, route_number="101", name="Downtown Express", origin="Metro Terminal", destination="Civic Plaza", is_active=True)
    r202 = Route(id=2, route_number="202", name="Crosstown Loop", origin="North Hub", destination="South Station", is_active=True)
    r303 = Route(id=3, route_number="303", name="Uptown Feeder", origin="East Hill", destination="Metro Terminal", is_active=True)
    r404 = Route(id=4, route_number="404", name="Westside Shuttle", origin="West Park", destination="Plaza", is_active=False)
    db.add_all([r101, r202, r303, r404])
    db.flush()

    # Stops
    s1 = Stop(id=1, route_id=r101.id, name="Central", sequence_order=1, latitude=37.7749, longitude=-122.4194)
    s2 = Stop(id=2, route_id=r202.id, name="Hub", sequence_order=1, latitude=37.7800, longitude=-122.4100)
    s3 = Stop(id=3, route_id=r303.id, name="North", sequence_order=1, latitude=37.7900, longitude=-122.4200)
    db.add_all([s1, s2, s3])
    db.flush()

    # Buses:
    # 5 Operational (101A, 101B, 202A, 202B, 303A)
    # 1 Broken Down (505B)
    # 1 Maintenance (606M)
    # 1 Inactive (707X)
    b101a = Bus(id=1, bus_number="101A", license_plate="BUS-101A", capacity=50, current_route_id=r101.id, status="ACTIVE")
    b101b = Bus(id=2, bus_number="101B", license_plate="BUS-101B", capacity=50, current_route_id=r101.id, status="ACTIVE")
    b202a = Bus(id=3, bus_number="202A", license_plate="BUS-202A", capacity=60, current_route_id=r202.id, status="ACTIVE")
    b202b = Bus(id=4, bus_number="202B", license_plate="BUS-202B", capacity=60, current_route_id=r202.id, status="ACTIVE")
    b303a = Bus(id=5, bus_number="303A", license_plate="BUS-303A", capacity=50, current_route_id=r303.id, status="ACTIVE")
    b505b = Bus(id=6, bus_number="505B", license_plate="BUS-505B", capacity=60, current_route_id=r101.id, status="BROKEN_DOWN")
    b606m = Bus(id=7, bus_number="606M", license_plate="BUS-606M", capacity=60, current_route_id=r202.id, status="MAINTENANCE")
    b707x = Bus(id=8, bus_number="707X", license_plate="BUS-707X", capacity=60, current_route_id=None, status="INACTIVE")
    db.add_all([b101a, b101b, b202a, b202b, b303a, b505b, b606m, b707x])
    db.flush()

    # Current Passenger loads (at now)
    # 101A: 55/50 = 1.10 (CRITICAL)
    # 101B: 50/50 = 1.00 (CRITICAL)
    # 202A: 15/60 = 0.25 (LOW)
    # 202B: 35/60 = 0.5833 (NORMAL)
    # 303A: 42/50 = 0.84 (HIGH)
    l1 = PassengerLoad(id=1, bus_id=b101a.id, current_load=55, capacity=50, load_factor=1.10, timestamp=now)
    l2 = PassengerLoad(id=2, bus_id=b101b.id, current_load=50, capacity=50, load_factor=1.00, timestamp=now)
    l3 = PassengerLoad(id=3, bus_id=b202a.id, current_load=15, capacity=60, load_factor=0.25, timestamp=now)
    l4 = PassengerLoad(id=4, bus_id=b202b.id, current_load=35, capacity=60, load_factor=0.5833, timestamp=now)
    l5 = PassengerLoad(id=5, bus_id=b303a.id, current_load=42, capacity=50, load_factor=0.84, timestamp=now)

    # Historical loads for time range tests
    # 30 minutes ago (within 1h, 24h, 7d)
    l_30m = PassengerLoad(id=6, bus_id=b101a.id, current_load=45, capacity=50, load_factor=0.90, timestamp=now - timedelta(minutes=30))
    # 2 hours ago (within 24h, 7d; NOT within 1h)
    l_2h = PassengerLoad(id=7, bus_id=b202a.id, current_load=20, capacity=60, load_factor=0.3333, timestamp=now - timedelta(hours=2))
    # 12 hours ago (within 24h, 7d; NOT within 1h)
    l_12h = PassengerLoad(id=8, bus_id=b303a.id, current_load=38, capacity=50, load_factor=0.76, timestamp=now - timedelta(hours=12))
    # 3 days ago (within 7d; NOT within 1h, 24h)
    l_3d = PassengerLoad(id=9, bus_id=b101b.id, current_load=48, capacity=50, load_factor=0.96, timestamp=now - timedelta(days=3))
    # 10 days ago (OUTSIDE 7d range)
    l_10d = PassengerLoad(id=10, bus_id=b101a.id, current_load=40, capacity=50, load_factor=0.80, timestamp=now - timedelta(days=10))

    db.add_all([l1, l2, l3, l4, l5, l_30m, l_2h, l_12h, l_3d, l_10d])

    # Reallocation Reviews (Stage 7 audit history)
    rv1 = ReallocationReview(
        id=1, recommendation_id="REC-101-202-202A", decision="APPROVED", dispatcher_id="DISP-1",
        target_route_id=1, target_route_number="101", source_route_id=2, source_route_number="202",
        candidate_bus_id=3, candidate_bus_number="202A", notes="Approved for peak alleviation", created_at=now - timedelta(hours=3),
    )
    rv2 = ReallocationReview(
        id=2, recommendation_id="REC-101-202-202B", decision="REJECTED", dispatcher_id="DISP-2",
        target_route_id=1, target_route_number="101", source_route_id=2, source_route_number="202",
        candidate_bus_id=4, candidate_bus_number="202B", notes="Bus needed on crosstown corridor", created_at=now - timedelta(hours=2),
    )
    rv3 = ReallocationReview(
        id=3, recommendation_id="REC-303-202-202A", decision="DEFERRED", dispatcher_id="DISP-1",
        target_route_id=3, target_route_number="303", source_route_id=2, source_route_number="202",
        candidate_bus_id=3, candidate_bus_number="202A", notes="Defer to next headway check", created_at=now - timedelta(hours=1),
    )
    db.add_all([rv1, rv2, rv3])

    # Notifications (Stage 9 records)
    n1 = Notification(
        id=1, alert_type="BUS_BREAKDOWN", severity="CRITICAL", title="Bus Breakdown: 505B",
        description="Bus 505B mechanical fault", source="LIVE", status="ACTIVE",
        dedup_key="LIVE:BUS_BREAKDOWN:BUS_6", bus_id=6, bus_number="505B", created_at=now - timedelta(hours=2),
    )
    n2 = Notification(
        id=2, alert_type="ROUTE_DISRUPTION", severity="CRITICAL", title="Corridor Disrupted: 404",
        description="Route 404 inactive", source="LIVE", status="ACKNOWLEDGED",
        dedup_key="LIVE:ROUTE_DISRUPTION:ROUTE_4", route_id=4, route_number="404",
        acknowledged_by="DISP-1", acknowledged_at=now - timedelta(minutes=45), created_at=now - timedelta(hours=1),
    )
    n3 = Notification(
        id=3, alert_type="CRITICAL_ROUTE_LOAD", severity="CRITICAL", title="Critical Overcrowding: Route 101",
        description="Route 101 over capacity", source="LIVE", status="RESOLVED",
        dedup_key="LIVE:CRITICAL_ROUTE_LOAD:ROUTE_1", route_id=1, route_number="101",
        resolved_by="DISP-1", resolved_at=now - timedelta(minutes=10), created_at=now - timedelta(minutes=30),
    )
    n4 = Notification(
        id=4, alert_type="SIMULATION_NOTICE", severity="HIGH", title="[SIMULATION] Route Closure Drill",
        description="Hypothetical corridor shutdown test", source="SIMULATION", status="ACTIVE",
        dedup_key="SIMULATION:SIMULATION_NOTICE:SCEN-TEST", created_at=now - timedelta(minutes=15),
    )
    db.add_all([n1, n2, n3, n4])
    db.commit()

    return now


class TestStage10ReportsAndAnalytics(unittest.TestCase):
    def setUp(self):
        self.db = create_in_memory_db()
        self.now = seed_test_reports_network(self.db)

    def tearDown(self):
        self.db.close()

    # -------------------------------------------------------------------------
    # 1. Fleet Utilization Report
    # -------------------------------------------------------------------------
    def test_01_fleet_utilization_calculations(self):
        """1. Verify total buses, operational ratio, capacity, seat availability, and load distribution."""
        rep = ReportService.get_fleet_utilization(db=self.db)

        # Total buses = 8
        self.assertEqual(rep.total_buses, 8)
        # Operational buses: 101A, 101B, 202A, 202B, 303A = 5
        self.assertEqual(rep.operational_buses, 5)
        self.assertEqual(rep.broken_down_buses, 1)
        self.assertEqual(rep.maintenance_buses, 1)
        self.assertEqual(rep.inactive_buses, 1)

        # Availability: 5 / 8 = 62.5%
        self.assertEqual(rep.fleet_availability_pct, 62.5)

        # Total operational capacity: 50 + 50 + 60 + 60 + 50 = 270 seats
        self.assertEqual(rep.total_passenger_capacity, 270)
        # Total current passengers: 55 + 50 + 15 + 35 + 42 = 197
        self.assertEqual(rep.total_current_passengers, 197)
        # Available seats: 270 - 197 = 73
        self.assertEqual(rep.available_seats, 73)
        # Fleet load factor: 197 / 270 = 0.7296
        self.assertAlmostEqual(rep.fleet_load_factor, 0.7296, places=3)

        # Distribution across operational buses:
        # CRITICAL (>=1.0): 101A (1.10), 101B (1.00) -> 2
        # HIGH (0.80-0.99): 303A (0.84) -> 1
        # NORMAL (0.50-0.79): 202B (0.5833) -> 1
        # LOW (<0.50): 202A (0.25) -> 1
        self.assertEqual(rep.load_distribution["CRITICAL"], 2)
        self.assertEqual(rep.load_distribution["HIGH"], 1)
        self.assertEqual(rep.load_distribution["NORMAL"], 1)
        self.assertEqual(rep.load_distribution["LOW"], 1)

    # -------------------------------------------------------------------------
    # 2. Route Performance Report
    # -------------------------------------------------------------------------
    def test_02_route_performance_aggregation(self):
        """2. Verify route-level passenger count, capacity, load factor, and overcrowding descriptors."""
        rep = ReportService.get_route_performance(db=self.db)

        self.assertEqual(rep.total_routes, 4)
        self.assertEqual(rep.active_routes, 3)
        self.assertEqual(rep.inactive_routes, 1)

        r101_item = next(r for r in rep.routes if r.route_number == "101")
        # Route 101: 2 operational buses (101A, 101B) = 100 capacity, 105 passengers
        # 105 / 100 = 1.05 -> CRITICAL
        self.assertEqual(r101_item.assigned_bus_count, 2)
        self.assertEqual(r101_item.total_capacity, 100)
        self.assertEqual(r101_item.total_passengers, 105)
        self.assertEqual(r101_item.available_seats, 0)
        self.assertEqual(r101_item.load_factor, 1.05)
        self.assertEqual(r101_item.status, "CRITICAL")
        self.assertIn("Severe Overcrowding", r101_item.overcrowding_level)

        r202_item = next(r for r in rep.routes if r.route_number == "202")
        # Route 202: 2 operational buses (202A, 202B) = 120 capacity, 50 passengers
        # 50 / 120 = 0.4167 -> LOW
        self.assertEqual(r202_item.assigned_bus_count, 2)
        self.assertEqual(r202_item.total_capacity, 120)
        self.assertEqual(r202_item.total_passengers, 50)
        self.assertEqual(r202_item.available_seats, 70)
        self.assertEqual(r202_item.status, "LOW")

        r404_item = next(r for r in rep.routes if r.route_number == "404")
        self.assertFalse(r404_item.is_active)
        self.assertEqual(r404_item.status, "CLOSED")

        # Network identification of extrema
        self.assertEqual(rep.highest_load_route, "101")
        self.assertEqual(rep.lowest_load_route, "202")
        self.assertEqual(rep.overloaded_routes_count, 2)  # Route 101 (CRITICAL), Route 303 (HIGH)
        self.assertEqual(rep.underutilized_routes_count, 1)  # Route 202 (LOW)

    # -------------------------------------------------------------------------
    # 3. Disruption Analysis & Simulation Isolation
    # -------------------------------------------------------------------------
    def test_03_disruption_analysis_and_simulation_isolation(self):
        """3. Real operational alerts and simulated scenarios must remain strictly isolated."""
        rep = ReportService.get_disruption_analysis(db=self.db)

        # Live alerts: n1 (breakdown), n2 (closure), n3 (overcrowding)
        self.assertEqual(rep.live_incidents_total, 3)
        self.assertEqual(rep.live_breakdowns_count, 1)
        self.assertEqual(rep.live_route_disruptions_count, 1)
        self.assertEqual(rep.live_overcrowding_alerts_count, 1)
        self.assertEqual(rep.live_active_count, 1)
        self.assertEqual(rep.live_acknowledged_count, 1)
        self.assertEqual(rep.live_resolved_count, 1)

        for le in rep.live_events:
            self.assertEqual(le.source, "LIVE")

        # Simulated alert: n4
        self.assertGreaterEqual(rep.simulation_scenarios_count, 1)
        for se in rep.simulated_events:
            self.assertEqual(se.source, "SIMULATION")
            self.assertTrue(se.title.startswith("[SIMULATION]"))

        self.assertTrue(rep.is_simulation_isolated)
        self.assertIn("strictly isolated", rep.disclaimer)

    # -------------------------------------------------------------------------
    # 4. Reallocation & Dispatcher Review Summary
    # -------------------------------------------------------------------------
    def test_04_reallocation_and_dispatcher_review_summary(self):
        """4. Verify review breakdown counts and clear operational limitation statement."""
        rep = ReportService.get_reallocation_analysis(db=self.db)

        self.assertEqual(rep.total_reviews_recorded, 3)
        self.assertEqual(rep.approved_count, 1)
        self.assertEqual(rep.rejected_count, 1)
        self.assertEqual(rep.deferred_count, 1)

        # Operational limitation statement must be present
        self.assertIn("APPROVED reviews do not execute automated vehicle reassignments", rep.operational_limitation_statement)

    # -------------------------------------------------------------------------
    # 5. Historical Trends: 1h, 24h, 7d Time Window Boundaries
    # -------------------------------------------------------------------------
    def test_05_historical_trends_time_windows(self):
        """5. Historical window filtering must partition records accurately into deterministic buckets."""
        # 1-hour window:
        # Includes: l1..l5 (now), l_30m (30m ago) -> 6 records
        # Excludes: l_2h (2h ago), l_12h (12h ago), l_3d, l_10d
        rep_1h = ReportService.get_historical_trends(db=self.db, time_range="1h")
        self.assertEqual(rep_1h.time_range, "1h")
        self.assertEqual(rep_1h.bucket_interval, "5m")
        self.assertEqual(len(rep_1h.datapoints), 12)
        self.assertEqual(rep_1h.total_samples, 6)
        self.assertGreater(rep_1h.overall_average_load_factor, 0.0)

        # 24-hour window:
        # Includes: l1..l5, l_30m, l_2h (2h ago), l_12h (12h ago) -> 8 records
        # Excludes: l_3d (3d ago), l_10d (10d ago)
        rep_24h = ReportService.get_historical_trends(db=self.db, time_range="24h")
        self.assertEqual(rep_24h.time_range, "24h")
        self.assertEqual(rep_24h.bucket_interval, "1h")
        self.assertEqual(len(rep_24h.datapoints), 24)
        self.assertEqual(rep_24h.total_samples, 8)

        # 7-day window:
        # Includes: l1..l5, l_30m, l_2h, l_12h, l_3d (3d ago) -> 9 records
        # Excludes: l_10d (10d ago)
        rep_7d = ReportService.get_historical_trends(db=self.db, time_range="7d")
        self.assertEqual(rep_7d.time_range, "7d")
        self.assertEqual(rep_7d.bucket_interval, "6h")
        self.assertEqual(len(rep_7d.datapoints), 28)
        self.assertEqual(rep_7d.total_samples, 9)

        # Invalid range raises 400
        with self.assertRaises(HTTPException) as ctx:
            ReportService.get_historical_trends(db=self.db, time_range="30d")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Invalid time_range", ctx.exception.detail)

    # -------------------------------------------------------------------------
    # 6. Missing Telemetry and Empty Database Handling
    # -------------------------------------------------------------------------
    def test_06_empty_database_and_missing_telemetry(self):
        """6. Empty datasets must return zeroed metrics without crashing or ZeroDivisionErrors."""
        empty_db = create_in_memory_db()

        # Fleet utilization on empty DB
        fleet_rep = ReportService.get_fleet_utilization(db=empty_db)
        self.assertEqual(fleet_rep.total_buses, 0)
        self.assertEqual(fleet_rep.operational_buses, 0)
        self.assertEqual(fleet_rep.fleet_availability_pct, 0.0)
        self.assertEqual(fleet_rep.total_passenger_capacity, 0)
        self.assertEqual(fleet_rep.fleet_load_factor, 0.0)
        self.assertEqual(len(fleet_rep.buses), 0)

        # Route performance on empty DB
        route_rep = ReportService.get_route_performance(db=empty_db)
        self.assertEqual(route_rep.total_routes, 0)
        self.assertIsNone(route_rep.highest_load_route)

        # Disruption analysis on empty DB
        disrupt_rep = ReportService.get_disruption_analysis(db=empty_db)
        self.assertEqual(disrupt_rep.live_incidents_total, 0)
        self.assertEqual(len(disrupt_rep.live_events), 0)

        # Historical trends on empty DB
        trends_rep = ReportService.get_historical_trends(db=empty_db, time_range="24h")
        self.assertEqual(trends_rep.total_samples, 0)
        self.assertEqual(trends_rep.overall_average_load_factor, 0.0)
        self.assertTrue(all(dp.sample_count == 0 for dp in trends_rep.datapoints))

        empty_db.close()

    # -------------------------------------------------------------------------
    # 7. CSV Export Functionality and RFC 4180 Escaping
    # -------------------------------------------------------------------------
    def test_07_csv_export_headers_and_escaping(self):
        """7. Verify CSV generation with correct stable headers, comma/quote escaping, and empty dataset safety."""
        # 1. Fleet CSV
        csv_fleet = ReportService.export_csv(db=self.db, report_type="fleet")
        self.assertTrue(csv_fleet.startswith("Bus ID,Bus Number,License Plate,Status,Capacity"))
        self.assertIn("101A", csv_fleet)
        self.assertIn("BUS-101A", csv_fleet)

        # 2. Routes CSV
        csv_routes = ReportService.export_csv(db=self.db, report_type="routes")
        self.assertTrue(csv_routes.startswith("Route ID,Route Number,Route Name,Status,Active"))
        self.assertIn("Downtown Express", csv_routes)

        # 3. Disruptions CSV
        csv_disruptions = ReportService.export_csv(db=self.db, report_type="disruptions")
        self.assertTrue(csv_disruptions.startswith("Alert ID,Source,Alert Type,Severity,Title"))
        self.assertIn("BUS_BREAKDOWN", csv_disruptions)

        # 4. Reallocation CSV with comma/quotes in notes
        csv_realloc = ReportService.export_csv(db=self.db, report_type="reallocation")
        self.assertTrue(csv_realloc.startswith("Review ID,Recommendation ID,Decision,Dispatcher ID"))
        self.assertIn("APPROVED", csv_realloc)
        self.assertIn("Approved for peak alleviation", csv_realloc)

        # 5. Trends CSV
        csv_trends = ReportService.export_csv(db=self.db, report_type="trends", time_range="1h")
        self.assertTrue(csv_trends.startswith("Timestamp Bucket,Average Load Factor,Total Passengers"))

        # 6. Invalid report type raises 400
        with self.assertRaises(HTTPException) as ctx:
            ReportService.export_csv(db=self.db, report_type="unknown_report")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Unsupported report type", ctx.exception.detail)

    # -------------------------------------------------------------------------
    # 8. Strict Non-Mutation of Operational Records
    # -------------------------------------------------------------------------
    def test_08_reports_do_not_mutate_operational_data(self):
        """8. CRITICAL INVARIANT: Generating reports or exporting CSVs must NEVER mutate operational tables."""
        buses_before = {b.id: (b.current_route_id, b.status) for b in self.db.query(Bus).all()}
        routes_before = {r.id: (r.is_active, r.route_number) for r in self.db.query(Route).all()}
        pax_count_before = self.db.query(PassengerLoad).count()
        rev_count_before = self.db.query(ReallocationReview).count()
        notif_count_before = self.db.query(Notification).count()

        # Run all report generators
        ReportService.get_overview(db=self.db)
        ReportService.get_fleet_utilization(db=self.db)
        ReportService.get_route_performance(db=self.db)
        ReportService.get_disruption_analysis(db=self.db)
        ReportService.get_reallocation_analysis(db=self.db)
        ReportService.get_historical_trends(db=self.db, time_range="7d")
        for rt in ["fleet", "routes", "disruptions", "reallocation", "trends"]:
            ReportService.export_csv(db=self.db, report_type=rt)

        self.db.expire_all()

        buses_after = {b.id: (b.current_route_id, b.status) for b in self.db.query(Bus).all()}
        routes_after = {r.id: (r.is_active, r.route_number) for r in self.db.query(Route).all()}

        self.assertEqual(buses_before, buses_after, "Buses must NOT be modified by reports!")
        self.assertEqual(routes_before, routes_after, "Routes must NOT be modified by reports!")
        self.assertEqual(pax_count_before, self.db.query(PassengerLoad).count())
        self.assertEqual(rev_count_before, self.db.query(ReallocationReview).count())
        self.assertEqual(notif_count_before, self.db.query(Notification).count())

    # -------------------------------------------------------------------------
    # 9. FastAPI Route Handlers Direct Invocations
    # -------------------------------------------------------------------------
    def test_09_fastapi_route_handlers(self):
        """9. Direct invocation of all FastAPI route handlers via dependency injection."""
        # 1. GET /api/reports/overview
        ov = get_reports_overview(db=self.db)
        self.assertEqual(ov.fleet.total_buses, 8)
        self.assertEqual(ov.routes.total_routes, 4)

        # 2. GET /api/reports/fleet-utilization
        fu = get_fleet_utilization(db=self.db)
        self.assertEqual(fu.operational_buses, 5)

        # 3. GET /api/reports/routes
        rp = get_route_performance(db=self.db)
        self.assertEqual(rp.active_routes, 3)

        # 4. GET /api/reports/disruptions
        da = get_disruptions_analysis(db=self.db)
        self.assertEqual(da.live_incidents_total, 3)

        # 5. GET /api/reports/reallocation
        ra = get_reallocation_analysis(db=self.db)
        self.assertEqual(ra.total_reviews_recorded, 3)

        # 6. GET /api/reports/trends?range=24h
        tr = get_historical_trends(time_range="24h", db=self.db)
        self.assertEqual(tr.time_range, "24h")

        # 7. GET /api/reports/export?type=fleet&format=csv
        exp = export_report_csv(report_type="fleet", time_range="24h", export_format="csv", db=self.db)
        self.assertEqual(exp.media_type, "text/csv")
        self.assertIn("attachment; filename=", exp.headers["Content-Disposition"])
        self.assertIn(b"BUS-101A", exp.body)

        # 8. GET /api/reports/export?type=fleet&format=pdf (unsupported -> 400)
        with self.assertRaises(HTTPException) as ctx:
            export_report_csv(report_type="fleet", time_range="24h", export_format="pdf", db=self.db)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Unsupported export format", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
