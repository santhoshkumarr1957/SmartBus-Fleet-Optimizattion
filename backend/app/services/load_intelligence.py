"""Rule-based Load Intelligence Engine for SmartBus.

Analyzes real-time bus passenger loads, route capacities, and identifies
overloaded routes, underutilized routes, and potential reallocation opportunities.
"""
from typing import List, Optional, Dict
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.bus import Bus
from app.models.route import Route
from app.models.passenger_load import PassengerLoad
from app.models.reallocation_execution import ReallocationExecution
from app.schemas.intelligence import (
    IntelligenceOverviewResponse,
    RouteIntelligenceResponse,
    BusIntelligenceResponse,
    ReallocationOpportunityResponse,
)

# Load factor classification threshold boundaries
THRESHOLD_LOW_UPPER = 0.50
THRESHOLD_NORMAL_UPPER = 0.80
THRESHOLD_HIGH_UPPER = 1.00


def _to_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensure a datetime object is timezone-aware in UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def classify_load_factor(load_factor: float) -> str:
    """Classify load factor according to established system thresholds.

    Thresholds:
        - LOW: load_factor < 0.50
        - NORMAL: 0.50 <= load_factor < 0.80
        - HIGH: 0.80 <= load_factor < 1.00
        - CRITICAL: load_factor >= 1.00
    """
    if load_factor < THRESHOLD_LOW_UPPER:
        return "LOW"
    elif load_factor < THRESHOLD_NORMAL_UPPER:
        return "NORMAL"
    elif load_factor < THRESHOLD_HIGH_UPPER:
        return "HIGH"
    else:
        return "CRITICAL"


def calculate_load_factor(passenger_count: int, capacity: int) -> float:
    """Safely compute load factor, handling zero or invalid capacity."""
    if capacity <= 0:
        return 0.0
    bounded_passengers = max(0, passenger_count)
    return round(bounded_passengers / capacity, 4)


def calculate_available_seats(capacity: int, passenger_count: int) -> int:
    """Compute remaining available seats, guaranteeing a non-negative result."""
    if capacity <= 0:
        return 0
    bounded_passengers = max(0, passenger_count)
    return max(0, capacity - bounded_passengers)


def generate_route_assessment(
    status: str,
    load_factor: float,
    total_passengers: int,
    total_capacity: int,
    available_seats: int,
    number_of_buses: int,
) -> str:
    """Generate an explainable, deterministic assessment summary for a route."""
    if number_of_buses == 0 or total_capacity <= 0:
        return "Route has no active buses assigned; total operational capacity is 0."

    pct = round(load_factor * 100, 1)

    if status == "CRITICAL":
        return (
            f"Critical overcrowding detected: load factor is {pct}% "
            f"({total_passengers}/{total_capacity} passengers). Urgent capacity addition required."
        )
    elif status == "HIGH":
        return (
            f"High passenger load: load factor is {pct}% "
            f"({total_passengers}/{total_capacity} passengers, {available_seats} seats remaining). "
            f"Route is operating near capacity and needs attention."
        )
    elif status == "NORMAL":
        return (
            f"Optimal operational load: load factor is {pct}% "
            f"({total_passengers}/{total_capacity} passengers). "
            f"Route is operating within acceptable capacity ({available_seats} seats available)."
        )
    else:  # LOW
        return (
            f"Route is underutilized: load factor is {pct}% "
            f"({total_passengers}/{total_capacity} passengers). "
            f"Potential spare capacity available ({available_seats} seats available)."
        )


def detect_reallocation_opportunities(
    routes: List[RouteIntelligenceResponse],
) -> List[ReallocationOpportunityResponse]:
    """Detect explainable reallocation opportunities between overloaded and underutilized routes.

    Pairs routes needing attention (HIGH or CRITICAL) with routes having spare
    capacity (LOW). Only routes with active buses can provide spare capacity.
    """
    overloaded = [r for r in routes if r.status in ("HIGH", "CRITICAL")]
    underutilized = [
        r for r in routes if r.status == "LOW" and (r.number_of_buses or 0) > 0
    ]

    # Prioritize CRITICAL over HIGH, then highest load factor descending
    severity_order = {"CRITICAL": 0, "HIGH": 1}
    overloaded.sort(
        key=lambda r: (severity_order.get(r.status, 2), -r.load_factor, r.route_id)
    )

    # Prioritize lowest load factor ascending for spare capacity sources
    underutilized.sort(key=lambda r: (r.load_factor, r.route_id))

    opportunities: List[ReallocationOpportunityResponse] = []
    for ov in overloaded:
        for un in underutilized:
            reason = (
                f"Route {ov.route_number} is operating at {ov.status} load "
                f"({round(ov.load_factor * 100, 1)}%), requiring additional capacity, while "
                f"Route {un.route_number} is underutilized "
                f"({round(un.load_factor * 100, 1)}%) with potential spare capacity."
            )
            opportunities.append(
                ReallocationOpportunityResponse(
                    overloaded_route_id=ov.route_id,
                    overloaded_route_number=ov.route_number,
                    overloaded_route_status=ov.status,
                    overloaded_route_load_factor=ov.load_factor,
                    underutilized_route_id=un.route_id,
                    underutilized_route_number=un.route_number,
                    underutilized_route_load_factor=un.load_factor,
                    reason=reason,
                )
            )

    return opportunities


class LoadIntelligenceService:
    """Service providing read-only intelligence aggregation and analysis."""

    @staticmethod
    def get_latest_passenger_load(db: Session, bus_id: int) -> Optional[PassengerLoad]:
        """Retrieve the most recent passenger load record for a specific bus."""
        return (
            db.query(PassengerLoad)
            .filter(PassengerLoad.bus_id == bus_id)
            .order_by(PassengerLoad.timestamp.desc(), PassengerLoad.id.desc())
            .first()
        )

    @classmethod
    def get_bus_intelligence(cls, db: Session) -> List[BusIntelligenceResponse]:
        """Calculate load intelligence for all active buses using their latest telemetry."""
        # 1. Authoritative in-process simulation telemetry
        try:
            from app.simulator.manager import simulation_manager
            sim_telemetry = simulation_manager.get_active_buses_telemetry()
            if sim_telemetry:
                return [
                    BusIntelligenceResponse(
                        bus_id=b["bus_id"],
                        bus_number=b["bus_number"],
                        route_id=b["route_id"],
                        route_number=b["route_number"],
                        home_route_id=b["home_route_id"],
                        home_route_number=b["home_route_number"],
                        assigned_route_id=b["assigned_route_id"],
                        assigned_route_number=b["assigned_route_number"],
                        active_route_id=b["active_route_id"],
                        active_route_number=b["active_route_number"],
                        passenger_count=b["passenger_count"],
                        capacity=b["capacity"],
                        available_seats=max(0, b["capacity"] - b["passenger_count"]),
                        load_factor=b["load_factor"],
                        status=classify_load_factor(b["load_factor"]),
                        is_transferring=b["is_transferring"],
                        transfer_status=b["transfer_status"],
                        target_route_id=b["target_route_id"],
                        target_route_number=b["target_route_number"],
                    )
                    for b in sim_telemetry
                ]
        except Exception:
            pass

        # 2. Database query fallback
        buses = (
            db.query(Bus)
            .filter(Bus.status.notin_(["INACTIVE", "OUT_OF_SERVICE", "MAINTENANCE"]))
            .order_by(Bus.id)
            .all()
        )
        routes = db.query(Route).all()
        routes_by_num = {r.route_number: r for r in routes}
        routes_by_id = {r.id: r for r in routes}

        # Query recent executions to accurately detect active transfers
        try:
            latest_executions = (
                db.query(ReallocationExecution)
                .order_by(ReallocationExecution.created_at.desc(), ReallocationExecution.id.desc())
                .limit(20)
                .all()
            )
            exec_by_bus = {}
            for ex in latest_executions:
                if ex.bus_id not in exec_by_bus:
                    exec_by_bus[ex.bus_id] = ex
        except Exception:
            exec_by_bus = {}

        results: List[BusIntelligenceResponse] = []

        for bus in buses:
            capacity = max(0, bus.capacity) if bus.capacity is not None else 0
            latest_load = cls.get_latest_passenger_load(db, bus.id)

            if latest_load is not None:
                raw_load = latest_load.current_load if latest_load.current_load is not None else 0
                passenger_count = max(0, min(capacity, raw_load))
            else:
                passenger_count = 0

            available_seats = calculate_available_seats(capacity, passenger_count)
            load_factor = calculate_load_factor(passenger_count, capacity)
            status = classify_load_factor(load_factor)

            assigned_route_id = bus.current_route_id
            assigned_route = routes_by_id.get(assigned_route_id) if assigned_route_id else None
            assigned_route_number = assigned_route.route_number if assigned_route else None

            # Determine home route from fleet setup convention (e.g. 101A -> 101, 202A -> 202, 303A -> 303)
            home_r_num = "".join([c for c in bus.bus_number if c.isdigit()]) or assigned_route_number
            home_r = routes_by_num.get(home_r_num)
            home_route_id = home_r.id if home_r else None
            home_route_number = home_r.route_number if home_r else home_r_num

            # Check for active transfer status
            recent_exec = exec_by_bus.get(bus.id)
            is_transferring = False
            transfer_status = "IDLE"
            target_route_id = None
            target_route_number = None

            if recent_exec and recent_exec.status in ("EXECUTED", "IN_PROGRESS"):
                created_at_utc = _to_utc(recent_exec.created_at)
                if created_at_utc is not None:
                    now_utc = datetime.now(timezone.utc)
                    time_since = (now_utc - created_at_utc).total_seconds()
                    if time_since < 180:
                        is_transferring = True
                        transfer_status = "IN_PROGRESS"
                        target_route_id = recent_exec.target_route_id
                        target_route_number = recent_exec.target_route_number

            # If bus is currently transferring, active route is source route until arrival
            if is_transferring and recent_exec:
                active_route_id = recent_exec.source_route_id
                active_route_number = recent_exec.source_route_number
            else:
                active_route_id = assigned_route_id
                active_route_number = assigned_route_number

            results.append(
                BusIntelligenceResponse(
                    bus_id=bus.id,
                    bus_number=bus.bus_number,
                    route_id=assigned_route_id,
                    route_number=assigned_route_number,
                    home_route_id=home_route_id,
                    home_route_number=home_route_number,
                    assigned_route_id=assigned_route_id,
                    assigned_route_number=assigned_route_number,
                    active_route_id=active_route_id,
                    active_route_number=active_route_number,
                    passenger_count=passenger_count,
                    capacity=capacity,
                    available_seats=available_seats,
                    load_factor=load_factor,
                    status=status,
                    is_transferring=is_transferring,
                    transfer_status=transfer_status,
                    target_route_id=target_route_id,
                    target_route_number=target_route_number,
                )
            )

        return results

    @classmethod
    def get_route_intelligence_from_buses(
        cls, db: Session, bus_intel: List[BusIntelligenceResponse]
    ) -> List[RouteIntelligenceResponse]:
        """Aggregate route intelligence from pre-fetched bus intelligence records."""
        routes = db.query(Route).filter(Route.is_active == True).order_by(Route.id).all()  # noqa: E712
        buses_by_route: Dict[int, List[BusIntelligenceResponse]] = {}
        for b in bus_intel:
            if b.route_id is not None:
                buses_by_route.setdefault(b.route_id, []).append(b)

        active_breakdown_bus_ids = set()
        if db is not None:
            try:
                from app.models.bus_breakdown import BusBreakdown
                active_bbs = (
                    db.query(BusBreakdown.bus_id)
                    .filter(BusBreakdown.status.in_(("REPORTED", "CONFIRMED", "UNDER_REPAIR")))
                    .all()
                )
                active_breakdown_bus_ids = {b_id for (b_id,) in active_bbs}
            except Exception:
                pass

        results: List[RouteIntelligenceResponse] = []
        for route in routes:
            assigned_buses = buses_by_route.get(route.id, [])
            operational_buses = [b for b in assigned_buses if b.bus_id not in active_breakdown_bus_ids]
            total_passengers = sum(b.passenger_count for b in assigned_buses)
            total_capacity = sum(b.capacity for b in operational_buses)
            available_seats = calculate_available_seats(total_capacity, total_passengers)
            load_factor = calculate_load_factor(total_passengers, total_capacity)
            status = classify_load_factor(load_factor)
            assessment = generate_route_assessment(
                status=status,
                load_factor=load_factor,
                total_passengers=total_passengers,
                total_capacity=total_capacity,
                available_seats=available_seats,
                number_of_buses=len(operational_buses),
            )

            prof = None
            try:
                from app.simulator.manager import simulation_manager
                prof = simulation_manager.route_demands.get(str(route.route_number))
            except Exception:
                pass

            results.append(
                RouteIntelligenceResponse(
                    route_id=route.id,
                    route_number=route.route_number,
                    number_of_buses=len(operational_buses),
                    total_passengers=total_passengers,
                    total_capacity=total_capacity,
                    available_seats=available_seats,
                    load_factor=load_factor,
                    status=status,
                    assessment=assessment,
                    demand_profile=prof or "NORMAL",
                )
            )

        return results

    @classmethod
    def get_route_intelligence(cls, db: Session) -> List[RouteIntelligenceResponse]:
        """Aggregate load intelligence across all active transit routes."""
        bus_intel = cls.get_bus_intelligence(db)
        return cls.get_route_intelligence_from_buses(db, bus_intel)

    @classmethod
    def get_overview(cls, db: Session) -> IntelligenceOverviewResponse:
        """Provide a fleet-wide overview of route statuses and reallocation opportunities."""
        buses_intel = cls.get_bus_intelligence(db)
        routes_intel = cls.get_route_intelligence_from_buses(db, buses_intel)
        opportunities = detect_reallocation_opportunities(routes_intel)

        low_routes = sum(1 for r in routes_intel if r.status == "LOW")
        normal_routes = sum(1 for r in routes_intel if r.status == "NORMAL")
        high_routes = sum(1 for r in routes_intel if r.status == "HIGH")
        critical_routes = sum(1 for r in routes_intel if r.status == "CRITICAL")
        routes_needing_attention = high_routes + critical_routes

        return IntelligenceOverviewResponse(
            total_routes=len(routes_intel),
            total_buses=len(buses_intel),
            low_routes=low_routes,
            normal_routes=normal_routes,
            high_routes=high_routes,
            critical_routes=critical_routes,
            routes_needing_attention=routes_needing_attention,
            potential_reallocation_opportunities=len(opportunities),
        )

    @classmethod
    def get_opportunities(cls, db: Session) -> List[ReallocationOpportunityResponse]:
        """Identify potential reallocation candidate pairs."""
        routes_intel = cls.get_route_intelligence(db)
        return detect_reallocation_opportunities(routes_intel)
