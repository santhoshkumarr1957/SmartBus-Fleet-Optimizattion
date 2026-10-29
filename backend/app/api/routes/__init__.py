from app.api.routes.health import router as health_router
from app.api.routes.buses import router as buses_router
from app.api.routes.routes import router as routes_router
from app.api.routes.intelligence import router as intelligence_router
from app.api.routes.optimization import router as optimization_router
from app.api.routes.disruption import router as disruption_router
from app.api.routes.notifications import router as notifications_router
from app.api.routes.reports import router as reports_router

__all__ = [
    "health_router",
    "buses_router",
    "routes_router",
    "intelligence_router",
    "optimization_router",
    "disruption_router",
    "notifications_router",
    "reports_router",
]
