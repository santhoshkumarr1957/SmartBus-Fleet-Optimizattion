"""Stage 4 Verification Test Suite for SmartBus.

Tests all Stage 4 criteria:
1. LOW, NORMAL, HIGH, and CRITICAL classifications.
2. Exact threshold boundaries: 0.50, 0.80, and 1.00.
3. Available-seat calculations (non-negative guarantee).
4. Multiple historical records for one bus: only the latest record must count.
5. Route passenger and capacity aggregation.
6. Detection of overloaded and underutilized routes and explainable opportunities.
7. Empty or missing telemetry handling.
8. Zero and invalid capacity handling.
9. Existing live endpoints remain functional.
10. High-demand simulator data produces expected intelligence results.
11. Immutability: No historical records are deleted or modified by the intelligence engine.
12. No route assignments are modified by the intelligence engine.
"""
import unittest
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.bus import Bus
from app.models.route import Route
from app.models.passenger_load import PassengerLoad
from app.models.bus_position import BusPosition
from app.services.load_intelligence import (
    classify_load_factor,
    calculate_load_factor,
    calculate_available_seats,
    generate_route_assessment,
    detect_reallocation_opportunities,
    LoadIntelligenceService,
)
from app.schemas.intelligence import (
    IntelligenceOverviewResponse,
    RouteIntelligenceResponse,
    BusIntelligenceResponse,
    ReallocationOpportunityResponse,
)
from app.api.routes.intelligence import (
    get_intelligence_overview,
    get_intelligence_routes,
    get_intelligence_buses,
    get_intelligence_opportunities,
)
from app.api.routes.health import get_health
from app.api.routes.buses import get_live_buses
from app.api.routes.routes import get_live_routes
from app.simulator.runner import SimulatorRunner


class TestStage4LoadIntelligence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db: Session = SessionLocal()

    @classmethod
    def tearDownClass(cls):
        if cls.db:
            cls.db.close()

    # -------------------------------------------------------------------------
    # 1 & 2. Classifications and Exact Threshold Boundaries
    # -------------------------------------------------------------------------
    def test_01_classification_threshold_boundaries(self):
        """Test exact threshold boundaries: 0.50, 0.80, and 1.00."""
        # LOW: < 0.50
        self.assertEqual(classify_load_factor(0.0), "LOW")
        self.assertEqual(classify_load_factor(0.25), "LOW")
        self.assertEqual(classify_load_factor(0.4999), "LOW")

        # Boundary at 0.50 -> NORMAL
        self.assertEqual(classify_load_factor(0.50), "NORMAL")
        self.assertEqual(classify_load_factor(0.65), "NORMAL")
        self.assertEqual(classify_load_factor(0.7999), "NORMAL")

        # Boundary at 0.80 -> HIGH
        self.assertEqual(classify_load_factor(0.80), "HIGH")
        self.assertEqual(classify_load_factor(0.90), "HIGH")
        self.assertEqual(classify_load_factor(0.9999), "HIGH")

        # Boundary at 1.00 -> CRITICAL
        self.assertEqual(classify_load_factor(1.00), "CRITICAL")
        self.assertEqual(classify_load_factor(1.05), "CRITICAL")
        self.assertEqual(classify_load_factor(1.50), "CRITICAL")

    # -------------------------------------------------------------------------
    # 3. Available Seats and Calculation Correctness
    # -------------------------------------------------------------------------
    def test_02_available_seats_calculation(self):
        """Test available seat calculations and ensure non-negative guarantee."""
        # Normal scenarios
        self.assertEqual(calculate_available_seats(60, 40), 20)
        self.assertEqual(calculate_available_seats(60, 0), 60)
        self.assertEqual(calculate_available_seats(60, 60), 0)

        # Passenger load exceeding physical capacity should never yield negative seats
        self.assertEqual(calculate_available_seats(60, 75), 0)

        # Negative passengers handled safely
        self.assertEqual(calculate_available_seats(60, -5), 60)

        # Load factors
        self.assertEqual(calculate_load_factor(30, 60), 0.5)
        self.assertEqual(calculate_load_factor(48, 60), 0.8)
        self.assertEqual(calculate_load_factor(60, 60), 1.0)
        self.assertEqual(calculate_load_factor(0, 60), 0.0)

    # -------------------------------------------------------------------------
    # 4. Multiple Historical Records: Only Latest Record Used
    # -------------------------------------------------------------------------
    def test_03_multiple_historical_records_uses_latest_only(self):
        """Ensure that multiple historical records for a bus do not get summed together."""
        # Find an existing bus
        bus = self.db.query(Bus).filter(Bus.status != "INACTIVE").first()
        self.assertIsNotNone(bus)

        # Retrieve the latest load record via service
        latest = LoadIntelligenceService.get_latest_passenger_load(self.db, bus.id)
        if latest:
            # Query all records for this bus
            all_loads = self.db.query(PassengerLoad).filter(PassengerLoad.bus_id == bus.id).all()
            if len(all_loads) > 1:
                # Summing all loads would be strictly greater than the latest single load
                total_historical = sum(l.current_load for l in all_loads)
                self.assertGreater(total_historical, latest.current_load)

            # Verify that the service's returned record matches the maximum timestamp / id
            db_latest = (
                self.db.query(PassengerLoad)
                .filter(PassengerLoad.bus_id == bus.id)
                .order_by(PassengerLoad.timestamp.desc(), PassengerLoad.id.desc())
                .first()
            )
            self.assertEqual(latest.id, db_latest.id)
            self.assertEqual(latest.current_load, db_latest.current_load)

    # -------------------------------------------------------------------------
    # 5. Route Passenger and Capacity Aggregation
    # -------------------------------------------------------------------------
    def test_04_route_passenger_and_capacity_aggregation(self):
        """Route passengers and capacities must strictly match the sum of assigned buses."""
        route_intel = LoadIntelligenceService.get_route_intelligence(self.db)
        bus_intel = LoadIntelligenceService.get_bus_intelligence(self.db)

        self.assertGreater(len(route_intel), 0)
        self.assertGreater(len(bus_intel), 0)

        # Map buses by route_id
        bus_map = {}
        for b in bus_intel:
            if b.route_id is not None:
                bus_map.setdefault(b.route_id, []).append(b)

        for route in route_intel:
            assigned_buses = bus_map.get(route.route_id, [])
            expected_passengers = sum(b.passenger_count for b in assigned_buses)
            expected_capacity = sum(b.capacity for b in assigned_buses)
            expected_available = max(0, expected_capacity - expected_passengers)

            self.assertEqual(route.number_of_buses, len(assigned_buses))
            self.assertEqual(route.total_passengers, expected_passengers)
            self.assertEqual(route.total_capacity, expected_capacity)
            self.assertEqual(route.available_seats, expected_available)

            if expected_capacity > 0:
                expected_lf = round(expected_passengers / expected_capacity, 4)
            else:
                expected_lf = 0.0

            self.assertEqual(route.load_factor, expected_lf)
            self.assertEqual(route.status, classify_load_factor(expected_lf))

    # -------------------------------------------------------------------------
    # 6. Detection of Overloaded and Underutilized Routes & Opportunities
    # -------------------------------------------------------------------------
    def test_05_reallocation_opportunity_detection_and_reasons(self):
        """Test pairing overloaded routes (HIGH/CRITICAL) with underutilized routes (LOW)."""
        sample_routes = [
            RouteIntelligenceResponse(
                route_id=1,
                route_number="101",
                number_of_buses=2,
                total_passengers=118,
                total_capacity=120,
                available_seats=2,
                load_factor=0.9833,
                status="HIGH",
                assessment="High passenger load",
            ),
            RouteIntelligenceResponse(
                route_id=2,
                route_number="202",
                number_of_buses=2,
                total_passengers=40,
                total_capacity=120,
                available_seats=80,
                load_factor=0.3333,
                status="LOW",
                assessment="Route is underutilized",
            ),
            RouteIntelligenceResponse(
                route_id=3,
                route_number="303",
                number_of_buses=2,
                total_passengers=75,
                total_capacity=120,
                available_seats=45,
                load_factor=0.6250,
                status="NORMAL",
                assessment="Optimal operational load",
            ),
        ]

        opps = detect_reallocation_opportunities(sample_routes)
        self.assertEqual(len(opps), 1)

        opp = opps[0]
        self.assertEqual(opp.overloaded_route_id, 1)
        self.assertEqual(opp.overloaded_route_number, "101")
        self.assertEqual(opp.overloaded_route_status, "HIGH")
        self.assertEqual(opp.underutilized_route_id, 2)
        self.assertEqual(opp.underutilized_route_number, "202")
        self.assertEqual(opp.underutilized_route_load_factor, 0.3333)
        self.assertIn("101", opp.reason)
        self.assertIn("202", opp.reason)
        self.assertIn("HIGH", opp.reason)

        # Test with no opportunities (all NORMAL)
        all_normal = [
            RouteIntelligenceResponse(
                route_id=1,
                route_number="101",
                number_of_buses=2,
                total_passengers=75,
                total_capacity=120,
                available_seats=45,
                load_factor=0.625,
                status="NORMAL",
                assessment="Optimal",
            ),
            RouteIntelligenceResponse(
                route_id=2,
                route_number="202",
                number_of_buses=2,
                total_passengers=75,
                total_capacity=120,
                available_seats=45,
                load_factor=0.625,
                status="NORMAL",
                assessment="Optimal",
            ),
        ]
        self.assertEqual(len(detect_reallocation_opportunities(all_normal)), 0)

        # Test with underutilized route having 0 buses (cannot spare a bus)
        no_bus_low = [
            RouteIntelligenceResponse(
                route_id=1,
                route_number="101",
                number_of_buses=2,
                total_passengers=120,
                total_capacity=120,
                available_seats=0,
                load_factor=1.0,
                status="CRITICAL",
                assessment="Critical",
            ),
            RouteIntelligenceResponse(
                route_id=2,
                route_number="202",
                number_of_buses=0,
                total_passengers=0,
                total_capacity=0,
                available_seats=0,
                load_factor=0.0,
                status="LOW",
                assessment="No buses",
            ),
        ]
        self.assertEqual(len(detect_reallocation_opportunities(no_bus_low)), 0)

    # -------------------------------------------------------------------------
    # 7 & 8. Empty Telemetry and Zero Capacity Handling
    # -------------------------------------------------------------------------
    def test_06_zero_and_invalid_capacity_handling(self):
        """Zero capacity must not raise division-by-zero and must return 0.0 load factor."""
        self.assertEqual(calculate_load_factor(0, 0), 0.0)
        self.assertEqual(calculate_load_factor(10, 0), 0.0)
        self.assertEqual(calculate_load_factor(10, -5), 0.0)

        self.assertEqual(calculate_available_seats(0, 0), 0)
        self.assertEqual(calculate_available_seats(0, 10), 0)
        self.assertEqual(calculate_available_seats(-10, 10), 0)

    def test_07_empty_telemetry_handling(self):
        """Assessment and calculations handle route with zero buses or empty telemetry explicitly."""
        assessment = generate_route_assessment(
            status="LOW",
            load_factor=0.0,
            total_passengers=0,
            total_capacity=0,
            available_seats=0,
            number_of_buses=0,
        )
        self.assertIn("no active buses", assessment.lower())

    # -------------------------------------------------------------------------
    # 9. API Endpoints Return Valid Pydantic Schemas
    # -------------------------------------------------------------------------
    def test_08_api_endpoints_schemas_and_overview_consistency(self):
        """Test GET /api/intelligence endpoints and verify overview consistency."""
        overview = get_intelligence_overview(self.db)
        self.assertIsInstance(overview, IntelligenceOverviewResponse)
        self.assertEqual(
            overview.low_routes + overview.normal_routes + overview.high_routes + overview.critical_routes,
            overview.total_routes,
        )
        self.assertEqual(
            overview.routes_needing_attention,
            overview.high_routes + overview.critical_routes,
        )

        routes = get_intelligence_routes(self.db)
        self.assertIsInstance(routes, list)
        self.assertEqual(len(routes), overview.total_routes)
        for r in routes:
            self.assertIsInstance(r, RouteIntelligenceResponse)
            self.assertGreaterEqual(r.available_seats, 0)
            self.assertIn(r.status, ["LOW", "NORMAL", "HIGH", "CRITICAL"])
            self.assertTrue(len(r.assessment) > 0)

        buses = get_intelligence_buses(self.db)
        self.assertIsInstance(buses, list)
        self.assertEqual(len(buses), overview.total_buses)
        for b in buses:
            self.assertIsInstance(b, BusIntelligenceResponse)
            self.assertGreaterEqual(b.available_seats, 0)
            self.assertGreaterEqual(b.passenger_count, 0)
            self.assertLessEqual(b.passenger_count, b.capacity)
            self.assertIn(b.status, ["LOW", "NORMAL", "HIGH", "CRITICAL"])

        opps = get_intelligence_opportunities(self.db)
        self.assertIsInstance(opps, list)
        self.assertEqual(len(opps), overview.potential_reallocation_opportunities)
        for o in opps:
            self.assertIsInstance(o, ReallocationOpportunityResponse)
            self.assertIn(o.overloaded_route_status, ["HIGH", "CRITICAL"])
            self.assertLess(o.underutilized_route_load_factor, 0.50)

    # -------------------------------------------------------------------------
    # 10. Existing Live Endpoints Remain Functional
    # -------------------------------------------------------------------------
    def test_09_existing_endpoints_remain_functional(self):
        """Verify /api/health, /api/buses/live, and /api/routes/live remain healthy."""
        health = get_health()
        self.assertEqual(health.status, "ok")

        live_buses = get_live_buses(self.db)
        self.assertGreaterEqual(len(live_buses), 6)

        live_routes = get_live_routes(self.db)
        self.assertGreaterEqual(len(live_routes), 3)

    # -------------------------------------------------------------------------
    # 11. High-Demand Scenario Verification
    # -------------------------------------------------------------------------
    def test_10_high_demand_produces_intelligence_results(self):
        """Simulator in high_demand produces expected intelligence flags and opportunities."""
        runner = SimulatorRunner(scenario="high_demand", interval_seconds=1.0)
        runner.setup(self.db)
        runner.step(self.db)

        overview = get_intelligence_overview(self.db)
        routes = get_intelligence_routes(self.db)
        opps = get_intelligence_opportunities(self.db)

        # High demand generates overloaded route 101 and underutilized route 202
        route_map = {r.route_number: r for r in routes}
        self.assertIn("101", route_map)
        self.assertIn("202", route_map)

        self.assertIn(route_map["101"].status, ["HIGH", "CRITICAL"])
        self.assertEqual(route_map["202"].status, "LOW")

        self.assertGreaterEqual(overview.routes_needing_attention, 1)
        self.assertGreaterEqual(overview.potential_reallocation_opportunities, 1)
        self.assertGreaterEqual(len(opps), 1)

    # -------------------------------------------------------------------------
    # 12. Immutability and No Route Reallocation
    # -------------------------------------------------------------------------
    def test_11_records_not_deleted_and_bus_routes_unchanged(self):
        """Intelligence engine must NOT delete/mutate historical loads or alter bus route assignments."""
        loads_count_before = self.db.query(PassengerLoad).count()
        positions_count_before = self.db.query(BusPosition).count()

        bus_route_assignments_before = {
            b.id: b.current_route_id for b in self.db.query(Bus).all()
        }

        # Run all intelligence services repeatedly
        LoadIntelligenceService.get_overview(self.db)
        LoadIntelligenceService.get_route_intelligence(self.db)
        LoadIntelligenceService.get_bus_intelligence(self.db)
        LoadIntelligenceService.get_opportunities(self.db)

        loads_count_after = self.db.query(PassengerLoad).count()
        positions_count_after = self.db.query(BusPosition).count()

        bus_route_assignments_after = {
            b.id: b.current_route_id for b in self.db.query(Bus).all()
        }

        # Counts must not have decreased (no records deleted)
        self.assertEqual(loads_count_before, loads_count_after)
        self.assertEqual(positions_count_before, positions_count_after)

        # Route assignments must be 100% unchanged
        self.assertEqual(bus_route_assignments_before, bus_route_assignments_after)


if __name__ == "__main__":
    unittest.main()
