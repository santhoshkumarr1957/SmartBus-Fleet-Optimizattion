from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from app.db.session import get_db
from app.models.route import Route
from app.models.passenger_load import PassengerLoad
from app.schemas.live import RouteLiveResponse
from app.schemas.route import RouteDetailedRead
from app.schemas.stop import StopRead
from app.simulator.manager import simulation_manager

router = APIRouter()


@router.get("", response_model=List[RouteDetailedRead], summary="Get all active routes with stops")
def get_all_routes(db: Session = Depends(get_db)) -> List[RouteDetailedRead]:
    """Retrieve all active routes including ordered transit stops and geometries."""
    # 1. Fetch from Database using eager joinedload to eliminate N+1 latency
    if db is not None:
        try:
            routes = (
                db.query(Route)
                .options(joinedload(Route.stops))
                .filter(Route.is_active == True)
                .order_by(Route.id)
                .all()
            )
            if routes and len(routes) >= 6:
                for r in routes:
                    r.stops.sort(key=lambda s: s.sequence_order)
                return routes
        except Exception as e:
            import logging
            logging.getLogger("smartbus.routes").warning(f"DB query for routes encountered error: {e}")

    # 2. In-memory fallback from active simulation manager runner
    if simulation_manager.runner and getattr(simulation_manager.runner, "routes", None):
        cached_routes = simulation_manager.runner.routes
        if cached_routes and len(cached_routes) >= 6:
            for r in cached_routes:
                if hasattr(r, "stops") and r.stops:
                    r.stops.sort(key=lambda s: s.sequence_order)
            return cached_routes

    # 3. Deterministic fallback to Coimbatore network seed data definitions
    from app.db.seed import SEED_ROUTES
    fallback_routes: List[RouteDetailedRead] = []
    now = datetime.now(timezone.utc)
    for idx, r_data in enumerate(SEED_ROUTES, start=1):
        stops = [
            StopRead(
                id=idx * 100 + s["sequence_order"],
                route_id=idx,
                name=s["name"],
                stop_code=s.get("stop_code"),
                sequence_order=s["sequence_order"],
                latitude=s["latitude"],
                longitude=s["longitude"],
                created_at=now,
            )
            for s in r_data["stops"]
        ]
        fallback_routes.append(
            RouteDetailedRead(
                id=idx,
                route_number=r_data["route_number"],
                name=r_data["name"],
                description=r_data.get("description"),
                origin=r_data["origin"],
                destination=r_data["destination"],
                is_active=True,
                created_at=now,
                updated_at=now,
                stops=stops,
            )
        )
    return fallback_routes


@router.get("/live", response_model=List[RouteLiveResponse], summary="Get live route statistics")
def get_live_routes(db: Session = Depends(get_db)) -> List[RouteLiveResponse]:
    """Retrieve aggregate live passenger loading, total capacity, and status for all active routes."""
    # 1. Authoritative source of truth: in-process active bus simulator fleet
    sim_routes = simulation_manager.get_active_routes_telemetry()
    if sim_routes:
        return [RouteLiveResponse(**r) for r in sim_routes]

    # 2. Database fallback if simulation has not yet initialized
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection not available",
        )

    routes = db.query(Route).filter(Route.is_active == True).order_by(Route.id).all()  # noqa: E712
    results: List[RouteLiveResponse] = []

    for route in routes:
        buses = [b for b in route.buses if b.status != "INACTIVE"]
        total_passengers = 0
        total_capacity = sum(b.capacity for b in buses)

        for bus in buses:
            latest_load = (
                db.query(PassengerLoad)
                .filter(PassengerLoad.bus_id == bus.id)
                .order_by(PassengerLoad.timestamp.desc(), PassengerLoad.id.desc())
                .first()
            )
            if latest_load:
                total_passengers += latest_load.current_load

        if total_capacity > 0:
            load_factor = round(total_passengers / total_capacity, 4)
        else:
            load_factor = 0.0

        # Status calculation based on configured thresholds
        # < 0.50 -> LOW
        # 0.50–0.80 -> NORMAL
        # 0.80–1.00 -> HIGH
        # >= 1.00 -> CRITICAL
        if load_factor < 0.50:
            route_status = "LOW"
        elif load_factor < 0.80:
            route_status = "NORMAL"
        elif load_factor < 1.00:
            route_status = "HIGH"
        else:
            route_status = "CRITICAL"

        results.append(
            RouteLiveResponse(
                route_id=route.id,
                route_number=route.route_number,
                number_of_buses=len(buses),
                total_passengers=total_passengers,
                total_capacity=total_capacity,
                load_factor=load_factor,
                status=route_status,
            )
        )

    return results
