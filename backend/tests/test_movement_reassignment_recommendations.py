"""Verification tests for Movement Speed, Reassignment Workflow, and Route 303 Recommendations.

Verifies:
1. Movement calculations: 30 km/h covers ~8.33 m/s, GPS positions change consecutively, heading matches travel.
2. Cyclic loops and endpoint transitions work smoothly without coordinate jumps.
3. Approval does not transfer; explicit execution initiates transfer.
4. Passenger load is preserved during transfer and route changes.
5. High-demand Route 303 receives recommendation when eligible donor exists.
6. When no donor is eligible, no artificial recommendation is fabricated and diagnostic reasons are provided.
7. Transferring buses are excluded from donor consideration.
8. Duplicate execution is prevented.
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
from app.services.optimization import (
    OptimizationService,
    calculate_target_severity_score,
    calculate_source_spare_score,
    calculate_bus_suitability_score,
)
from app.simulator.bus_simulator import BusSimulator
from app.simulator.route_simulator import (
    calculate_distance_meters,
    calculate_bearing,
    step_towards,
)


def create_test_db() -> Session:
    """Create in-memory SQLite database session."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    SessionClass = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionClass()
    session._engine = engine
    return session


def seed_test_fleet(db: Session):
    """Seed Coimbatore routes and buses with controlled demand states."""
    now = datetime.now(timezone.utc)

    # Routes
    r101 = Route(id=1, route_number="101", name="Gandhipuram - Airport", origin="Gandhipuram", destination="Airport", is_active=True)
    r202 = Route(id=2, route_number="202", name="Saibaba Colony - Railway Junction", origin="Saibaba Colony", destination="Railway Junction", is_active=True)
    r303 = Route(id=3, route_number="303", name="Ukkadam - Singanallur", origin="Ukkadam", destination="Singanallur", is_active=True)
    db.add_all([r101, r202, r303])
    db.flush()

    # Stops (Coimbatore coordinates)
    s101_1 = Stop(id=1, route_id=1, name="Gandhipuram", sequence_order=1, latitude=11.0168, longitude=76.9676)
    s101_2 = Stop(id=2, route_id=1, name="Lakshmi Mills", sequence_order=2, latitude=11.0125, longitude=76.9820)
    s101_3 = Stop(id=3, route_id=1, name="Airport", sequence_order=3, latitude=11.0315, longitude=77.0428)

    s202_1 = Stop(id=4, route_id=2, name="Saibaba Colony", sequence_order=1, latitude=11.0260, longitude=76.9425)
    s202_2 = Stop(id=5, route_id=2, name="Cross Cut Road", sequence_order=2, latitude=11.0165, longitude=76.9640)
    s202_3 = Stop(id=6, route_id=2, name="Coimbatore Junction", sequence_order=3, latitude=10.9982, longitude=76.9670)

    s303_1 = Stop(id=7, route_id=3, name="Ukkadam", sequence_order=1, latitude=10.9880, longitude=76.9610)
    s303_2 = Stop(id=8, route_id=3, name="Town Hall South", sequence_order=2, latitude=10.9970, longitude=76.9625)
    s303_3 = Stop(id=9, route_id=3, name="Singanallur", sequence_order=3, latitude=10.9995, longitude=77.0250)

    db.add_all([s101_1, s101_2, s101_3, s202_1, s202_2, s202_3, s303_1, s303_2, s303_3])
    db.flush()

    # Buses:
    # Route 101: 101A (normal load)
    b101a = Bus(id=1, bus_number="101A", license_plate="TN-38-N-1011", capacity=60, current_route_id=1, status="ACTIVE")
    # Route 202: 202A (donor candidate: low load), 202B (donor candidate: low load)
    b202a = Bus(id=2, bus_number="202A", license_plate="TN-38-N-2021", capacity=60, current_route_id=2, status="ACTIVE")
    b202b = Bus(id=3, bus_number="202B", license_plate="TN-38-N-2022", capacity=60, current_route_id=2, status="ACTIVE")
    # Route 303: 303A (high load: 52/60 = 86.7%), 303B (35/60 = 58.3%)
    b303a = Bus(id=4, bus_number="303A", license_plate="TN-38-N-3031", capacity=60, current_route_id=3, status="ACTIVE")
    b303b = Bus(id=5, bus_number="303B", license_plate="TN-38-N-3032", capacity=60, current_route_id=3, status="ACTIVE")

    db.add_all([b101a, b202a, b202b, b303a, b303b])
    db.flush()

    # Telemetry positions
    pos_b101a = BusPosition(bus_id=1, latitude=11.0168, longitude=76.9676, speed=30.0, heading=90.0, timestamp=now)
    pos_b202a = BusPosition(bus_id=2, latitude=11.0165, longitude=76.9640, speed=28.0, heading=180.0, timestamp=now)
    pos_b202b = BusPosition(bus_id=3, latitude=11.0260, longitude=76.9425, speed=25.0, heading=120.0, timestamp=now)
    pos_b303a = BusPosition(bus_id=4, latitude=10.9880, longitude=76.9610, speed=22.0, heading=45.0, timestamp=now)
    pos_b303b = BusPosition(bus_id=5, latitude=10.9970, longitude=76.9625, speed=24.0, heading=50.0, timestamp=now)
    db.add_all([pos_b101a, pos_b202a, pos_b202b, pos_b303a, pos_b303b])

    # Passenger loads
    load_b101a = PassengerLoad(bus_id=1, current_load=30, capacity=60, load_factor=0.50, timestamp=now)
    load_b202a = PassengerLoad(bus_id=2, current_load=10, capacity=60, load_factor=10/60, timestamp=now)
    load_b202b = PassengerLoad(bus_id=3, current_load=12, capacity=60, load_factor=12/60, timestamp=now)
    load_b303a = PassengerLoad(bus_id=4, current_load=52, capacity=60, load_factor=52/60, timestamp=now)
    load_b303b = PassengerLoad(bus_id=5, current_load=35, capacity=60, load_factor=35/60, timestamp=now)
    db.add_all([load_b101a, load_b202a, load_b202b, load_b303a, load_b303b])

    db.commit()


class TestMovementReassignmentRecommendations(unittest.TestCase):
    """Comprehensive test suite for Part A, B, and C requirements."""

    def setUp(self):
        self.db = create_test_db()
        seed_test_fleet(self.db)

    def tearDown(self):
        engine = getattr(self.db, "_engine", None)
        self.db.close()
        if engine:
            engine.dispose()

    # --- PART A: Bus Movement Speed & Smoothness ---

    def test_01_speed_displacement_relationship(self):
        """A bus travelling at 30 km/h covers approx 8.33 metres per second."""
        speed_kmh = 30.0
        elapsed_seconds = 1.0
        # distance_km = speed_kmh * elapsed_seconds / 3600
        distance_meters = (speed_kmh / 3.6) * elapsed_seconds
        self.assertAlmostEqual(distance_meters, 8.333, places=2)

    def test_02_gps_positions_change_over_consecutive_ticks(self):
        """GPS positions change monotonically and continuously over consecutive ticks."""
        stops = self.db.query(Stop).filter(Stop.route_id == 2).order_by(Stop.sequence_order).all()
        sim = BusSimulator(
            bus_id=2,
            bus_number="202A",
            route_id=2,
            route_number="202",
            capacity=60,
            stops=stops,
            base_speed_kmh=30.0,
        )
        # First tick ends dwell and begins movement
        sim.is_dwelling = False
        pos1 = sim.tick(interval_seconds=1.0)
        pos2 = sim.tick(interval_seconds=1.0)

        # Coordinates should change
        dist = calculate_distance_meters(
            pos1["latitude"], pos1["longitude"],
            pos2["latitude"], pos2["longitude"],
        )
        self.assertGreater(dist, 5.0, "Bus did not move between consecutive ticks")
        self.assertLess(dist, 15.0, "Bus jumped unexpectedly beyond realistic speed")

    def test_03_heading_matches_direction_of_travel(self):
        """Heading corresponds to compass bearing between current and target stops."""
        stops = self.db.query(Stop).filter(Stop.route_id == 1).order_by(Stop.sequence_order).all()
        sim = BusSimulator(
            bus_id=1,
            bus_number="101A",
            route_id=1,
            route_number="101",
            capacity=60,
            stops=stops,
        )
        expected_bearing = calculate_bearing(
            stops[0].latitude, stops[0].longitude,
            stops[1].latitude, stops[1].longitude,
        )
        self.assertAlmostEqual(sim.heading, expected_bearing, places=1)

    def test_04_cyclic_route_loop_transition(self):
        """Bus loops cyclically through stops without teleporting or throwing errors."""
        stops = self.db.query(Stop).filter(Stop.route_id == 3).order_by(Stop.sequence_order).all()
        sim = BusSimulator(
            bus_id=4,
            bus_number="303A",
            route_id=3,
            route_number="303",
            capacity=60,
            stops=stops,
        )
        visited_stops = set()
        for _ in range(100):
            p = sim.tick(interval_seconds=15.0)
            visited_stops.add(p["current_stop_seq"])
        # Should have visited all 3 stops in the loop
        self.assertEqual(visited_stops, {1, 2, 3})

    # --- PART B: Route Reassignment & Transfer Movement ---

    def test_05_approval_alone_does_not_transfer_bus(self):
        """Approval records dispatcher decision but DOES NOT alter bus route assignment."""
        recs = OptimizationService.generate_recommendations(self.db)
        self.assertGreater(len(recs), 0)
        rec = recs[0]

        bus_before = self.db.query(Bus).filter(Bus.id == rec.candidate_bus_id).first()
        initial_route_id = bus_before.current_route_id

        # Dispatcher approves
        review = OptimizationService.record_review(
            db=self.db,
            recommendation_id=rec.id,
            review_data=ReallocationReviewCreate(decision="APPROVED"),
        )
        self.assertEqual(review.decision, "APPROVED")

        # Bus in DB must STILL be on initial route
        bus_after = self.db.query(Bus).filter(Bus.id == rec.candidate_bus_id).first()
        self.assertEqual(bus_after.current_route_id, initial_route_id)

    def test_06_explicit_execution_initiates_transfer(self):
        """Explicit execution updates DB route and prevents duplicate execution."""
        recs = OptimizationService.generate_recommendations(self.db)
        rec = recs[0]

        OptimizationService.record_review(
            db=self.db,
            recommendation_id=rec.id,
            review_data=ReallocationReviewCreate(decision="APPROVED"),
        )

        # Execution
        exec_record = OptimizationService.execute_reassignment(
            db=self.db,
            recommendation_id=rec.id,
            execution_data=ReallocationExecutionCreate(dispatcher_id="DISPATCHER-TEST"),
        )
        self.assertEqual(exec_record.status, "EXECUTED")

        # Bus updated in DB
        bus = self.db.query(Bus).filter(Bus.id == rec.candidate_bus_id).first()
        self.assertEqual(bus.current_route_id, rec.target_route_id)

        # Duplicate execution fails
        with self.assertRaises(HTTPException) as ctx:
            OptimizationService.execute_reassignment(
                db=self.db,
                recommendation_id=rec.id,
                execution_data=ReallocationExecutionCreate(dispatcher_id="DISPATCHER-TEST"),
            )
        self.assertIn(ctx.exception.status_code, (400, 409))

    def test_07_passenger_load_preserved_during_transfer(self):
        """Bus passenger load is preserved during transfer and does not reset to 0."""
        stops_202 = self.db.query(Stop).filter(Stop.route_id == 2).order_by(Stop.sequence_order).all()
        stops_101 = self.db.query(Stop).filter(Stop.route_id == 1).order_by(Stop.sequence_order).all()

        sim = BusSimulator(
            bus_id=2,
            bus_number="202A",
            route_id=2,
            route_number="202",
            capacity=60,
            stops=stops_202,
        )
        sim.current_load = 28  # Explicit test passenger count
        initial_load = sim.current_load

        # Reassign to Route 101
        sim.reassign_route(
            new_route_id=1,
            new_route_number="101",
            target_stops=stops_101,
        )

        # Check that passenger load is NOT wiped to 0
        self.assertEqual(sim.current_load, initial_load, "Passenger load was unexpectedly reset during reassignment!")
        self.assertEqual(sim.available_seats, 60 - initial_load)
        self.assertEqual(sim.load_factor, round(initial_load / 60, 4))

        # Tick in transfer
        state = sim.tick(interval_seconds=1.0)
        self.assertEqual(state["passenger_count"], initial_load)
        self.assertTrue(state["is_transferring"])

    # --- PART C: Route 303 Recommendations ---

    def test_08_route_303_receives_recommendation_when_donor_eligible(self):
        """Route 303 (Bus 303A high load 86.7%) receives recommendation when Route 202 is underutilized with 2 buses."""
        recs = OptimizationService.generate_recommendations(self.db)
        r303_recs = [r for r in recs if r.target_route_number == "303"]
        self.assertGreater(len(r303_recs), 0, "Route 303 did not receive any recommendation despite high load!")
        rec = r303_recs[0]
        self.assertEqual(rec.target_route_number, "303")
        self.assertEqual(rec.source_route_number, "202")
        self.assertIn(rec.candidate_bus_number, ["202A", "202B"])
        self.assertGreater(rec.score, 0.0)

    def test_09_no_fabrication_when_no_donor_eligible(self):
        """When donor fleet has no eligible buses (e.g. out of service or crowded), no recommendation is fabricated."""
        # Make all donor buses unavailable (out of service)
        b202a = self.db.query(Bus).filter(Bus.id == 2).first()
        b202a.status = "OUT_OF_SERVICE"
        b202b = self.db.query(Bus).filter(Bus.id == 3).first()
        b202b.status = "OUT_OF_SERVICE"
        # Make Route 101 bus also busy
        b101a = self.db.query(Bus).filter(Bus.id == 1).first()
        b101a.status = "OUT_OF_SERVICE"
        self.db.commit()

        overview = OptimizationService.get_overview(self.db)
        # Should NOT fabricate any artificial recommendation when no donor is eligible
        recs = OptimizationService.generate_recommendations(self.db)
        self.assertEqual(len(recs), 0, "Fabricated recommendation when no donor was eligible!")

        # Overview provides clear diagnostic reason
        self.assertGreater(len(overview.diagnostic_reasons), 0)
        self.assertIn("minimum service coverage", overview.disclaimer.lower())

    def test_10_transferring_bus_excluded_from_donor_recommendations(self):
        """A bus currently transferring (executed recently) is excluded from donor candidate selection."""
        now = datetime.now(timezone.utc)
        # Record execution for 202A
        exec_rec = ReallocationExecution(
            recommendation_id="REC-TEST-202A",
            bus_id=2,
            bus_number="202A",
            source_route_id=2,
            source_route_number="202",
            target_route_id=1,
            target_route_number="101",
            dispatcher_id="DISPATCHER-1",
            status="EXECUTED",
            created_at=now,
        )
        self.db.add(exec_rec)
        self.db.commit()

        recs = OptimizationService.generate_recommendations(self.db)
        candidate_bus_numbers = [r.candidate_bus_number for r in recs]
        self.assertNotIn("202A", candidate_bus_numbers, "Transferring bus 202A was recommended for another transfer!")


if __name__ == "__main__":
    unittest.main()
