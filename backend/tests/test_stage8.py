"""Stage 8 Verification Test Suite for SmartBus (TRANSIGHT).

Tests all Stage 8 criteria:
1. Supported disruption types: BUS_BREAKDOWN, ROUTE_CLOSURE, DEMAND_SPIKE, SERVICE_DELAY.
2. Input validation: Invalid types, out-of-range parameters, and missing target vehicles/routes raise HTTP 400.
3. Non-existent identifiers: Invalid bus or route IDs/numbers raise HTTP 404.
4. Capacity and occupancy boundaries: 0 capacity, 100% capacity loss, over-capacity calculations.
5. Missing telemetry handling: Missing GPS coordinates or passenger records handled safely.
6. Calculation correctness: Before-vs-after loads, available seats, fleet availability, resilience metrics.
7. Strict isolation and non-mutation: Zero database writes, bus route assignments, and fleet statuses remain unchanged.
8. Scenario caching and repeatability: Scenarios can be retrieved by ID; repeatable execution.
9. Reallocation advisory suggestions: Reallocation proposals generated on simulated corridor congestion.
10. Compatibility with Stage 4, Stage 5, and Stage 7 behavior.
"""
import unittest
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.db.base import Base
from app.models.route import Route
from app.models.stop import Stop
from app.models.bus import Bus
from app.models.bus_position import BusPosition
from app.models.passenger_load import PassengerLoad
from app.models.reallocation_review import ReallocationReview

from app.schemas.disruption import (
    DisruptionSimulationRequest,
    DisruptionSimulationResponse,
    DisruptionTypeInfo,
)
from app.services.disruption import DisruptionService
from app.api.routes.disruption import (
    get_supported_disruption_types,
    simulate_disruption_scenario,
    get_recent_scenarios,
    get_scenario_impact,
)
from app.services.load_intelligence import classify_load_factor
from app.services.optimization import OptimizationService


def create_in_memory_db() -> Session:
    """Create a completely self-contained in-memory SQLite database session."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    SessionClass = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionClass()
    session._engine = engine
    return session


def close_db(session: Session) -> None:
    """Cleanly close session and dispose underlying engine."""
    if session:
        engine = getattr(session, "_engine", None)
        session.close()
        if engine:
            engine.dispose()


def seed_test_transit_network(db: Session):
    """Seed test routes, buses, stops, and telemetry records:

    - Route 101: "Downtown Express" (2 buses: 101A [load 40, cap 60], 101B [load 35, cap 60]) -> LF 75/120 = 0.625 (NORMAL)
    - Route 202: "Suburban Loop" (2 buses: 202A [load 10, cap 60], 202B [load 5, cap 60]) -> LF 15/120 = 0.125 (LOW)
    - Route 303: "Crosstown Line" (1 bus: 303A [load 45, cap 50]) -> LF 45/50 = 0.900 (HIGH)
    - Bus 999S: Standby spare bus (load 0, cap 60, unassigned route)
    - Bus 888M: Missing GPS and passenger history bus (cap 60, route 202)
    """
    now = datetime.now(timezone.utc)

    # Routes
    r101 = Route(
        id=1,
        route_number="101",
        name="Downtown Express",
        origin="Central Station",
        destination="Market Square",
        is_active=True,
    )
    r202 = Route(
        id=2,
        route_number="202",
        name="Suburban Loop",
        origin="Suburban Hub",
        destination="Valley Mall",
        is_active=True,
    )
    r303 = Route(
        id=3,
        route_number="303",
        name="Crosstown Line",
        origin="North Terminal",
        destination="South Station",
        is_active=True,
    )
    db.add_all([r101, r202, r303])
    db.flush()

    # Stops
    s101_1 = Stop(id=1, route_id=r101.id, name="Central Station", sequence_order=1, latitude=37.7749, longitude=-122.4194)
    s101_2 = Stop(id=2, route_id=r101.id, name="Market Square", sequence_order=2, latitude=37.7850, longitude=-122.4080)
    s202_1 = Stop(id=3, route_id=r202.id, name="Suburban Hub", sequence_order=1, latitude=37.7800, longitude=-122.4100)
    s202_2 = Stop(id=4, route_id=r202.id, name="Valley Mall", sequence_order=2, latitude=37.7900, longitude=-122.4200)
    s303_1 = Stop(id=5, route_id=r303.id, name="North Terminal", sequence_order=1, latitude=37.8000, longitude=-122.4300)
    db.add_all([s101_1, s101_2, s202_1, s202_2, s303_1])
    db.flush()

    # Buses
    b101a = Bus(id=1, bus_number="101A", license_plate="BUS-101A", capacity=60, current_route_id=r101.id, status="ACTIVE")
    b101b = Bus(id=2, bus_number="101B", license_plate="BUS-101B", capacity=60, current_route_id=r101.id, status="ACTIVE")
    b202a = Bus(id=3, bus_number="202A", license_plate="BUS-202A", capacity=60, current_route_id=r202.id, status="ACTIVE")
    b202b = Bus(id=4, bus_number="202B", license_plate="BUS-202B", capacity=60, current_route_id=r202.id, status="ACTIVE")
    b303a = Bus(id=5, bus_number="303A", license_plate="BUS-303A", capacity=50, current_route_id=r303.id, status="ACTIVE")
    b999s = Bus(id=6, bus_number="999S", license_plate="BUS-999S", capacity=60, current_route_id=None, status="IDLE")
    b888m = Bus(id=7, bus_number="888M", license_plate="BUS-888M", capacity=60, current_route_id=r202.id, status="ACTIVE")
    db.add_all([b101a, b101b, b202a, b202b, b303a, b999s, b888m])
    db.flush()

    # Passenger loads
    l1 = PassengerLoad(id=1, bus_id=b101a.id, current_load=40, capacity=60, load_factor=round(40 / 60, 4), timestamp=now)
    l2 = PassengerLoad(id=2, bus_id=b101b.id, current_load=35, capacity=60, load_factor=round(35 / 60, 4), timestamp=now)
    l3 = PassengerLoad(id=3, bus_id=b202a.id, current_load=10, capacity=60, load_factor=round(10 / 60, 4), timestamp=now)
    l4 = PassengerLoad(id=4, bus_id=b202b.id, current_load=5, capacity=60, load_factor=round(5 / 60, 4), timestamp=now)
    l5 = PassengerLoad(id=5, bus_id=b303a.id, current_load=45, capacity=50, load_factor=round(45 / 50, 4), timestamp=now)
    l6 = PassengerLoad(id=6, bus_id=b999s.id, current_load=0, capacity=60, load_factor=0.0, timestamp=now)
    # Note: b888m intentionally has NO passenger load record and NO GPS position
    db.add_all([l1, l2, l3, l4, l5, l6])

    # Bus positions
    p1 = BusPosition(id=1, bus_id=b101a.id, latitude=37.7750, longitude=-122.4190, speed=25.0, heading=90.0, timestamp=now)
    p2 = BusPosition(id=2, bus_id=b101b.id, latitude=37.7800, longitude=-122.4150, speed=30.0, heading=85.0, timestamp=now)
    p3 = BusPosition(id=3, bus_id=b202a.id, latitude=37.7810, longitude=-122.4090, speed=20.0, heading=45.0, timestamp=now)
    p4 = BusPosition(id=4, bus_id=b202b.id, latitude=37.7820, longitude=-122.4080, speed=22.0, heading=50.0, timestamp=now)
    p5 = BusPosition(id=5, bus_id=b303a.id, latitude=37.8010, longitude=-122.4290, speed=15.0, heading=180.0, timestamp=now)
    db.add_all([p1, p2, p3, p4, p5])
    db.commit()


class TestStage8DisruptionSimulation(unittest.TestCase):
    def setUp(self):
        self.db = create_in_memory_db()
        seed_test_transit_network(self.db)
        DisruptionService.clear_cache()

    def tearDown(self):
        close_db(self.db)

    # -------------------------------------------------------------------------
    # 1. Catalog Supported Disruption Types
    # -------------------------------------------------------------------------
    def test_01_catalog_supported_disruption_types(self):
        """1. Verify catalog of supported disruption simulation types."""
        types = DisruptionService.get_supported_types()
        type_keys = [t.type for t in types]

        self.assertIn("BUS_BREAKDOWN", type_keys)
        self.assertIn("ROUTE_CLOSURE", type_keys)
        self.assertIn("DEMAND_SPIKE", type_keys)
        self.assertIn("SERVICE_DELAY", type_keys)
        self.assertEqual(len(types), 4)

        for t in types:
            self.assertTrue(len(t.name) > 0)
            self.assertTrue(len(t.description) > 0)
            self.assertIsInstance(t.required_parameters, list)
            self.assertIsInstance(t.optional_parameters, list)

    # -------------------------------------------------------------------------
    # 2. Bus Breakdown Simulation and Metrics
    # -------------------------------------------------------------------------
    def test_02_bus_breakdown_simulation_and_metrics(self):
        """2. Simulate bus breakdown and verify capacity, load, and resilience calculations."""
        req = DisruptionSimulationRequest(
            disruption_type="BUS_BREAKDOWN",
            bus_number="101A",
            notes="Mechanical breakdown test",
        )
        res = DisruptionService.simulate_disruption(db=self.db, request=req)

        self.assertTrue(res.is_simulated)
        self.assertTrue(res.scenario_id.startswith("SCEN-BUS_BREAKDOWN-"))
        self.assertEqual(res.parameters["bus_number"], "101A")

        # Bus impact check
        target_bus = next((b for b in res.affected_buses if b.bus_number == "101A"), None)
        self.assertIsNotNone(target_bus)
        self.assertEqual(target_bus.status_before, "ACTIVE")
        self.assertEqual(target_bus.status_after, "BROKEN_DOWN")
        self.assertFalse(target_bus.is_operational_after)

        # Route 101 impact check
        r101_impact = next((r for r in res.affected_routes if r.route_number == "101"), None)
        self.assertIsNotNone(r101_impact)
        self.assertTrue(r101_impact.is_directly_affected)
        self.assertEqual(r101_impact.buses_count_before, 2)
        self.assertEqual(r101_impact.buses_count_after, 1)
        self.assertEqual(r101_impact.capacity_before, 120)
        self.assertEqual(r101_impact.capacity_after, 60)
        # Load factor before: 75/120 = 0.625; after: 75/60 = 1.25 (CRITICAL)
        self.assertAlmostEqual(r101_impact.load_factor_before, 0.625, places=3)
        self.assertAlmostEqual(r101_impact.load_factor_after, 1.25, places=2)
        self.assertEqual(r101_impact.status_before, "NORMAL")
        self.assertEqual(r101_impact.status_after, "CRITICAL")
        self.assertEqual(r101_impact.severity_change, "SEVERELY_DEGRADED")

        # Network Resilience Metrics
        metrics = res.resilience_metrics
        # Baseline total operational buses: 7; simulated operational buses: 6 -> ~85.7%
        self.assertAlmostEqual(metrics.fleet_availability_pct, round(6 / 7 * 100.0, 1), places=1)
        # Total baseline capacity = 60+60+60+60+60+50 = 350 on active routes; lost = 60
        self.assertEqual(metrics.capacity_lost, 60)
        self.assertGreater(metrics.capacity_retention_pct, 0.0)
        self.assertEqual(metrics.routes_critical_count, 1)
        self.assertGreater(metrics.resilience_score, 0.0)
        self.assertIn(metrics.resilience_rating, ["EXCELLENT", "ADEQUATE", "VULNERABLE", "CRITICAL"])

    # -------------------------------------------------------------------------
    # 3. Route Closure Simulation and Stranded Buses
    # -------------------------------------------------------------------------
    def test_03_route_closure_simulation_and_stranded_buses(self):
        """3. Simulate route closure and verify route shutdown and stranded vehicles."""
        req = DisruptionSimulationRequest(
            disruption_type="ROUTE_CLOSURE",
            route_number="202",
            notes="Emergency road closure",
        )
        res = DisruptionService.simulate_disruption(db=self.db, request=req)

        self.assertEqual(res.parameters["route_number"], "202")

        # Route 202 impact
        r202_impact = next((r for r in res.affected_routes if r.route_number == "202"), None)
        self.assertIsNotNone(r202_impact)
        self.assertTrue(r202_impact.is_directly_affected)
        self.assertEqual(r202_impact.status_after, "CLOSED")
        self.assertEqual(r202_impact.capacity_after, 0)
        self.assertEqual(r202_impact.available_seats_after, 0)
        self.assertEqual(r202_impact.severity_change, "CLOSED")

        # Buses on route 202 become stranded
        b202a_impact = next((b for b in res.affected_buses if b.bus_number == "202A"), None)
        b202b_impact = next((b for b in res.affected_buses if b.bus_number == "202B"), None)
        self.assertIsNotNone(b202a_impact)
        self.assertIsNotNone(b202b_impact)
        self.assertEqual(b202a_impact.status_after, "STRANDED_ON_CLOSED_ROUTE")
        self.assertEqual(b202b_impact.status_after, "STRANDED_ON_CLOSED_ROUTE")
        self.assertFalse(b202a_impact.is_operational_after)
        self.assertFalse(b202b_impact.is_operational_after)

        # Service continuity: 2 out of 3 routes operating = 66.7%
        self.assertAlmostEqual(res.resilience_metrics.service_continuity_pct, 66.7, places=1)

    # -------------------------------------------------------------------------
    # 4. Demand Spike Simulation
    # -------------------------------------------------------------------------
    def test_04_demand_spike_simulation_route_specific_and_systemwide(self):
        """4. Simulate passenger demand surge: corridor-specific and network-wide."""
        # A. Corridor-specific spike (+50% on Route 101)
        req_corridor = DisruptionSimulationRequest(
            disruption_type="DEMAND_SPIKE",
            route_number="101",
            spike_percentage=50.0,
        )
        res_corridor = DisruptionService.simulate_disruption(db=self.db, request=req_corridor)

        r101 = next(r for r in res_corridor.affected_routes if r.route_number == "101")
        # Baseline passengers: 75. Added 50% = +38 passengers -> 113 total
        self.assertEqual(r101.passengers_before, 75)
        self.assertEqual(r101.passengers_after, 113)
        self.assertEqual(r101.capacity_after, 120)
        self.assertAlmostEqual(r101.load_factor_after, round(113 / 120, 4), places=3)
        self.assertEqual(r101.status_after, "HIGH")

        # Unaffected route should remain unchanged
        r202 = next(r for r in res_corridor.affected_routes if r.route_number == "202")
        self.assertEqual(r202.passengers_after, r202.passengers_before)
        self.assertEqual(r202.severity_change, "UNCHANGED")

        # B. System-wide demand spike (+100%)
        req_system = DisruptionSimulationRequest(
            disruption_type="DEMAND_SPIKE",
            spike_percentage=100.0,
        )
        res_system = DisruptionService.simulate_disruption(db=self.db, request=req_system)
        for r in res_system.affected_routes:
            self.assertGreater(r.passengers_after, r.passengers_before)

    # -------------------------------------------------------------------------
    # 5. Service Delay Simulation
    # -------------------------------------------------------------------------
    def test_05_service_delay_simulation_route_and_bus(self):
        """5. Simulate service delay and headway expansion on route and vehicle."""
        # A. Route delay on Route 303 (30 mins)
        req_route = DisruptionSimulationRequest(
            disruption_type="SERVICE_DELAY",
            route_number="303",
            delay_minutes=30.0,
        )
        res_route = DisruptionService.simulate_disruption(db=self.db, request=req_route)

        r303 = next(r for r in res_route.affected_routes if r.route_number == "303")
        self.assertTrue(r303.is_directly_affected)
        # Demand multiplier: 1.0 + min(0.60, 3 * 0.08) = 1.24
        # Capacity multiplier: max(0.65, 1.0 - 3 * 0.05) = 0.85
        # Base pax = 45 -> 45 * 1.24 = 56
        # Base cap = 50 -> 50 * 0.85 = 42
        self.assertEqual(r303.passengers_after, 56)
        self.assertEqual(r303.capacity_after, 42)
        self.assertAlmostEqual(r303.load_factor_after, round(56 / 42, 4), places=3)
        self.assertEqual(r303.status_after, "CRITICAL")

        # B. Bus delay on Bus 101A (25 mins)
        req_bus = DisruptionSimulationRequest(
            disruption_type="SERVICE_DELAY",
            bus_number="101A",
            delay_minutes=25.0,
        )
        res_bus = DisruptionService.simulate_disruption(db=self.db, request=req_bus)
        b101a = next(b for b in res_bus.affected_buses if b.bus_number == "101A")
        self.assertEqual(b101a.status_after, "DELAYED")
        self.assertTrue(b101a.is_operational_after)
        self.assertIn("Vehicle impacted by simulated delay", b101a.impact_note)

    # -------------------------------------------------------------------------
    # 6. Invalid Disruption Type Validation
    # -------------------------------------------------------------------------
    def test_06_invalid_disruption_type_raises_400(self):
        """6. Invalid or unsupported disruption type raises HTTP 400 Bad Request."""
        req = DisruptionSimulationRequest(
            disruption_type="ALIEN_INVASION",
            route_number="101",
        )
        with self.assertRaises(HTTPException) as ctx:
            DisruptionService.simulate_disruption(db=self.db, request=req)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Unsupported disruption type", ctx.exception.detail)

    # -------------------------------------------------------------------------
    # 7. Invalid Parameter Values Validation
    # -------------------------------------------------------------------------
    def test_07_invalid_parameters_raise_400(self):
        """7. Missing target entities or out-of-range numerical parameters raise HTTP 400."""
        # Missing bus for BUS_BREAKDOWN
        req_no_bus = DisruptionSimulationRequest(disruption_type="BUS_BREAKDOWN")
        with self.assertRaises(HTTPException) as ctx:
            DisruptionService.simulate_disruption(db=self.db, request=req_no_bus)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Target bus must be specified", ctx.exception.detail)

        # Missing route for ROUTE_CLOSURE
        req_no_route = DisruptionSimulationRequest(disruption_type="ROUTE_CLOSURE")
        with self.assertRaises(HTTPException) as ctx:
            DisruptionService.simulate_disruption(db=self.db, request=req_no_route)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Target route must be specified", ctx.exception.detail)

        # Pydantic schema validation rejects out-of-range values
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            DisruptionSimulationRequest(
                disruption_type="DEMAND_SPIKE",
                route_number="101",
                spike_percentage=2.0,  # Below minimum 5.0%
            )
        with self.assertRaises(ValidationError):
            DisruptionSimulationRequest(
                disruption_type="SERVICE_DELAY",
                route_number="101",
                delay_minutes=300.0,  # Above maximum 240.0 minutes
            )

        # Service-level boundary validation
        req_spike = DisruptionSimulationRequest(disruption_type="DEMAND_SPIKE", route_number="101", spike_percentage=50.0)
        req_spike.spike_percentage = 2.0
        with self.assertRaises(HTTPException) as ctx:
            DisruptionService.simulate_disruption(db=self.db, request=req_spike)
        self.assertEqual(ctx.exception.status_code, 400)

        req_delay = DisruptionSimulationRequest(disruption_type="SERVICE_DELAY", route_number="101", delay_minutes=20.0)
        req_delay.delay_minutes = 300.0
        with self.assertRaises(HTTPException) as ctx:
            DisruptionService.simulate_disruption(db=self.db, request=req_delay)
        self.assertEqual(ctx.exception.status_code, 400)

    # -------------------------------------------------------------------------
    # 8. Non-Existent Identifier Validation
    # -------------------------------------------------------------------------
    def test_08_nonexistent_bus_and_route_raises_404(self):
        """8. Non-existent bus or route identifiers raise HTTP 404 Not Found."""
        req_bad_bus = DisruptionSimulationRequest(
            disruption_type="BUS_BREAKDOWN",
            bus_number="NONEXISTENT_999",
        )
        with self.assertRaises(HTTPException) as ctx:
            DisruptionService.simulate_disruption(db=self.db, request=req_bad_bus)
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertIn("not found in fleet", ctx.exception.detail)

        req_bad_route = DisruptionSimulationRequest(
            disruption_type="ROUTE_CLOSURE",
            route_number="NONEXISTENT_888",
        )
        with self.assertRaises(HTTPException) as ctx:
            DisruptionService.simulate_disruption(db=self.db, request=req_bad_route)
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertIn("not found in transit network", ctx.exception.detail)

    # -------------------------------------------------------------------------
    # 9. Strict Invariant: Zero Database Mutations
    # -------------------------------------------------------------------------
    def test_09_strict_database_immutability_and_scenario_isolation(self):
        """9. CRITICAL INVARIANT: Simulation must NEVER mutate operational database records.

        Verifies:
        - bus.current_route_id remains unchanged
        - bus.status remains unchanged
        - telemetry records count is identical
        - passenger load records are unmodified
        """
        # Baseline snapshot from database
        buses_before = {b.id: (b.current_route_id, b.status) for b in self.db.query(Bus).all()}
        routes_before = {r.id: (r.is_active, r.route_number) for r in self.db.query(Route).all()}
        pos_count_before = self.db.query(BusPosition).count()
        load_count_before = self.db.query(PassengerLoad).count()

        # Run multiple aggressive disruptions
        DisruptionService.simulate_disruption(
            db=self.db,
            request=DisruptionSimulationRequest(disruption_type="BUS_BREAKDOWN", bus_number="101A"),
        )
        DisruptionService.simulate_disruption(
            db=self.db,
            request=DisruptionSimulationRequest(disruption_type="ROUTE_CLOSURE", route_number="101"),
        )
        DisruptionService.simulate_disruption(
            db=self.db,
            request=DisruptionSimulationRequest(disruption_type="DEMAND_SPIKE", spike_percentage=200.0),
        )

        # Refresh database session
        self.db.expire_all()

        # Check buses
        buses_after = {b.id: (b.current_route_id, b.status) for b in self.db.query(Bus).all()}
        self.assertEqual(buses_before, buses_after, "Bus records must NOT be mutated by simulation!")

        # Check routes
        routes_after = {r.id: (r.is_active, r.route_number) for r in self.db.query(Route).all()}
        self.assertEqual(routes_before, routes_after, "Route records must NOT be mutated by simulation!")

        # Check telemetry counts
        self.assertEqual(pos_count_before, self.db.query(BusPosition).count())
        self.assertEqual(load_count_before, self.db.query(PassengerLoad).count())

    # -------------------------------------------------------------------------
    # 10. Scenario Repeatability and Caching
    # -------------------------------------------------------------------------
    def test_10_scenario_repeatability_and_caching(self):
        """10. Repeated simulation runs produce consistent metrics and cache storage."""
        req = DisruptionSimulationRequest(
            disruption_type="BUS_BREAKDOWN",
            bus_number="101B",
        )
        res1 = DisruptionService.simulate_disruption(db=self.db, request=req)
        res2 = DisruptionService.simulate_disruption(db=self.db, request=req)

        # Calculations are deterministic
        self.assertEqual(res1.resilience_metrics.capacity_lost, res2.resilience_metrics.capacity_lost)
        self.assertEqual(res1.resilience_metrics.resilience_score, res2.resilience_metrics.resilience_score)

        # Verify caching
        cached = DisruptionService.get_scenario_by_id(res1.scenario_id)
        self.assertIsNotNone(cached)
        self.assertEqual(cached.scenario_id, res1.scenario_id)

        briefs = DisruptionService.get_cached_scenarios()
        self.assertGreaterEqual(len(briefs), 2)

        # Nonexistent scenario returns None
        self.assertIsNone(DisruptionService.get_scenario_by_id("SCEN-NONEXISTENT-999"))

    # -------------------------------------------------------------------------
    # 11. Capacity and Occupancy Boundaries
    # -------------------------------------------------------------------------
    def test_11_capacity_and_occupancy_boundaries(self):
        """11. Boundary test: single bus route breakdown, 100% loss, available seats >= 0."""
        # Route 303 has only 1 bus (303A). Simulating its breakdown leaves Route 303 with 0 capacity
        req = DisruptionSimulationRequest(
            disruption_type="BUS_BREAKDOWN",
            bus_number="303A",
        )
        res = DisruptionService.simulate_disruption(db=self.db, request=req)

        r303 = next(r for r in res.affected_routes if r.route_number == "303")
        self.assertEqual(r303.capacity_after, 0)
        self.assertEqual(r303.buses_count_after, 0)
        self.assertEqual(r303.available_seats_after, 0)
        self.assertEqual(r303.status_after, "CRITICAL")
        self.assertEqual(r303.load_factor_after, 1.0)

    # -------------------------------------------------------------------------
    # 12. Missing Telemetry Handling
    # -------------------------------------------------------------------------
    def test_12_missing_telemetry_handling(self):
        """12. Bus without GPS position or passenger load record handled safely."""
        # Bus 888M was seeded without GPS or passenger load
        req = DisruptionSimulationRequest(
            disruption_type="BUS_BREAKDOWN",
            bus_number="888M",
        )
        res = DisruptionService.simulate_disruption(db=self.db, request=req)

        b888 = next(b for b in res.affected_buses if b.bus_number == "888M")
        self.assertEqual(b888.status_after, "BROKEN_DOWN")
        self.assertEqual(b888.passenger_count_before, 0)
        self.assertEqual(b888.passenger_count_after, 0)

    # -------------------------------------------------------------------------
    # 13. Simulated Reallocation Recommendations Integration
    # -------------------------------------------------------------------------
    def test_13_simulated_reallocations_integration(self):
        """13. Simulated congestion produces advisory Stage 5 reallocation proposals."""
        # Bus breakdown pushes Route 101 to CRITICAL (load factor 1.25)
        # Route 202 is underutilized (load factor 0.125 with 3 buses)
        req = DisruptionSimulationRequest(
            disruption_type="BUS_BREAKDOWN",
            bus_number="101A",
        )
        res = DisruptionService.simulate_disruption(db=self.db, request=req)

        # Suggested reallocations should propose donor bus from Route 202 to Route 101
        self.assertGreater(len(res.suggested_reallocations), 0)
        rec = res.suggested_reallocations[0]
        self.assertEqual(rec.target_route_number, "101")
        self.assertEqual(rec.source_route_number, "202")
        self.assertTrue(rec.is_advisory)
        self.assertIn("Simulated scenario recommendation only", rec.advisory_note)
        self.assertIn(rec.candidate_bus_number, ["202A", "202B", "888M"])

    # -------------------------------------------------------------------------
    # 14. Compatibility with Stage 4, Stage 5, and Stage 7 Behavior
    # -------------------------------------------------------------------------
    def test_14_compatibility_with_stages_4_5_and_7(self):
        """14. Verify Stage 4 load classification and Stage 7 review workflows remain fully intact."""
        # Stage 4 classification verification
        self.assertEqual(classify_load_factor(0.40), "LOW")
        self.assertEqual(classify_load_factor(0.65), "NORMAL")
        self.assertEqual(classify_load_factor(0.85), "HIGH")
        self.assertEqual(classify_load_factor(1.10), "CRITICAL")

        # Stage 7 review creation verification
        rev = ReallocationReview(
            recommendation_id="REC-TEST-101-202",
            decision="APPROVED",
            dispatcher_id="DISP-TEST",
            target_route_id=1,
            target_route_number="101",
            source_route_id=2,
            source_route_number="202",
            candidate_bus_id=3,
            candidate_bus_number="202A",
            score=85.0,
            priority="HIGH",
            notes="Approved during Stage 8 compatibility test",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.db.add(rev)
        self.db.commit()

        # Run disruption simulation
        req = DisruptionSimulationRequest(disruption_type="DEMAND_SPIKE", spike_percentage=25.0)
        res = DisruptionService.simulate_disruption(db=self.db, request=req)
        self.assertIsNotNone(res)

        # Verify Stage 7 review record remains completely intact
        db_rev = self.db.query(ReallocationReview).filter_by(recommendation_id="REC-TEST-101-202").first()
        self.assertIsNotNone(db_rev)
        self.assertEqual(db_rev.decision, "APPROVED")
        self.assertEqual(db_rev.dispatcher_id, "DISP-TEST")

    # -------------------------------------------------------------------------
    # 15. FastAPI Route Handlers via Dependency Injection
    # -------------------------------------------------------------------------
    def test_15_api_endpoints_via_dependency_injection(self):
        """15. Direct invocation of FastAPI route handler functions."""
        # GET /api/disruption/types
        types = get_supported_disruption_types()
        self.assertEqual(len(types), 4)

        # POST /api/disruption/simulate
        req = DisruptionSimulationRequest(
            disruption_type="SERVICE_DELAY",
            route_number="101",
            delay_minutes=15.0,
        )
        sim_res = simulate_disruption_scenario(request=req, db=self.db)
        self.assertEqual(sim_res.disruption_type, "SERVICE_DELAY")

        # GET /api/disruption/scenarios
        cached_list = get_recent_scenarios()
        self.assertGreater(len(cached_list), 0)

        # GET /api/disruption/scenarios/{scenario_id}
        impact_res = get_scenario_impact(scenario_id=sim_res.scenario_id)
        self.assertEqual(impact_res.scenario_id, sim_res.scenario_id)

        # GET /api/disruption/scenarios/{invalid_id} raises 404
        with self.assertRaises(HTTPException) as ctx:
            get_scenario_impact(scenario_id="INVALID_ID_999")
        self.assertEqual(ctx.exception.status_code, 404)

    # -------------------------------------------------------------------------
    # 16. DEMAND_SURGE Alias and Demand Multiplier
    # -------------------------------------------------------------------------
    def test_16_demand_surge_alias_and_multiplier(self):
        """16. DEMAND_SURGE accepted as alias and demand_multiplier converted to spike_percentage."""
        # Multiplier 1.5 -> +50%
        req = DisruptionSimulationRequest(
            disruption_type="DEMAND_SURGE",
            route_number="101",
            demand_multiplier=1.5,
        )
        res = DisruptionService.simulate_disruption(db=self.db, request=req)
        self.assertEqual(res.disruption_type, "DEMAND_SURGE")
        self.assertEqual(res.parameters.get("spike_percentage"), 50.0)

        # Multiplier out of range (< 1.05) raises ValidationError in Pydantic schema
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            DisruptionSimulationRequest(
                disruption_type="DEMAND_SURGE",
                route_number="101",
                demand_multiplier=0.9,
            )

        # Service-level boundary validation check
        req_mod = DisruptionSimulationRequest(
            disruption_type="DEMAND_SURGE",
            route_number="101",
            demand_multiplier=1.2,
        )
        req_mod.demand_multiplier = 0.9
        with self.assertRaises(HTTPException) as ctx:
            DisruptionService.simulate_disruption(db=self.db, request=req_mod)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("demand_multiplier must be between 1.05 and 4.0", ctx.exception.detail)

    # -------------------------------------------------------------------------
    # 17. Identifier and Boundary Validation
    # -------------------------------------------------------------------------
    def test_17_invalid_identifier_and_boundary_validation(self):
        """17. Negative IDs and route 'ALL' restrictions enforced."""
        # Negative bus_id
        req_neg_bus = DisruptionSimulationRequest(
            disruption_type="BUS_BREAKDOWN",
            bus_id=-1,
        )
        with self.assertRaises(HTTPException) as ctx:
            DisruptionService.simulate_disruption(db=self.db, request=req_neg_bus)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("must be a positive integer", ctx.exception.detail)

        # Negative route_id
        req_neg_route = DisruptionSimulationRequest(
            disruption_type="ROUTE_CLOSURE",
            route_id=-5,
        )
        with self.assertRaises(HTTPException) as ctx:
            DisruptionService.simulate_disruption(db=self.db, request=req_neg_route)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("must be a positive integer", ctx.exception.detail)

        # ROUTE_CLOSURE with route_number='ALL' raises 400
        req_all_close = DisruptionSimulationRequest(
            disruption_type="ROUTE_CLOSURE",
            route_number="ALL",
        )
        with self.assertRaises(HTTPException) as ctx:
            DisruptionService.simulate_disruption(db=self.db, request=req_all_close)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("'ALL' is not permitted", ctx.exception.detail)

        # DEMAND_SPIKE with route_number='ALL' is accepted and works systemwide
        req_all_spike = DisruptionSimulationRequest(
            disruption_type="DEMAND_SPIKE",
            route_number="ALL",
            spike_percentage=25.0,
        )
        res_all_spike = DisruptionService.simulate_disruption(db=self.db, request=req_all_spike)
        self.assertEqual(len(res_all_spike.affected_routes), 3)

        # SERVICE_DELAY with route_number='ALL' is accepted
        req_all_delay = DisruptionSimulationRequest(
            disruption_type="SERVICE_DELAY",
            route_number="ALL",
            delay_minutes=15.0,
        )
        res_all_delay = DisruptionService.simulate_disruption(db=self.db, request=req_all_delay)
        self.assertEqual(len(res_all_delay.affected_routes), 3)

    # -------------------------------------------------------------------------
    # 18. Notes and Operational Warnings in Response Schema
    # -------------------------------------------------------------------------
    def test_18_notes_and_warnings_in_response(self):
        """18. Optional notes and dynamic warnings returned in DisruptionSimulationResponse."""
        req = DisruptionSimulationRequest(
            disruption_type="BUS_BREAKDOWN",
            bus_number="303A",
            notes="Critical test breakdown for single bus line",
        )
        res = DisruptionService.simulate_disruption(db=self.db, request=req)
        self.assertEqual(res.notes, "Critical test breakdown for single bus line")
        self.assertIsInstance(res.warnings, list)
        self.assertGreater(len(res.warnings), 0)
        self.assertTrue(any("Route 303" in w for w in res.warnings))

    # -------------------------------------------------------------------------
    # 19. Scenario History Retention (Max 50)
    # -------------------------------------------------------------------------
    def test_19_cache_retention_limit_50(self):
        """19. Cache enforces maximum 50 scenarios retention (LRU behavior)."""
        DisruptionService.clear_cache()
        for i in range(55):
            req = DisruptionSimulationRequest(
                disruption_type="SERVICE_DELAY",
                route_number="101",
                delay_minutes=float(10 + (i % 20)),
                notes=f"Iteration {i}",
            )
            DisruptionService.simulate_disruption(db=self.db, request=req)

        cached = DisruptionService.get_cached_scenarios()
        self.assertEqual(len(cached), 50)

    # -------------------------------------------------------------------------
    # 20. Comprehensive Live Fleet & Telemetry Invariance
    # -------------------------------------------------------------------------
    def test_20_live_fleet_and_telemetry_invariance(self):
        """20. Ensure live bus assignments, GPS coordinates, passenger counts, and dispatcher review history remain unmodified."""
        # Capture exact initial state
        bus_records = [(b.id, b.bus_number, b.current_route_id, b.status) for b in self.db.query(Bus).order_by(Bus.id).all()]
        positions = [(p.id, p.bus_id, p.latitude, p.longitude, p.speed) for p in self.db.query(BusPosition).order_by(BusPosition.id).all()]
        passengers = [(p.id, p.bus_id, p.current_load, p.load_factor) for p in self.db.query(PassengerLoad).order_by(PassengerLoad.id).all()]
        review_count = self.db.query(ReallocationReview).count()

        # Execute all 4 scenario types sequentially
        DisruptionService.simulate_disruption(db=self.db, request=DisruptionSimulationRequest(disruption_type="BUS_BREAKDOWN", bus_number="101A"))
        DisruptionService.simulate_disruption(db=self.db, request=DisruptionSimulationRequest(disruption_type="ROUTE_CLOSURE", route_number="202"))
        DisruptionService.simulate_disruption(db=self.db, request=DisruptionSimulationRequest(disruption_type="DEMAND_SPIKE", route_number="101", spike_percentage=60.0))
        DisruptionService.simulate_disruption(db=self.db, request=DisruptionSimulationRequest(disruption_type="SERVICE_DELAY", route_number="303", delay_minutes=20.0))

        # Re-query
        self.db.expire_all()
        bus_records_after = [(b.id, b.bus_number, b.current_route_id, b.status) for b in self.db.query(Bus).order_by(Bus.id).all()]
        positions_after = [(p.id, p.bus_id, p.latitude, p.longitude, p.speed) for p in self.db.query(BusPosition).order_by(BusPosition.id).all()]
        passengers_after = [(p.id, p.bus_id, p.current_load, p.load_factor) for p in self.db.query(PassengerLoad).order_by(PassengerLoad.id).all()]
        review_count_after = self.db.query(ReallocationReview).count()

        self.assertEqual(bus_records, bus_records_after, "Live bus status/routes must NOT change!")
        self.assertEqual(positions, positions_after, "Live GPS coordinates must NOT change!")
        self.assertEqual(passengers, passengers_after, "Live passenger telemetry must NOT change!")
        self.assertEqual(review_count, review_count_after, "Live dispatcher reviews must NOT change!")


if __name__ == "__main__":
    unittest.main()
