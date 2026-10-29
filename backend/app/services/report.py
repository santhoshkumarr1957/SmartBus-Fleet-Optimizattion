"""TRANSIGHT Stage 10: Reports and Performance Analytics Service.

Provides deterministic, rule-based transit operational analytics across fleet utilization,
route performance comparisons, disruption event audits, dispatcher review workflows,
and historical timeseries telemetry trends.
"""
from datetime import datetime, timezone, timedelta
import csv
import io
from typing import Dict, List, Optional, Tuple, Any
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.bus import Bus
from app.models.route import Route
from app.models.passenger_load import PassengerLoad
from app.models.reallocation_review import ReallocationReview
from app.models.notification import Notification
from app.services.optimization import OptimizationService
from app.services.disruption import DisruptionService
from app.schemas.report import (
    BusUtilizationBrief,
    FleetUtilizationReportResponse,
    RoutePerformanceItem,
    RoutePerformanceReportResponse,
    DisruptionEventBrief,
    DisruptionReportResponse,
    ReviewOutcomeBrief,
    ReallocationReportResponse,
    TrendDataPoint,
    TrendsReportResponse,
    ReportsOverviewResponse,
)


def _to_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensure a datetime object is timezone-aware in UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class ReportService:
    """Service generating deterministic reports and analytics."""

    # -------------------------------------------------------------------------
    # A. Fleet Utilization
    # -------------------------------------------------------------------------
    @classmethod
    def get_fleet_utilization(cls, db: Session) -> FleetUtilizationReportResponse:
        """Calculate fleet asset availability, total seat capacities, and utilization."""
        now = datetime.now(timezone.utc)
        all_buses = db.query(Bus).order_by(Bus.id).all()
        all_routes = {r.id: r.route_number for r in db.query(Route).all()}

        # Latest passenger load for each bus
        latest_loads: Dict[int, int] = {}
        for b in all_buses:
            rec = (
                db.query(PassengerLoad)
                .filter(PassengerLoad.bus_id == b.id)
                .order_by(PassengerLoad.timestamp.desc(), PassengerLoad.id.desc())
                .first()
            )
            latest_loads[b.id] = rec.current_load if rec and rec.current_load is not None else 0

        # Categorize vehicle operational statuses
        operational_buses: List[Bus] = []
        broken_down_buses: List[Bus] = []
        maintenance_buses: List[Bus] = []
        inactive_buses: List[Bus] = []

        for b in all_buses:
            st = (b.status or "").upper()
            if st == "BROKEN_DOWN":
                broken_down_buses.append(b)
            elif st == "MAINTENANCE":
                maintenance_buses.append(b)
            elif st == "INACTIVE":
                inactive_buses.append(b)
            else:
                operational_buses.append(b)

        total_buses = len(all_buses)
        op_count = len(operational_buses)
        availability_pct = round((op_count / total_buses) * 100, 2) if total_buses > 0 else 0.0

        total_capacity = sum(b.capacity for b in operational_buses)
        total_passengers = sum(latest_loads.get(b.id, 0) for b in operational_buses)
        available_seats = max(0, total_capacity - total_passengers)
        fleet_load_factor = round(total_passengers / total_capacity, 4) if total_capacity > 0 else 0.0

        # Load factor distribution across operational buses
        load_dist: Dict[str, int] = {"LOW": 0, "NORMAL": 0, "HIGH": 0, "CRITICAL": 0}
        bus_briefs: List[BusUtilizationBrief] = []

        for b in all_buses:
            b_cap = b.capacity or 60
            b_pax = latest_loads.get(b.id, 0)
            b_lf = round(b_pax / b_cap, 4) if b_cap > 0 else 0.0
            avail_seats = max(0, b_cap - b_pax)

            is_op = (b.status or "").upper() not in ("INACTIVE", "BROKEN_DOWN", "MAINTENANCE")
            if is_op:
                if b_lf >= 1.0:
                    load_dist["CRITICAL"] += 1
                elif b_lf >= 0.8:
                    load_dist["HIGH"] += 1
                elif b_lf >= 0.5:
                    load_dist["NORMAL"] += 1
                else:
                    load_dist["LOW"] += 1

            bus_briefs.append(
                BusUtilizationBrief(
                    bus_id=b.id,
                    bus_number=b.bus_number,
                    license_plate=b.license_plate,
                    status=b.status,
                    capacity=b_cap,
                    current_load=b_pax,
                    available_seats=avail_seats,
                    load_factor=b_lf,
                    current_route_id=b.current_route_id,
                    current_route_number=all_routes.get(b.current_route_id) if b.current_route_id else None,
                )
            )

        return FleetUtilizationReportResponse(
            generated_at=now,
            time_scope="CURRENT_OPERATIONAL_SNAPSHOT",
            total_buses=total_buses,
            operational_buses=op_count,
            inactive_buses=len(inactive_buses),
            broken_down_buses=len(broken_down_buses),
            maintenance_buses=len(maintenance_buses),
            fleet_availability_pct=availability_pct,
            total_passenger_capacity=total_capacity,
            total_current_passengers=total_passengers,
            available_seats=available_seats,
            fleet_load_factor=fleet_load_factor,
            load_distribution=load_dist,
            buses=bus_briefs,
        )

    # -------------------------------------------------------------------------
    # B. Route Performance
    # -------------------------------------------------------------------------
    @classmethod
    def get_route_performance(cls, db: Session) -> RoutePerformanceReportResponse:
        """Compare route-level passenger demand, capacities, and identify congestion imbalances."""
        now = datetime.now(timezone.utc)
        all_routes = db.query(Route).order_by(Route.id).all()
        all_buses = db.query(Bus).order_by(Bus.id).all()

        # Map latest passenger loads
        latest_loads: Dict[int, int] = {}
        for b in all_buses:
            rec = (
                db.query(PassengerLoad)
                .filter(PassengerLoad.bus_id == b.id)
                .order_by(PassengerLoad.timestamp.desc(), PassengerLoad.id.desc())
                .first()
            )
            latest_loads[b.id] = rec.current_load if rec and rec.current_load is not None else 0

        # Group operational buses by route
        route_buses: Dict[int, List[Bus]] = {}
        for b in all_buses:
            if b.current_route_id is not None:
                is_op = (b.status or "").upper() not in ("INACTIVE", "BROKEN_DOWN", "MAINTENANCE")
                if is_op:
                    route_buses.setdefault(b.current_route_id, []).append(b)

        route_items: List[RoutePerformanceItem] = []
        active_count = 0
        inactive_count = 0
        overloaded_count = 0
        underutilized_count = 0

        highest_lf = -1.0
        highest_route_no: Optional[str] = None
        lowest_lf = 999.0
        lowest_route_no: Optional[str] = None

        for r in all_routes:
            if r.is_active:
                active_count += 1
            else:
                inactive_count += 1

            assigned = route_buses.get(r.id, [])
            tot_cap = sum(b.capacity for b in assigned)
            tot_pax = sum(latest_loads.get(b.id, 0) for b in assigned)
            avail = max(0, tot_cap - tot_pax)
            lf = round(tot_pax / tot_cap, 4) if tot_cap > 0 else 0.0

            # Classification
            if not r.is_active:
                status_label = "CLOSED"
                oc_level = "Route Disrupted / Inactive"
            elif lf >= 1.0:
                status_label = "CRITICAL"
                oc_level = "Severe Overcrowding (>=100% Capacity)"
            elif lf >= 0.8:
                status_label = "HIGH"
                oc_level = "Heavy Congestion (80%-99% Capacity)"
            elif lf >= 0.5:
                status_label = "NORMAL"
                oc_level = "Balanced Operational Load (50%-79%)"
            else:
                status_label = "LOW"
                oc_level = "Underutilized Surplus Capacity (<50%)"

            if r.is_active:
                if status_label in ("HIGH", "CRITICAL"):
                    overloaded_count += 1
                elif status_label == "LOW":
                    underutilized_count += 1

                if assigned:
                    if lf > highest_lf:
                        highest_lf = lf
                        highest_route_no = r.route_number
                    if lf < lowest_lf:
                        lowest_lf = lf
                        lowest_route_no = r.route_number

            route_items.append(
                RoutePerformanceItem(
                    route_id=r.id,
                    route_number=r.route_number,
                    name=r.name,
                    origin=r.origin,
                    destination=r.destination,
                    is_active=r.is_active,
                    assigned_bus_count=len(assigned),
                    total_capacity=tot_cap,
                    total_passengers=tot_pax,
                    available_seats=avail,
                    load_factor=lf,
                    status=status_label,
                    overcrowding_level=oc_level,
                )
            )

        return RoutePerformanceReportResponse(
            generated_at=now,
            time_scope="CURRENT_OPERATIONAL_SNAPSHOT",
            total_routes=len(all_routes),
            active_routes=active_count,
            inactive_routes=inactive_count,
            overloaded_routes_count=overloaded_count,
            underutilized_routes_count=underutilized_count,
            highest_load_route=highest_route_no,
            lowest_load_route=lowest_route_no,
            routes=route_items,
        )

    # -------------------------------------------------------------------------
    # C. Disruption Analysis
    # -------------------------------------------------------------------------
    @classmethod
    def get_disruption_analysis(cls, db: Session) -> DisruptionReportResponse:
        """Audit real transit disruptions and clearly isolated simulated disruption scenarios."""
        now = datetime.now(timezone.utc)

        # 1. Real operational alerts from Notification table
        live_notifications = (
            db.query(Notification)
            .filter(Notification.source == "LIVE")
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .all()
        )

        live_breakdowns = sum(1 for n in live_notifications if n.alert_type == "BUS_BREAKDOWN")
        live_closures = sum(1 for n in live_notifications if n.alert_type == "ROUTE_DISRUPTION")
        live_critical_loads = sum(1 for n in live_notifications if n.alert_type == "CRITICAL_ROUTE_LOAD")
        live_active = sum(1 for n in live_notifications if n.status == "ACTIVE")
        live_ack = sum(1 for n in live_notifications if n.status == "ACKNOWLEDGED")
        live_resolved = sum(1 for n in live_notifications if n.status == "RESOLVED")

        live_events = [
            DisruptionEventBrief(
                alert_id=n.id,
                alert_type=n.alert_type,
                severity=n.severity,
                title=n.title,
                description=n.description,
                source="LIVE",
                status=n.status,
                route_number=n.route_number,
                bus_number=n.bus_number,
                created_at=n.created_at,
                resolved_at=n.resolved_at,
                acknowledged_by=n.acknowledged_by,
                resolved_by=n.resolved_by,
            )
            for n in live_notifications
        ]

        # 2. Simulated disruption scenarios
        sim_notifications = (
            db.query(Notification)
            .filter(Notification.source == "SIMULATION")
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .all()
        )
        sim_events = [
            DisruptionEventBrief(
                alert_id=n.id,
                alert_type=n.alert_type,
                severity=n.severity,
                title=n.title,
                description=n.description,
                source="SIMULATION",
                status=n.status,
                route_number=n.route_number,
                bus_number=n.bus_number,
                created_at=n.created_at,
                resolved_at=n.resolved_at,
                acknowledged_by=n.acknowledged_by,
                resolved_by=n.resolved_by,
            )
            for n in sim_notifications
        ]

        cached_scenarios = DisruptionService.get_cached_scenarios()
        total_sim = len(sim_events) + len(cached_scenarios)

        return DisruptionReportResponse(
            generated_at=now,
            live_incidents_total=len(live_notifications),
            live_active_count=live_active,
            live_acknowledged_count=live_ack,
            live_resolved_count=live_resolved,
            live_breakdowns_count=live_breakdowns,
            live_route_disruptions_count=live_closures,
            live_overcrowding_alerts_count=live_critical_loads,
            live_events=live_events,
            simulation_scenarios_count=total_sim,
            simulated_events=sim_events,
            is_simulation_isolated=True,
            disclaimer=(
                "Live operational alerts and simulated scenarios are strictly isolated. "
                "Simulated results reflect hypothetical resilience tests and do NOT reflect real-world breakdowns or route disruptions."
            ),
        )

    # -------------------------------------------------------------------------
    # D. Reallocation & Dispatcher Review
    # -------------------------------------------------------------------------
    @classmethod
    def get_reallocation_analysis(cls, db: Session) -> ReallocationReportResponse:
        """Report advisory reallocation recommendations and human dispatcher review audit metrics."""
        now = datetime.now(timezone.utc)

        # 1. Advisory recommendations from Stage 5 engine
        try:
            proposals = OptimizationService.generate_recommendations(db=db)
        except Exception:
            proposals = []

        high_pri = sum(1 for p in proposals if p.priority == "HIGH")
        med_pri = sum(1 for p in proposals if p.priority == "MEDIUM")
        low_pri = sum(1 for p in proposals if p.priority == "LOW")

        # 2. Historical dispatcher reviews from Stage 7
        reviews = (
            db.query(ReallocationReview)
            .order_by(ReallocationReview.created_at.desc(), ReallocationReview.id.desc())
            .all()
        )

        appr = sum(1 for r in reviews if (r.decision or "").upper() == "APPROVED")
        rej = sum(1 for r in reviews if (r.decision or "").upper() == "REJECTED")
        def_count = sum(1 for r in reviews if (r.decision or "").upper() == "DEFERRED")

        reviewed_rec_ids = {r.recommendation_id for r in reviews}
        pending_count = sum(1 for p in proposals if p.id not in reviewed_rec_ids)

        review_briefs = [
            ReviewOutcomeBrief(
                id=r.id,
                recommendation_id=r.recommendation_id,
                decision=r.decision,
                dispatcher_id=r.dispatcher_id,
                target_route_number=r.target_route_number,
                source_route_number=r.source_route_number,
                candidate_bus_number=r.candidate_bus_number,
                created_at=r.created_at,
                notes=r.notes,
            )
            for r in reviews[:100]
        ]

        return ReallocationReportResponse(
            generated_at=now,
            active_proposals_count=len(proposals),
            high_priority_count=high_pri,
            medium_priority_count=med_pri,
            low_priority_count=low_pri,
            total_reviews_recorded=len(reviews),
            approved_count=appr,
            rejected_count=rej,
            deferred_count=def_count,
            pending_count=pending_count,
            recent_reviews=review_briefs,
            operational_limitation_statement=(
                "The current transit schema records dispatcher review determinations and advisory proposals for supervisory oversight. "
                "In accordance with safety constraints, APPROVED reviews do not execute automated vehicle reassignments or track actual completed physical deadhead transfers."
            ),
        )

    # -------------------------------------------------------------------------
    # E. Historical Trends
    # -------------------------------------------------------------------------
    @classmethod
    def get_historical_trends(cls, db: Session, time_range: str = "24h") -> TrendsReportResponse:
        """Aggregate timestamped telemetry and passenger loads into configurable timeseries buckets."""
        now = datetime.now(timezone.utc)
        clean_range = (time_range or "24h").strip().lower()

        if clean_range == "1h":
            start_time = now - timedelta(hours=1)
            bucket_duration = timedelta(minutes=5)
            bucket_label = "5m"
            num_buckets = 12
        elif clean_range == "24h":
            start_time = now - timedelta(hours=24)
            bucket_duration = timedelta(hours=1)
            bucket_label = "1h"
            num_buckets = 24
        elif clean_range == "7d":
            start_time = now - timedelta(days=7)
            bucket_duration = timedelta(hours=6)
            bucket_label = "6h"
            num_buckets = 28
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid time_range '{time_range}'. Supported ranges are '1h', '24h', and '7d'.",
            )

        # Query passenger loads in historical window
        records = (
            db.query(PassengerLoad)
            .filter(PassengerLoad.timestamp >= start_time, PassengerLoad.timestamp <= now)
            .order_by(PassengerLoad.timestamp.asc())
            .all()
        )

        total_samples = len(records)
        overall_avg_lf = (
            round(sum(r.load_factor for r in records) / total_samples, 4)
            if total_samples > 0
            else 0.0
        )
        peak_lf = (
            round(max(r.load_factor for r in records), 4)
            if total_samples > 0
            else 0.0
        )

        # Partition records into deterministic timeseries buckets
        datapoints: List[TrendDataPoint] = []
        for i in range(num_buckets):
            b_start = start_time + (i * bucket_duration)
            b_end = b_start + bucket_duration

            # Match records within bucket interval
            b_records = [
                r for r in records
                if _to_utc(r.timestamp) is not None
                and b_start <= _to_utc(r.timestamp) < b_end
            ]

            if b_records:
                avg_b_lf = round(sum(r.load_factor for r in b_records) / len(b_records), 4)
                tot_pax = sum(r.current_load for r in b_records)
                peak_b_lf = round(max(r.load_factor for r in b_records), 4)
                count = len(b_records)
            else:
                avg_b_lf = 0.0
                tot_pax = 0
                peak_b_lf = 0.0
                count = 0

            # Formatted bucket label
            if clean_range == "1h":
                ts_str = b_start.strftime("%H:%M")
            elif clean_range == "24h":
                ts_str = b_start.strftime("%m-%d %H:%M")
            else:
                ts_str = b_start.strftime("%m-%d %Hh")

            datapoints.append(
                TrendDataPoint(
                    timestamp=ts_str,
                    average_load_factor=avg_b_lf,
                    total_passengers=tot_pax,
                    peak_load_factor=peak_b_lf,
                    sample_count=count,
                )
            )

        note = (
            f"Timeseries trends aggregated across {total_samples} recorded telemetry samples in the last {time_range}. "
            f"Empty buckets indicate periods without recorded vehicle telemetry."
        )

        return TrendsReportResponse(
            generated_at=now,
            time_range=clean_range,
            bucket_interval=bucket_label,
            start_time=start_time,
            end_time=now,
            total_samples=total_samples,
            overall_average_load_factor=overall_avg_lf,
            peak_observed_load_factor=peak_lf,
            datapoints=datapoints,
            data_density_note=note,
        )

    # -------------------------------------------------------------------------
    # F. Reports Executive Overview
    # -------------------------------------------------------------------------
    @classmethod
    def get_overview(cls, db: Session) -> ReportsOverviewResponse:
        """Consolidated executive dashboard summary across all performance domains."""
        now = datetime.now(timezone.utc)
        fleet = cls.get_fleet_utilization(db)
        routes = cls.get_route_performance(db)
        disruptions = cls.get_disruption_analysis(db)
        reallocation = cls.get_reallocation_analysis(db)
        trends = cls.get_historical_trends(db, time_range="24h")

        return ReportsOverviewResponse(
            generated_at=now,
            fleet=fleet,
            routes=routes,
            disruptions_summary={
                "live_incidents_total": disruptions.live_incidents_total,
                "live_active": disruptions.live_active_count,
                "live_breakdowns": disruptions.live_breakdowns_count,
                "live_closures": disruptions.live_route_disruptions_count,
                "simulated_scenarios": disruptions.simulation_scenarios_count,
            },
            reviews_summary={
                "total_reviews": reallocation.total_reviews_recorded,
                "approved": reallocation.approved_count,
                "rejected": reallocation.rejected_count,
                "deferred": reallocation.deferred_count,
                "pending": reallocation.pending_count,
            },
            trends_preview=trends,
        )

    # -------------------------------------------------------------------------
    # G. CSV Report Exporter
    # -------------------------------------------------------------------------
    @classmethod
    def export_csv(cls, db: Session, report_type: str, time_range: str = "24h") -> str:
        """Generate safe, RFC 4180 compliant CSV string for transit operational reports."""
        clean_type = (report_type or "").strip().lower()
        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

        if clean_type == "fleet":
            rep = cls.get_fleet_utilization(db)
            writer.writerow([
                "Bus ID",
                "Bus Number",
                "License Plate",
                "Status",
                "Capacity",
                "Current Load",
                "Available Seats",
                "Load Factor",
                "Route Number",
            ])
            for b in rep.buses:
                writer.writerow([
                    b.bus_id,
                    b.bus_number,
                    b.license_plate,
                    b.status,
                    b.capacity,
                    b.current_load,
                    b.available_seats,
                    f"{b.load_factor:.4f}",
                    b.current_route_number or "Unassigned",
                ])

        elif clean_type == "routes":
            rep = cls.get_route_performance(db)
            writer.writerow([
                "Route ID",
                "Route Number",
                "Route Name",
                "Status",
                "Active",
                "Assigned Buses",
                "Total Capacity",
                "Total Passengers",
                "Available Seats",
                "Load Factor",
                "Overcrowding Level",
            ])
            for r in rep.routes:
                writer.writerow([
                    r.route_id,
                    r.route_number,
                    r.name or "",
                    r.status,
                    "Yes" if r.is_active else "No",
                    r.assigned_bus_count,
                    r.total_capacity,
                    r.total_passengers,
                    r.available_seats,
                    f"{r.load_factor:.4f}",
                    r.overcrowding_level,
                ])

        elif clean_type == "disruptions":
            rep = cls.get_disruption_analysis(db)
            writer.writerow([
                "Alert ID",
                "Source",
                "Alert Type",
                "Severity",
                "Title",
                "Route Number",
                "Bus Number",
                "Status",
                "Created At",
                "Resolved At",
                "Acknowledged By",
                "Resolved By",
            ])
            for e in rep.live_events:
                writer.writerow([
                    e.alert_id,
                    e.source,
                    e.alert_type,
                    e.severity,
                    e.title,
                    e.route_number or "",
                    e.bus_number or "",
                    e.status,
                    e.created_at.isoformat() if e.created_at else "",
                    e.resolved_at.isoformat() if e.resolved_at else "",
                    e.acknowledged_by or "",
                    e.resolved_by or "",
                ])
            for s in rep.simulated_events:
                writer.writerow([
                    s.alert_id,
                    s.source,
                    s.alert_type,
                    s.severity,
                    s.title,
                    s.route_number or "",
                    s.bus_number or "",
                    s.status,
                    s.created_at.isoformat() if s.created_at else "",
                    s.resolved_at.isoformat() if s.resolved_at else "",
                    s.acknowledged_by or "",
                    s.resolved_by or "",
                ])

        elif clean_type == "reallocation":
            rep = cls.get_reallocation_analysis(db)
            writer.writerow([
                "Review ID",
                "Recommendation ID",
                "Decision",
                "Dispatcher ID",
                "Target Route",
                "Source Route",
                "Candidate Bus",
                "Created At",
                "Notes",
            ])
            for rv in rep.recent_reviews:
                writer.writerow([
                    rv.id,
                    rv.recommendation_id,
                    rv.decision,
                    rv.dispatcher_id or "",
                    rv.target_route_number or "",
                    rv.source_route_number or "",
                    rv.candidate_bus_number or "",
                    rv.created_at.isoformat() if rv.created_at else "",
                    rv.notes or "",
                ])

        elif clean_type == "trends":
            rep = cls.get_historical_trends(db, time_range=time_range)
            writer.writerow([
                "Timestamp Bucket",
                "Average Load Factor",
                "Total Passengers",
                "Peak Load Factor",
                "Sample Count",
            ])
            for dp in rep.datapoints:
                writer.writerow([
                    dp.timestamp,
                    f"{dp.average_load_factor:.4f}",
                    dp.total_passengers,
                    f"{dp.peak_load_factor:.4f}",
                    dp.sample_count,
                ])

        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported report type '{report_type}'. Supported types: 'fleet', 'routes', 'disruptions', 'reallocation', 'trends'.",
            )

        return output.getvalue()
