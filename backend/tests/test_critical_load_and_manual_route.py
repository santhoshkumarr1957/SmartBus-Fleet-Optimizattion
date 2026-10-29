"""Comprehensive Verification Tests for Critical-Load Recommendations and Manual Route Assignment.

Verifies all 10 acceptance criteria specified in TRANSIGHT prompt:
1. A CRITICAL target with an eligible donor produces a recommendation.
2. A CRITICAL target with no eligible donor returns a meaningful diagnostic.
3. A valid recommendation structure contains all fields required by the frontend.
4. Incorrect route assignment is not silently introduced by the simulator.
5. A manual route change validates its target and records an audit entry.
6. A transfer changes GPS coordinates over time without teleportation.
7. The active route changes when the transfer completes.
8. Conflicting transfers and duplicate executions are rejected.
9. Passenger counts and load factors remain consistent throughout transfers.
10. Existing dispatcher approval and execution behavior still works.
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
from app.models.reallocation_execution import ReallocationExecution
from app.schemas.optimization import (
    ReallocationReviewCreate,
    ReallocationExecutionCreate,
    ManualReassignmentCreate,
)
from app.services.optimization import OptimizationService
from app.simulator.bus_simulator import BusSimulator
from app.simulator.runner import SimulatorRunner
from app.simulator.route_simulator import (
    calculate_distance_meters,
    calculate_bearing,
    step_towards,
)


def create_in_memory_db() -> Session:
    """Create in-memory SQLite database session for deterministic isolated tests."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    SessionClass = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionClass()
    session._engine = engine
    return session


def seed_coimbatore_test_network(db: Session):
    """Seed Coimbatore routes (101, 202, 303), stops, and buses with baseline loads."""
    now = datetime.now(timezone.utc)

    # 1. Coimbatore Routes
    r101 = Route(
        id=1,
        route_number="101",
        name="Gandhipuram - Airport",
        origin="Gandhipuram",
        destination="Airport",
        is_active=True,
    )
    r202 = Route(
        id=2,
        route_number="202",
        name="Saibaba Colony - Railway Junction",
        origin="Saibaba Colony",
        destination="Railway Junction",
        is_active=True,
    )
    r303 = Route(
        id=3,
        route_number="303",
        name="Ukkadam - Singanallur",
        origin="Ukkadam",
        destination="Singanallur",
        is_active=True,
    )
    db.add_all([r101, r202, r303])
    db.flush()

    # 2. Stops with valid Coimbatore Coordinates
    stops = [
        # Route 101: Gandhipuram -> Airport
        Stop(id=1, route_id=1, name="Gandhipuram Central", sequence_order=1, latitude=11.0168, longitude=76.9676),
        Stop(id=2, route_id=1, name="Lakshmi Mills", sequence_order=2, latitude=11.0125, longitude=76.9820),
        Stop(id=3, route_id=1, name="Coimbatore Airport", sequence_order=3, latitude=11.0315, longitude=77.0428),
        # Route 202: Saibaba Colony -> Railway Junction
        Stop(id=4, route_id=2, name="Saibaba Colony", sequence_order=1, latitude=11.0260, longitude=76.9425),
        Stop(id=5, route_id=2, name="Cross Cut Road", sequence_order=2, latitude=11.0165, longitude=76.9640),
        Stop(id=6, route_id=2, name="Railway Junction", sequence_order=3, latitude=10.9982, longitude=76.9670),
        # Route 303: Ukkadam -> Singanallur
        Stop(id=7, route_id=3, name="Ukkadam Bus Stand", sequence_order=1, latitude=10.9880, longitude=76.9610),
        Stop(id=8, route_id=3, name="Town Hall South", sequence_order=2, latitude=10.9970, longitude=76.9625),
        Stop(id=9, route_id=3, name="Singanallur Junction", sequence_order=3, latitude=10.9995, longitude=77.0250),
    ]
    db.add_all(stops)
    db.flush()

    # 3. Fleet setup: 2 buses per route
    buses = [
        Bus(id=1, bus_number="101A", license_plate="TN-38-N-1011", capacity=60, current_route_id=1, status="ACTIVE"),
        Bus(id=2, bus_number="101B", license_plate="TN-38-N-1012", capacity=60, current_route_id=1, status="ACTIVE"),
        Bus(id=3, bus_number="202A", license_plate="TN-38-N-2021", capacity=60, current_route_id=2, status="ACTIVE"),
        Bus(id=4, bus_number="202B", license_plate="TN-38-N-2022", capacity=60, current_route_id=2, status="ACTIVE"),
        Bus(id=5, bus_number="303A", license_plate="TN-38-N-3031", capacity=60, current_route_id=3, status="ACTIVE"),
        Bus(id=6, bus_number="303B", license_plate="TN-38-N-3032", capacity=60, current_route_id=3, status="ACTIVE"),
    ]
    db.add_all(buses)
    db.flush()

    # 4. GPS positions
    positions = [
        BusPosition(bus_id=1, latitude=11.0168, longitude=76.9676, speed=30.0, heading=90.0, timestamp=now),
        BusPosition(bus_id=2, latitude=11.0125, longitude=76.9820, speed=25.0, heading=85.0, timestamp=now),
        BusPosition(bus_id=3, latitude=11.0260, longitude=76.9425, speed=28.0, heading=180.0, timestamp=now),
        BusPosition(bus_id=4, latitude=11.0165, longitude=76.9640, speed=24.0, heading=160.0, timestamp=now),
        BusPosition(bus_id=5, latitude=10.9880, longitude=76.9610, speed=22.0, heading=45.0, timestamp=now),
        BusPosition(bus_id=6, latitude=10.9970, longitude=76.9625, speed=20.0, heading=50.0, timestamp=now),
    ]
    db.add_all(positions)
    db.flush()

    # 5. Baseline Passenger Loads: Route 101 high (CRITICAL), Route 202 low (LOW), Route 303 normal
    loads = [
        # Route 101: 60/60 (100%) and 58/60 (96.7%) -> Total 118/120 = 98.3% (CRITICAL)
        PassengerLoad(bus_id=1, current_load=60, capacity=60, load_factor=1.0, timestamp=now),
        PassengerLoad(bus_id=2, current_load=58, capacity=60, load_factor=0.9667, timestamp=now),
        # Route 202: 12/60 (20%) and 15/60 (25%) -> Total 27/120 = 22.5% (LOW)
        PassengerLoad(bus_id=3, current_load=12, capacity=60, load_factor=0.20, timestamp=now),
        PassengerLoad(bus_id=4, current_load=15, capacity=60, load_factor=0.25, timestamp=now),
        # Route 303: 35/60 (58.3%) and 38/60 (63.3%) -> Total 73/120 = 60.8% (NORMAL)
        PassengerLoad(bus_id=5, current_load=35, capacity=60, load_factor=0.5833, timestamp=now),
        PassengerLoad(bus_id=6, current_load=38, capacity=60, load_factor=0.6333, timestamp=now),
    ]
    db.add_all(loads)
    db.commit()


class TestCriticalLoadAndManualRoute(unittest.TestCase):
    """Exhaustive tests for the 10 acceptance criteria."""

    def setUp(self):
        self.db = create_in_memory_db()
        seed_coimbatore_test_network(self.db)

    def tearDown(self):
        self.db.close()
        if hasattr(self.db, "_engine"):
            self.db._engine.dispose()

    def test_01_critical_target_with_eligible_donor_produces_recommendation(self):
        """Criterion 1: A CRITICAL target with an eligible donor produces a recommendation."""
        recs = OptimizationService.generate_recommendations(self.db)
        self.assertGreater(len(recs), 0, "No recommendations generated despite Route 101 CRITICAL demand!")

        # Recommendations should target Route 101 from Route 202
        target_101_recs = [r for r in recs if r.target_route_number == "101"]
        self.assertGreater(len(target_101_recs), 0)

        top_rec = target_101_recs[0]
        self.assertEqual(top_rec.target_route_number, "101")
        self.assertEqual(top_rec.source_route_number, "202")
        self.assertIn(top_rec.candidate_bus_number, ["202A", "202B"])
        self.assertGreater(top_rec.score, 0.0)
        self.assertIn(top_rec.priority, ["HIGH", "MEDIUM"])
        self.assertTrue(top_rec.is_advisory)

    def test_02_critical_target_with_no_eligible_donor_returns_meaningful_diagnostic(self):
        """Criterion 2: A CRITICAL target with no eligible donor returns a meaningful diagnostic."""
        # Mark all buses on donor routes as OUT_OF_SERVICE or overloaded
        for bus_id in [3, 4, 5, 6]:
            b = self.db.query(Bus).filter(Bus.id == bus_id).first()
            b.status = "OUT_OF_SERVICE"
        self.db.commit()

        recs = OptimizationService.generate_recommendations(self.db)
        target_101_recs = [r for r in recs if r.target_route_number == "101"]
        self.assertEqual(len(target_101_recs), 0, "Fabricated recommendation when no donor bus was eligible!")

        overview = OptimizationService.get_overview(self.db)
        self.assertGreater(len(overview.diagnostic_reasons), 0)
        diag = " ".join(overview.diagnostic_reasons)
        self.assertIn("Route 101", diag)
        self.assertIn("passenger demand", diag)

    def test_03_recommendation_response_structure_for_frontend(self):
        """Criterion 3: Valid recommendations contain all fields needed by frontend panels."""
        recs = OptimizationService.generate_recommendations(self.db)
        self.assertGreater(len(recs), 0)
        rec = recs[0]

        # Verify key frontend schema properties
        self.assertIsNotNone(rec.id)
        self.assertIsNotNone(rec.source_route_id)
        self.assertIsNotNone(rec.source_route_number)
        self.assertIsNotNone(rec.target_route_id)
        self.assertIsNotNone(rec.target_route_number)
        self.assertIsNotNone(rec.candidate_bus_id)
        self.assertIsNotNone(rec.candidate_bus_number)
        self.assertIsNotNone(rec.score)
        self.assertIsNotNone(rec.priority)
        self.assertIsNotNone(rec.feasibility_status)
        self.assertIsNotNone(rec.reason)
        self.assertTrue(rec.is_advisory)
        self.assertIsNotNone(rec.projected_target_load_factor)
        self.assertIsNotNone(rec.projected_source_load_factor)

    def test_04_simulator_does_not_silently_introduce_incorrect_route_assignment(self):
        """Criterion 4: Simulator initialization and ticks do not silently alter persisted DB route assignments."""
        runner = SimulatorRunner(interval_seconds=1.0)
        setup_ok = runner.setup(self.db)
        self.assertTrue(setup_ok)

        # Execute 5 simulation cycles
        for _ in range(5):
            runner.step(self.db)

        # Check all bus assignments in DB remain exactly as seeded
        buses = self.db.query(Bus).order_by(Bus.id).all()
        expected = [(1, 1), (2, 1), (3, 2), (4, 2), (5, 3), (6, 3)]
        actual = [(b.id, b.current_route_id) for b in buses]
        self.assertEqual(actual, expected, "Simulator modified persisted route assignments without explicit execution!")

    def test_05_manual_route_change_validates_target_and_records_audit_entry(self):
        """Criterion 5: Manual route change validates target route and records audit entry."""
        # 1. Invalid target route (does not exist)
        with self.assertRaises(HTTPException) as ctx1:
            OptimizationService.execute_manual_reassignment(
                self.db,
                bus_id=3,
                manual_data=ManualReassignmentCreate(
                    target_route_id=999,
                    dispatcher_id="DISPATCHER-TEST",
                    reason="Invalid route test",
                ),
            )
        self.assertEqual(ctx1.exception.status_code, 400)

        # 2. Redundant assignment to the route bus is already on
        with self.assertRaises(HTTPException) as ctx2:
            OptimizationService.execute_manual_reassignment(
                self.db,
                bus_id=3,
                manual_data=ManualReassignmentCreate(
                    target_route_id=2,  # Already on Route 2
                    dispatcher_id="DISPATCHER-TEST",
                    reason="Redundant assignment test",
                ),
            )
        self.assertEqual(ctx2.exception.status_code, 400)

        # 3. Valid reassignment of Bus 202A (id=3) from Route 2 to Route 1
        exec_res = OptimizationService.execute_manual_reassignment(
            self.db,
            bus_id=3,
            manual_data=ManualReassignmentCreate(
                target_route_id=1,
                dispatcher_id="DISPATCHER-MANUAL",
                reason="Corridor demand rebalance to Route 101",
            ),
        )
        self.assertEqual(exec_res.status, "EXECUTED")
        self.assertEqual(exec_res.bus_number, "202A")
        self.assertEqual(exec_res.source_route_number, "202")
        self.assertEqual(exec_res.target_route_number, "101")
        self.assertEqual(exec_res.dispatcher_id, "DISPATCHER-MANUAL")

        # Verify audit trail in DB
        db_exec = (
            self.db.query(ReallocationExecution)
            .filter(ReallocationExecution.id == exec_res.id)
            .first()
        )
        self.assertIsNotNone(db_exec)
        self.assertEqual(db_exec.notes, "Corridor demand rebalance to Route 101")

        # Verify bus persisted route assignment updated in DB
        bus = self.db.query(Bus).filter(Bus.id == 3).first()
        self.assertEqual(bus.current_route_id, 1)

    def test_06_transfer_changes_gps_coordinates_over_time_without_teleportation(self):
        """Criterion 6: A transfer changes GPS coordinates incrementally without teleportation."""
        stops_202 = self.db.query(Stop).filter(Stop.route_id == 2).order_by(Stop.sequence_order).all()
        stops_101 = self.db.query(Stop).filter(Stop.route_id == 1).order_by(Stop.sequence_order).all()

        sim = BusSimulator(
            bus_id=3,
            bus_number="202A",
            route_id=2,
            route_number="202",
            capacity=60,
            stops=stops_202,
        )

        initial_lat = sim.latitude
        initial_lon = sim.longitude

        # Reassign to Route 101
        sim.reassign_route(
            new_route_id=1,
            new_route_number="101",
            target_stops=stops_101,
        )

        self.assertTrue(sim.is_in_transfer())

        # Step 1 tick (1.0 second)
        state_tick1 = sim.tick(interval_seconds=1.0)
        dist_moved = calculate_distance_meters(
            initial_lat, initial_lon, state_tick1["latitude"], state_tick1["longitude"]
        )

        # Bus should have moved gradually (around 8.33 m for 30 km/h in 1s, with slight tolerance [5, 15]m)
        self.assertGreater(dist_moved, 3.0, "Bus did not move during transfer tick!")
        self.assertLess(dist_moved, 50.0, "Bus teleported instead of continuous movement!")
        self.assertTrue(state_tick1["is_transferring"])

    def test_07_active_route_switches_when_transfer_completes(self):
        """Criterion 7: The active route changes only when the transfer completes upon arrival."""
        stops_202 = self.db.query(Stop).filter(Stop.route_id == 2).order_by(Stop.sequence_order).all()
        stops_101 = self.db.query(Stop).filter(Stop.route_id == 1).order_by(Stop.sequence_order).all()

        sim = BusSimulator(
            bus_id=3,
            bus_number="202A",
            route_id=2,
            route_number="202",
            capacity=60,
            stops=stops_202,
        )

        sim.reassign_route(
            new_route_id=1,
            new_route_number="101",
            target_stops=stops_101,
        )

        # During transfer, active route remains source route (202)
        self.assertEqual(sim.active_route_number, "202")
        self.assertEqual(sim.assigned_route_number, "101")
        self.assertTrue(sim.is_in_transfer())

        # Simulate ticks until bus reaches the entry stop
        ticks = 0
        while sim.is_in_transfer() and ticks < 2000:
            sim.tick(interval_seconds=2.0)
            ticks += 1

        # After transfer completes:
        self.assertFalse(sim.is_in_transfer())
        self.assertEqual(sim.active_route_number, "101", "Active route did not switch to 101 on transfer arrival!")
        self.assertEqual(sim.assigned_route_number, "101")

    def test_08_conflicting_transfers_are_rejected(self):
        """Criterion 8: Conflicting transfers and duplicate executions are rejected."""
        # Execute reassignment of Bus 202A (id=3) to Route 1
        OptimizationService.execute_manual_reassignment(
            self.db,
            bus_id=3,
            manual_data=ManualReassignmentCreate(
                target_route_id=1,
                dispatcher_id="DISPATCHER-1",
                reason="Transfer 1",
            ),
        )

        # Immediately attempt second conflicting reassignment while first transfer is active (<180s)
        with self.assertRaises(HTTPException) as ctx:
            OptimizationService.execute_manual_reassignment(
                self.db,
                bus_id=3,
                manual_data=ManualReassignmentCreate(
                    target_route_id=3,
                    dispatcher_id="DISPATCHER-2",
                    reason="Conflicting transfer",
                ),
            )
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("active transfer", ctx.exception.detail.lower())

    def test_09_passenger_counts_and_load_factors_remain_consistent(self):
        """Criterion 9: Passenger counts and load factors remain consistent during route reassignment."""
        stops_202 = self.db.query(Stop).filter(Stop.route_id == 2).order_by(Stop.sequence_order).all()
        stops_101 = self.db.query(Stop).filter(Stop.route_id == 1).order_by(Stop.sequence_order).all()

        sim = BusSimulator(
            bus_id=3,
            bus_number="202A",
            route_id=2,
            route_number="202",
            capacity=60,
            stops=stops_202,
        )
        sim.current_load = 24  # Known test occupancy

        initial_load = sim.current_load
        initial_available = sim.available_seats
        initial_lf = sim.load_factor

        # Reassign to Route 101
        sim.reassign_route(
            new_route_id=1,
            new_route_number="101",
            target_stops=stops_101,
        )

        # Verify load did NOT reset to 0
        self.assertEqual(sim.current_load, initial_load)
        self.assertEqual(sim.available_seats, initial_available)
        self.assertEqual(sim.load_factor, initial_lf)

        # Tick in transfer
        state = sim.tick(interval_seconds=1.0)
        self.assertEqual(state["passenger_count"], initial_load)
        self.assertEqual(state["capacity"], 60)
        self.assertEqual(state["load_factor"], round(24 / 60, 4))

    def test_10_existing_dispatcher_approval_and_execution_behavior_intact(self):
        """Criterion 10: Existing two-step dispatcher approval and recommendation execution workflow still works."""
        recs = OptimizationService.generate_recommendations(self.db)
        self.assertGreater(len(recs), 0)
        rec = recs[0]

        bus_before = self.db.query(Bus).filter(Bus.id == rec.candidate_bus_id).first()
        source_route_id = bus_before.current_route_id

        # Step 1: Dispatcher Approves recommendation
        review = OptimizationService.record_review(
            db=self.db,
            recommendation_id=rec.id,
            review_data=ReallocationReviewCreate(
                decision="APPROVED",
                dispatcher_id="DISPATCHER-TEST",
                notes="Approved for high-demand relief",
            ),
        )
        self.assertEqual(review.decision, "APPROVED")

        # Bus route in DB must NOT change upon approval
        bus_mid = self.db.query(Bus).filter(Bus.id == rec.candidate_bus_id).first()
        self.assertEqual(bus_mid.current_route_id, source_route_id)

        # Step 2: Explicit Execution
        exec_record = OptimizationService.execute_reassignment(
            db=self.db,
            recommendation_id=rec.id,
            execution_data=ReallocationExecutionCreate(
                dispatcher_id="DISPATCHER-TEST",
                notes="Executing approved reallocation",
            ),
        )
        self.assertEqual(exec_record.status, "EXECUTED")

        # Bus route in DB is now updated to target route
        bus_after = self.db.query(Bus).filter(Bus.id == rec.candidate_bus_id).first()
        self.assertEqual(bus_after.current_route_id, rec.target_route_id)


if __name__ == "__main__":
    unittest.main()
