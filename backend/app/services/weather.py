"""Weather Service for Weather-Aware Transit Operations (Phase 3).

Integrates free Open-Meteo weather observations for Coimbatore, Tamil Nadu,
maintains in-memory caching, provides deterministic operational impact modeling,
and supports manual scenario testing (NORMAL, LIGHT_RAIN, HEAVY_RAIN, SEVERE_WEATHER).
"""
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple
import httpx
from app.schemas.weather import WeatherObservationResponse

logger = logging.getLogger("smartbus.weather")

COIMBATORE_LAT = 11.0168
COIMBATORE_LON = 76.9558
COIMBATORE_LOCATION = "Coimbatore, Tamil Nadu, India"
CACHE_TTL_SECONDS = 600  # 10 minutes cache


class WeatherService:
    """Manages real-time weather observations, manual scenarios, and transit impact models."""

    _cached_observation: Optional[WeatherObservationResponse] = None
    _cached_at: Optional[datetime] = None
    _scenario_override: Optional[str] = None  # None = Live API, or "NORMAL", "LIGHT_RAIN", "HEAVY_RAIN", "SEVERE_WEATHER"
    _scenario_notes: Optional[str] = None

    @classmethod
    def _map_wmo_code(cls, code: int, precip: float) -> Tuple[str, str]:
        """Map WMO weather code to condition string and description."""
        if code == 0:
            return "NORMAL", "Clear Sky"
        elif code in (1, 2, 3):
            return "NORMAL", "Partly Cloudy"
        elif code in (45, 48):
            return "LIGHT_RAIN", "Foggy / Mist"
        elif code in (51, 53, 55, 61, 63):
            return "LIGHT_RAIN", "Light Rain / Drizzle"
        elif code in (65, 80, 81):
            return "HEAVY_RAIN", "Heavy Rain Showers"
        elif code in (82, 95, 96, 99):
            return "SEVERE_WEATHER", "Thunderstorm & High Winds"
        elif precip > 5.0:
            return "HEAVY_RAIN", "Active Rain Precipitation"
        elif precip > 0.5:
            return "LIGHT_RAIN", "Scattered Showers"
        return "NORMAL", "Fair Weather"

    @classmethod
    def _calculate_impacts(cls, condition: str) -> Dict[str, Any]:
        """Deterministic operational transit impact model."""
        cond = (condition or "NORMAL").upper()
        if cond == "SEVERE_WEATHER":
            speed_factor = 0.55
            multiplier = round(1.0 / speed_factor, 2)  # ~1.82x
            delay_min = 18.0
            impact = (
                "Severe weather warning: Operating speeds reduced by 45%. Deadhead transfers take 82% longer. "
                "High risk of corridor waterlogging along Avinashi Rd and Trichy Rd. Prioritize emergency fleet resilience."
            )
            affected = ["101", "202", "303", "404", "505", "606"]
        elif cond == "HEAVY_RAIN":
            speed_factor = 0.75
            multiplier = round(1.0 / speed_factor, 2)  # ~1.33x
            delay_min = 8.0
            impact = (
                "Heavy rainfall in Coimbatore: Operating speeds reduced by 25%. Deadhead transfers take 33% longer. "
                "Passenger boarding queues expanding at major terminals (Gandhipuram, Ukkadam). Transfer delays factored into optimization."
            )
            affected = ["101", "404", "303"]
        elif cond == "LIGHT_RAIN":
            speed_factor = 0.90
            multiplier = round(1.0 / speed_factor, 2)  # ~1.11x
            delay_min = 3.5
            impact = (
                "Light rain / wet road surfaces: Operating speeds reduced by 10%. Minor transfer delay (+11% travel time). "
                "Moderate passenger demand surge at covered stops."
            )
            affected = ["101", "404"]
        else:
            speed_factor = 1.0
            multiplier = 1.0
            delay_min = 0.0
            impact = (
                "Optimal dry transit weather: Nominal operating speeds (30–35 km/h). "
                "No weather-related transfer penalties applied."
            )
            affected = []

        return {
            "speed_factor": speed_factor,
            "travel_time_multiplier": multiplier,
            "delay_minutes_per_corridor": delay_min,
            "impact_summary": impact,
            "affected_corridors": affected,
        }

    @classmethod
    def get_current_weather(cls, force_refresh: bool = False) -> WeatherObservationResponse:
        """Fetch current weather observation with caching, scenario override, and fallback."""
        now = datetime.now(timezone.utc)

        # 1. Manual scenario override active?
        if cls._scenario_override is not None:
            impacts = cls._calculate_impacts(cls._scenario_override)
            desc_map = {
                "NORMAL": "Simulated Clear Sky & Fair Weather",
                "LIGHT_RAIN": "Simulated Light Rain & Wet Surfaces",
                "HEAVY_RAIN": "Simulated Heavy Downpour & Waterlogging",
                "SEVERE_WEATHER": "Simulated Severe Thunderstorm & High Winds",
            }
            temp_map = {"NORMAL": 31.0, "LIGHT_RAIN": 26.5, "HEAVY_RAIN": 23.0, "SEVERE_WEATHER": 21.5}
            precip_map = {"NORMAL": 0.0, "LIGHT_RAIN": 2.5, "HEAVY_RAIN": 16.0, "SEVERE_WEATHER": 45.0}

            return WeatherObservationResponse(
                condition=cls._scenario_override,
                description=desc_map.get(cls._scenario_override, "Simulated Scenario"),
                temperature_c=temp_map.get(cls._scenario_override, 28.0),
                precipitation_mm=precip_map.get(cls._scenario_override, 0.0),
                relative_humidity_pct=85.0 if cls._scenario_override != "NORMAL" else 55.0,
                wind_speed_kmh=35.0 if cls._scenario_override == "SEVERE_WEATHER" else 12.0,
                visibility_km=4.0 if cls._scenario_override == "HEAVY_RAIN" else (1.5 if cls._scenario_override == "SEVERE_WEATHER" else 10.0),
                location=COIMBATORE_LOCATION,
                latitude=COIMBATORE_LAT,
                longitude=COIMBATORE_LON,
                observed_at=now,
                source="MANUAL_SCENARIO",
                is_live=False,
                freshness_seconds=0,
                speed_factor=impacts["speed_factor"],
                travel_time_multiplier=impacts["travel_time_multiplier"],
                delay_minutes_per_corridor=impacts["delay_minutes_per_corridor"],
                impact_summary=f"[MANUAL DRILL] {impacts['impact_summary']}" + (f" Note: {cls._scenario_notes}" if cls._scenario_notes else ""),
                affected_corridors=impacts["affected_corridors"],
            )

        # 2. Check cache freshness
        if not force_refresh and cls._cached_observation and cls._cached_at:
            age = (now - cls._cached_at).total_seconds()
            if age < CACHE_TTL_SECONDS:
                cached_copy = cls._cached_observation.model_copy()
                cached_copy.freshness_seconds = int(age)
                return cached_copy

        # 3. Live fetch from Open-Meteo free API
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={COIMBATORE_LAT}&longitude={COIMBATORE_LON}"
            f"&current=temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m"
        )
        try:
            timeout_cfg = httpx.Timeout(1.5, connect=1.0)
            with httpx.Client(timeout=timeout_cfg) as client:
                res = client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    curr = data.get("current", {})
                    temp = float(curr.get("temperature_2m", 29.0))
                    precip = float(curr.get("precipitation", 0.0))
                    code = int(curr.get("weather_code", 0))
                    humidity = float(curr.get("relative_humidity_2m", 60.0))
                    wind = float(curr.get("wind_speed_10m", 10.0))

                    condition, desc = cls._map_wmo_code(code, precip)
                    impacts = cls._calculate_impacts(condition)

                    obs = WeatherObservationResponse(
                        condition=condition,
                        description=desc,
                        temperature_c=temp,
                        precipitation_mm=precip,
                        relative_humidity_pct=humidity,
                        wind_speed_kmh=wind,
                        visibility_km=10.0 if condition == "NORMAL" else 6.0,
                        location=COIMBATORE_LOCATION,
                        latitude=COIMBATORE_LAT,
                        longitude=COIMBATORE_LON,
                        observed_at=now,
                        source="LIVE_OPEN_METEO",
                        is_live=True,
                        freshness_seconds=0,
                        speed_factor=impacts["speed_factor"],
                        travel_time_multiplier=impacts["travel_time_multiplier"],
                        delay_minutes_per_corridor=impacts["delay_minutes_per_corridor"],
                        impact_summary=impacts["impact_summary"],
                        affected_corridors=impacts["affected_corridors"],
                    )
                    cls._cached_observation = obs
                    cls._cached_at = now
                    logger.info(f"[WEATHER] Live observation refreshed for Coimbatore: {condition} ({desc}, {temp}°C, {precip}mm)")
                    return obs
        except Exception as e:
            logger.warning(f"[WEATHER] Live weather API unavailable: {e}. Falling back safely.")

        # 4. Fallback if network call fails or timed out
        if cls._cached_observation:
            fallback = cls._cached_observation.model_copy()
            fallback.source = "OFFLINE_FALLBACK"
            fallback.is_live = False
            return fallback

        # Default fallback
        impacts = cls._calculate_impacts("NORMAL")
        default_obs = WeatherObservationResponse(
            condition="NORMAL",
            description="Clear Sky (Estimated baseline)",
            temperature_c=29.0,
            precipitation_mm=0.0,
            relative_humidity_pct=58.0,
            wind_speed_kmh=11.0,
            visibility_km=10.0,
            location=COIMBATORE_LOCATION,
            latitude=COIMBATORE_LAT,
            longitude=COIMBATORE_LON,
            observed_at=now,
            source="OFFLINE_FALLBACK",
            is_live=False,
            freshness_seconds=0,
            speed_factor=impacts["speed_factor"],
            travel_time_multiplier=impacts["travel_time_multiplier"],
            delay_minutes_per_corridor=impacts["delay_minutes_per_corridor"],
            impact_summary="Operating under baseline weather parameters. Live provider offline.",
            affected_corridors=[],
        )
        cls._cached_observation = default_obs
        cls._cached_at = now
        return default_obs

    @classmethod
    def set_scenario(cls, scenario: str, notes: Optional[str] = None) -> WeatherObservationResponse:
        """Set manual weather scenario override or reset to live."""
        clean = (scenario or "").strip().upper()
        if clean in ("LIVE_RESET", "LIVE", "AUTO", "RESET"):
            cls._scenario_override = None
            cls._scenario_notes = None
            logger.info("[WEATHER] Manual weather scenario cleared; restored live observations.")
            return cls.get_current_weather(force_refresh=True)

        if clean not in ("NORMAL", "LIGHT_RAIN", "HEAVY_RAIN", "SEVERE_WEATHER"):
            raise ValueError(
                f"Invalid weather scenario '{scenario}'. Must be NORMAL, LIGHT_RAIN, HEAVY_RAIN, SEVERE_WEATHER, or LIVE_RESET."
            )

        cls._scenario_override = clean
        cls._scenario_notes = notes
        logger.info(f"[WEATHER] Manual weather scenario configured: {clean}")
        return cls.get_current_weather()
