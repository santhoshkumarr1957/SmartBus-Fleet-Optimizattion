"""Weather schemas for Weather-Aware Transit Operations (Phase 3)."""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class WeatherObservationResponse(BaseModel):
    """Real-time or simulated weather observation for Coimbatore transit operations."""

    condition: str = Field(
        ...,
        description="Standardized weather condition: NORMAL, LIGHT_RAIN, HEAVY_RAIN, SEVERE_WEATHER",
    )
    description: str = Field(
        ...,
        description="Human-readable weather description (e.g. 'Clear Sky', 'Heavy Rain Showers')",
    )
    temperature_c: float = Field(..., description="Ambient temperature in degrees Celsius")
    precipitation_mm: float = Field(..., description="Precipitation or rainfall intensity in mm")
    relative_humidity_pct: Optional[float] = Field(default=None, description="Relative humidity %")
    wind_speed_kmh: Optional[float] = Field(default=None, description="Wind speed in km/h")
    visibility_km: Optional[float] = Field(default=None, description="Atmospheric visibility in km")
    location: str = Field(default="Coimbatore, Tamil Nadu, India")
    latitude: float = Field(default=11.0168)
    longitude: float = Field(default=76.9558)
    observed_at: datetime = Field(..., description="Timestamp of weather observation")
    source: str = Field(
        default="LIVE_OPEN_METEO",
        description="Source of observation: LIVE_OPEN_METEO, MANUAL_SCENARIO, or OFFLINE_FALLBACK",
    )
    is_live: bool = Field(default=True, description="True if fetched from live weather provider")
    freshness_seconds: int = Field(default=0, description="Age of observation in seconds")

    # Operational impacts
    speed_factor: float = Field(
        default=1.0,
        description="Operating speed reduction factor (1.0 = nominal, 0.75 = 25% reduction)",
    )
    travel_time_multiplier: float = Field(
        default=1.0,
        description="Deadhead transfer travel time multiplier (1.0 = nominal, 1.33 = 33% longer)",
    )
    delay_minutes_per_corridor: float = Field(
        default=0.0,
        description="Estimated traffic & weather headway expansion delay per corridor in minutes",
    )
    impact_summary: str = Field(
        ...,
        description="Operational impact analysis explaining effect on vehicle deadheads and boarding",
    )
    affected_corridors: List[str] = Field(
        default_factory=list,
        description="Corridors particularly vulnerable to weather slowdowns",
    )

    model_config = ConfigDict(from_attributes=True)


class WeatherScenarioRequest(BaseModel):
    """Request to configure manual weather scenario or restore live observation."""

    scenario: str = Field(
        ...,
        description="Target scenario: NORMAL, LIGHT_RAIN, HEAVY_RAIN, SEVERE_WEATHER, or LIVE_RESET",
        examples=["NORMAL", "LIGHT_RAIN", "HEAVY_RAIN", "SEVERE_WEATHER", "LIVE_RESET"],
    )
    notes: Optional[str] = Field(
        default=None,
        description="Optional operator notes or justification for scenario override",
    )
