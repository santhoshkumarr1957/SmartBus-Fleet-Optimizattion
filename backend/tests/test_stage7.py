"""Stage 7 Verification Test Suite for SmartBus.

Tests all Stage 7 criteria:
1. Dispatcher review decisions: APPROVED, REJECTED, and DEFERRED.
2. Invariant: Operational approval ONLY; bus route assignment is strictly unchanged.
3. Input validation: Invalid decisions (e.g. DISPATCHED, INVALID) raise 400 Bad Request.
4. Non-existent recommendations raise 404 Not Found.
5. Review persistence, snapshotting, and audit history retrieval.
6. Recommendation list integration: review_status and latest_review included in responses.
7. Optimization overview aggregates approved, rejected, deferred, and pending counts.
8. API endpoints function correctly with dependency injection.
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

from app.schemas.optimization import (
    ReallocationReviewCreate,
    ReallocationReviewResponse,
    ReallocationRecommendationResponse,
    OptimizationOverviewResponse,
)
from app.services.optimization import OptimizationService
from app.api.routes.optimization import (
    record_dispatcher_review,
    get_dispatcher_reviews,
    get_recommendation_review_history,
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


def seed_test_imbalance_environment(db: Session):
    """Seed test routes and buses with demand imbalance:

    - Route 101: Overloaded (CRITICAL, 65 passengers / 60 capacity)
    - Route 202: Underutilized (LOW, 10 passengers / 120 capacity across 2 buses)
      - Bus 202A (occupied 10, capacity 60)
      - Bus 202B (occupied 0, capacity 60 -> prime candidate)
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
    db.add_all([r101, r202])
    db.flush()

    # Stops
    s101 = Stop(
        id=1,
        route_id=r101.id,
        name="Central Station",
        sequence_order=1,
        latitude=37.7749,
        longitude=-122.4194,
    )
    s202 = Stop(
        id=2,
        route_id=r202.id,
        name="Suburban Hub",
        sequence_order=1,
        latitude=37.7800,
        longitude=-122.4100,
    )
    db.add_all([s101, s202])
    db.flush()

    # Buses
    b101 = Bus(
        id=1,
        bus_number="101A",
        license_plate="BUS-101A",
        capacity=60,
        current_route_id=r101.id,
        status="ACTIVE",
    )
    b202a = Bus(
        id=2,
        bus_number="202A",
        license_plate="BUS-202A",
        capacity=60,
        current_route_id=r202.id,
        status="ACTIVE",
    )
    b202b = Bus(
        id=3,
        bus_number="202B",
        license_plate="BUS-202B",
        capacity=60,
        current_route_id=r202.id,
        status="ACTIVE",
    )
    db.add_all([b101, b202a, b202b])
    db.flush()

    # Telemetry and loads
    l101 = PassengerLoad(
        bus_id=b101.id,
        stop_id=s101.id,
        current_load=65,
        capacity=60,
        load_factor=1.0833,
        timestamp=now,
    )
    l202a = PassengerLoad(
        bus_id=b202a.id,
        stop_id=s202.id,
        current_load=10,
        capacity=60,
        load_factor=0.1667,
        timestamp=now,
    )
    l202b = PassengerLoad(
        bus_id=b202b.id,
        stop_id=s202.id,
        current_load=0,
        capacity=60,
        load_factor=0.0,
        timestamp=now,
    )

    p202b = BusPosition(
        bus_id=b202b.id,
        latitude=37.7760,
        longitude=-122.4180,
        speed=25.0,
        heading=90.0,
        timestamp=now,
    )
    db.add_all([l101, l202a, l202b, p202b])
    db.commit()


class TestStage7DispatcherReview(unittest.TestCase):
    """Test suite for Stage 7 Reallocation Workflow and Dispatcher Approval."""

    def setUp(self):
        self.db = create_in_memory_db()
        seed_test_imbalance_environment(self.db)

    def tearDown(self):
        close_db(self.db)

    # -------------------------------------------------------------------------
    # 1. Review Decisions: APPROVED, REJECTED, DEFERRED
    # -------------------------------------------------------------------------

    def test_01_approve_recommendation_and_verify_persistence(self):
        """Test recording an APPROVED decision and verify persistence."""
        recs = OptimizationService.generate_recommendations(self.db)
        self.assertGreater(len(recs), 0)
        target_rec = recs[0]

        review_data = ReallocationReviewCreate(
            decision="APPROVED",
            dispatcher_id="DISPATCHER-42",
            notes="Authorized for operational consideration during evening peak.",
        )

        response = OptimizationService.record_review(
            db=self.db,
            recommendation_id=target_rec.id,
            review_data=review_data,
        )

        self.assertIsInstance(response, ReallocationReviewResponse)
        self.assertEqual(response.decision, "APPROVED")
        self.assertEqual(response.recommendation_id, target_rec.id)
        self.assertEqual(response.dispatcher_id, "DISPATCHER-42")
        self.assertEqual(response.notes, "Authorized for operational consideration during evening peak.")
        self.assertTrue(response.is_advisory)
        self.assertIn("operational consideration only", response.advisory_note.lower())

        # Verify database record
        saved = self.db.query(ReallocationReview).filter_by(id=response.id).first()
        self.assertIsNotNone(saved)
        self.assertEqual(saved.decision, "APPROVED")
        self.assertEqual(saved.target_route_id, target_rec.target_route_id)
        self.assertEqual(saved.candidate_bus_id, target_rec.candidate_bus_id)

    def test_02_reject_recommendation(self):
        """Test recording a REJECTED decision with operational rationale."""
        recs = OptimizationService.generate_recommendations(self.db)
        target_rec = recs[0]

        review_data = ReallocationReviewCreate(
            decision="REJECTED",
            dispatcher_id="DISPATCHER-99",
            notes="Road works on connecting corridor prevent vehicle deadheading.",
        )

        response = OptimizationService.record_review(
            db=self.db,
            recommendation_id=target_rec.id,
            review_data=review_data,
        )

        self.assertEqual(response.decision, "REJECTED")
        self.assertEqual(response.notes, "Road works on connecting corridor prevent vehicle deadheading.")

    def test_03_defer_recommendation(self):
        """Test recording a DEFERRED decision for re-evaluation in next cycle."""
        recs = OptimizationService.generate_recommendations(self.db)
        target_rec = recs[0]

        review_data = ReallocationReviewCreate(
            decision="DEFERRED",
            dispatcher_id="DISPATCHER-1",
            notes="Waiting for 18:30 passenger exchange update.",
        )

        response = OptimizationService.record_review(
            db=self.db,
            recommendation_id=target_rec.id,
            review_data=review_data,
        )

        self.assertEqual(response.decision, "DEFERRED")

    def test_04_case_insensitivity_handling(self):
        """Test that decisions with varying case (e.g. 'approved') are normalized to uppercase."""
        recs = OptimizationService.generate_recommendations(self.db)
        target_rec = recs[0]

        for raw_decision, expected in [("approved", "APPROVED"), ("Rejected", "REJECTED"), ("DeFeRrEd", "DEFERRED")]:
            review_data = ReallocationReviewCreate(decision=raw_decision)
            response = OptimizationService.record_review(
                db=self.db,
                recommendation_id=target_rec.id,
                review_data=review_data,
            )
            self.assertEqual(response.decision, expected)

    # -------------------------------------------------------------------------
    # 2. Strict Invariant: Absolute Prevention of Route Reassignment
    # -------------------------------------------------------------------------

    def test_05_approval_does_not_mutate_bus_route_or_status(self):
        """CRITICAL INVARIANT: Approval must NEVER reassign the bus or change fleet status."""
        recs = OptimizationService.generate_recommendations(self.db)
        target_rec = recs[0]
        candidate_bus_id = target_rec.candidate_bus_id
        self.assertIsNotNone(candidate_bus_id)

        # Capture bus state before review
        bus_before = self.db.query(Bus).filter_by(id=candidate_bus_id).first()
        original_route_id = bus_before.current_route_id
        original_status = bus_before.status
        self.assertEqual(original_route_id, target_rec.source_route_id)

        # Dispatcher APPROVES the recommendation
        review_data = ReallocationReviewCreate(
            decision="APPROVED",
            dispatcher_id="DISPATCHER-CHIEF",
            notes="Advisory approval granted.",
        )
        OptimizationService.record_review(
            db=self.db,
            recommendation_id=target_rec.id,
            review_data=review_data,
        )

        # Query bus state after review
        bus_after = self.db.query(Bus).filter_by(id=candidate_bus_id).first()
        self.assertEqual(bus_after.current_route_id, original_route_id, "Bus route assignment must NOT be changed!")
        self.assertEqual(bus_after.status, original_status, "Bus operational status must NOT be changed!")
        self.assertNotEqual(
            bus_after.current_route_id,
            target_rec.target_route_id,
            "Bus must not be automatically dispatched to target route!",
        )

    # -------------------------------------------------------------------------
    # 3. Input Validation & Error Handling
    # -------------------------------------------------------------------------

    def test_06_invalid_decision_raises_400(self):
        """Test that invalid decisions raise HTTP 400 Bad Request."""
        recs = OptimizationService.generate_recommendations(self.db)
        target_rec = recs[0]

        invalid_decisions = ["DISPATCHED", "EXECUTE", "CANCEL", "MAYBE", "", "123"]
        for bad_dec in invalid_decisions:
            review_data = ReallocationReviewCreate(decision=bad_dec)
            with self.assertRaises(HTTPException) as ctx:
                OptimizationService.record_review(
                    db=self.db,
                    recommendation_id=target_rec.id,
                    review_data=review_data,
                )
            self.assertEqual(ctx.exception.status_code, 400)
            self.assertIn("Invalid decision", ctx.exception.detail)

    def test_07_missing_recommendation_raises_404(self):
        """Test that reviewing a non-existent recommendation raises HTTP 404 Not Found."""
        review_data = ReallocationReviewCreate(decision="APPROVED")
        with self.assertRaises(HTTPException) as ctx:
            OptimizationService.record_review(
                db=self.db,
                recommendation_id="REC-UNKNOWN-ROUTE-999",
                review_data=review_data,
            )
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertIn("not found", ctx.exception.detail)

    # -------------------------------------------------------------------------
    # 4. Persistence, History & Retrieval
    # -------------------------------------------------------------------------

    def test_08_get_reviews_and_filtering(self):
        """Test retrieving all reviews and filtering by decision."""
        recs = OptimizationService.generate_recommendations(self.db)
        rec = recs[0]

        # Record 3 decisions
        OptimizationService.record_review(
            self.db, rec.id, ReallocationReviewCreate(decision="APPROVED", dispatcher_id="D1")
        )
        OptimizationService.record_review(
            self.db, rec.id, ReallocationReviewCreate(decision="REJECTED", dispatcher_id="D2")
        )
        OptimizationService.record_review(
            self.db, rec.id, ReallocationReviewCreate(decision="DEFERRED", dispatcher_id="D3")
        )

        # All reviews
        all_revs = OptimizationService.get_reviews(self.db)
        self.assertEqual(len(all_revs), 3)

        # Filter by APPROVED
        app_revs = OptimizationService.get_reviews(self.db, decision="APPROVED")
        self.assertEqual(len(app_revs), 1)
        self.assertEqual(app_revs[0].decision, "APPROVED")

        # Filter by REJECTED
        rej_revs = OptimizationService.get_reviews(self.db, decision="REJECTED")
        self.assertEqual(len(rej_revs), 1)
        self.assertEqual(rej_revs[0].decision, "REJECTED")

    def test_09_recommendation_history_ordered_latest_first(self):
        """Test that get_recommendation_history returns audit trail ordered latest first."""
        recs = OptimizationService.generate_recommendations(self.db)
        rec = recs[0]

        # First DEFERRED, then APPROVED
        OptimizationService.record_review(
            self.db, rec.id, ReallocationReviewCreate(decision="DEFERRED", notes="Round 1")
        )
        OptimizationService.record_review(
            self.db, rec.id, ReallocationReviewCreate(decision="APPROVED", notes="Round 2")
        )

        history = OptimizationService.get_recommendation_history(self.db, rec.id)
        self.assertEqual(len(history), 2)
        # Latest first
        self.assertEqual(history[0].decision, "APPROVED")
        self.assertEqual(history[0].notes, "Round 2")
        self.assertEqual(history[1].decision, "DEFERRED")
        self.assertEqual(history[1].notes, "Round 1")

    # -------------------------------------------------------------------------
    # 5. Recommendation List & Overview Enrichment
    # -------------------------------------------------------------------------

    def test_10_recommendations_include_latest_review_status(self):
        """Test that generate_recommendations includes review_status and latest_review."""
        recs = OptimizationService.generate_recommendations(self.db)
        rec = recs[0]
        self.assertIsNone(rec.review_status)
        self.assertIsNone(rec.latest_review)

        # Dispatcher approves
        OptimizationService.record_review(
            self.db, rec.id, ReallocationReviewCreate(decision="APPROVED", dispatcher_id="D-CHIEF")
        )

        # Re-fetch recommendations
        updated_recs = OptimizationService.generate_recommendations(self.db)
        updated_rec = next(r for r in updated_recs if r.id == rec.id)
        self.assertEqual(updated_rec.review_status, "APPROVED")
        self.assertIsNotNone(updated_rec.latest_review)
        self.assertEqual(updated_rec.latest_review.dispatcher_id, "D-CHIEF")

    def test_11_optimization_overview_counts_reviews(self):
        """Test that get_overview returns accurate approved, rejected, deferred, and pending counts."""
        overview_initial = OptimizationService.get_overview(self.db)
        self.assertGreater(overview_initial.total_recommendations, 0)
        self.assertEqual(overview_initial.approved_count, 0)
        self.assertEqual(overview_initial.pending_count, overview_initial.total_recommendations)

        recs = OptimizationService.generate_recommendations(self.db)
        OptimizationService.record_review(
            self.db, recs[0].id, ReallocationReviewCreate(decision="APPROVED")
        )

        overview_after = OptimizationService.get_overview(self.db)
        self.assertEqual(overview_after.approved_count, 1)
        self.assertEqual(overview_after.pending_count, overview_initial.total_recommendations - 1)

    # -------------------------------------------------------------------------
    # 6. API Route Handlers
    # -------------------------------------------------------------------------

    def test_12_api_route_handlers(self):
        """Test FastAPI route handlers directly with dependency injection."""
        recs = get_optimization_recommendations(db=self.db)
        self.assertGreater(len(recs), 0)
        rec_id = recs[0].id

        # POST /recommendations/{id}/review
        review_res = record_dispatcher_review(
            recommendation_id=rec_id,
            review_data=ReallocationReviewCreate(decision="APPROVED", notes="Tested via route handler"),
            db=self.db,
        )
        self.assertEqual(review_res.decision, "APPROVED")

        # GET /reviews
        all_reviews = get_dispatcher_reviews(db=self.db)
        self.assertEqual(len(all_reviews), 1)

        # GET /recommendations/{id}/history
        history = get_recommendation_review_history(recommendation_id=rec_id, db=self.db)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].recommendation_id, rec_id)

        # GET /overview
        overview = get_optimization_overview(db=self.db)
        self.assertEqual(overview.approved_count, 1)


if __name__ == "__main__":
    unittest.main()
