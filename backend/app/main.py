from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.routes.health import router as health_router
from app.api.routes.buses import router as buses_router
from app.api.routes.routes import router as routes_router
from app.api.routes.intelligence import router as intelligence_router
from app.api.routes.optimization import router as optimization_router
from app.api.routes.disruption import router as disruption_router
from app.api.routes.notifications import router as notifications_router
from app.api.routes.reports import router as reports_router
from app.api.routes.weather import router as weather_router
from app.api.routes.breakdowns import router as breakdowns_router

from app.api.routes.simulation import router as simulation_router
from app.simulator.manager import simulation_manager

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="SmartBus (TRANSIGHT) — Hybrid Intelligent Fleet Optimization and Resilience System Backend API",
    version="1.0.0",
)

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Register API routes
app.include_router(health_router, prefix="/api", tags=["Health"])
app.include_router(buses_router, prefix="/api/buses", tags=["Buses"])
app.include_router(routes_router, prefix="/api/routes", tags=["Routes"])
app.include_router(intelligence_router, prefix="/api/intelligence", tags=["Intelligence"])
app.include_router(optimization_router, prefix="/api/optimization", tags=["Optimization"])
app.include_router(simulation_router, prefix="/api/simulation", tags=["Simulation"])
app.include_router(disruption_router, prefix="/api/disruption", tags=["Disruption"])
app.include_router(notifications_router, prefix="/api/notifications", tags=["Notifications"])
app.include_router(reports_router, prefix="/api/reports", tags=["Reports"])
app.include_router(weather_router, prefix="/api/weather", tags=["Weather"])
app.include_router(breakdowns_router, prefix="/api/breakdowns", tags=["Breakdowns"])


@app.on_event("startup")
def startup_event():
    """Start the authoritative transit simulation engine on backend startup."""
    try:
        simulation_manager.start()
    except Exception as exc:
        import logging
        logging.getLogger("uvicorn.error").error(f"Error starting simulation manager: {exc}")


@app.on_event("shutdown")
def shutdown_event():
    """Cleanly stop simulation background worker on backend shutdown."""
    try:
        simulation_manager.stop()
    except Exception:
        pass


@app.get("/")
def root():
    return {
        "name": settings.PROJECT_NAME,
        "status": "online",
        "health_check": "/api/health",
        "simulation": "/api/simulation/status",
        "documentation": "/docs",
    }

