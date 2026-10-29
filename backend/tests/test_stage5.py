"""Stage 5 Verification Test Suite for SmartBus.

Tests all Stage 5 criteria:
1. Overloaded (HIGH/CRITICAL) and underutilized (LOW) route detection using Stage 4 intelligence.
2. Suitable and unsuitable bus candidates (e.g. status, target route exclusion, spare capacity).
3. Capacity and occupancy boundaries (threshold boundary testing, non-negative guarantees).
4. No demand-imbalance scenarios (all normal, no overloaded routes, no underutilized routes).
5. Missing or insufficient operational data handling (missing GPS telemetry, missing stops).
6. Stable, deterministic recommendation ranking.
7. Advisory-only guarantee: recommendations are advisory; route assignments and records are immutable.
8. API endpoints response schema validity and query parameter filtering.
9. Regression verification for existing Stage 4 intelligence services.
"""
import unittest
from datetime import datetime, timezone
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.db.base import Base
from app.models.route import Route
from app.models.stop import Stop
from app.models.bus import Bus
from app.models.bus_position import BusPosition
from app.models.passenger_load import PassengerLoad

from app.services.load_intelligence import (
    LoadIntelligenceService,
    classify_load_factor,
    calculate_load_factor,
    calculate_available_seats,
)
from app.schemas.intelligence import (
    RouteIntelligenceResponse,
    BusIntelligenceResponse,
)
from app.services.optimization import (
    OptimizationService,
    calculate_target_severity_score,
    calculate_source_spare_score,
    calculate_bus_suitability_score,
    calculate_proximity_score,
    determine_priority,
    evaluate_bus_reallocation,
)
from app.schemas.optimization import (
    ReallocationRecommendationResponse,
    OptimizationOverviewResponse,
)
from app.api.routes.optimization import (
    get_optimization_recommendations,
    get_optimization_overview,
)


def create_in_memory_db() -> Session:
    """Create a completely self-contained in-memory SQLite database session with all models."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    SessionClass = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionClass()
    session._engine = engine
    return session


def close_db(session: Session) -> None:
    """Cleanly close session and dispose underlying engine to prevent resource leaks."""
    if session:
        engine = getattr(session, "_engine", None)
        session.close()
        if engine:
            engine.dispose()


class TestOptimizationScoringFormulas(unittest.TestCase):
    """Unit tests for transparent rule-based scoring components and boundary conditions."""

    def test_01_target_severity_scoring(self):
        """Test target route severity scoring: CRITICAL (30-35) and HIGH (20-30)."""
        # CRITICAL routes (LF >= 1.00):
        # Base 30.0 + min(5.0, (LF - 1.0) * 10.0)
        self.assertEqual(calculate_target_severity_score(1.00, "CRITICAL"), 30.0)
        self.assertEqual(calculate_target_severity_score(1.20, "CRITICAL"), 32.0)
        self.assertEqual(calculate_target_severity_score(1.50, "CRITICAL"), 35.0)  # Capped at 35.0
        self.assertEqual(calculate_target_severity_score(2.00, "CRITICAL"), 35.0)

        # HIGH routes (0.80 <= LF < 1.00):
        # Base 20.0 + ((LF - 0.80) / 0.20) * 10.0
        self.assertEqual(calculate_target_severity_score(0.80, "HIGH"), 20.0)
        self.assertEqual(calculate_target_severity_score(0.90, "HIGH"), 25.0)
        self.assertEqual(calculate_target_severity_score(0.95, "HIGH"), 27.5)
        self.assertEqual(calculate_target_severity_score(0.99, "HIGH"), 29.5)

        # NORMAL and LOW routes: not in need of capacity addition
        self.assertEqual(calculate_target_severity_score(0.79, "NORMAL"), 0.0)
        self.assertEqual(calculate_target_severity_score(0.30, "LOW"), 0.0)

    def test_02_source_spare_scoring(self):
        """Test source route spare capacity scoring: headroom (0-20) + fleet bonus (5)."""
        # Route with 0% load and 2 buses: full 20 headroom + 5 bonus = 25.0
        self.assertEqual(calculate_source_spare_score(0.00, number_of_buses=2), 25.0)

        # Route with 25% load (half of 50% limit) and 2 buses: 10 headroom + 5 bonus = 15.0
        self.assertEqual(calculate_source_spare_score(0.25, number_of_buses=2), 15.0)

        # Single-bus penalty (leaves route unserviced): 0% load but only 1 bus -> 20.0 (no 5 bonus)
        self.assertEqual(calculate_source_spare_score(0.00, number_of_buses=1), 20.0)
        self.assertEqual(calculate_source_spare_score(0.25, number_of_buses=1), 10.0)

        # Routes not underutilized (>= 0.50): 0.0
        self.assertEqual(calculate_source_spare_score(0.50, number_of_buses=2), 0.0)
        self.assertEqual(calculate_source_spare_score(0.85, number_of_buses=2), 0.0)

    def test_03_bus_suitability_scoring(self):
        """Test candidate bus suitability scoring: low occupancy (0-15) + available seats (0-10)."""
        # Completely empty bus (0 passengers / 60 capacity):
        # Occupancy: 15.0, Capacity: 10.0 -> 25.0
        self.assertEqual(calculate_bus_suitability_score(0, 60, 60), 25.0)

        # Half-full bus (30 passengers / 60 capacity):
        # Occupancy: (1 - 0.5) * 15 = 7.5, Capacity: (30/60) * 10 = 5.0 -> 12.5
        self.assertEqual(calculate_bus_suitability_score(30, 60, 30), 12.5)

        # Crowded bus (>= 80% load): unsuitable
        self.assertEqual(calculate_bus_suitability_score(48, 60, 12), 0.0)
        self.assertEqual(calculate_bus_suitability_score(55, 60, 5), 0.0)

        # Invalid capacity or 0 available seats
        self.assertEqual(calculate_bus_suitability_score(0, 0, 0), 0.0)
        self.assertEqual(calculate_bus_suitability_score(60, 60, 0), 0.0)

    def test_04_proximity_scoring_and_missing_gps(self):
        """Test geographic proximity scoring with known distance and missing GPS telemetry."""
        # Short deadhead (<= 2 km): full 15.0 points
        score, limitation = calculate_proximity_score(1500.0)
        self.assertEqual(score, 15.0)
        self.assertIsNone(limitation)

        # Moderate deadhead (4 km): decays smoothly: 15.0 - (4 - 2)*1.3 = 12.4
        score, limitation = calculate_proximity_score(4000.0)
        self.assertEqual(score, 12.4)
        self.assertIsNone(limitation)

        # Extended deadhead (> 12 km): clamped at minimum 2.0 points
        score, limitation = calculate_proximity_score(18000.0)
        self.assertEqual(score, 2.0)
        self.assertIsNone(limitation)

        # Missing GPS telemetry (None): neutral baseline 7.5 points and explicit limitation
        score, limitation = calculate_proximity_score(None)
        self.assertEqual(score, 7.5)
        self.assertIsNotNone(limitation)
        self.assertIn("neutral baseline", limitation)

    def test_05_priority_tiers(self):
        """Test deterministic priority tier assignment."""
        self.assertEqual(determine_priority(85.0, "CRITICAL"), "HIGH")
        self.assertEqual(determine_priority(75.0, "HIGH"), "HIGH")
        self.assertEqual(determine_priority(68.0, "CRITICAL"), "HIGH")  # Critical urgency bonus
        self.assertEqual(determine_priority(68.0, "HIGH"), "MEDIUM")
        self.assertEqual(determine_priority(50.0, "HIGH"), "MEDIUM")
        self.assertEqual(determine_priority(45.0, "HIGH"), "LOW")


class TestOptimizationFleetScenarios(unittest.TestCase):
    """End-to-end scenario tests with simulated transit networks."""

    def setUp(self):
        self.db = create_in_memory_db()

    def tearDown(self):
        close_db(self.db)

    def _seed_transit_network(self) -> None:
        """Seed a 3-route transit network:
        - Route 101: Overloaded target (CRITICAL: 100% load)
        - Route 202: Underutilized source (LOW: 30% load)
        - Route 303: Balanced route (NORMAL: 60% load)
        """
        # 1. Routes
        r101 = Route(id=1, route_number="101", name="Downtown Express", origin="A", destination="B", is_active=True)
        r202 = Route(id=2, route_number="202", name="Suburban Feeder", origin="C", destination="D", is_active=True)
        r303 = Route(id=3, route_number="303", name="Crosstown Link", origin="E", destination="F", is_active=True)
        self.db.add_all([r101, r202, r303])
        self.db.flush()

        # 2. Stops for Route 101 (target route)
        s1 = Stop(id=1, route_id=1, name="Origin Terminal", sequence_order=1, latitude=37.7749, longitude=-122.4194)
        s2 = Stop(id=2, route_id=1, name="Downtown Central", sequence_order=2, latitude=37.7890, longitude=-122.4015)
        self.db.add_all([s1, s2])

        # 3. Buses
        # Route 101 buses (Overloaded: 60/60 and 60/60 -> 100%)
        b101a = Bus(id=1, bus_number="101A", license_plate="P-101A", capacity=60, current_route_id=1, status="ACTIVE")
        b101b = Bus(id=2, bus_number="101B", license_plate="P-101B", capacity=60, current_route_id=1, status="ACTIVE")

        # Route 202 buses (Underutilized: 10/60 and 26/60 -> 36/120 = 30%)
        b202a = Bus(id=3, bus_number="202A", license_plate="P-202A", capacity=60, current_route_id=2, status="ACTIVE")
        b202b = Bus(id=4, bus_number="202B", license_plate="P-202B", capacity=60, current_route_id=2, status="ACTIVE")

        # Route 303 buses (Normal: 36/60 and 36/60 -> 60%)
        b303a = Bus(id=5, bus_number="303A", license_plate="P-303A", capacity=60, current_route_id=3, status="ACTIVE")
        b303b = Bus(id=6, bus_number="303B", license_plate="P-303B", capacity=60, current_route_id=3, status="ACTIVE")

        self.db.add_all([b101a, b101b, b202a, b202b, b303a, b303b])
        self.db.flush()

        # 4. Passenger Loads
        now = datetime.now(timezone.utc)
        loads = [
            PassengerLoad(bus_id=1, current_load=60, capacity=60, load_factor=1.0, timestamp=now),
            PassengerLoad(bus_id=2, current_load=60, capacity=60, load_factor=1.0, timestamp=now),
            PassengerLoad(bus_id=3, current_load=10, capacity=60, load_factor=0.1667, timestamp=now),
            PassengerLoad(bus_id=4, current_load=26, capacity=60, load_factor=0.4333, timestamp=now),
            PassengerLoad(bus_id=5, current_load=36, capacity=60, load_factor=0.60, timestamp=now),
            PassengerLoad(bus_id=6, current_load=36, capacity=60, load_factor=0.60, timestamp=now),
        ]
        self.db.add_all(loads)

        # 5. GPS Positions for candidate buses (near Route 101 origin)
        positions = [
            BusPosition(bus_id=3, latitude=37.7800, longitude=-122.4200, speed=25.0, timestamp=now),  # ~600m away
            BusPosition(bus_id=4, latitude=37.8100, longitude=-122.4350, speed=30.0, timestamp=now),  # ~4.1 km away
        ]
        self.db.add_all(positions)
        self.db.commit()

    def test_06_overloaded_and_underutilized_detection_and_candidate_ranking(self):
        """Test detection of overloaded target (101) and underutilized source (202), and candidate ranking."""
        self._seed_transit_network()

        recs = OptimizationService.generate_recommendations(self.db)
        self.assertEqual(len(recs), 2)  # Two candidate buses (202A and 202B) on source Route 202

        # Verify all recommendations target Route 101 from Source Route 202
        for r in recs:
            self.assertEqual(r.target_route_id, 1)
            self.assertEqual(r.target_route_number, "101")
            self.assertEqual(r.target_route_status, "CRITICAL")
            self.assertEqual(r.source_route_id, 2)
            self.assertEqual(r.source_route_number, "202")
            self.assertEqual(r.source_route_status, "LOW")
            self.assertTrue(r.is_advisory)
            self.assertIn("advisory", r.advisory_note.lower())

        # Verify stable ranking: 202A (lower occupancy, closer GPS) must rank higher than 202B
        top_rec = recs[0]
        second_rec = recs[1]

        self.assertEqual(top_rec.candidate_bus_id, 3)
        self.assertEqual(top_rec.candidate_bus_number, "202A")
        self.assertEqual(second_rec.candidate_bus_id, 4)
        self.assertEqual(second_rec.candidate_bus_number, "202B")

        self.assertGreater(top_rec.score, second_rec.score)
        self.assertLess(top_rec.current_occupancy, second_rec.current_occupancy)
        self.assertGreater(top_rec.available_capacity, second_rec.available_capacity)

        # Proximity verified
        self.assertIsNotNone(top_rec.distance_meters)
        self.assertIsNotNone(top_rec.estimated_travel_time_minutes)
        self.assertLess(top_rec.distance_meters, second_rec.distance_meters)

        # Projected load relief verified
        # Route 101 has 120 passengers / 120 capacity (1.0). Adding 60 cap yields 120/180 = 0.6667 (66.7%)
        self.assertAlmostEqual(top_rec.projected_target_load_factor, 0.6667, places=3)
        self.assertIn("101", top_rec.reason)
        self.assertIn("202", top_rec.reason)

    def test_07_suitable_vs_unsuitable_bus_filtering(self):
        """Test that buses in MAINTENANCE/INACTIVE, buses already on target route, or crowded buses are excluded."""
        self._seed_transit_network()

        # Add an INACTIVE bus and a crowded bus to Route 202
        b_inactive = Bus(id=7, bus_number="202-INACT", license_plate="P-202-INACT", capacity=60, current_route_id=2, status="INACTIVE")
        b_maint = Bus(id=8, bus_number="202-MAINT", license_plate="P-202-MAINT", capacity=60, current_route_id=2, status="MAINTENANCE")
        b_crowded = Bus(id=9, bus_number="202-FULL", license_plate="P-202-FULL", capacity=60, current_route_id=2, status="ACTIVE")
        self.db.add_all([b_inactive, b_maint, b_crowded])
        self.db.flush()

        now = datetime.now(timezone.utc)
        self.db.add(PassengerLoad(bus_id=9, current_load=55, capacity=60, load_factor=0.9167, timestamp=now))
        self.db.commit()

        recs = OptimizationService.generate_recommendations(self.db)
        candidate_bus_numbers = [r.candidate_bus_number for r in recs]

        # Inactive, maintenance, and crowded buses must NOT appear in recommendations
        self.assertNotIn("202-INACT", candidate_bus_numbers)
        self.assertNotIn("202-MAINT", candidate_bus_numbers)
        self.assertNotIn("202-FULL", candidate_bus_numbers)

        # Buses already assigned to target route (101A, 101B) must NEVER be recommended
        self.assertNotIn("101A", candidate_bus_numbers)
        self.assertNotIn("101B", candidate_bus_numbers)

    def test_08_no_demand_imbalance_scenarios(self):
        """Test scenarios where no recommendations should be generated."""
        # Scenario A: Empty DB
        self.assertEqual(len(OptimizationService.generate_recommendations(self.db)), 0)

        # Scenario B: All routes are NORMAL load
        now = datetime.now(timezone.utc)
        r1 = Route(id=1, route_number="101", name="R1", origin="A", destination="B", is_active=True)
        r2 = Route(id=2, route_number="202", name="R2", origin="C", destination="D", is_active=True)
        self.db.add_all([r1, r2])
        self.db.flush()

        b1 = Bus(id=1, bus_number="101A", license_plate="P1", capacity=60, current_route_id=1, status="ACTIVE")
        b2 = Bus(id=2, bus_number="202A", license_plate="P2", capacity=60, current_route_id=2, status="ACTIVE")
        self.db.add_all([b1, b2])
        self.db.flush()

        # Both at 60% load (NORMAL: 0.50 - 0.80)
        self.db.add(PassengerLoad(bus_id=1, current_load=36, capacity=60, load_factor=0.60, timestamp=now))
        self.db.add(PassengerLoad(bus_id=2, current_load=36, capacity=60, load_factor=0.60, timestamp=now))
        self.db.commit()

        self.assertEqual(len(OptimizationService.generate_recommendations(self.db)), 0)

        # Scenario C: Target route is CRITICAL, but source route is also HIGH (no low-load route)
        # Update Bus 2 to 90% load (HIGH)
        self.db.add(PassengerLoad(bus_id=1, current_load=60, capacity=60, load_factor=1.0, timestamp=now))
        self.db.add(PassengerLoad(bus_id=2, current_load=54, capacity=60, load_factor=0.90, timestamp=now))
        self.db.commit()

        self.assertEqual(len(OptimizationService.generate_recommendations(self.db)), 0)

    def test_09_missing_gps_telemetry_handling(self):
        """Test handling of candidate bus with missing GPS telemetry."""
        now = datetime.now(timezone.utc)
        r1 = Route(id=1, route_number="101", name="R1", origin="A", destination="B", is_active=True)
        r2 = Route(id=2, route_number="202", name="R2", origin="C", destination="D", is_active=True)
        self.db.add_all([r1, r2])
        self.db.flush()

        b1 = Bus(id=1, bus_number="101A", license_plate="P1", capacity=60, current_route_id=1, status="ACTIVE")
        b2 = Bus(id=2, bus_number="202A", license_plate="P2", capacity=60, current_route_id=2, status="ACTIVE")
        self.db.add_all([b1, b2])
        self.db.flush()

        # Route 101 CRITICAL, Route 202 LOW
        self.db.add(PassengerLoad(bus_id=1, current_load=60, capacity=60, load_factor=1.0, timestamp=now))
        self.db.add(PassengerLoad(bus_id=2, current_load=10, capacity=60, load_factor=0.1667, timestamp=now))
        self.db.commit()
        # Note: NO BusPosition added for b2

        recs = OptimizationService.generate_recommendations(self.db)
        self.assertEqual(len(recs), 1)

        rec = recs[0]
        self.assertIsNone(rec.distance_meters)
        self.assertIsNone(rec.estimated_travel_time_minutes)
        self.assertEqual(rec.feasibility_status, "CONDITIONALLY_FEASIBLE")

        # Must report data limitation clearly
        limitation_str = " ".join(rec.limitations).lower()
        self.assertIn("gps", limitation_str)
        self.assertIn("telemetry", limitation_str)

    def test_10_single_bus_source_service_abandonment_warning(self):
        """Test that reallocating from a source route with only 1 bus flags a service warning."""
        now = datetime.now(timezone.utc)
        r1 = Route(id=1, route_number="101", name="R1", origin="A", destination="B", is_active=True)
        r2 = Route(id=2, route_number="202", name="R2", origin="C", destination="D", is_active=True)
        self.db.add_all([r1, r2])
        self.db.flush()

        b1 = Bus(id=1, bus_number="101A", license_plate="P1", capacity=60, current_route_id=1, status="ACTIVE")
        # Route 202 only has ONE bus
        b2 = Bus(id=2, bus_number="202A", license_plate="P2", capacity=60, current_route_id=2, status="ACTIVE")
        self.db.add_all([b1, b2])
        self.db.flush()

        self.db.add(PassengerLoad(bus_id=1, current_load=60, capacity=60, load_factor=1.0, timestamp=now))
        self.db.add(PassengerLoad(bus_id=2, current_load=5, capacity=60, load_factor=0.0833, timestamp=now))
        self.db.commit()

        recs = OptimizationService.generate_recommendations(self.db)
        self.assertEqual(len(recs), 1)

        rec = recs[0]
        limitation_str = " ".join(rec.limitations).lower()
        self.assertIn("only 1 active bus", limitation_str)
        self.assertEqual(rec.feasibility_status, "CONDITIONALLY_FEASIBLE")

    def test_11_best_only_and_query_filtering(self):
        """Test best_only=True query parameter returns only the top recommendation per pair."""
        self._seed_transit_network()

        # Default best_only=False returns both 202A and 202B
        all_recs = OptimizationService.generate_recommendations(self.db, best_only=False)
        self.assertEqual(len(all_recs), 2)

        # best_only=True returns only the single highest-scoring bus (202A)
        best_recs = OptimizationService.generate_recommendations(self.db, best_only=True)
        self.assertEqual(len(best_recs), 1)
        self.assertEqual(best_recs[0].candidate_bus_number, "202A")

        # min_score filter
        high_score_recs = OptimizationService.generate_recommendations(self.db, min_score=999.0)
        self.assertEqual(len(high_score_recs), 0)

        # target_route_id filter
        filtered_recs = OptimizationService.generate_recommendations(self.db, target_route_id=1)
        self.assertEqual(len(filtered_recs), 2)
        filtered_empty = OptimizationService.generate_recommendations(self.db, target_route_id=99)
        self.assertEqual(len(filtered_empty), 0)


class TestOptimizationAPI(unittest.TestCase):
    """Test API endpoint route handlers and Pydantic schema serialization."""

    def setUp(self):
        self.db = create_in_memory_db()

    def tearDown(self):
        close_db(self.db)

    def test_12_api_recommendations_and_overview(self):
        """Test GET /api/optimization/recommendations and GET /api/optimization/overview."""
        # Seed network
        now = datetime.now(timezone.utc)
        r1 = Route(id=1, route_number="101", name="R1", origin="A", destination="B", is_active=True)
        r2 = Route(id=2, route_number="202", name="R2", origin="C", destination="D", is_active=True)
        self.db.add_all([r1, r2])
        self.db.flush()

        b1 = Bus(id=1, bus_number="101A", license_plate="P1", capacity=60, current_route_id=1, status="ACTIVE")
        b2 = Bus(id=2, bus_number="202A", license_plate="P2", capacity=60, current_route_id=2, status="ACTIVE")
        b3 = Bus(id=3, bus_number="202B", license_plate="P3", capacity=60, current_route_id=2, status="ACTIVE")
        self.db.add_all([b1, b2, b3])
        self.db.flush()

        self.db.add(PassengerLoad(bus_id=1, current_load=60, capacity=60, load_factor=1.0, timestamp=now))
        self.db.add(PassengerLoad(bus_id=2, current_load=15, capacity=60, load_factor=0.25, timestamp=now))
        self.db.add(PassengerLoad(bus_id=3, current_load=20, capacity=60, load_factor=0.33, timestamp=now))
        self.db.commit()

        # Call API handler directly
        recs = get_optimization_recommendations(db=self.db)
        self.assertIsInstance(recs, list)
        self.assertEqual(len(recs), 2)

        for rec in recs:
            self.assertIsInstance(rec, ReallocationRecommendationResponse)
            self.assertTrue(rec.is_advisory)
            self.assertGreaterEqual(rec.score, 0.0)
            self.assertLessEqual(rec.score, 100.0)
            self.assertIn(rec.priority, ["HIGH", "MEDIUM", "LOW"])
            self.assertIn(rec.feasibility_status, ["FEASIBLE", "CONDITIONALLY_FEASIBLE", "LIMITED_DATA", "INFEASIBLE"])
            self.assertTrue(len(rec.reason) > 0)
            self.assertEqual(rec.target_route_number, "101")
            self.assertEqual(rec.source_route_number, "202")

        # Test overview endpoint
        overview = get_optimization_overview(db=self.db)
        self.assertIsInstance(overview, OptimizationOverviewResponse)
        self.assertEqual(overview.total_recommendations, 2)
        self.assertEqual(
            overview.high_priority_count + overview.medium_priority_count + overview.low_priority_count,
            2,
        )
        self.assertTrue(overview.is_advisory)


class TestOptimizationImmutabilityAndRegression(unittest.TestCase):
    """Test immutability guarantees and verify Stage 4 compatibility."""

    def setUp(self):
        self.db = create_in_memory_db()

    def tearDown(self):
        close_db(self.db)

    def test_13_immutability_guarantee_no_reassignments(self):
        """Verify that optimization NEVER deletes records or alters bus route assignments."""
        now = datetime.now(timezone.utc)
        r1 = Route(id=1, route_number="101", name="R1", origin="A", destination="B", is_active=True)
        r2 = Route(id=2, route_number="202", name="R2", origin="C", destination="D", is_active=True)
        self.db.add_all([r1, r2])
        self.db.flush()

        b1 = Bus(id=1, bus_number="101A", license_plate="P1", capacity=60, current_route_id=1, status="ACTIVE")
        b2 = Bus(id=2, bus_number="202A", license_plate="P2", capacity=60, current_route_id=2, status="ACTIVE")
        self.db.add_all([b1, b2])
        self.db.flush()

        self.db.add(PassengerLoad(bus_id=1, current_load=60, capacity=60, load_factor=1.0, timestamp=now))
        self.db.add(PassengerLoad(bus_id=2, current_load=15, capacity=60, load_factor=0.25, timestamp=now))
        self.db.commit()

        # Capture pre-optimization snapshot
        routes_before = self.db.query(Route).count()
        buses_before = self.db.query(Bus).count()
        loads_before = self.db.query(PassengerLoad).count()
        assignments_before = {b.id: b.current_route_id for b in self.db.query(Bus).all()}

        # Run optimization services repeatedly
        OptimizationService.generate_recommendations(self.db)
        OptimizationService.get_overview(self.db)
        get_optimization_recommendations(db=self.db)

        # Capture post-optimization state
        routes_after = self.db.query(Route).count()
        buses_after = self.db.query(Bus).count()
        loads_after = self.db.query(PassengerLoad).count()
        assignments_after = {b.id: b.current_route_id for b in self.db.query(Bus).all()}

        # Database rows must not change
        self.assertEqual(routes_before, routes_after)
        self.assertEqual(buses_before, buses_after)
        self.assertEqual(loads_before, loads_after)

        # Bus route assignments must be 100% untouched
        self.assertEqual(assignments_before, assignments_after)
        self.assertEqual(self.db.query(Bus).filter(Bus.id == 2).first().current_route_id, 2)

    def test_14_capacity_and_occupancy_boundaries(self):
        """Boundary test: 79% load is suitable, 80% is unsuitable, 0 capacity handled safely."""
        # Exact suitability boundary: 47 / 60 = 78.3% -> suitable (> 0 score)
        self.assertGreater(calculate_bus_suitability_score(47, 60, 13), 0.0)

        # Exact suitability boundary: 48 / 60 = 80.0% -> unsuitable (0.0 score)
        self.assertEqual(calculate_bus_suitability_score(48, 60, 12), 0.0)

        # 0 capacity and negative passengers handled safely
        self.assertEqual(calculate_bus_suitability_score(0, 0, 0), 0.0)
        self.assertEqual(calculate_bus_suitability_score(-5, 60, 60), 25.0)

        # Available seats boundary
        self.assertEqual(calculate_available_seats(60, 60), 0)
        self.assertEqual(calculate_available_seats(60, 65), 0)
        self.assertEqual(calculate_available_seats(0, 0), 0)

    def test_15_deterministic_scoring_tie_breaking(self):
        """Ensure that recommendation ranking is strictly deterministic even with identical loads and positions."""
        now = datetime.now(timezone.utc)
        r1 = Route(id=1, route_number="101", name="R1", origin="A", destination="B", is_active=True)
        r2 = Route(id=2, route_number="202", name="R2", origin="C", destination="D", is_active=True)
        self.db.add_all([r1, r2])
        self.db.flush()

        # Two identical buses on Route 202
        b1 = Bus(id=1, bus_number="101A", license_plate="P1", capacity=60, current_route_id=1, status="ACTIVE")
        b2 = Bus(id=2, bus_number="202A", license_plate="P2", capacity=60, current_route_id=2, status="ACTIVE")
        b3 = Bus(id=3, bus_number="202B", license_plate="P3", capacity=60, current_route_id=2, status="ACTIVE")
        self.db.add_all([b1, b2, b3])
        self.db.flush()

        self.db.add(PassengerLoad(bus_id=1, current_load=60, capacity=60, load_factor=1.0, timestamp=now))
        # Exactly identical loads: 10 passengers each
        self.db.add(PassengerLoad(bus_id=2, current_load=10, capacity=60, load_factor=0.1667, timestamp=now))
        self.db.add(PassengerLoad(bus_id=3, current_load=10, capacity=60, load_factor=0.1667, timestamp=now))
        self.db.commit()

        run1 = [r.candidate_bus_id for r in OptimizationService.generate_recommendations(self.db)]
        run2 = [r.candidate_bus_id for r in OptimizationService.generate_recommendations(self.db)]
        run3 = [r.candidate_bus_id for r in OptimizationService.generate_recommendations(self.db)]

        self.assertEqual(run1, run2)
        self.assertEqual(run2, run3)
        self.assertEqual(run1, [2, 3])  # Deterministic tie-break by bus_id

    def test_16_advisory_status_guarantees(self):
        """Verify that every single recommendation explicitly carries is_advisory=True."""
        now = datetime.now(timezone.utc)
        r1 = Route(id=1, route_number="101", name="R1", origin="A", destination="B", is_active=True)
        r2 = Route(id=2, route_number="202", name="R2", origin="C", destination="D", is_active=True)
        self.db.add_all([r1, r2])
        self.db.flush()

        b1 = Bus(id=1, bus_number="101A", license_plate="P1", capacity=60, current_route_id=1, status="ACTIVE")
        b2 = Bus(id=2, bus_number="202A", license_plate="P2", capacity=60, current_route_id=2, status="ACTIVE")
        self.db.add_all([b1, b2])
        self.db.flush()

        self.db.add(PassengerLoad(bus_id=1, current_load=60, capacity=60, load_factor=1.0, timestamp=now))
        self.db.add(PassengerLoad(bus_id=2, current_load=10, capacity=60, load_factor=0.1667, timestamp=now))
        self.db.commit()

        recs = OptimizationService.generate_recommendations(self.db)
        self.assertGreater(len(recs), 0)
        for r in recs:
            self.assertTrue(r.is_advisory)
            self.assertIn("advisory", r.advisory_note.lower())

    def test_17_stage4_compatibility(self):
        """Verify that Stage 4 intelligence engine functions identically alongside optimization."""
        now = datetime.now(timezone.utc)
        r1 = Route(id=1, route_number="101", name="R1", origin="A", destination="B", is_active=True)
        r2 = Route(id=2, route_number="202", name="R2", origin="C", destination="D", is_active=True)
        self.db.add_all([r1, r2])
        self.db.flush()

        b1 = Bus(id=1, bus_number="101A", license_plate="P1", capacity=60, current_route_id=1, status="ACTIVE")
        b2 = Bus(id=2, bus_number="202A", license_plate="P2", capacity=60, current_route_id=2, status="ACTIVE")
        self.db.add_all([b1, b2])
        self.db.flush()

        self.db.add(PassengerLoad(bus_id=1, current_load=60, capacity=60, load_factor=1.0, timestamp=now))
        self.db.add(PassengerLoad(bus_id=2, current_load=10, capacity=60, load_factor=0.1667, timestamp=now))
        self.db.commit()

        # Stage 4 methods work without error
        overview = LoadIntelligenceService.get_overview(self.db)
        routes_intel = LoadIntelligenceService.get_route_intelligence(self.db)
        buses_intel = LoadIntelligenceService.get_bus_intelligence(self.db)
        opps = LoadIntelligenceService.get_opportunities(self.db)

        self.assertEqual(overview.total_routes, 2)
        self.assertEqual(overview.total_buses, 2)
        self.assertEqual(len(routes_intel), 2)
        self.assertEqual(len(buses_intel), 2)
        self.assertEqual(len(opps), 1)


if __name__ == "__main__":
    unittest.main()
