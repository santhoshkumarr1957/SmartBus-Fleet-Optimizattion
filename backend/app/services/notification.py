"""Rule-based Transit Notification and Alert Management Engine (Stage 9).

Evaluates real-time operational data across corridors and fleet vehicles to detect
critical load, high load, bus breakdowns, corridor disruptions, and advisory
fleet reallocation opportunities. Provides stable alert identity, duplicate
suppression on polling, recurrence after resolution, and dispatcher review workflows.
"""
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi import HTTPException, status

from app.models.notification import Notification
from app.models.route import Route
from app.models.bus import Bus
from app.models.passenger_load import PassengerLoad
from app.schemas.notification import (
    NotificationSummaryResponse,
    NotificationRefreshResponse,
)
from app.services.optimization import OptimizationService
from app.services.disruption import DisruptionService

# Track the timestamp of the last operational sweep in memory
_LAST_EVALUATED_AT: Optional[datetime] = None


class NotificationService:
    """Manages deterministic transit alerts, duplicate suppression, and dispatcher workflows."""

    VALID_STATUSES = {"ACTIVE", "ACKNOWLEDGED", "RESOLVED"}
    VALID_SEVERITIES = {"CRITICAL", "HIGH", "WARNING", "INFO"}
    VALID_SOURCES = {"LIVE", "SIMULATION"}

    @classmethod
    def get_notifications(
        cls,
        db: Session,
        status_filter: Optional[str] = None,
        severity_filter: Optional[str] = None,
        type_filter: Optional[str] = None,
        source_filter: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Notification]:
        """Retrieve notifications with optional status, severity, type, and source filtering."""
        query = db.query(Notification)

        if status_filter and isinstance(status_filter, str):
            clean_status = status_filter.strip().upper()
            if clean_status != "ALL":
                query = query.filter(Notification.status == clean_status)

        if severity_filter and isinstance(severity_filter, str):
            clean_sev = severity_filter.strip().upper()
            if clean_sev != "ALL":
                query = query.filter(Notification.severity == clean_sev)

        if type_filter and isinstance(type_filter, str):
            clean_type = type_filter.strip().upper()
            if clean_type != "ALL":
                query = query.filter(Notification.alert_type == clean_type)

        if source_filter and isinstance(source_filter, str):
            clean_source = source_filter.strip().upper()
            if clean_source != "ALL":
                query = query.filter(Notification.source == clean_source)

        clean_limit = limit if isinstance(limit, int) and limit > 0 else 50
        clean_offset = offset if isinstance(offset, int) and offset >= 0 else 0
        return (
            query.order_by(Notification.created_at.desc(), Notification.id.desc())
            .offset(clean_offset)
            .limit(clean_limit)
            .all()
        )

    @classmethod
    def get_summary(cls, db: Session) -> NotificationSummaryResponse:
        """Compute aggregate counts of notifications grouped by status, severity, and source."""
        all_alerts = db.query(Notification).all()

        total = len(all_alerts)
        active_count = sum(1 for a in all_alerts if a.status == "ACTIVE")
        ack_count = sum(1 for a in all_alerts if a.status == "ACKNOWLEDGED")
        res_count = sum(1 for a in all_alerts if a.status == "RESOLVED")

        # Active or acknowledged alerts contribute to operational severity attention
        ongoing_alerts = [a for a in all_alerts if a.status in ("ACTIVE", "ACKNOWLEDGED")]
        crit_count = sum(1 for a in ongoing_alerts if a.severity == "CRITICAL")
        high_count = sum(1 for a in ongoing_alerts if a.severity == "HIGH")
        warn_count = sum(1 for a in ongoing_alerts if a.severity == "WARNING")
        info_count = sum(1 for a in ongoing_alerts if a.severity == "INFO")

        live_active = sum(1 for a in all_alerts if a.status == "ACTIVE" and a.source == "LIVE")
        sim_count = sum(1 for a in all_alerts if a.source == "SIMULATION")

        return NotificationSummaryResponse(
            total_alerts=total,
            active_count=active_count,
            acknowledged_count=ack_count,
            resolved_count=res_count,
            critical_count=crit_count,
            high_count=high_count,
            warning_count=warn_count,
            info_count=info_count,
            live_active_count=live_active,
            simulation_count=sim_count,
            last_evaluated_at=_LAST_EVALUATED_AT,
        )

    @classmethod
    def acknowledge_alert(
        cls,
        db: Session,
        alert_id: int,
        dispatcher_id: Optional[str] = "DISPATCHER-1",
        notes: Optional[str] = None,
    ) -> Notification:
        """Acknowledge an active alert by transit dispatcher."""
        alert = db.query(Notification).filter(Notification.id == alert_id).first()
        if not alert:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Notification with ID {alert_id} not found.",
            )

        if alert.status == "ACKNOWLEDGED":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Notification {alert_id} is already acknowledged.",
            )

        if alert.status == "RESOLVED":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot acknowledge notification {alert_id} because it has already been resolved.",
            )

        now = datetime.now(timezone.utc)
        clean_dispatcher = (dispatcher_id or "DISPATCHER-1").strip()
        alert.status = "ACKNOWLEDGED"
        alert.acknowledged_by = clean_dispatcher
        alert.acknowledged_at = now
        if notes:
            alert.notes = notes.strip()
        alert.updated_at = now

        db.commit()
        db.refresh(alert)
        return alert

    @classmethod
    def resolve_alert(
        cls,
        db: Session,
        alert_id: int,
        dispatcher_id: Optional[str] = "DISPATCHER-1",
        notes: Optional[str] = None,
    ) -> Notification:
        """Mark an alert resolved by transit dispatcher."""
        alert = db.query(Notification).filter(Notification.id == alert_id).first()
        if not alert:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Notification with ID {alert_id} not found.",
            )

        if alert.status == "RESOLVED":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Notification {alert_id} is already resolved.",
            )

        now = datetime.now(timezone.utc)
        clean_dispatcher = (dispatcher_id or "DISPATCHER-1").strip()
        alert.status = "RESOLVED"
        alert.resolved_by = clean_dispatcher
        alert.resolved_at = now
        if notes:
            alert.notes = (alert.notes + " | " + notes.strip()) if alert.notes else notes.strip()
        alert.updated_at = now

        db.commit()
        db.refresh(alert)
        return alert

    @classmethod
    def evaluate_operational_alerts(
        cls,
        db: Session,
        include_simulation: bool = True,
    ) -> NotificationRefreshResponse:
        """Evaluate operational database state and create/update alerts with duplicate suppression.

        Detection Rules:
        1. Critical Route Load (LF >= 1.00) -> CRITICAL
        2. High Route Load (0.80 <= LF < 1.00) -> HIGH
        3. Bus Breakdown (status in ("BROKEN_DOWN", "MAINTENANCE")) -> CRITICAL or HIGH
        4. Route Disruption (route is_active == False) -> CRITICAL
        5. Reallocation Opportunity (Stage 5 advisory recommendation on overloaded route) -> HIGH or WARNING
        6. Simulation Notice (disruption simulation scenario cached) -> SIMULATION source notice

        Deduplication Strategy:
        - Uses stable dedup_key per incident.
        - If an ongoing incident (ACTIVE or ACKNOWLEDGED) already exists with dedup_key,
          it is updated with latest values rather than creating a duplicate.
        - If no alert exists or all prior matching alerts were RESOLVED, a new ACTIVE alert
          is created, enabling clean recurrence detection.
        """
        global _LAST_EVALUATED_AT
        now = datetime.now(timezone.utc)
        _LAST_EVALUATED_AT = now

        created_count = 0
        updated_count = 0

        # Pre-fetch existing active or acknowledged alerts to avoid duplicate queries
        existing_ongoing: Dict[str, Notification] = {}
        ongoing_records = (
            db.query(Notification)
            .filter(Notification.status.in_(["ACTIVE", "ACKNOWLEDGED"]))
            .all()
        )
        for r in ongoing_records:
            existing_ongoing[r.dedup_key] = r

        # ---------------------------------------------------------------------
        # 1. Fetch current operational routes and buses (Read-only)
        # ---------------------------------------------------------------------
        all_routes = db.query(Route).all()
        all_buses = db.query(Bus).all()

        # Latest passenger load mapping per bus
        latest_loads: Dict[int, int] = {}
        for b in all_buses:
            rec = (
                db.query(PassengerLoad)
                .filter(PassengerLoad.bus_id == b.id)
                .order_by(PassengerLoad.timestamp.desc(), PassengerLoad.id.desc())
                .first()
            )
            latest_loads[b.id] = rec.current_load if rec and rec.current_load is not None else 0

        # ---------------------------------------------------------------------
        # 2. Rule 1 & 2: Route Passenger Loads (CRITICAL and HIGH)
        # ---------------------------------------------------------------------
        for r in all_routes:
            if not r.is_active:
                continue

            r_buses = [
                b
                for b in all_buses
                if b.current_route_id == r.id
                and (b.status or "").upper() not in ("INACTIVE", "BROKEN_DOWN", "MAINTENANCE")
            ]
            tot_cap = sum(b.capacity for b in r_buses)
            tot_pax = sum(latest_loads.get(b.id, 0) for b in r_buses)
            lf = round(tot_pax / tot_cap, 4) if tot_cap > 0 else 0.0

            # Rule 1: Critical Route Load (LF >= 1.00)
            if lf >= 1.00:
                dedup_key = f"LIVE:CRITICAL_ROUTE_LOAD:ROUTE_{r.id}"
                title = f"Critical Overcrowding: Route {r.route_number}"
                desc = (
                    f"Route {r.route_number} ({r.name or 'Corridor'}) load factor is {(lf * 100):.1f}%, "
                    f"exceeding 100% capacity ({tot_pax} passengers across {tot_cap} total seats)."
                )
                created, updated = cls._upsert_alert(
                    db=db,
                    existing_ongoing=existing_ongoing,
                    dedup_key=dedup_key,
                    alert_type="CRITICAL_ROUTE_LOAD",
                    severity="CRITICAL",
                    title=title,
                    description=desc,
                    source="LIVE",
                    route_id=r.id,
                    route_number=r.route_number,
                    now=now,
                )
                if created: created_count += 1
                elif updated: updated_count += 1

            # Rule 2: High Route Load (0.80 <= LF < 1.00)
            elif lf >= 0.80:
                dedup_key = f"LIVE:HIGH_ROUTE_LOAD:ROUTE_{r.id}"
                title = f"High Passenger Load: Route {r.route_number}"
                desc = (
                    f"Route {r.route_number} ({r.name or 'Corridor'}) load factor is {(lf * 100):.1f}%, "
                    f"nearing capacity ({tot_pax} passengers across {tot_cap} seats)."
                )
                created, updated = cls._upsert_alert(
                    db=db,
                    existing_ongoing=existing_ongoing,
                    dedup_key=dedup_key,
                    alert_type="HIGH_ROUTE_LOAD",
                    severity="HIGH",
                    title=title,
                    description=desc,
                    source="LIVE",
                    route_id=r.id,
                    route_number=r.route_number,
                    now=now,
                )
                if created: created_count += 1
                elif updated: updated_count += 1

        # ---------------------------------------------------------------------
        # 3. Rule 3: Bus Breakdown / Non-Operational Fleet Vehicles
        # ---------------------------------------------------------------------
        for b in all_buses:
            status_clean = (b.status or "").upper()
            if status_clean in ("BROKEN_DOWN", "MAINTENANCE"):
                sev = "CRITICAL" if status_clean == "BROKEN_DOWN" else "HIGH"
                dedup_key = f"LIVE:BUS_BREAKDOWN:BUS_{b.id}"
                r_num = b.current_route.route_number if b.current_route else None
                title = f"Vehicle Non-Operational: Bus {b.bus_number}"
                desc = (
                    f"Bus {b.bus_number} on Route {r_num or 'Unassigned'} has reported status '{status_clean}' "
                    f"and is unavailable for passenger service."
                )
                created, updated = cls._upsert_alert(
                    db=db,
                    existing_ongoing=existing_ongoing,
                    dedup_key=dedup_key,
                    alert_type="BUS_BREAKDOWN",
                    severity=sev,
                    title=title,
                    description=desc,
                    source="LIVE",
                    bus_id=b.id,
                    bus_number=b.bus_number,
                    route_id=b.current_route_id,
                    route_number=r_num,
                    now=now,
                )
                if created: created_count += 1
                elif updated: updated_count += 1

        # ---------------------------------------------------------------------
        # 4. Rule 4: Route Disruption (Inactive / Suspended Corridors)
        # ---------------------------------------------------------------------
        for r in all_routes:
            if not r.is_active:
                dedup_key = f"LIVE:ROUTE_DISRUPTION:ROUTE_{r.id}"
                title = f"Corridor Disrupted: Route {r.route_number}"
                desc = (
                    f"Route {r.route_number} ({r.name or 'Corridor'}) is marked inactive/closed. "
                    f"Service between {r.origin or 'Origin'} and {r.destination or 'Destination'} is discontinued."
                )
                created, updated = cls._upsert_alert(
                    db=db,
                    existing_ongoing=existing_ongoing,
                    dedup_key=dedup_key,
                    alert_type="ROUTE_DISRUPTION",
                    severity="CRITICAL",
                    title=title,
                    description=desc,
                    source="LIVE",
                    route_id=r.id,
                    route_number=r.route_number,
                    now=now,
                )
                if created: created_count += 1
                elif updated: updated_count += 1

        # ---------------------------------------------------------------------
        # 5. Rule 5: Fleet Reallocation Opportunities (Actionable Stage 5)
        # ---------------------------------------------------------------------
        try:
            recommendations = OptimizationService.generate_recommendations(db=db)
            for rec in recommendations:
                if rec.target_route_status in ("HIGH", "CRITICAL"):
                    sev = "HIGH" if rec.priority == "HIGH" else "WARNING"
                    dedup_key = f"LIVE:REALLOCATION_OPPORTUNITY:REC_{rec.id}"
                    title = f"Reallocation Advisory: Route {rec.target_route_number}"
                    desc = (
                        f"Actionable proposal available: Reallocate candidate Bus {rec.candidate_bus_number} "
                        f"from underutilized Route {rec.source_route_number} to alleviate Route {rec.target_route_number} "
                        f"(Optimization Score: {rec.score})."
                    )
                    created, updated = cls._upsert_alert(
                        db=db,
                        existing_ongoing=existing_ongoing,
                        dedup_key=dedup_key,
                        alert_type="REALLOCATION_OPPORTUNITY",
                        severity=sev,
                        title=title,
                        description=desc,
                        source="LIVE",
                        route_id=rec.target_route_id,
                        route_number=rec.target_route_number,
                        bus_id=rec.candidate_bus_id,
                        bus_number=rec.candidate_bus_number,
                        now=now,
                    )
                    if created: created_count += 1
                    elif updated: updated_count += 1
        except Exception:
            # Reallocation advisory calculation failure should not halt basic alerting
            pass

        # ---------------------------------------------------------------------
        # 6. Rule 6: Simulation Notices (Clearly Labeled as SIMULATION)
        # ---------------------------------------------------------------------
        if include_simulation:
            try:
                cached_scenarios = DisruptionService.get_cached_scenarios()
                for scen in cached_scenarios:
                    dedup_key = f"SIMULATION:SIMULATION_NOTICE:{scen.scenario_id}"
                    sev_map = {
                        "CRITICAL": "CRITICAL",
                        "VULNERABLE": "HIGH",
                        "ADEQUATE": "INFO",
                        "EXCELLENT": "INFO",
                    }
                    sev = sev_map.get(scen.resilience_rating, "INFO")
                    title = f"[SIMULATION] {scen.target_description}"
                    desc = (
                        f"Simulated scenario {scen.scenario_id} calculated resilience rating '{scen.resilience_rating}' "
                        f"({scen.resilience_score} pts), with {scen.capacity_lost} capacity lost across "
                        f"{scen.routes_affected_count} corridors. No live vehicle dispatches performed."
                    )
                    created, updated = cls._upsert_alert(
                        db=db,
                        existing_ongoing=existing_ongoing,
                        dedup_key=dedup_key,
                        alert_type="SIMULATION_NOTICE",
                        severity=sev,
                        title=title,
                        description=desc,
                        source="SIMULATION",
                        now=now,
                    )
                    if created: created_count += 1
                    elif updated: updated_count += 1
            except Exception:
                pass

        db.commit()

        # Count active alerts
        total_active = db.query(Notification).filter(Notification.status == "ACTIVE").count()
        total_critical = (
            db.query(Notification)
            .filter(Notification.status.in_(["ACTIVE", "ACKNOWLEDGED"]), Notification.severity == "CRITICAL")
            .count()
        )

        return NotificationRefreshResponse(
            evaluated_at=now,
            new_alerts_created=created_count,
            existing_alerts_updated=updated_count,
            total_active_alerts=total_active,
            critical_alerts_count=total_critical,
            message=(
                f"Evaluated operational conditions: {created_count} new alerts created, "
                f"{updated_count} active incidents updated, {total_active} currently active."
            ),
        )

    @classmethod
    def _upsert_alert(
        cls,
        db: Session,
        existing_ongoing: Dict[str, Notification],
        dedup_key: str,
        alert_type: str,
        severity: str,
        title: str,
        description: str,
        source: str = "LIVE",
        route_id: Optional[int] = None,
        route_number: Optional[str] = None,
        bus_id: Optional[int] = None,
        bus_number: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> Tuple[bool, bool]:
        """Insert a new alert or update an existing active/acknowledged alert.

        Returns (was_created, was_updated).
        """
        if now is None:
            now = datetime.now(timezone.utc)

        existing = existing_ongoing.get(dedup_key)
        if existing:
            # Ongoing incident: suppress duplicate, update metrics
            existing.title = title
            existing.description = description
            existing.severity = severity
            existing.updated_at = now
            return False, True

        # Check if there is an active/acknowledged alert in DB that wasn't in memory map
        db_existing = (
            db.query(Notification)
            .filter(
                Notification.dedup_key == dedup_key,
                Notification.status.in_(["ACTIVE", "ACKNOWLEDGED"]),
            )
            .first()
        )
        if db_existing:
            db_existing.title = title
            db_existing.description = description
            db_existing.severity = severity
            db_existing.updated_at = now
            existing_ongoing[dedup_key] = db_existing
            return False, True

        # No active/acknowledged alert exists -> New alert or genuine recurrence after resolution
        new_alert = Notification(
            alert_type=alert_type,
            severity=severity,
            title=title,
            description=description,
            source=source,
            status="ACTIVE",
            dedup_key=dedup_key,
            route_id=route_id,
            route_number=route_number,
            bus_id=bus_id,
            bus_number=bus_number,
            created_at=now,
            updated_at=now,
        )
        db.add(new_alert)
        existing_ongoing[dedup_key] = new_alert
        return True, False
