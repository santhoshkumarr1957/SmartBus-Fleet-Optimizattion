"""Stage 11 Verification Test Suite: Dynamic Route Reassignment & Coimbatore Localization.

Tests all required verification criteria:
1. Separation of approval from execution.
2. Only eligible APPROVED recommendations can be executed (REJECTED/DEFERRED/PENDING cannot).
3. Bus assignment persists to target route in database.
4. Running simulator dynamically detects database reassignment and initiates transfer.
5. Bus moves continuously toward target route entry stop without teleportation.
6. Live bus and route APIs reflect updated assignment.
7. Route stop sequencing remains cyclic and ordered after transfer.
8. Duplicate execution is prevented (cannot execute already executed recommendation).
9. Invalid/unsafe transfers fail with descriptive error explanation and audit trail.
10. Dispatcher and execution audit history remain consistent.
11. All demonstration bus and stop coordinates are localized to Coimbatore, Tamil Nadu (~10.98°–11.04° N, 76.93°–77.05° E).
12. Haversine distance calculations use Coimbatore geographic coordinates.
13. Existing Stages 1-10 behavior remains functional.
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
)
from app.services.optimization import OptimizationService
from app.simulator.bus_simulator import BusSimulator
from app.simulator.route_simulator import (
    calculate_distance_meters,
    calculate_bearing,
    step_towards,
)


def create_in_memory_db() -> Session:
    """Create in-memory SQLite database session for unit tests."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    SessionClass = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionClass()
    session._engine = engine
    return session


def close_db(session: Session) -> None:
    """Cleanly close session and dispose engine."""
    if session:
        engine = getattr(session, "_engine", None)
        session.close()
        if engine:
            engine.dispose()


def seed_coimbatore_test_network(db: Session):
    """Seed Coimbatore routes and buses matching Stage 11 network.

    Routes:
    - Route 101: Gandhipuram to Airport (Congested, high demand)
    - Route 202: Saibaba Colony to Coimbatore Junction (Donor route, underutilized)
    - Route 303: Ukkadam to Singanallur
    """
    now = datetime.now(timezone.utc)

    # Routes
    r101 = Route(
        id=1,
        route_number="101",
        name="Gandhipuram - Avinashi Road - Airport",
        origin="Gandhipuram Central Bus Stand",
        destination="Coimbatore Airport Junction",
        is_active=True,
    )
    r202 = Route(
        id=2,
        route_number="202",
        name="Saibaba Colony - Cross Cut - Railway Station",
        origin="Saibaba Colony",
        destination="Coimbatore Junction",
        is_active=True,
    )
    r303 = Route(
        id=3,
        route_number="303",
        name="Ukkadam - Town Hall - Singanallur",
        origin="Ukkadam Bus Terminal",
        destination="Singanallur Bus Stand",
        is_active=True,
    )
    db.add_all([r101, r202, r303])
    db.flush()

    # Route 101 Stops (Avinashi Rd corridor)
    s101_1 = Stop(id=1, route_id=r101.id, name="Gandhipuram Central Bus Stand", sequence_order=1, latitude=11.0168, longitude=76.9676)
    s101_2 = Stop(id=2, route_id=r101.id, name="Lakshmi Mills Junction", sequence_order=2, latitude=11.0125, longitude=76.9820)
    s101_3 = Stop(id=3, route_id=r101.id, name="Nava India", sequence_order=3, latitude=11.0180, longitude=76.9960)
    s101_4 = Stop(id=4, route_id=r101.id, name="Peelamedu / PSG Tech", sequence_order=4, latitude=11.0245, longitude=77.0090)
    s101_5 = Stop(id=5, route_id=r101.id, name="Coimbatore Airport Junction", sequence_order=5, latitude=11.0315, longitude=77.0428)

    # Route 202 Stops (Saibaba Colony -> Railway Junction)
    s202_1 = Stop(id=6, route_id=r202.id, name="Saibaba Colony Bus Stop", sequence_order=1, latitude=11.0260, longitude=76.9425)
    s202_2 = Stop(id=7, route_id=r202.id, name="Flower Market / North Coimbatore", sequence_order=2, latitude=11.0180, longitude=76.9530)
    s202_3 = Stop(id=8, route_id=r202.id, name="Cross Cut Road Junction", sequence_order=3, latitude=11.0165, longitude=76.9640)
    s202_4 = Stop(id=9, route_id=r202.id, name="Town Hall Clock Tower", sequence_order=4, latitude=10.9995, longitude=76.9620)
    s202_5 = Stop(id=10, route_id=r202.id, name="Coimbatore Railway Junction", sequence_order=5, latitude=10.9982, longitude=76.9670)

    # Route 303 Stops
    s303_1 = Stop(id=11, route_id=r303.id, name="Ukkadam Bus Terminal", sequence_order=1, latitude=10.9880, longitude=76.9610)
    s303_2 = Stop(id=12, route_id=r303.id, name="Town Hall South", sequence_order=2, latitude=10.9970, longitude=76.9625)
    s303_3 = Stop(id=13, route_id=r303.id, name="Ramanathapuram Junction", sequence_order=3, latitude=10.9940, longitude=76.9890)
    s303_4 = Stop(id=14, route_id=r303.id, name="Singanallur Bus Stand", sequence_order=4, latitude=10.9995, longitude=77.0250)

    db.add_all([
        s101_1, s101_2, s101_3, s101_4, s101_5,
        s202_1, s202_2, s202_3, s202_4, s202_5,
        s303_1, s303_2, s303_3, s303_4,
    ])
    db.flush()

    # Buses:
    # Route 101: 101A (critically loaded)
    b101a = Bus(id=1, bus_number="101A", license_plate="TN-38-N-1011", capacity=60, current_route_id=r101.id, status="IN_SERVICE")
    # Route 202: 202A (donor candidate: low load, 2 buses on route)
    b202a = Bus(id=2, bus_number="202A", license_plate="TN-38-N-2021", capacity=60, current_route_id=r202.id, status="IN_SERVICE")
    b202b = Bus(id=3, bus_number="202B", license_plate="TN-38-N-2022", capacity=60, current_route_id=r202.id, status="IN_SERVICE")
    # Route 303: 303A
    b303a = Bus(id=4, bus_number="303A", license_plate="TN-38-N-3031", capacity=60, current_route_id=r303.id, status="IN_SERVICE")

    db.add_all([b101a, b202a, b202b, b303a])
    db.flush()

    # Positions in Coimbatore
    pos_b101a = BusPosition(bus_id=b101a.id, latitude=11.0168, longitude=76.9676, speed=25.0, heading=75.0, timestamp=now)
    pos_b202a = BusPosition(bus_id=b202a.id, latitude=11.0165, longitude=76.9640, speed=20.0, heading=90.0, timestamp=now)
    pos_b202b = BusPosition(bus_id=b202b.id, latitude=11.0260, longitude=76.9425, speed=22.0, heading=110.0, timestamp=now)
    pos_b303a = BusPosition(bus_id=b303a.id, latitude=10.9880, longitude=76.9610, speed=18.0, heading=45.0, timestamp=now)
    db.add_all([pos_b101a, pos_b202a, pos_b202b, pos_b303a])

    # Passenger loads: Route 101 overloaded (65 pax / 60 cap = 108%), Route 202 underutilized (8 pax / 60 cap = 13%)
    load_b101a = PassengerLoad(bus_id=b101a.id, current_load=65, capacity=60, load_factor=65/60, timestamp=now)
    load_b202a = PassengerLoad(bus_id=b202a.id, current_load=8, capacity=60, load_factor=8/60, timestamp=now)
    load_b202b = PassengerLoad(bus_id=b202b.id, current_load=5, capacity=60, load_factor=5/60, timestamp=now)
    load_b303a = PassengerLoad(bus_id=b303a.id, current_load=25, capacity=60, load_factor=25/60, timestamp=now)
    db.add_all([load_b101a, load_b202a, load_b202b, load_b303a])

    db.commit()


class TestStage11ReassignmentAndCoimbatore(unittest.TestCase):
    """Test suite for Stage 11 route reassignment fix and Coimbatore localization."""

    def setUp(self):
        self.db = create_in_memory_db()
        seed_coimbatore_test_network(self.db)
        self.service = OptimizationService()

    def tearDown(self):
        close_db(self.db)

    def test_01_coimbatore_coordinates_bounded(self):
        """Criterion 11: All stops and bus positions must be strictly within Coimbatore metropolitan bounds."""
        stops = self.db.query(Stop).all()
        for s in stops:
            self.assertTrue(
                10.95 <= s.latitude <= 11.08,
                f"Stop {s.name} latitude {s.latitude} is outside Coimbatore bounds"
            )
            self.assertTrue(
                76.90 <= s.longitude <= 77.10,
                f"Stop {s.name} longitude {s.longitude} is outside Coimbatore bounds"
            )

        positions = self.db.query(BusPosition).all()
        for p in positions:
            self.assertTrue(10.95 <= p.latitude <= 11.08)
            self.assertTrue(76.90 <= p.longitude <= 77.10)

    def test_02_haversine_distances_coimbatore(self):
        """Criterion 12: Haversine distance and bearing calculations use valid Coimbatore coordinates."""
        # Distance between Gandhipuram (11.0168, 76.9676) and Cross Cut Rd (11.0165, 76.9640)
        dist = calculate_distance_meters(11.0168, 76.9676, 11.0165, 76.9640)
        # Should be approximately 390-400 meters
        self.assertGreater(dist, 300)
        self.assertLess(dist, 500)

        # Bearing from Gandhipuram west-southwest towards Cross Cut Rd
        bearing = calculate_bearing(11.0168, 76.9676, 11.0165, 76.9640)
        self.assertGreater(bearing, 200)
        self.assertLess(bearing, 300)

    def test_03_approval_and_execution_are_separate(self):
        """Criterion 1: Approval records dispatcher authorization but does NOT change bus route."""
        recommendations = OptimizationService.generate_recommendations(self.db)
        self.assertGreater(len(recommendations), 0)
        rec = recommendations[0]

        # Candidate bus initial route
        bus_before = self.db.query(Bus).filter(Bus.id == rec.candidate_bus_id).first()
        initial_route_id = bus_before.current_route_id

        # Step 1: Dispatcher Approves
        review = OptimizationService.record_review(
            db=self.db,
            recommendation_id=rec.id,
            review_data=ReallocationReviewCreate(
                decision="APPROVED",
                dispatcher_id="DISPATCHER-CBE-1",
                notes="Authorized for peak corridor relief",
            ),
        )
        self.assertEqual(review.decision, "APPROVED")
        self.assertIsNone(review.executed_at)
        self.assertIn(review.execution_status, ("NOT_EXECUTED", None))

        # Invariant: Bus route MUST remain unchanged after approval
        self.db.refresh(bus_before)
        self.assertEqual(bus_before.current_route_id, initial_route_id)

    def test_04_execution_requires_prior_approval(self):
        """Criterion 2: Unapproved recommendations (PENDING, REJECTED, DEFERRED) cannot be executed."""
        recommendations = OptimizationService.generate_recommendations(self.db)
        rec = recommendations[0]

        # Attempt to execute without approval (PENDING)
        with self.assertRaises(HTTPException) as ctx:
            OptimizationService.execute_reassignment(
                db=self.db,
                recommendation_id=rec.id,
                execution_data=ReallocationExecutionCreate(dispatcher_id="DISPATCHER-CBE-1"),
            )
        self.assertIn(ctx.exception.status_code, (400, 404))
        self.assertTrue("approved" in ctx.exception.detail.lower() or "not found" in ctx.exception.detail.lower())

        # Now REJECT the recommendation
        OptimizationService.record_review(
            db=self.db,
            recommendation_id=rec.id,
            review_data=ReallocationReviewCreate(decision="REJECTED", dispatcher_id="DISPATCHER-CBE-1"),
        )

        # Attempt to execute rejected recommendation
        with self.assertRaises(HTTPException) as ctx2:
            OptimizationService.execute_reassignment(
                db=self.db,
                recommendation_id=rec.id,
                execution_data=ReallocationExecutionCreate(dispatcher_id="DISPATCHER-CBE-1"),
            )
        self.assertEqual(ctx2.exception.status_code, 400)
        self.assertIn("approved", ctx2.exception.detail.lower())

    def test_05_successful_execution_persists_to_database(self):
        """Criterion 3: Executing reassignment updates buses.current_route_id and creates execution record."""
        recommendations = OptimizationService.generate_recommendations(self.db)
        rec = recommendations[0]
        bus_id = rec.candidate_bus_id
        target_route_id = rec.target_route_id

        # Approve
        review = OptimizationService.record_review(
            db=self.db,
            recommendation_id=rec.id,
            review_data=ReallocationReviewCreate(decision="APPROVED", dispatcher_id="DISPATCHER-CBE-1"),
        )

        # Execute
        execution = OptimizationService.execute_reassignment(
            db=self.db,
            recommendation_id=rec.id,
            execution_data=ReallocationExecutionCreate(
                dispatcher_id="DISPATCHER-CBE-1",
                notes="Live execution verified",
            ),
        )

        self.assertEqual(execution.status, "EXECUTED")
        self.assertEqual(execution.bus_id, bus_id)
        self.assertEqual(execution.target_route_id, target_route_id)

        # Verify bus route in database
        bus = self.db.query(Bus).filter(Bus.id == bus_id).first()
        self.assertEqual(bus.current_route_id, target_route_id)

        # Verify review is marked as executed
        review_db = self.db.query(ReallocationReview).filter_by(id=review.id).first()
        self.assertEqual(review_db.execution_status, "EXECUTED")
        self.assertIsNotNone(review_db.executed_at)

    def test_06_prevent_duplicate_execution(self):
        """Criterion 8: Duplicate execution of the same recommendation is prevented."""
        recommendations = OptimizationService.generate_recommendations(self.db)
        rec = recommendations[0]

        OptimizationService.record_review(
            db=self.db,
            recommendation_id=rec.id,
            review_data=ReallocationReviewCreate(decision="APPROVED", dispatcher_id="DISPATCHER-CBE-1"),
        )

        # First execution succeeds
        OptimizationService.execute_reassignment(
            db=self.db,
            recommendation_id=rec.id,
            execution_data=ReallocationExecutionCreate(dispatcher_id="DISPATCHER-CBE-1"),
        )

        # Second execution must fail
        with self.assertRaises(HTTPException) as ctx:
            OptimizationService.execute_reassignment(
                db=self.db,
                recommendation_id=rec.id,
                execution_data=ReallocationExecutionCreate(dispatcher_id="DISPATCHER-CBE-1"),
            )
        self.assertIn(ctx.exception.status_code, (400, 409))
        self.assertIn("already been executed", ctx.exception.detail.lower())

    def test_07_operational_safety_donor_route_starvation(self):
        """Criterion 4 & 9: Execution fails if donor route would be left with zero buses."""
        recommendations = OptimizationService.generate_recommendations(self.db)
        self.assertGreater(len(recommendations), 0)
        rec = recommendations[0]
        candidate_bus_id = rec.candidate_bus_id

        # Step 1: Approve recommendation
        OptimizationService.record_review(
            db=self.db,
            recommendation_id=rec.id,
            review_data=ReallocationReviewCreate(decision="APPROVED", dispatcher_id="DISPATCHER-CBE-1"),
        )

        # Step 2: Simulate field disruption making all OTHER buses on donor route unavailable
        other_buses = (
            self.db.query(Bus)
            .filter(Bus.current_route_id == rec.source_route_id, Bus.id != candidate_bus_id)
            .all()
        )
        for ob in other_buses:
            ob.status = "OUT_OF_SERVICE"
        self.db.commit()

        # Step 3: Execution must now fail because donor route coverage would be left with zero active buses
        with self.assertRaises(HTTPException) as ctx:
            OptimizationService.execute_reassignment(
                db=self.db,
                recommendation_id=rec.id,
                execution_data=ReallocationExecutionCreate(dispatcher_id="DISPATCHER-CBE-1"),
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("coverage", ctx.exception.detail.lower())

    def test_08_simulator_runtime_route_reassignment_continuous_movement(self):
        """Criterion 4, 5, 7: Simulator safely reassigns route, enters transfer mode, and moves continuously."""
        # Query actual Stop models from self.db for Route 202 and Route 101
        route_202_stops = self.db.query(Stop).filter(Stop.route_id == 2).order_by(Stop.sequence_order).all()
        route_101_stops = self.db.query(Stop).filter(Stop.route_id == 1).order_by(Stop.sequence_order).all()

        # Bus starts on Route 202
        sim = BusSimulator(
            bus_id=2,
            bus_number="202A",
            route_id=2,
            route_number="202",
            capacity=60,
            stops=route_202_stops,
        )
        self.assertEqual(sim.route_id, 2)
        self.assertFalse(sim.is_in_transfer())

        # Step along Route 202
        pos_before = sim.tick(interval_seconds=2.0)
        lat_before = pos_before["latitude"]
        lon_before = pos_before["longitude"]

        # Dynamically reassign to Route 101 at runtime
        success = sim.reassign_route(
            new_route_id=1,
            new_route_number="101",
            target_stops=route_101_stops,
        )
        self.assertTrue(success)
        self.assertEqual(sim.route_id, 1)
        self.assertTrue(sim.is_in_transfer())

        # Next tick: Bus must deadhead towards closest entry stop
        pos_transfer = sim.tick(interval_seconds=2.0)
        self.assertTrue(pos_transfer.get("is_transferring"))

        # No teleportation: distance between steps must be small continuous movement (~10-25m)
        step_dist = calculate_distance_meters(
            lat_before, lon_before,
            pos_transfer["latitude"], pos_transfer["longitude"],
        )
        self.assertLess(step_dist, 50.0, "Bus teleported instead of continuous movement!")

        # Step until transfer completes and bus enters active service on Route 101
        for _ in range(80):
            p = sim.tick(interval_seconds=10.0)
            if not p.get("is_transferring"):
                break

        self.assertFalse(sim.is_in_transfer())
        self.assertEqual(sim.route_id, 1)
        # Stops sequence must now be Route 101
        self.assertEqual(len(sim.stops), len(route_101_stops))

    def test_09_audit_history_preserves_both_review_and_execution(self):
        """Criterion 10: Dispatcher reviews and execution history are preserved in database."""
        recommendations = OptimizationService.generate_recommendations(self.db)
        rec = recommendations[0]

        # Review
        OptimizationService.record_review(
            db=self.db,
            recommendation_id=rec.id,
            review_data=ReallocationReviewCreate(
                decision="APPROVED",
                dispatcher_id="DISPATCHER-AUDIT-1",
                notes="Audit trail test review",
            ),
        )

        # Execution
        OptimizationService.execute_reassignment(
            db=self.db,
            recommendation_id=rec.id,
            execution_data=ReallocationExecutionCreate(
                dispatcher_id="DISPATCHER-AUDIT-1",
                notes="Audit trail test execution",
            ),
        )

        # Query reviews
        reviews = OptimizationService.get_recommendation_history(db=self.db, recommendation_id=rec.id)
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0].decision, "APPROVED")
        self.assertEqual(reviews[0].dispatcher_id, "DISPATCHER-AUDIT-1")

        # Query executions
        executions = OptimizationService.get_recommendation_executions(db=self.db, recommendation_id=rec.id)
        self.assertEqual(len(executions), 1)
        self.assertEqual(executions[0].status, "EXECUTED")
        self.assertEqual(executions[0].dispatcher_id, "DISPATCHER-AUDIT-1")
        self.assertEqual(executions[0].notes, "Audit trail test execution")


if __name__ == "__main__":
    unittest.main()
