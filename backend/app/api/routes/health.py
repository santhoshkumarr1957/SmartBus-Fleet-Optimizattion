from typing import Dict, Any, Optional
from fastapi import APIRouter
from pydantic import BaseModel
from app.db.session import verify_db_connection
from app.simulator.manager import simulation_manager

router = APIRouter()


class DatabaseHealth(BaseModel):
    connected: bool
    message: str


class SimulationHealth(BaseModel):
    status: str
    initialized: bool
    active_profile: str
    total_buses: int


class HealthResponse(BaseModel):
    status: str
    database: DatabaseHealth
    simulation: SimulationHealth


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    """Health check endpoint actively verifying database connectivity and simulator engine state."""
    db_connected, db_err = verify_db_connection()
    sim_status = simulation_manager.get_status()
    sim_initialized = sim_status.get("total_buses", 0) > 0 and sim_status.get("status") in ("RUNNING", "PAUSED")

    # Determine overall health status
    if db_connected and sim_initialized:
        overall_status = "ok"
    elif db_connected or sim_initialized:
        overall_status = "degraded"
    else:
        overall_status = "error"

    db_msg = "Connected to Supabase PostgreSQL" if db_connected else (db_err or "Database unreachable")

    return HealthResponse(
        status=overall_status,
        database=DatabaseHealth(
            connected=db_connected,
            message=db_msg,
        ),
        simulation=SimulationHealth(
            status=sim_status.get("status", "STOPPED"),
            initialized=sim_initialized,
            active_profile=sim_status.get("active_profile", "NORMAL"),
            total_buses=sim_status.get("total_buses", 0),
        ),
    )

