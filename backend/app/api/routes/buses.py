from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.bus import Bus
from app.models.route import Route
from app.models.bus_position import BusPosition
from app.models.passenger_load import PassengerLoad
from app.models.reallocation_execution import ReallocationExecution
from app.schemas.live import BusLiveResponse
from app.schemas.optimization import ManualReassignmentCreate, ReallocationExecutionResponse
from app.services.optimization import OptimizationService
from app.simulator.manager import simulation_manager

router = APIRouter()


def _to_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensure a datetime object is timezone-aware in UTC.

    - If dt is None, returns None.
    - If dt is naive, assumes UTC and sets tzinfo to timezone.utc.
    - If dt is timezone-aware, converts to timezone.utc.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@router.get("/live", response_model=List[BusLiveResponse], summary="Get live state of active buses")
def get_live_buses(db: Session = Depends(get_db)) -> List[BusLiveResponse]:
    """Retrieve the latest GPS position, speed, heading, and passenger load for all active buses."""
    # 1. Authoritative source of truth: in-process active bus simulator telemetry
    sim_telemetry = simulation_manager.get_active_buses_telemetry()
    if sim_telemetry:
        return [BusLiveResponse(**b) for b in sim_telemetry]

    # 2. Fallback to database telemetry if simulator has not yet initialized
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection not available",
        )

    # Subqueries to retrieve the latest id for each bus
    pos_subq = (
        db.query(
            BusPosition.bus_id,
            func.max(BusPosition.id).label("max_pos_id"),
        )
        .group_by(BusPosition.bus_id)
        .subquery()
    )

    load_subq = (
        db.query(
            PassengerLoad.bus_id,
            func.max(PassengerLoad.id).label("max_load_id"),
        )
        .group_by(PassengerLoad.bus_id)
        .subquery()
    )

    # Single joined query for all active buses
    rows = (
        db.query(Bus, Route, BusPosition, PassengerLoad)
        .outerjoin(Route, Bus.current_route_id == Route.id)
        .outerjoin(pos_subq, Bus.id == pos_subq.c.bus_id)
        .outerjoin(BusPosition, BusPosition.id == pos_subq.c.max_pos_id)
        .outerjoin(load_subq, Bus.id == load_subq.c.bus_id)
        .outerjoin(PassengerLoad, PassengerLoad.id == load_subq.c.max_load_id)
        .filter(Bus.status != "INACTIVE")
        .order_by(Bus.id)
        .all()
    )

    all_routes = {r.id: r for r in db.query(Route).all()}
    routes_by_num = {r.route_number: r for r in all_routes.values()}

    # Fetch latest executions for active transfer status
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

    results: List[BusLiveResponse] = []
    for bus, route, latest_pos, latest_load in rows:
        assigned_route_id = bus.current_route_id
        assigned_route_number = route.route_number if route else None

        # Determine home route from fleet setup convention (e.g. 101A -> 101, 202A -> 202, 303A -> 303)
        home_r_num = "".join([c for c in bus.bus_number if c.isdigit()]) or assigned_route_number
        home_r = routes_by_num.get(home_r_num)
        home_route_id = home_r.id if home_r else None
        home_route_number = home_r.route_number if home_r else home_r_num

        p_count = latest_load.current_load if latest_load else 0
        cap = bus.capacity if bus.capacity > 0 else 60
        lf = latest_load.load_factor if latest_load else (round(p_count / cap, 4) if cap > 0 else 0.0)

        # Check for transfer status
        recent_exec = exec_by_bus.get(bus.id)
        is_transferring = False
        transfer_status = "IDLE"
        target_route_id = None
        target_route_number = None

        if recent_exec and recent_exec.status in ("EXECUTED", "IN_PROGRESS"):
            # Check elapsed seconds since execution dispatch using UTC timestamps
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
            BusLiveResponse(
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
                latitude=latest_pos.latitude if latest_pos else None,
                longitude=latest_pos.longitude if latest_pos else None,
                speed=latest_pos.speed if latest_pos else 0.0,
                heading=latest_pos.heading if latest_pos else None,
                passenger_count=p_count,
                capacity=cap,
                load_factor=lf,
                is_transferring=is_transferring,
                transfer_status=transfer_status,
                target_route_id=target_route_id,
                target_route_number=target_route_number,
                timestamp=latest_pos.timestamp if latest_pos else (
                    latest_load.timestamp if latest_load else None
                ),
            )
        )

    return results


@router.post(
    "/{bus_id}/reassign",
    response_model=ReallocationExecutionResponse,
    summary="Manually reassign a bus to a target route",
)
def manually_reassign_bus(
    bus_id: int,
    payload: ManualReassignmentCreate,
    db: Session = Depends(get_db),
) -> ReallocationExecutionResponse:
    """Dispatcher-accessible endpoint to reassign a bus to an active target route.

    Follows the full operational safety lifecycle:
    1. Validates the target route and bus eligibility.
    2. Records an execution audit entry in reallocation_executions.
    3. Initiates a continuous transfer in the simulator without teleportation.
    4. Updates persisted route assignment in the database.
    5. Dispatches an operational alert notification.
    """
    return OptimizationService.execute_manual_reassignment(db, bus_id, payload)

