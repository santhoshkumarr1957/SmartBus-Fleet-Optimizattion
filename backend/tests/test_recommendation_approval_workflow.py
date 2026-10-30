"""Regression Test Suite for TRANSIGHT Recommendation Approval Workflow.

Verifies:
1. Successful approval persists and updates recommendation status to APPROVED.
2. An approved recommendation does not reappear as PENDING after refresh.
3. A failed approval leaves the recommendation available for retry.
4. Rapid double-clicking Confirm does not create duplicate reviews (idempotency).
5. An aborted or failed request is not mistaken for a successful approval.
6. Live dispatch execution remains a strictly separate operation from approval:
   - Approval records the dispatcher's decision without modifying bus assignment.
   - Live execution reassigns the bus and creates an execution record.
   - Unapproved recommendations cannot be executed.
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
from app.api.routes.optimization import (
    record_dispatcher_review,
    get_optimization_recommendations,
    execute_dispatcher_reallocation,
)


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


def seed_test_routes_and_buses(db: Session):
    """Seed test routes, stops, buses, and passenger loads."""
    now = datetime.now(timezone.utc)

    # Route 101: Overcrowded target
    r101 = Route(
        id=1,
        route_number="101",
        name="Gandhipuram - Railway Station",
        origin="Gandhipuram",
        destination="Railway Station",
        is_active=True,
    )
    # Route 202: Underutilized source
    r202 = Route(
        id=2,
        route_number="202",
        name="Singanallur - Ukkadam Loop",
        origin="Singanallur",
        destination="Ukkadam",
        is_active=True,
    )
    db.add_all([r101, r202])
    db.flush()

    # Stops
    s101 = Stop(
        id=1,
        route_id=r101.id,
        name="Gandhipuram Central",
        sequence_order=1,
        latitude=11.0168,
        longitude=76.9558,
    )
    s202 = Stop(
        id=2,
        route_id=r202.id,
        name="Singanallur Terminal",
        sequence_order=1,
        latitude=11.0020,
        longitude=77.0180,
    )
    db.add_all([s101, s202])
    db.flush()

    # Buses: Route 101 has 1 bus with high load; Route 202 has 2 buses (one empty)
    b101 = Bus(
        id=1,
        bus_number="101A",
        license_plate="TN-38-N-1011",
        capacity=60,
        current_route_id=r101.id,
        status="ACTIVE",
    )
    b202a = Bus(
        id=2,
        bus_number="202A",
        license_plate="TN-38-N-2021",
        capacity=60,
        current_route_id=r202.id,
        status="ACTIVE",
    )
    b202b = Bus(
        id=3,
        bus_number="202B",
        license_plate="TN-38-N-2022",
        capacity=60,
        current_route_id=r202.id,
        status="ACTIVE",
    )
    db.add_all([b101, b202a, b202b])
    db.flush()

    # Bus Positions
    pos1 = BusPosition(
        bus_id=b101.id,
        latitude=11.0170,
        longitude=76.9560,
        speed=20.0,
        heading=90.0,
        timestamp=now,
    )
    pos2 = BusPosition(
        bus_id=b202a.id,
        latitude=11.0025,
        longitude=77.0185,
        speed=15.0,
        heading=180.0,
        timestamp=now,
    )
    pos3 = BusPosition(
        bus_id=b202b.id,
        latitude=11.0030,
        longitude=77.0190,
        speed=0.0,
        heading=0.0,
        timestamp=now,
    )
    db.add_all([pos1, pos2, pos3])

    # Passenger Loads: Route 101 critical (65 pax / 60 cap = 1.08), Route 202 low (5 pax / 120 cap = 0.04)
    load1 = PassengerLoad(
        bus_id=b101.id,
        stop_id=s101.id,
        current_load=65,
        capacity=60,
        load_factor=1.0833,
        timestamp=now,
    )
    load2 = PassengerLoad(
        bus_id=b202a.id,
        stop_id=s202.id,
        current_load=5,
        capacity=60,
        load_factor=0.0833,
        timestamp=now,
    )
    load3 = PassengerLoad(
        bus_id=b202b.id,
        stop_id=s202.id,
        current_load=0,
        capacity=60,
        load_factor=0.00,
        timestamp=now,
    )
    db.add_all([load1, load2, load3])
    db.commit()


class TestRecommendationApprovalWorkflow(unittest.TestCase):
    """Verifies all aspects of recommendation approval and execution separation."""

    def setUp(self):
        self.db = create_in_memory_db()
        seed_test_routes_and_buses(self.db)

    def tearDown(self):
        close_db(self.db)

    def test_01_successful_approval_persists_and_updates_status(self):
        """A successful approval persists the decision and updates recommendation review_status."""
        # 1. Fetch recommendations
        recs = OptimizationService.generate_recommendations(self.db, best_only=False)
        self.assertGreaterEqual(len(recs), 1, "At least one candidate recommendation should be generated")
        target_rec = recs[0]
        rec_id = target_rec.id

        # 2. Record approval review
        review_data = ReallocationReviewCreate(
            decision="APPROVED",
            dispatcher_id="DISPATCHER-TEST",
            notes="Approved for corridor relief",
            target_route_id=target_rec.target_route_id,
            target_route_number=target_rec.target_route_number,
            source_route_id=target_rec.source_route_id,
            source_route_number=target_rec.source_route_number,
            candidate_bus_id=target_rec.candidate_bus_id,
            candidate_bus_number=target_rec.candidate_bus_number,
            score=target_rec.score,
            priority=target_rec.priority,
        )
        saved_review = OptimizationService.record_review(self.db, rec_id, review_data)

        # 3. Verify review row in database
        self.assertIsNotNone(saved_review.id)
        self.assertEqual(saved_review.recommendation_id, rec_id)
        self.assertEqual(saved_review.decision, "APPROVED")
        self.assertEqual(saved_review.dispatcher_id, "DISPATCHER-TEST")

        db_review = (
            self.db.query(ReallocationReview)
            .filter(ReallocationReview.recommendation_id == rec_id)
            .first()
        )
        self.assertIsNotNone(db_review)
        self.assertEqual(db_review.decision, "APPROVED")

        # 4. Invariant: bus assignment remains strictly unchanged after approval
        candidate_bus = self.db.query(Bus).filter(Bus.id == target_rec.candidate_bus_id).first()
        self.assertEqual(
            candidate_bus.current_route_id,
            target_rec.source_route_id,
            "Approval alone must NOT modify the bus route assignment",
        )

    def test_02_approved_recommendation_does_not_reopen_modal_after_refresh(self):
        """Approved recommendation returns review_status='APPROVED' and is not pending."""
        recs = OptimizationService.generate_recommendations(self.db, best_only=False)
        target_rec = recs[0]
        rec_id = target_rec.id

        # Submit approval
        review_data = ReallocationReviewCreate(
            decision="APPROVED",
            dispatcher_id="DISPATCHER-TEST",
            notes="Approved",
        )
        OptimizationService.record_review(self.db, rec_id, review_data)

        # Refresh recommendations list from service/endpoint
        refreshed_recs = OptimizationService.generate_recommendations(self.db, best_only=False)
        approved_rec = next((r for r in refreshed_recs if r.id == rec_id), None)

        self.assertIsNotNone(approved_rec, "Approved recommendation must be present in full list")
        self.assertEqual(
            approved_rec.review_status,
            "APPROVED",
            "Refreshed recommendation must have review_status='APPROVED', preventing pending modal",
        )
        self.assertIsNotNone(approved_rec.latest_review)
        self.assertEqual(approved_rec.latest_review.decision, "APPROVED")

    def test_03_failed_approval_leaves_recommendation_available_for_retry(self):
        """Invalid review raises 400 and leaves recommendation in pending state."""
        recs = OptimizationService.generate_recommendations(self.db, best_only=False)
        target_rec = recs[0]
        rec_id = target_rec.id

        # Attempt invalid decision
        invalid_data = ReallocationReviewCreate(
            decision="DISPATCHED",  # Invalid enum
            dispatcher_id="DISPATCHER-TEST",
        )
        with self.assertRaises(HTTPException) as ctx:
            OptimizationService.record_review(self.db, rec_id, invalid_data)
        self.assertEqual(ctx.exception.status_code, 400)

        # Verify no review record was committed
        review_count = (
            self.db.query(ReallocationReview)
            .filter(ReallocationReview.recommendation_id == rec_id)
            .count()
        )
        self.assertEqual(review_count, 0)

        # Verify recommendation is still pending (review_status is None)
        refreshed_recs = OptimizationService.generate_recommendations(self.db, best_only=False)
        pending_rec = next((r for r in refreshed_recs if r.id == rec_id), None)
        self.assertIsNotNone(pending_rec)
        self.assertIsNone(pending_rec.review_status, "Recommendation must remain unreviewed and retryable")

    def test_04_double_clicking_confirm_does_not_create_duplicate_approvals(self):
        """Rapid double-click on Confirm Approval returns the existing review without duplicates."""
        recs = OptimizationService.generate_recommendations(self.db, best_only=False)
        target_rec = recs[0]
        rec_id = target_rec.id

        review_data = ReallocationReviewCreate(
            decision="APPROVED",
            dispatcher_id="DISPATCHER-FAST",
            notes="Rapid click 1",
            target_route_id=target_rec.target_route_id,
            target_route_number=target_rec.target_route_number,
            source_route_id=target_rec.source_route_id,
            source_route_number=target_rec.source_route_number,
            candidate_bus_id=target_rec.candidate_bus_id,
            candidate_bus_number=target_rec.candidate_bus_number,
        )

        # Click 1
        res1 = OptimizationService.record_review(self.db, rec_id, review_data)
        # Click 2 (immediate repeat)
        res2 = OptimizationService.record_review(self.db, rec_id, review_data)

        # Both calls return valid review objects
        self.assertEqual(res1.id, res2.id)
        self.assertEqual(res1.decision, "APPROVED")
        self.assertEqual(res2.decision, "APPROVED")

        # Database contains exactly ONE review row
        count = (
            self.db.query(ReallocationReview)
            .filter(ReallocationReview.recommendation_id == rec_id)
            .count()
        )
        self.assertEqual(count, 1, "Idempotent review must not create duplicate database records")

    def test_05_aborted_request_not_mistaken_for_success(self):
        """Simulated abort/rollback before completion leaves database unaffected."""
        recs = OptimizationService.generate_recommendations(self.db, best_only=False)
        target_rec = recs[0]
        rec_id = target_rec.id

        # Simulate aborted/failed transaction
        try:
            with self.db.begin_nested():
                fake_review = ReallocationReview(
                    recommendation_id=rec_id,
                    decision="APPROVED",
                    dispatcher_id="DISPATCHER-TEST",
                )
                self.db.add(fake_review)
                # Client aborts or connection drops -> rollback
                raise RuntimeError("Client aborted connection")
        except RuntimeError:
            pass

        # Verify no review committed
        review_count = (
            self.db.query(ReallocationReview)
            .filter(ReallocationReview.recommendation_id == rec_id)
            .count()
        )
        self.assertEqual(review_count, 0)

        # Recommendation remains pending
        refreshed_recs = OptimizationService.generate_recommendations(self.db, best_only=False)
        pending_rec = next((r for r in refreshed_recs if r.id == rec_id), None)
        self.assertIsNone(pending_rec.review_status)

    def test_06_live_dispatch_execution_remains_separate_operation(self):
        """Approval records operational decision; execution performs actual bus transfer."""
        recs = OptimizationService.generate_recommendations(self.db, best_only=False)
        target_rec = recs[0]
        rec_id = target_rec.id

        # 1. Unapproved recommendation cannot be executed
        exec_payload = ReallocationExecutionCreate(
            dispatcher_id="DISPATCHER-EXEC",
            notes="Attempting early execution",
        )
        with self.assertRaises(HTTPException) as ctx:
            OptimizationService.execute_reassignment(self.db, rec_id, exec_payload)
        self.assertEqual(ctx.exception.status_code, 404, "Unreviewed recommendation cannot be executed")

        # 2. Stage 7 Approval
        review_data = ReallocationReviewCreate(
            decision="APPROVED",
            dispatcher_id="DISPATCHER-APPROVAL",
            notes="Corridor approved for live transfer",
            target_route_id=target_rec.target_route_id,
            target_route_number=target_rec.target_route_number,
            source_route_id=target_rec.source_route_id,
            source_route_number=target_rec.source_route_number,
            candidate_bus_id=target_rec.candidate_bus_id,
            candidate_bus_number=target_rec.candidate_bus_number,
        )
        review = OptimizationService.record_review(self.db, rec_id, review_data)
        self.assertEqual(review.decision, "APPROVED")

        # Bus still on source route 202
        bus_before = self.db.query(Bus).filter(Bus.id == target_rec.candidate_bus_id).first()
        self.assertEqual(bus_before.current_route_id, 2)

        # 3. Live Execution
        exec_result = OptimizationService.execute_reassignment(self.db, rec_id, exec_payload)
        self.assertEqual(exec_result.status, "EXECUTED")
        self.assertEqual(exec_result.bus_id, target_rec.candidate_bus_id)
        self.assertEqual(exec_result.target_route_id, target_rec.target_route_id)

        # Now bus route is updated to route 101
        bus_after = self.db.query(Bus).filter(Bus.id == target_rec.candidate_bus_id).first()
        self.assertEqual(bus_after.current_route_id, 1, "Bus current_route_id must be updated to target route")

        # Execution record exists in reallocation_executions
        exec_record = (
            self.db.query(ReallocationExecution)
            .filter(ReallocationExecution.recommendation_id == rec_id)
            .first()
        )
        self.assertIsNotNone(exec_record)
        self.assertEqual(exec_record.status, "EXECUTED")


if __name__ == "__main__":
    unittest.main()
