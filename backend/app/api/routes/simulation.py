"""Traffic Simulation control and monitoring API endpoints."""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.simulator.manager import simulation_manager
from app.services.load_intelligence import LoadIntelligenceService
from app.schemas.simulation import (
    SimulationStatusResponse,
    SimulationProfileInfo,
    SimulationDemandRequest,
    SimulationSpeedRequest,
    SimulationEventItem,
    SimulationKpiResponse,
    RouteDemandUpdateRequest,
    RouteDemandItem,
    RouteDemandResponse,
)

router = APIRouter()


@router.get(
    "/status",
    response_model=SimulationStatusResponse,
    summary="Get current traffic simulation status",
)
def get_simulation_status() -> SimulationStatusResponse:
    """Retrieve the active status, demand profile, speed, and timing of the transit simulation engine."""
    return simulation_manager.get_status()


@router.get(
    "/profiles",
    response_model=List[SimulationProfileInfo],
    summary="List available transit demand profiles",
)
def get_simulation_profiles() -> List[SimulationProfileInfo]:
    """Retrieve catalog of supported demand profiles (LOW, NORMAL, HIGH) with active flag."""
    return simulation_manager.get_profiles()


@router.post(
    "/start",
    response_model=SimulationStatusResponse,
    summary="Start traffic simulation",
)
def start_simulation() -> SimulationStatusResponse:
    """Start transit fleet progression if not already running."""
    return simulation_manager.start()


@router.post(
    "/pause",
    response_model=SimulationStatusResponse,
    summary="Pause traffic simulation",
)
def pause_simulation() -> SimulationStatusResponse:
    """Pause bus movements and passenger exchanges without corrupting current state."""
    return simulation_manager.pause()


@router.post(
    "/resume",
    response_model=SimulationStatusResponse,
    summary="Resume traffic simulation",
)
def resume_simulation() -> SimulationStatusResponse:
    """Resume bus movements from paused state."""
    return simulation_manager.resume()


@router.post(
    "/stop",
    response_model=SimulationStatusResponse,
    summary="Stop traffic simulation",
)
def stop_simulation() -> SimulationStatusResponse:
    """Stop the simulation loop cleanly."""
    return simulation_manager.stop()


@router.post(
    "/reset",
    response_model=SimulationStatusResponse,
    summary="Reset traffic simulation safely",
)
def reset_simulation() -> SimulationStatusResponse:
    """Safely reset bus positions and passenger loads to initial route terminals.

    Preserves dispatcher review audits, reallocations, and notification history.
    """
    return simulation_manager.reset()


@router.post(
    "/demand",
    response_model=SimulationStatusResponse,
    summary="Change active simulation demand profile",
)
def change_simulation_demand(
    payload: SimulationDemandRequest,
) -> SimulationStatusResponse:
    """Switch active demand profile to LOW, NORMAL, or HIGH.

    Immediately alters passenger arrival and boarding pressures across the network.
    """
    try:
        return simulation_manager.set_demand(payload.profile)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )


@router.put(
    "/routes/{route_id}/demand",
    response_model=RouteDemandResponse,
    summary="Configure route-specific passenger demand profile",
)
def update_route_demand(
    route_id: str,
    payload: RouteDemandUpdateRequest,
) -> RouteDemandResponse:
    """Set independent demand profile (LOW, NORMAL, HIGH) for a specific route corridor."""
    clean_profile = (payload.profile or "").strip().upper()
    if clean_profile not in ("LOW", "NORMAL", "HIGH"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid demand profile '{payload.profile}'. Must be 'LOW', 'NORMAL', or 'HIGH'.",
        )

    try:
        res = simulation_manager.set_route_demand(route_id, clean_profile)
        return RouteDemandResponse(
            route_id=res["route_id"],
            route_number=res["route_number"],
            route_name=res["route_name"],
            demand_profile=res["demand_profile"],
            message=res["message"],
        )
    except KeyError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e).strip("'\""),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )


@router.get(
    "/routes/demand",
    response_model=List[RouteDemandItem],
    summary="Get demand profiles for all transit routes",
)
def get_all_route_demands() -> List[RouteDemandItem]:
    """Retrieve the authoritative demand profile setting for all six Coimbatore routes."""
    return [RouteDemandItem(**item) for item in simulation_manager.get_route_demands()]


@router.get(
    "/routes/{route_id}/demand",
    response_model=RouteDemandResponse,
    summary="Get demand profile for a specific transit route",
)
def get_single_route_demand(route_id: str) -> RouteDemandResponse:
    """Retrieve the authoritative demand profile setting for a single route corridor."""
    try:
        item = simulation_manager.get_route_demand(route_id)
        return RouteDemandResponse(
            route_id=item["route_id"],
            route_number=item["route_number"],
            route_name=item["route_name"],
            demand_profile=item["demand_profile"],
            message=f"Route {item['route_number']} ({item['route_name']}) is set to {item['demand_profile']} DEMAND.",
        )
    except KeyError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e).strip("'\""),
        )


@router.post(
    "/speed",
    response_model=SimulationStatusResponse,
    summary="Change simulation progression speed",
)
def change_simulation_speed(
    payload: SimulationSpeedRequest,
) -> SimulationStatusResponse:
    """Adjust simulation speed multiplier (1x, 2x, or 5x)."""
    try:
        return simulation_manager.set_speed(payload.speed)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )


@router.get(
    "/events",
    response_model=List[SimulationEventItem],
    summary="Get recent simulation event logs",
)
def get_simulation_events(
    limit: int = Query(default=30, ge=1, le=100),
) -> List[SimulationEventItem]:
    """Retrieve chronological log of significant simulation events (demand changes, load alerts)."""
    return simulation_manager.get_events(limit=limit)


@router.get(
    "/kpis",
    response_model=SimulationKpiResponse,
    summary="Get live traffic KPIs",
)
def get_simulation_kpis(
    db: Session = Depends(get_db),
) -> SimulationKpiResponse:
    """Compute live traffic KPIs directly from database intelligence and simulation state."""
    route_intels = []
    bus_intels = []

    if db is not None:
        try:
            route_intels = LoadIntelligenceService.get_route_intelligence(db)
            bus_intels = LoadIntelligenceService.get_bus_intelligence(db)
        except Exception as e:
            import logging
            logging.getLogger("smartbus.simulation").warning(f"Error computing KPIs from DB: {e}")

    # Fallback directly to in-process simulation manager telemetry if DB records unavailable
    if not route_intels or not bus_intels:
        sim_buses = simulation_manager.get_active_buses_telemetry() or []
        sim_routes = simulation_manager.get_active_routes_telemetry() or []

        low_count = sum(1 for r in sim_routes if r.get("status") == "LOW")
        normal_count = sum(1 for r in sim_routes if r.get("status") == "NORMAL")
        high_count = sum(1 for r in sim_routes if r.get("status") == "HIGH")
        critical_count = sum(1 for r in sim_routes if r.get("status") == "CRITICAL")
        attention_required = high_count + critical_count

        total_cap = sum(b.get("capacity", 60) for b in sim_buses)
        total_pass = sum(b.get("passenger_count", 0) for b in sim_buses)
        available_seats = sum(max(0, b.get("capacity", 60) - (b.get("passenger_count", 0) or 0)) for b in sim_buses)
        avg_lf = round(total_pass / total_cap, 4) if total_cap > 0 else 0.0

        current_status = simulation_manager.get_status()

        return SimulationKpiResponse(
            total_active_buses=len(sim_buses) if sim_buses else 12,
            total_routes=len(sim_routes) if sim_routes else 6,
            average_load_factor=avg_lf,
            low_load_routes_count=low_count,
            normal_load_routes_count=normal_count,
            high_load_routes_count=high_count,
            critical_load_routes_count=critical_count,
            attention_required_count=attention_required,
            total_fleet_capacity=total_cap if total_cap > 0 else 720,
            total_passengers=total_pass,
            available_capacity_seats=available_seats,
            active_profile=current_status["active_profile"],
            simulation_status=current_status["status"],
        )

    low_count = sum(1 for r in route_intels if r.status == "LOW")
    normal_count = sum(1 for r in route_intels if r.status == "NORMAL")
    high_count = sum(1 for r in route_intels if r.status == "HIGH")
    critical_count = sum(1 for r in route_intels if r.status == "CRITICAL")
    attention_required = high_count + critical_count

    total_cap = sum(b.capacity for b in bus_intels)
    total_pass = sum(b.current_load for b in bus_intels)
    available_seats = sum(b.available_seats for b in bus_intels)
    avg_lf = round(total_pass / total_cap, 4) if total_cap > 0 else 0.0

    current_status = simulation_manager.get_status()

    return SimulationKpiResponse(
        total_active_buses=len(bus_intels),
        total_routes=len(route_intels),
        average_load_factor=avg_lf,
        low_load_routes_count=low_count,
        normal_load_routes_count=normal_count,
        high_load_routes_count=high_count,
        critical_load_routes_count=critical_count,
        attention_required_count=attention_required,
        total_fleet_capacity=total_cap,
        total_passengers=total_pass,
        available_capacity_seats=available_seats,
        active_profile=current_status["active_profile"],
        simulation_status=current_status["status"],
    )
