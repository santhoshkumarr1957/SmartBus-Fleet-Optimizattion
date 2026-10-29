"""Business logic and transit services package.

Uses lazy loading for package-level service attributes to prevent
unnecessary eager imports and circular module initialization chains.
"""
from typing import Any

__all__ = [
    "LoadIntelligenceService",
    "OptimizationService",
    "DisruptionService",
    "NotificationService",
    "ReportService",
    "WeatherService",
    "BreakdownService",
    "HybridOptimizationEngine",
]


def __getattr__(name: str) -> Any:
    """Dynamically resolve public service classes on demand."""
    if name == "LoadIntelligenceService":
        from app.services.load_intelligence import LoadIntelligenceService
        return LoadIntelligenceService
    elif name == "OptimizationService":
        from app.services.optimization import OptimizationService
        return OptimizationService
    elif name == "DisruptionService":
        from app.services.disruption import DisruptionService
        return DisruptionService
    elif name == "NotificationService":
        from app.services.notification import NotificationService
        return NotificationService
    elif name == "ReportService":
        from app.services.report import ReportService
        return ReportService
    elif name == "WeatherService":
        from app.services.weather import WeatherService
        return WeatherService
    elif name == "BreakdownService":
        from app.services.breakdown import BreakdownService
        return BreakdownService
    elif name == "HybridOptimizationEngine":
        from app.services.hybrid_optimization import HybridOptimizationEngine
        return HybridOptimizationEngine
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
