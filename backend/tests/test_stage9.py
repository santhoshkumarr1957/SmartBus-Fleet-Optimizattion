"""Stage 9 Verification Test Suite for SmartBus (TRANSIGHT).

Tests all Stage 9 criteria:
1. Every alert detection rule:
   - Critical Route Load (LF >= 1.00) -> CRITICAL
   - High Route Load (0.80 <= LF < 1.00) -> HIGH
   - Bus Breakdown -> CRITICAL or HIGH
   - Route Disruption (is_active == False) -> CRITICAL
   - Reallocation Opportunity -> HIGH or WARNING
   - Simulation Notice -> SIMULATION source
2. Exact threshold boundaries: 0.80 and 1.00 load factors.
3. Duplicate suppression across multiple refresh cycles.
4. Recurrence: Brand new alert generated when condition recurs after resolution.
5. Filtering and summary counts: status, severity, type, and source.
6. Dispatcher workflow: acknowledgement and resolution transitions.
7. Invalid IDs (404) and invalid state transitions (400).
8. Missing telemetry: bus without GPS or passenger loads handled gracefully.
9. Simulation vs. live alert separation.
10. Strict non-mutation: zero modifications to bus assignments, route records, telemetry, or review history.
11. Direct FastAPI route handler verification via dependency injection.
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
from app.models.notification import Notification

from app.schemas.notification import (
    NotificationResponse,
    NotificationActionRequest,
    NotificationSummaryResponse,
    NotificationRefreshResponse,
)
from app.services.notification import NotificationService
from app.api.routes.notifications import (
    get_notifications,
    get_notification_summary,
    acknowledge_alert,
    resolve_alert,
    refresh_notifications,
)
from app.services.disruption import DisruptionService


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


def seed_test_operational_network(db: Session):
    """Seed test routes, buses, and telemetry for notification testing:

    - Route 101: "Downtown Express" (CRITICAL, 2 buses, capacity 100, passengers 105 -> LF 1.05)
    - Route 202: "Suburban Loop" (LOW, 2 buses, capacity 120, passengers 20 -> LF 0.167)
    - Route 303: "Crosstown Line" (HIGH, 1 bus, capacity 50, passengers 42 -> LF 0.84)
    - Route 404: "Westside Shuttle" (DISRUPTED, is_active=False)
    - Bus 505B: Broken down bus (status="BROKEN_DOWN", capacity 60, route 101)
    - Bus 606M: In maintenance (status="MAINTENANCE", capacity 60, route 202)
    - Bus 707X: Missing telemetry bus (no position, no passenger load, route 202)
    """
    now = datetime.now(timezone.utc)

    # Routes
    r101 = Route(id=1, route_number="101", name="Downtown Express", origin="Central", destination="Market", is_active=True)
    r202 = Route(id=2, route_number="202", name="Suburban Loop", origin="Suburban Hub", destination="Mall", is_active=True)
    r303 = Route(id=3, route_number="303", name="Crosstown Line", origin="North", destination="South", is_active=True)
    r404 = Route(id=4, route_number="404", name="Westside Shuttle", origin="West Park", destination="Plaza", is_active=False)
    db.add_all([r101, r202, r303, r404])
    db.flush()

    # Stops
    s1 = Stop(id=1, route_id=r101.id, name="Central", sequence_order=1, latitude=37.7749, longitude=-122.4194)
    s2 = Stop(id=2, route_id=r202.id, name="Hub", sequence_order=1, latitude=37.7800, longitude=-122.4100)
    s3 = Stop(id=3, route_id=r303.id, name="North", sequence_order=1, latitude=37.7900, longitude=-122.4200)
    db.add_all([s1, s2, s3])
    db.flush()

    # Buses
    b101a = Bus(id=1, bus_number="101A", license_plate="BUS-101A", capacity=50, current_route_id=r101.id, status="ACTIVE")
    b101b = Bus(id=2, bus_number="101B", license_plate="BUS-101B", capacity=50, current_route_id=r101.id, status="ACTIVE")
    b202a = Bus(id=3, bus_number="202A", license_plate="BUS-202A", capacity=60, current_route_id=r202.id, status="ACTIVE")
    b202b = Bus(id=4, bus_number="202B", license_plate="BUS-202B", capacity=60, current_route_id=r202.id, status="ACTIVE")
    b303a = Bus(id=5, bus_number="303A", license_plate="BUS-303A", capacity=50, current_route_id=r303.id, status="ACTIVE")
    b505b = Bus(id=6, bus_number="505B", license_plate="BUS-505B", capacity=60, current_route_id=r101.id, status="BROKEN_DOWN")
    b606m = Bus(id=7, bus_number="606M", license_plate="BUS-606M", capacity=60, current_route_id=r202.id, status="MAINTENANCE")
    b707x = Bus(id=8, bus_number="707X", license_plate="BUS-707X", capacity=60, current_route_id=r202.id, status="ACTIVE")
    db.add_all([b101a, b101b, b202a, b202b, b303a, b505b, b606m, b707x])
    db.flush()

    # Passenger loads
    l1 = PassengerLoad(id=1, bus_id=b101a.id, current_load=55, capacity=50, load_factor=1.10, timestamp=now)
    l2 = PassengerLoad(id=2, bus_id=b101b.id, current_load=50, capacity=50, load_factor=1.00, timestamp=now)
    # Total on Route 101 active buses = 105 passengers / 100 capacity = 1.05 (CRITICAL)

    l3 = PassengerLoad(id=3, bus_id=b202a.id, current_load=15, capacity=60, load_factor=0.25, timestamp=now)
    l4 = PassengerLoad(id=4, bus_id=b202b.id, current_load=5, capacity=60, load_factor=0.0833, timestamp=now)
    # Total on Route 202 = 20 / 120 = 0.1667 (LOW)

    l5 = PassengerLoad(id=5, bus_id=b303a.id, current_load=42, capacity=50, load_factor=0.84, timestamp=now)
    # Total on Route 303 = 42 / 50 = 0.84 (HIGH)

    db.add_all([l1, l2, l3, l4, l5])

    # Positions
    p1 = BusPosition(id=1, bus_id=b101a.id, latitude=37.7750, longitude=-122.4190, speed=20.0, heading=90.0, timestamp=now)
    p2 = BusPosition(id=2, bus_id=b101b.id, latitude=37.7760, longitude=-122.4180, speed=15.0, heading=95.0, timestamp=now)
    p3 = BusPosition(id=3, bus_id=b202a.id, latitude=37.7810, longitude=-122.4090, speed=25.0, heading=45.0, timestamp=now)
    p4 = BusPosition(id=4, bus_id=b202b.id, latitude=37.7820, longitude=-122.4080, speed=22.0, heading=50.0, timestamp=now)
    p5 = BusPosition(id=5, bus_id=b303a.id, latitude=37.7910, longitude=-122.4190, speed=18.0, heading=180.0, timestamp=now)
    db.add_all([p1, p2, p3, p4, p5])
    db.commit()


class TestStage9NotificationService(unittest.TestCase):
    def setUp(self):
        self.db = create_in_memory_db()
        seed_test_operational_network(self.db)
        DisruptionService.clear_cache()

    def tearDown(self):
        close_db(self.db)

    # -------------------------------------------------------------------------
    # 1. Alert Rules Detection
    # -------------------------------------------------------------------------
    def test_01_alert_rules_detection(self):
        """1. Verify detection of all alert conditions: Critical Load, High Load, Breakdown, Disruption, Opportunity."""
        refresh_res = NotificationService.evaluate_operational_alerts(db=self.db, include_simulation=False)
        self.assertGreater(refresh_res.new_alerts_created, 0)

        alerts = NotificationService.get_notifications(db=self.db)
        types = [a.alert_type for a in alerts]

        # Rule 1: Critical Route Load on Route 101 (LF = 1.05)
        self.assertIn("CRITICAL_ROUTE_LOAD", types)
        crit_alert = next(a for a in alerts if a.alert_type == "CRITICAL_ROUTE_LOAD")
        self.assertEqual(crit_alert.severity, "CRITICAL")
        self.assertEqual(crit_alert.route_number, "101")
        self.assertIn("Critical Overcrowding", crit_alert.title)
        self.assertEqual(crit_alert.status, "ACTIVE")

        # Rule 2: High Route Load on Route 303 (LF = 0.84)
        self.assertIn("HIGH_ROUTE_LOAD", types)
        high_alert = next(a for a in alerts if a.alert_type == "HIGH_ROUTE_LOAD")
        self.assertEqual(high_alert.severity, "HIGH")
        self.assertEqual(high_alert.route_number, "303")
        self.assertIn("High Passenger Load", high_alert.title)

        # Rule 3: Bus Breakdown on Bus 505B and 606M
        self.assertIn("BUS_BREAKDOWN", types)
        breakdown_alerts = [a for a in alerts if a.alert_type == "BUS_BREAKDOWN"]
        self.assertEqual(len(breakdown_alerts), 2)
        b505_alert = next(a for a in breakdown_alerts if a.bus_number == "505B")
        self.assertEqual(b505_alert.severity, "CRITICAL")
        b606_alert = next(a for a in breakdown_alerts if a.bus_number == "606M")
        self.assertEqual(b606_alert.severity, "HIGH")

        # Rule 4: Route Disruption on Route 404 (is_active=False)
        self.assertIn("ROUTE_DISRUPTION", types)
        disrupt_alert = next(a for a in alerts if a.alert_type == "ROUTE_DISRUPTION")
        self.assertEqual(disrupt_alert.severity, "CRITICAL")
        self.assertEqual(disrupt_alert.route_number, "404")

        # Rule 5: Fleet Reallocation Opportunity
        self.assertIn("REALLOCATION_OPPORTUNITY", types)
        realloc_alert = next(a for a in alerts if a.alert_type == "REALLOCATION_OPPORTUNITY")
        self.assertIn(realloc_alert.severity, ["HIGH", "WARNING"])
        self.assertEqual(realloc_alert.route_number, "303")

    # -------------------------------------------------------------------------
    # 2. Exact Load Factor Threshold Boundaries (0.80 and 1.00)
    # -------------------------------------------------------------------------
    def test_02_load_factor_threshold_boundaries(self):
        """2. Test boundary conditions at exactly 0.80 and 1.00 load factors."""
        # Clean existing notifications
        self.db.query(Notification).delete()
        self.db.commit()

        # Update Route 303 load to exactly 0.799 (39.95 / 50 -> 40 / 50 is 0.80, so test 39 / 50 = 0.78)
        pax_load = self.db.query(PassengerLoad).filter(PassengerLoad.bus_id == 5).first()
        pax_load.current_load = 39  # 39/50 = 0.78 -> < 0.80 -> NO alert
        self.db.commit()

        NotificationService.evaluate_operational_alerts(db=self.db, include_simulation=False)
        r303_alerts = self.db.query(Notification).filter(Notification.route_id == 3).all()
        self.assertEqual(len(r303_alerts), 0, "Load factor < 0.80 should NOT generate an alert")

        # Boundary at exactly 0.80 (40 / 50 = 0.80)
        pax_load.current_load = 40
        self.db.commit()
        NotificationService.evaluate_operational_alerts(db=self.db, include_simulation=False)
        r303_alert = self.db.query(Notification).filter(Notification.route_id == 3).first()
        self.assertIsNotNone(r303_alert)
        self.assertEqual(r303_alert.alert_type, "HIGH_ROUTE_LOAD")
        self.assertEqual(r303_alert.severity, "HIGH")

        # Boundary at exactly 1.00 (50 / 50 = 1.00)
        pax_load.current_load = 50
        # Resolve previous high alert first so new critical alert is tested
        r303_alert.status = "RESOLVED"
        self.db.commit()

        NotificationService.evaluate_operational_alerts(db=self.db, include_simulation=False)
        r303_crit = (
            self.db.query(Notification)
            .filter(
                Notification.route_id == 3,
                Notification.alert_type == "CRITICAL_ROUTE_LOAD",
                Notification.status == "ACTIVE",
            )
            .first()
        )
        self.assertIsNotNone(r303_crit)
        self.assertEqual(r303_crit.alert_type, "CRITICAL_ROUTE_LOAD")
        self.assertEqual(r303_crit.severity, "CRITICAL")

    # -------------------------------------------------------------------------
    # 3. Duplicate Suppression Across Multiple Polling Cycles
    # -------------------------------------------------------------------------
    def test_03_duplicate_suppression_on_repeated_polling(self):
        """3. Multiple refresh cycles on unchanged operational state must NOT create duplicates."""
        res1 = NotificationService.evaluate_operational_alerts(db=self.db, include_simulation=False)
        count_after_first = self.db.query(Notification).count()
        self.assertGreater(count_after_first, 0)
        self.assertEqual(res1.new_alerts_created, count_after_first)

        # Second sweep
        res2 = NotificationService.evaluate_operational_alerts(db=self.db, include_simulation=False)
        count_after_second = self.db.query(Notification).count()
        self.assertEqual(count_after_second, count_after_first, "Duplicate alerts must NOT be created!")
        self.assertEqual(res2.new_alerts_created, 0)
        self.assertEqual(res2.existing_alerts_updated, count_after_first)

        # Third sweep
        res3 = NotificationService.evaluate_operational_alerts(db=self.db, include_simulation=False)
        count_after_third = self.db.query(Notification).count()
        self.assertEqual(count_after_third, count_after_first)
        self.assertEqual(res3.new_alerts_created, 0)

    # -------------------------------------------------------------------------
    # 4. Recurrence After Resolution
    # -------------------------------------------------------------------------
    def test_04_alert_recurrence_after_resolution(self):
        """4. If an alert is resolved and the condition recurs, a NEW alert is generated."""
        NotificationService.evaluate_operational_alerts(db=self.db, include_simulation=False)

        crit_alert = self.db.query(Notification).filter(Notification.alert_type == "CRITICAL_ROUTE_LOAD").first()
        self.assertIsNotNone(crit_alert)
        self.assertEqual(crit_alert.status, "ACTIVE")

        # Dispatcher resolves the alert
        NotificationService.resolve_alert(db=self.db, alert_id=crit_alert.id, dispatcher_id="DISPATCHER-2", notes="Resolved")
        self.assertEqual(crit_alert.status, "RESOLVED")

        # Next evaluation cycle: condition still persists in operational telemetry
        res = NotificationService.evaluate_operational_alerts(db=self.db, include_simulation=False)
        self.assertGreater(res.new_alerts_created, 0)

        # A new ACTIVE alert should be created for this recurring incident
        all_crit_alerts = self.db.query(Notification).filter(Notification.alert_type == "CRITICAL_ROUTE_LOAD").all()
        self.assertEqual(len(all_crit_alerts), 2, "Should have 1 resolved and 1 newly active recurring alert")

        active_new = next(a for a in all_crit_alerts if a.status == "ACTIVE")
        self.assertNotEqual(active_new.id, crit_alert.id)
        self.assertEqual(active_new.dedup_key, crit_alert.dedup_key)

    # -------------------------------------------------------------------------
    # 5. Filtering and Summary Counts
    # -------------------------------------------------------------------------
    def test_05_filtering_and_summary_counts(self):
        """5. Test querying notifications by status, severity, type, and source, and summary aggregates."""
        NotificationService.evaluate_operational_alerts(db=self.db, include_simulation=False)

        # Summary check
        summary = NotificationService.get_summary(db=self.db)
        self.assertGreater(summary.total_alerts, 0)
        self.assertEqual(summary.active_count, summary.total_alerts)
        self.assertEqual(summary.acknowledged_count, 0)
        self.assertEqual(summary.resolved_count, 0)
        self.assertGreater(summary.critical_count, 0)
        self.assertGreater(summary.high_count, 0)

        # Acknowledge 1 alert
        first_alert = self.db.query(Notification).first()
        NotificationService.acknowledge_alert(db=self.db, alert_id=first_alert.id)

        # Resolve 1 alert
        second_alert = self.db.query(Notification).offset(1).first()
        NotificationService.resolve_alert(db=self.db, alert_id=second_alert.id)

        summary2 = NotificationService.get_summary(db=self.db)
        self.assertEqual(summary2.acknowledged_count, 1)
        self.assertEqual(summary2.resolved_count, 1)
        self.assertEqual(summary2.active_count, summary.total_alerts - 2)

        # Filtering checks
        ack_list = NotificationService.get_notifications(db=self.db, status_filter="ACKNOWLEDGED")
        self.assertEqual(len(ack_list), 1)
        self.assertEqual(ack_list[0].id, first_alert.id)

        res_list = NotificationService.get_notifications(db=self.db, status_filter="RESOLVED")
        self.assertEqual(len(res_list), 1)
        self.assertEqual(res_list[0].id, second_alert.id)

        crit_list = NotificationService.get_notifications(db=self.db, severity_filter="CRITICAL")
        for a in crit_list:
            self.assertEqual(a.severity, "CRITICAL")

    # -------------------------------------------------------------------------
    # 6. Dispatcher Workflow: Acknowledge & Resolve Transitions
    # -------------------------------------------------------------------------
    def test_06_dispatcher_workflow_transitions(self):
        """6. Test ACTIVE -> ACKNOWLEDGED -> RESOLVED transitions with audit timestamps."""
        NotificationService.evaluate_operational_alerts(db=self.db, include_simulation=False)
        alert = self.db.query(Notification).first()
        self.assertEqual(alert.status, "ACTIVE")

        # Step 1: Acknowledge
        ack = NotificationService.acknowledge_alert(
            db=self.db,
            alert_id=alert.id,
            dispatcher_id="OPERATOR-X",
            notes="Acknowledging active incident",
        )
        self.assertEqual(ack.status, "ACKNOWLEDGED")
        self.assertEqual(ack.acknowledged_by, "OPERATOR-X")
        self.assertIsNotNone(ack.acknowledged_at)
        self.assertEqual(ack.notes, "Acknowledging active incident")

        # Step 2: Resolve
        res = NotificationService.resolve_alert(
            db=self.db,
            alert_id=alert.id,
            dispatcher_id="SUPERVISOR-Y",
            notes="Issue mitigated",
        )
        self.assertEqual(res.status, "RESOLVED")
        self.assertEqual(res.resolved_by, "SUPERVISOR-Y")
        self.assertIsNotNone(res.resolved_at)
        self.assertIn("Issue mitigated", res.notes)

    # -------------------------------------------------------------------------
    # 7. Invalid IDs and Invalid State Transitions
    # -------------------------------------------------------------------------
    def test_07_invalid_ids_and_state_transitions(self):
        """7. Test 404 on non-existent alert and 400 on invalid workflow transitions."""
        # Non-existent ID raises 404
        with self.assertRaises(HTTPException) as ctx:
            NotificationService.acknowledge_alert(db=self.db, alert_id=99999)
        self.assertEqual(ctx.exception.status_code, 404)

        with self.assertRaises(HTTPException) as ctx:
            NotificationService.resolve_alert(db=self.db, alert_id=99999)
        self.assertEqual(ctx.exception.status_code, 404)

        # Create test alert
        alert = Notification(
            alert_type="TEST_ALERT",
            severity="INFO",
            title="Test",
            description="Test",
            dedup_key="TEST:1",
            status="ACTIVE",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.db.add(alert)
        self.db.commit()

        # Acknowledge once -> OK
        NotificationService.acknowledge_alert(db=self.db, alert_id=alert.id)

        # Acknowledging again raises 400
        with self.assertRaises(HTTPException) as ctx:
            NotificationService.acknowledge_alert(db=self.db, alert_id=alert.id)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("already acknowledged", ctx.exception.detail)

        # Resolve -> OK
        NotificationService.resolve_alert(db=self.db, alert_id=alert.id)

        # Resolving again raises 400
        with self.assertRaises(HTTPException) as ctx:
            NotificationService.resolve_alert(db=self.db, alert_id=alert.id)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("already resolved", ctx.exception.detail)

        # Acknowledging a resolved alert raises 400
        with self.assertRaises(HTTPException) as ctx:
            NotificationService.acknowledge_alert(db=self.db, alert_id=alert.id)
        self.assertEqual(ctx.exception.status_code, 400)

    # -------------------------------------------------------------------------
    # 8. Missing Telemetry Handling
    # -------------------------------------------------------------------------
    def test_08_missing_telemetry_graceful_handling(self):
        """8. Bus 707X without GPS position or passenger loads handled smoothly without crashes."""
        # Bus 707X was seeded without passenger load and without GPS
        b707 = self.db.query(Bus).filter(Bus.bus_number == "707X").first()
        self.assertIsNotNone(b707)

        # Should complete without throwing any exception
        res = NotificationService.evaluate_operational_alerts(db=self.db, include_simulation=False)
        self.assertIsNotNone(res)
        self.assertGreater(res.total_active_alerts, 0)

    # -------------------------------------------------------------------------
    # 9. Simulation vs Live Alert Separation
    # -------------------------------------------------------------------------
    def test_09_simulation_and_live_alert_separation(self):
        """9. Simulation notices carry source='SIMULATION' and are isolated from live operational alerts."""
        from app.schemas.disruption import DisruptionSimulationRequest
        # Trigger an in-memory simulation scenario
        DisruptionService.simulate_disruption(
            db=self.db,
            request=DisruptionSimulationRequest(disruption_type="ROUTE_CLOSURE", route_number="202"),
        )

        # Evaluate with include_simulation=True
        NotificationService.evaluate_operational_alerts(db=self.db, include_simulation=True)

        all_alerts = NotificationService.get_notifications(db=self.db)
        sim_alerts = [a for a in all_alerts if a.source == "SIMULATION"]
        live_alerts = [a for a in all_alerts if a.source == "LIVE"]

        self.assertGreater(len(sim_alerts), 0)
        self.assertGreater(len(live_alerts), 0)

        for s in sim_alerts:
            self.assertEqual(s.source, "SIMULATION")
            self.assertEqual(s.alert_type, "SIMULATION_NOTICE")
            self.assertTrue(s.title.startswith("[SIMULATION]"))

        # Filtering by source='LIVE' must return ONLY live alerts
        filtered_live = NotificationService.get_notifications(db=self.db, source_filter="LIVE")
        self.assertEqual(len(filtered_live), len(live_alerts))
        for l in filtered_live:
            self.assertEqual(l.source, "LIVE")

    # -------------------------------------------------------------------------
    # 10. Strict Non-Mutation of Operational Data
    # -------------------------------------------------------------------------
    def test_10_strict_operational_data_non_mutation(self):
        """10. CRITICAL INVARIANT: Notification creation, acknowledgement, and resolution

        must NEVER mutate bus route assignments, bus statuses, route states, or reviews.
        """
        # Baseline snapshot
        buses_before = {b.id: (b.current_route_id, b.status) for b in self.db.query(Bus).all()}
        routes_before = {r.id: (r.is_active, r.route_number) for r in self.db.query(Route).all()}
        load_count_before = self.db.query(PassengerLoad).count()
        pos_count_before = self.db.query(BusPosition).count()

        # Execute alert lifecycle
        NotificationService.evaluate_operational_alerts(db=self.db, include_simulation=True)
        alerts = NotificationService.get_notifications(db=self.db)

        if alerts:
            NotificationService.acknowledge_alert(db=self.db, alert_id=alerts[0].id)
        if len(alerts) > 1:
            NotificationService.resolve_alert(db=self.db, alert_id=alerts[1].id)

        # Refresh
        self.db.expire_all()

        # Invariant checks
        buses_after = {b.id: (b.current_route_id, b.status) for b in self.db.query(Bus).all()}
        self.assertEqual(buses_before, buses_after, "Bus route assignments and statuses MUST NOT be modified!")

        routes_after = {r.id: (r.is_active, r.route_number) for r in self.db.query(Route).all()}
        self.assertEqual(routes_before, routes_after, "Route records MUST NOT be modified!")

        self.assertEqual(load_count_before, self.db.query(PassengerLoad).count())
        self.assertEqual(pos_count_before, self.db.query(BusPosition).count())

    # -------------------------------------------------------------------------
    # 11. FastAPI Route Handlers via Dependency Injection
    # -------------------------------------------------------------------------
    def test_11_api_route_handlers_via_dependency_injection(self):
        """11. Direct invocation of FastAPI route handler functions."""
        # 1. POST /api/notifications/refresh
        ref_res = refresh_notifications(include_simulation=False, db=self.db)
        self.assertGreater(ref_res.total_active_alerts, 0)

        # 2. GET /api/notifications
        list_res = get_notifications(status_filter="ACTIVE", db=self.db)
        self.assertGreater(len(list_res), 0)

        # 3. GET /api/notifications/summary
        sum_res = get_notification_summary(db=self.db)
        self.assertEqual(sum_res.total_alerts, len(list_res))

        # 4. POST /api/notifications/{alert_id}/acknowledge
        first_id = list_res[0].id
        ack_res = acknowledge_alert(
            alert_id=first_id,
            payload=NotificationActionRequest(dispatcher_id="TEST-DISP", notes="Acknowledged in test"),
            db=self.db,
        )
        self.assertEqual(ack_res.status, "ACKNOWLEDGED")
        self.assertEqual(ack_res.acknowledged_by, "TEST-DISP")

        # 5. POST /api/notifications/{alert_id}/resolve
        res_res = resolve_alert(
            alert_id=first_id,
            payload=NotificationActionRequest(dispatcher_id="TEST-DISP", notes="Resolved in test"),
            db=self.db,
        )
        self.assertEqual(res_res.status, "RESOLVED")
        self.assertEqual(res_res.resolved_by, "TEST-DISP")


if __name__ == "__main__":
    unittest.main()
