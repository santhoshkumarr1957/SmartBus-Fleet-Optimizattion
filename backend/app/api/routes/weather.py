"""Weather API endpoints for Coimbatore transit operations (Phase 3)."""
from fastapi import APIRouter, HTTPException, status
from app.schemas.weather import WeatherObservationResponse, WeatherScenarioRequest
from app.services.weather import WeatherService

router = APIRouter()


@router.get(
    "/current",
    response_model=WeatherObservationResponse,
    summary="Get current weather observation and transit impacts",
)
def get_current_weather() -> WeatherObservationResponse:
    """Retrieve real-time weather observation for Coimbatore, Tamil Nadu.

    Returns ambient temperature, rainfall, wind speed, visibility, and operational
    transit impacts (speed factor, deadhead transfer delay multiplier).
    """
    return WeatherService.get_current_weather()


@router.post(
    "/scenario",
    response_model=WeatherObservationResponse,
    summary="Configure manual weather scenario or restore live observation",
)
def configure_weather_scenario(request: WeatherScenarioRequest) -> WeatherObservationResponse:
    """Configure a simulated weather condition for operational drill testing.

    Supported scenarios: NORMAL, LIGHT_RAIN, HEAVY_RAIN, SEVERE_WEATHER, or LIVE_RESET.
    """
    try:
        obs = WeatherService.set_scenario(request.scenario, notes=request.notes)
        try:
            from app.simulator.manager import simulation_manager
            simulation_manager.set_weather_speed_factor(obs.speed_factor)
        except Exception:
            pass
        return obs
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
