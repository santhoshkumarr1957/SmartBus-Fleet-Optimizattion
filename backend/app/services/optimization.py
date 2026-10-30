"""Rule-based Fleet Reallocation Optimization Engine for SmartBus.

Stage 5 Implementation:
Analyzes transit demand intelligence from Stage 4, identifies overloaded and
underutilized routes, determines operationally plausible candidate buses, and scores
reallocation recommendations using transparent, deterministic formulas.

Constraints Guarantee:
- Purely advisory: No route reassignments or database mutations occur.
- No machine learning or paid external APIs used.
- Transparent rule-based mathematical scoring.
- Realistic operational constraints and data limitation disclosures.
"""
import math
import time
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Dict, Any


def _get_db_session_id(db: Any) -> Optional[str]:
    """Retrieve or attach a stable unique identifier to a database session."""
    if db is None:
        return None
    session_id = getattr(db, "_session_uuid", None)
    if not session_id:
        session_id = uuid.uuid4().hex
        try:
            setattr(db, "_session_uuid", session_id)
        except Exception:
            pass
    return session_id
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.models.bus import Bus
from app.models.route import Route
from app.models.stop import Stop
from app.models.bus_position import BusPosition
from app.models.passenger_load import PassengerLoad
from app.models.reallocation_review import ReallocationReview
from app.models.reallocation_execution import ReallocationExecution
from app.models.notification import Notification
from app.services.load_intelligence import (
    LoadIntelligenceService,
    classify_load_factor,
    calculate_load_factor,
    calculate_available_seats,
)
from app.schemas.intelligence import RouteIntelligenceResponse, BusIntelligenceResponse
from app.schemas.optimization import (
    ReallocationRecommendationResponse,
    OptimizationOverviewResponse,
    ReallocationReviewCreate,
    ReallocationReviewResponse,
    ReallocationExecutionCreate,
    ReallocationExecutionResponse,
    ManualReassignmentCreate,
    RouteBrief,
    BusBrief,
)
from app.simulator.route_simulator import calculate_distance_meters

# Operational parameters & scoring weights
NOMINAL_DEADHEAD_SPEED_KMH = 30.0  # Assumed urban transit deadhead transfer speed (km/h)
MAX_TARGET_SEVERITY_SCORE = 35.0   # Weight for target route overcrowding severity
MAX_SOURCE_SPARE_SCORE = 25.0      # Weight for source route capacity headroom
MAX_BUS_SUITABILITY_SCORE = 25.0   # Weight for bus spare seats and low occupancy
MAX_PROXIMITY_SCORE = 15.0         # Weight for geographic deadhead transfer proximity
NEUTRAL_PROXIMITY_SCORE = 7.5      # Neutral proximity score when GPS telemetry is unavailable


def calculate_target_severity_score(target_load_factor: float, target_status: str) -> float:
    """Calculate target route overcrowding severity score component (0.0 to 35.0).

    Scoring Logic:
    - CRITICAL (load_factor >= 1.00):
        Base 30.0 points + bonus up to 5.0 points proportional to overcrowding
        Formula: 30.0 + min(5.0, (target_load_factor - 1.0) * 10.0)
    - HIGH (0.80 <= load_factor < 1.00):
        Base 20.0 points + proportional scaling up to 10.0 points
        Formula: 20.0 + ((target_load_factor - 0.80) / 0.20) * 10.0
    - NORMAL / LOW:
        0.0 points (not in need of capacity addition)
    """
    if target_status == "CRITICAL" or target_load_factor >= 1.00:
        overcrowding_bonus = min(5.0, max(0.0, (target_load_factor - 1.00) * 10.0))
        return round(30.0 + overcrowding_bonus, 2)
    elif target_status == "HIGH" or target_load_factor >= 0.80:
        ratio = max(0.0, min(1.0, (target_load_factor - 0.80) / 0.20))
        return round(20.0 + ratio * 10.0, 2)
    return 0.0


def calculate_source_spare_score(source_load_factor: float, number_of_buses: int) -> float:
    """Calculate source route spare capacity score component (0.0 to 25.0).

    Scoring Logic:
    - Headroom component (0.0 to 20.0):
        Lower source load factor yields higher headroom.
        Formula: max(0.0, 1.0 - (source_load_factor / 0.50)) * 20.0
    - Fleet resilience bonus (5.0 points):
        Awarded if source route has > 1 bus assigned, ensuring route retains
        scheduled service after potential bus reallocation.
        If number_of_buses <= 1: 0.0 bonus (penalized for service abandonment risk).
    """
    if source_load_factor >= 0.50:
        return 0.0

    headroom_ratio = max(0.0, min(1.0, 1.0 - (source_load_factor / 0.50)))
    headroom_score = headroom_ratio * 20.0

    fleet_depth_bonus = 5.0 if number_of_buses > 1 else 0.0
    return round(min(MAX_SOURCE_SPARE_SCORE, headroom_score + fleet_depth_bonus), 2)


def calculate_bus_suitability_score(
    passenger_count: int, capacity: int, available_seats: int
) -> float:
    """Calculate candidate bus suitability score component (0.0 to 25.0).

    Scoring Logic:
    - Low occupancy component (0.0 to 15.0):
        Bus with low current occupancy is easier to deadhead and provides maximum relief.
        Formula: (1.0 - (passenger_count / capacity)) * 15.0
        If bus load factor >= 0.80: 0.0 (bus is crowded, not suitable).
    - Available capacity component (0.0 to 10.0):
        Scales with available seats relative to standard bus capacity (60 seats).
        Formula: min(10.0, (available_seats / 60.0) * 10.0)
    """
    if capacity <= 0 or available_seats <= 0:
        return 0.0

    bounded_passengers = max(0, min(capacity, passenger_count))
    bus_load_factor = bounded_passengers / capacity

    if bus_load_factor >= 0.80:
        return 0.0

    occupancy_score = (1.0 - bus_load_factor) * 15.0
    capacity_score = min(10.0, (available_seats / 60.0) * 10.0)

    return round(min(MAX_BUS_SUITABILITY_SCORE, occupancy_score + capacity_score), 2)


def calculate_proximity_score(
    distance_meters: Optional[float],
) -> Tuple[float, Optional[str]]:
    """Calculate geographic proximity score component (0.0 to 15.0).

    Scoring Logic:
    - If distance_meters is None (telemetry missing):
        Assign neutral baseline 7.5 points (50% of weight) and report limitation.
    - If distance <= 2.0 km:
        15.0 points (rapid response, minimal deadhead).
    - If distance > 2.0 km:
        Decays smoothly with deadhead distance:
        Formula: max(2.0, 15.0 - (distance_km - 2.0) * 1.3)
    """
    if distance_meters is None or distance_meters < 0:
        return (
            NEUTRAL_PROXIMITY_SCORE,
            "Proximity scored at neutral baseline (7.5/15) due to missing GPS coordinates.",
        )

    distance_km = distance_meters / 1000.0
    if distance_km <= 2.0:
        return 15.0, None

    decayed = max(2.0, 15.0 - (distance_km - 2.0) * 1.3)
    return round(min(MAX_PROXIMITY_SCORE, decayed), 2), None


def determine_priority(score: float, target_status: str) -> str:
    """Determine priority tier based on overall score and target urgency."""
    if score >= 75.0 or (target_status == "CRITICAL" and score >= 65.0):
        return "HIGH"
    elif score >= 50.0:
        return "MEDIUM"
    return "LOW"


def evaluate_bus_reallocation(
    target_route: RouteIntelligenceResponse,
    source_route: RouteIntelligenceResponse,
    candidate_bus: Optional[BusIntelligenceResponse],
    target_origin_stop: Optional[Stop],
    bus_position: Optional[BusPosition],
    db_bus: Optional[Bus],
    weather_obs: Optional[Any] = None,
) -> ReallocationRecommendationResponse:
    """Evaluate and score a potential bus reallocation from source to target route."""
    limitations: List[str] = []
    feasibility_status = "FEASIBLE"

    # 1. Geographic proximity & deadhead travel time
    distance_meters: Optional[float] = None
    estimated_travel_time_minutes: Optional[float] = None

    if weather_obs is None:
        try:
            from app.services.weather import WeatherService
            weather_obs = WeatherService.get_current_weather()
        except Exception:
            pass
    weather_multiplier = getattr(weather_obs, "travel_time_multiplier", 1.0) or 1.0

    if bus_position and bus_position.latitude is not None and bus_position.longitude is not None:
        if target_origin_stop and target_origin_stop.latitude is not None and target_origin_stop.longitude is not None:
            raw_dist = calculate_distance_meters(
                bus_position.latitude,
                bus_position.longitude,
                target_origin_stop.latitude,
                target_origin_stop.longitude,
            )
            distance_meters = round(raw_dist, 1)
            dist_km = distance_meters / 1000.0
            estimated_travel_time_minutes = round((dist_km / NOMINAL_DEADHEAD_SPEED_KMH) * 60.0 * weather_multiplier, 1)
            if weather_multiplier > 1.0 and weather_obs:
                limitations.append(
                    f"Weather condition ({weather_obs.condition}) adds +{round((weather_multiplier - 1.0) * 100)}% deadhead travel delay."
                )
        else:
            limitations.append("Target route has no origin stop GPS coordinates for proximity measurement.")
            feasibility_status = "CONDITIONALLY_FEASIBLE"
    else:
        limitations.append("Missing live GPS position telemetry for candidate bus; deadhead distance cannot be determined.")
        feasibility_status = "CONDITIONALLY_FEASIBLE"

    # 2. Candidate bus availability & constraints
    has_candidate = candidate_bus is not None
    candidate_bus_id = candidate_bus.bus_id if candidate_bus else None
    candidate_bus_number = candidate_bus.bus_number if candidate_bus else None
    bus_capacity = candidate_bus.capacity if candidate_bus else None
    current_occupancy = candidate_bus.passenger_count if candidate_bus else None
    available_capacity = candidate_bus.available_seats if candidate_bus else None
    bus_load_factor = candidate_bus.load_factor if candidate_bus else None

    if not has_candidate:
        limitations.append("No active candidate bus with spare capacity found on source route.")
        feasibility_status = "NO_CANDIDATE_BUS"
    else:
        if db_bus and db_bus.status in ("INACTIVE", "MAINTENANCE"):
            limitations.append(f"Bus status is {db_bus.status}; bus cannot be deployed.")
            feasibility_status = "INFEASIBLE"

        if current_occupancy and current_occupancy > 0:
            limitations.append(
                f"Candidate bus has {current_occupancy} passengers on board; requires passenger alighting at route terminal prior to transfer."
            )
            if feasibility_status == "FEASIBLE":
                feasibility_status = "CONDITIONALLY_FEASIBLE"

    # 3. Source route operational resilience constraints
    if source_route.number_of_buses <= 1:
        limitations.append("Source route has only 1 active bus; reallocating would violate Minimum Service Coverage Invariant.")
        if feasibility_status != "INFEASIBLE":
            feasibility_status = "CONDITIONALLY_FEASIBLE"

    # 4. Projected load factors post-reallocation
    projected_target_lf: Optional[float] = None
    projected_source_lf: Optional[float] = None

    if has_candidate and bus_capacity and bus_capacity > 0:
        new_target_capacity = target_route.total_capacity + bus_capacity
        projected_target_lf = round(target_route.total_passengers / new_target_capacity, 4)

        remaining_source_capacity = source_route.total_capacity - bus_capacity
        rem_source_passengers = max(0, source_route.total_passengers - (current_occupancy or 0))
        if remaining_source_capacity > 0:
            projected_source_lf = round(rem_source_passengers / remaining_source_capacity, 4)
            corridor_lf = round(source_route.total_passengers / remaining_source_capacity, 4)
            if corridor_lf > 1.00:
                limitations.append(
                    f"Corridor passenger demand ({source_route.total_passengers} pax) exceeds remaining route capacity ({remaining_source_capacity} seats)."
                )
                feasibility_status = "INFEASIBLE"
            elif corridor_lf >= 0.80:
                limitations.append(
                    f"Corridor passenger demand will elevate source route load factor to {round(corridor_lf * 100, 1)}% (HIGH)."
                )
                if feasibility_status != "INFEASIBLE":
                    feasibility_status = "CONDITIONALLY_FEASIBLE"
        else:
            projected_source_lf = 1.0
            limitations.append("Reallocating this bus will exhaust source route operational capacity.")
            if feasibility_status != "INFEASIBLE":
                feasibility_status = "CONDITIONALLY_FEASIBLE"

    # 5. Component Scoring
    target_score = calculate_target_severity_score(target_route.load_factor, target_route.status)
    source_score = calculate_source_spare_score(source_route.load_factor, source_route.number_of_buses)

    if has_candidate and bus_capacity:
        bus_score = calculate_bus_suitability_score(
            passenger_count=current_occupancy or 0,
            capacity=bus_capacity,
            available_seats=available_capacity or 0,
        )
    else:
        bus_score = 0.0

    prox_score, prox_limitation = calculate_proximity_score(distance_meters)
    if prox_limitation:
        limitations.append(prox_limitation)

    if not has_candidate:
        total_score = 0.0
    else:
        raw_score = target_score + source_score + bus_score + prox_score
        total_score = round(max(0.0, min(100.0, raw_score)), 2)

    priority = determine_priority(total_score, target_route.status)

    # 6. Recommendation Reason Synthesis
    target_pct = round(target_route.load_factor * 100, 1)
    source_pct = round(source_route.load_factor * 100, 1)

    if has_candidate and candidate_bus_number:
        proj_target_str = (
            f" (projected {round(projected_target_lf * 100, 1)}% post-addition)"
            if projected_target_lf is not None
            else ""
        )
        dist_str = (
            f" Deadhead transfer distance: {round(distance_meters / 1000.0, 2)} km (est. {estimated_travel_time_minutes} min)."
            if distance_meters is not None
            else " Proximity unavailable due to missing GPS."
        )
        reason = (
            f"Target Route {target_route.route_number} is experiencing {target_route.status} passenger demand "
            f"({target_pct}% load factor), requiring additional capacity. Source Route {source_route.route_number} "
            f"is underutilized ({source_pct}% load factor) with spare capacity. Candidate Bus {candidate_bus_number} "
            f"has {available_capacity} available seats{proj_target_str}.{dist_str}"
        )
    else:
        reason = (
            f"Target Route {target_route.route_number} is experiencing {target_route.status} passenger demand "
            f"({target_pct}% load factor), while Source Route {source_route.route_number} is underutilized "
            f"({source_pct}% load factor), but no suitable candidate bus is currently available."
        )

    rec_id = (
        f"REC-{target_route.route_number}-{source_route.route_number}-{candidate_bus_number or 'NOBUS'}"
    )

    # Nested helper models for client convenience
    source_brief = RouteBrief(
        route_id=source_route.route_id,
        route_number=source_route.route_number,
        load_factor=source_route.load_factor,
        status=source_route.status,
    )
    target_brief = RouteBrief(
        route_id=target_route.route_id,
        route_number=target_route.route_number,
        load_factor=target_route.load_factor,
        status=target_route.status,
    )
    candidate_bus_brief = (
        BusBrief(
            bus_id=candidate_bus.bus_id,
            bus_number=candidate_bus.bus_number,
            capacity=candidate_bus.capacity,
            current_occupancy=candidate_bus.passenger_count,
            available_capacity=candidate_bus.available_seats,
            load_factor=candidate_bus.load_factor,
        )
        if candidate_bus
        else None
    )

    return ReallocationRecommendationResponse(
        id=rec_id,
        source_route_id=source_route.route_id,
        source_route_number=source_route.route_number,
        source_route_load_factor=source_route.load_factor,
        source_route_status=source_route.status,
        source_route=source_brief,
        target_route_id=target_route.route_id,
        target_route_number=target_route.route_number,
        target_route_load_factor=target_route.load_factor,
        target_route_status=target_route.status,
        target_route=target_brief,
        candidate_bus_id=candidate_bus_id,
        candidate_bus_number=candidate_bus_number,
        bus_capacity=bus_capacity,
        current_occupancy=current_occupancy,
        available_capacity=available_capacity,
        bus_load_factor=bus_load_factor,
        candidate_bus=candidate_bus_brief,
        distance_meters=distance_meters,
        estimated_travel_time_minutes=estimated_travel_time_minutes,
        projected_target_load_factor=projected_target_lf,
        projected_source_load_factor=projected_source_lf,
        score=total_score,
        priority=priority,
        feasibility_status=feasibility_status,
        limitations=limitations,
        reason=reason,
        is_advisory=True,
    )


class OptimizationService:
    """Service providing advisory rule-based fleet reallocation recommendations."""

    _cached_recommendations_by_id: Dict[str, ReallocationRecommendationResponse] = {}
    _cached_recommendations_db: Optional[str] = None
    _recommendations_cache: List[ReallocationRecommendationResponse] = []
    _recommendations_cache_time: Optional[float] = None
    _recommendations_cache_db: Optional[str] = None
    _cache_ttl_seconds: float = 4.0

    @staticmethod
    def get_latest_bus_position(db: Session, bus_id: int) -> Optional[BusPosition]:
        """Retrieve most recent recorded GPS position for a bus."""
        try:
            from app.simulator.manager import simulation_manager
            if simulation_manager.runner and simulation_manager.runner.bus_simulators:
                sim_b = next((b for b in simulation_manager.runner.bus_simulators if b.bus_id == bus_id), None)
                if sim_b and sim_b.latitude is not None and sim_b.longitude is not None:
                    return BusPosition(
                        bus_id=bus_id,
                        latitude=sim_b.latitude,
                        longitude=sim_b.longitude,
                        timestamp=datetime.now(timezone.utc),
                    )
        except Exception:
            pass

        return (
            db.query(BusPosition)
            .filter(BusPosition.bus_id == bus_id)
            .order_by(BusPosition.timestamp.desc(), BusPosition.id.desc())
            .first()
        )

    @staticmethod
    def get_route_origin_stop(db: Session, route_id: int) -> Optional[Stop]:
        """Retrieve origin terminal stop (sequence_order = 1) for a route."""
        return (
            db.query(Stop)
            .filter(Stop.route_id == route_id)
            .order_by(Stop.sequence_order.asc())
            .first()
        )

    @classmethod
    def generate_recommendations(
        cls,
        db: Session,
        target_route_id: Optional[int] = None,
        source_route_id: Optional[int] = None,
        min_score: Optional[float] = None,
        best_only: bool = False,
    ) -> List[ReallocationRecommendationResponse]:
        """Generate structured rule-based fleet reallocation recommendations.

        Analyzes Stage 4 load intelligence across all routes and buses, identifies
        overloaded target routes (HIGH/CRITICAL) and underutilized source routes (LOW),
        evaluates candidate buses, and ranks recommendations deterministically.
        """
        db_key = _get_db_session_id(db)
        # Return fresh cache copy if within TTL for global recommendation query on same DB session
        if (
            not target_route_id
            and not source_route_id
            and min_score is None
            and not best_only
            and cls._recommendations_cache_db == db_key
            and cls._recommendations_cache
            and cls._recommendations_cache_time is not None
            and (time.time() - cls._recommendations_cache_time) < cls._cache_ttl_seconds
        ):
            return [r.model_copy() for r in cls._recommendations_cache]

        bus_intel_list = LoadIntelligenceService.get_bus_intelligence(db)
        route_intel_list = LoadIntelligenceService.get_route_intelligence_from_buses(db, bus_intel_list)

        # 1. Identify overloaded target routes needing additional capacity
        # A route is a candidate target if route status is HIGH/CRITICAL, or if any active bus is HIGH/CRITICAL
        overloaded_routes: List[RouteIntelligenceResponse] = []
        for r in route_intel_list:
            r_buses = [b for b in bus_intel_list if b.route_id == r.route_id]
            has_overloaded_bus = any(b.status in ("HIGH", "CRITICAL") for b in r_buses)
            if r.status in ("HIGH", "CRITICAL") or has_overloaded_bus:
                overloaded_routes.append(r)

        if target_route_id is not None:
            overloaded_routes = [r for r in overloaded_routes if r.route_id == target_route_id]

        # 2. Identify potential source routes with spare capacity
        underutilized_routes: List[RouteIntelligenceResponse] = []
        for r in route_intel_list:
            if r.status == "LOW" or r.load_factor < 0.75:
                underutilized_routes.append(r)

        if source_route_id is not None:
            underutilized_routes = [r for r in underutilized_routes if r.route_id == source_route_id]

        # If no demand imbalance exists, return empty list
        if not overloaded_routes or not underutilized_routes:
            return []

        # Cache DB buses by id for operational status verification
        all_db_buses = {b.id: b for b in db.query(Bus).all()}

        # Active transfer bus IDs (executed or in transfer in the last 5 minutes)
        active_transfer_bus_ids = set()
        if db is not None:
            try:
                recent_execs = (
                    db.query(ReallocationExecution)
                    .filter(ReallocationExecution.status.in_(("IN_PROGRESS", "EXECUTED")))
                    .all()
                )
                for ex in recent_execs:
                    if ex.created_at:
                        tz = ex.created_at.tzinfo or timezone.utc
                        if (datetime.now(tz) - ex.created_at.replace(tzinfo=tz)).total_seconds() < 300:
                            active_transfer_bus_ids.add(ex.bus_id)
            except Exception:
                pass

        # Active breakdown bus IDs to strictly exclude
        active_breakdown_bus_ids = set()
        if db is not None:
            try:
                from app.models.bus_breakdown import BusBreakdown
                active_bbs = (
                    db.query(BusBreakdown.bus_id)
                    .filter(BusBreakdown.status.in_(("REPORTED", "CONFIRMED", "UNDER_REPAIR")))
                    .all()
                )
                active_breakdown_bus_ids = {b_id for (b_id,) in active_bbs}
            except Exception:
                pass

        # Group bus intelligence by route_id
        buses_by_route: Dict[int, List[BusIntelligenceResponse]] = {}
        for b in bus_intel_list:
            if b.route_id is not None:
                buses_by_route.setdefault(b.route_id, []).append(b)

        # Pre-fetch route origin stops in one batched query
        target_ids = [target.route_id for target in overloaded_routes]
        origin_stops: Dict[int, Optional[Stop]] = {}
        if target_ids:
            stops = (
                db.query(Stop)
                .filter(Stop.route_id.in_(target_ids), Stop.sequence_order == 1)
                .all()
            )
            origin_stops = {s.route_id: s for s in stops}

        weather_obs = None
        try:
            from app.services.weather import WeatherService
            weather_obs = WeatherService.get_current_weather()
        except Exception:
            pass

        recommendations: List[ReallocationRecommendationResponse] = []

        for target in overloaded_routes:
            target_stop = origin_stops.get(target.route_id)

            for source in underutilized_routes:
                if source.route_id == target.route_id:
                    continue  # A route cannot be reallocated to itself

                source_buses = buses_by_route.get(source.route_id, [])

                # Operational donor count: must have at least 1 operational bus
                operational_donor_count = sum(
                    1 for b in source_buses
                    if b.bus_id not in active_breakdown_bus_ids
                    and b.bus_id not in active_transfer_bus_ids
                    and all_db_buses.get(b.bus_id, Bus()).status in ("ACTIVE", "IDLE", "IN_SERVICE")
                )
                if operational_donor_count < 1:
                    continue

                # Filter suitable candidate buses
                suitable_buses: List[BusIntelligenceResponse] = []
                for b_intel in source_buses:
                    # Do not recommend a bus already assigned to target route
                    if b_intel.route_id == target.route_id:
                        continue

                    # Do not recommend a bus currently deadheading/transferring
                    if b_intel.bus_id in active_transfer_bus_ids:
                        continue

                    # Do not recommend a broken down bus
                    if b_intel.bus_id in active_breakdown_bus_ids:
                        continue

                    # Check DB bus operational status
                    db_bus = all_db_buses.get(b_intel.bus_id)
                    if db_bus and db_bus.status in ("INACTIVE", "MAINTENANCE", "OUT_OF_SERVICE", "BROKEN_DOWN"):
                        continue

                    # Check bus capacity and load suitability
                    if b_intel.available_seats <= 0 or b_intel.load_factor >= 0.80:
                        continue  # Bus is crowded, not a suitable donor

                    # Operational resilience: donating must not cause donor route to exceed physical capacity
                    if source.number_of_buses > 1:
                        remaining_cap = source.total_capacity - b_intel.capacity
                        rem_pax_on_donor = max(0, source.total_passengers - b_intel.passenger_count)
                        if remaining_cap <= 0:
                            continue
                        if rem_pax_on_donor > remaining_cap or (source.total_passengers / remaining_cap) > 1.00:
                            continue

                    suitable_buses.append(b_intel)

                # If no genuinely suitable buses found on this route, do not fabricate artificial recommendations
                if not suitable_buses:
                    continue

                # Evaluate recommendations for each suitable bus
                pair_recs: List[ReallocationRecommendationResponse] = []
                for b_intel in suitable_buses:
                    db_bus = all_db_buses.get(b_intel.bus_id)
                    latest_pos = cls.get_latest_bus_position(db, b_intel.bus_id)

                    rec = evaluate_bus_reallocation(
                        target_route=target,
                        source_route=source,
                        candidate_bus=b_intel,
                        target_origin_stop=target_stop,
                        bus_position=latest_pos,
                        db_bus=db_bus,
                        weather_obs=weather_obs,
                    )
                    # Exclude infeasible reallocations from recommendation list
                    if rec.feasibility_status == "INFEASIBLE":
                        continue
                    pair_recs.append(rec)

                # Sort pair recommendations by score descending
                pair_recs.sort(
                    key=lambda r: (
                        -r.score,
                        -(r.available_capacity or 0),
                        r.distance_meters if r.distance_meters is not None else float("inf"),
                        r.candidate_bus_id or 0,
                    )
                )

                if best_only and pair_recs:
                    recommendations.append(pair_recs[0])
                else:
                    recommendations.extend(pair_recs)

        # Apply score filter if requested
        if min_score is not None:
            recommendations = [r for r in recommendations if r.score >= min_score]

        # Deterministic, stable global ranking
        # Order by: score desc, target load factor desc, available capacity desc, tie-breaker IDs
        recommendations.sort(
            key=lambda r: (
                -r.score,
                -r.target_route_load_factor,
                -(r.available_capacity or 0),
                r.target_route_id,
                r.source_route_id,
                r.candidate_bus_id or 0,
            )
        )

        # Stage 7 & Execution: Populate latest review & execution status for generated recommendations
        if db is not None and recommendations:
            try:
                rec_ids = [r.id for r in recommendations]
                reviews = (
                    db.query(ReallocationReview)
                    .filter(ReallocationReview.recommendation_id.in_(rec_ids))
                    .order_by(ReallocationReview.created_at.desc(), ReallocationReview.id.desc())
                    .all()
                )
                latest_reviews_by_rec_id: Dict[str, ReallocationReview] = {}
                for rev in reviews:
                    if rev.recommendation_id not in latest_reviews_by_rec_id:
                        latest_reviews_by_rec_id[rev.recommendation_id] = rev

                executions = (
                    db.query(ReallocationExecution)
                    .filter(ReallocationExecution.recommendation_id.in_(rec_ids))
                    .order_by(ReallocationExecution.created_at.desc(), ReallocationExecution.id.desc())
                    .all()
                )
                latest_exec_by_rec_id: Dict[str, ReallocationExecution] = {}
                for ex in executions:
                    if ex.recommendation_id not in latest_exec_by_rec_id:
                        latest_exec_by_rec_id[ex.recommendation_id] = ex

                for r in recommendations:
                    if r.id in latest_reviews_by_rec_id:
                        matched_rev = latest_reviews_by_rec_id[r.id]
                        r.review_status = matched_rev.decision
                        r.latest_review = ReallocationReviewResponse.model_validate(matched_rev)
                        r.execution_status = matched_rev.execution_status
                        r.executed_at = matched_rev.executed_at
                    if r.id in latest_exec_by_rec_id:
                        matched_ex = latest_exec_by_rec_id[r.id]
                        r.latest_execution = ReallocationExecutionResponse.model_validate(matched_ex)
                        if not r.execution_status:
                            r.execution_status = matched_ex.status
                            r.executed_at = matched_ex.created_at
            except Exception:
                # Fallback gracefully if database or table is not initialized yet
                pass

        # Populate in-memory lookup cache by recommendation ID for fast zero-latency review resolution
        if cls._cached_recommendations_db != db_key:
            cls._cached_recommendations_by_id.clear()
            cls._cached_recommendations_db = db_key

        for r in recommendations:
            cls._cached_recommendations_by_id[r.id] = r

        if not target_route_id and not source_route_id and min_score is None and not best_only:
            cls._recommendations_cache = [r.model_copy() for r in recommendations]
            cls._recommendations_cache_time = time.time()
            cls._recommendations_cache_db = db_key

        return recommendations

    @classmethod
    def get_overview(cls, db: Session) -> OptimizationOverviewResponse:
        """Provide a fleet-wide overview of optimization recommendations, feasibility, and reviews."""
        recs = cls.generate_recommendations(db, best_only=False)

        high = sum(1 for r in recs if r.priority == "HIGH")
        med = sum(1 for r in recs if r.priority == "MEDIUM")
        low = sum(1 for r in recs if r.priority == "LOW")

        feasible = sum(1 for r in recs if r.feasibility_status == "FEASIBLE")
        cond = sum(1 for r in recs if r.feasibility_status in ("CONDITIONALLY_FEASIBLE", "LIMITED_DATA"))
        infeasible = sum(1 for r in recs if r.feasibility_status in ("INFEASIBLE", "NO_CANDIDATE_BUS"))

        approved = sum(1 for r in recs if (r.review_status or "").upper() == "APPROVED")
        rejected = sum(1 for r in recs if (r.review_status or "").upper() == "REJECTED")
        deferred = sum(1 for r in recs if (r.review_status or "").upper() == "DEFERRED")
        pending = sum(1 for r in recs if not r.review_status)
        executed = sum(1 for r in recs if (r.execution_status or "").upper() == "EXECUTED")

        bus_intel_list = LoadIntelligenceService.get_bus_intelligence(db)
        route_intel_list = LoadIntelligenceService.get_route_intelligence_from_buses(db, bus_intel_list)

        diagnostic_reasons: List[str] = []
        for r in route_intel_list:
            r_buses = [b for b in bus_intel_list if b.route_id == r.route_id]
            overloaded_buses = [b for b in r_buses if b.status in ("HIGH", "CRITICAL")]
            if r.status in ("HIGH", "CRITICAL") or overloaded_buses:
                matching_recs = [rec for rec in recs if rec.target_route_id == r.route_id and rec.candidate_bus_id is not None]
                if not matching_recs:
                    b_detail = f" (Bus {overloaded_buses[0].bus_number} at {round(overloaded_buses[0].load_factor * 100, 1)}%)" if overloaded_buses else ""
                    donor_constraints = []
                    for other_r in route_intel_list:
                        if other_r.route_id != r.route_id:
                            if other_r.number_of_buses <= 1:
                                donor_constraints.append(f"Route {other_r.route_number} has only {other_r.number_of_buses} operational bus (minimum coverage rule)")
                            elif other_r.load_factor >= 0.80 or other_r.status in ("HIGH", "CRITICAL"):
                                donor_constraints.append(f"Route {other_r.route_number} is overloaded ({round(other_r.load_factor * 100, 1)}% LF)")
                            else:
                                rem_cap = other_r.total_capacity - 60
                                if rem_cap <= 0:
                                    donor_constraints.append(f"Route {other_r.route_number} has insufficient capacity to donate")
                                elif other_r.total_passengers > rem_cap:
                                    donor_constraints.append(f"Route {other_r.route_number} corridor demand ({other_r.total_passengers} pax) exceeds single-bus capacity ({rem_cap} seats)")
                                else:
                                    donor_constraints.append(f"Route {other_r.route_number} buses are currently unavailable or transferring")
                    constraint_str = f" [{'; '.join(donor_constraints)}]" if donor_constraints else ""
                    msg = (
                        f"Route {r.route_number}{b_detail} is experiencing {r.status} passenger demand "
                        f"({round(r.load_factor * 100, 1)}% load factor), but no eligible donor route "
                        f"possesses surplus fleet depth (>1 bus) and spare capacity without violating "
                        f"minimum service coverage or causing route overcrowding.{constraint_str}"
                    )
                    diagnostic_reasons.append(msg)

        disclaimer_text = (
            "All optimization recommendations are strictly advisory. Final dispatch authority "
            "remains with human transit controllers."
        )
        if diagnostic_reasons:
            disclaimer_text += " " + " ".join(diagnostic_reasons)

        return OptimizationOverviewResponse(
            total_recommendations=len(recs),
            high_priority_count=high,
            medium_priority_count=med,
            low_priority_count=low,
            feasible_count=feasible,
            conditionally_feasible_count=cond,
            infeasible_count=infeasible,
            approved_count=approved,
            rejected_count=rejected,
            deferred_count=deferred,
            pending_count=pending,
            executed_count=executed,
            is_advisory=True,
            disclaimer=disclaimer_text,
            diagnostic_reasons=diagnostic_reasons,
        )

    @classmethod
    def record_review(
        cls,
        db: Session,
        recommendation_id: str,
        review_data: ReallocationReviewCreate,
    ) -> ReallocationReviewResponse:
        """Record a human dispatcher review decision for a fleet reallocation recommendation.

        Enforces Stage 7 constraints:
        1. Decisions must strictly be APPROVED, REJECTED, or DEFERRED.
        2. Validates recommendation existence and snapshots route/bus attributes.
        3. Persists the decision in `reallocation_reviews`.
        4. Absolute non-mutation guarantee: DOES NOT modify bus route assignments or dispatch vehicles.
        """
        if db is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database connection not available",
            )

        # 1. Validate decision
        decision_clean = (review_data.decision or "").strip().upper()
        valid_decisions = {"APPROVED", "REJECTED", "DEFERRED"}
        if decision_clean not in valid_decisions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Invalid decision '{review_data.decision}'. "
                    f"Must be one of: {', '.join(sorted(valid_decisions))}."
                ),
            )

        clean_rec_id = (recommendation_id or "").strip()
        if not clean_rec_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Recommendation ID cannot be empty.",
            )

        # 2. Check for duplicate/idempotent recent review (e.g. from rapid double-click)
        existing_rev = (
            db.query(ReallocationReview)
            .filter(ReallocationReview.recommendation_id == clean_rec_id)
            .order_by(ReallocationReview.created_at.desc(), ReallocationReview.id.desc())
            .first()
        )
        if existing_rev and existing_rev.decision == decision_clean:
            # Idempotently return the existing review without creating duplicate database row
            return ReallocationReviewResponse.model_validate(existing_rev)

        target_route_id: Optional[int] = None
        target_route_number: Optional[str] = None
        source_route_id: Optional[int] = None
        source_route_number: Optional[str] = None
        candidate_bus_id: Optional[int] = None
        candidate_bus_number: Optional[str] = None
        score: Optional[float] = None
        priority: Optional[str] = None

        # 3. Fast resolution of recommendation metadata
        db_key = _get_db_session_id(db)
        # Strategy A: Check in-memory cache of generated recommendations (0ms)
        matched_rec = cls._cached_recommendations_by_id.get(clean_rec_id) if cls._cached_recommendations_db == db_key else None
        if matched_rec:
            target_route_id = matched_rec.target_route_id
            target_route_number = matched_rec.target_route_number
            source_route_id = matched_rec.source_route_id
            source_route_number = matched_rec.source_route_number
            candidate_bus_id = matched_rec.candidate_bus_id
            candidate_bus_number = matched_rec.candidate_bus_number
            score = matched_rec.score
            priority = matched_rec.priority

        # Strategy B: Use client-provided metadata if present
        if not target_route_id and review_data.target_route_id and review_data.source_route_id:
            target_route_id = review_data.target_route_id
            target_route_number = review_data.target_route_number
            source_route_id = review_data.source_route_id
            source_route_number = review_data.source_route_number
            candidate_bus_id = review_data.candidate_bus_id
            candidate_bus_number = review_data.candidate_bus_number
            score = review_data.score or 75.0
            priority = review_data.priority or "MEDIUM"

        # Strategy C: Check prior review history for this recommendation ID
        if not target_route_id and existing_rev:
            target_route_id = existing_rev.target_route_id
            target_route_number = existing_rev.target_route_number
            source_route_id = existing_rev.source_route_id
            source_route_number = existing_rev.source_route_number
            candidate_bus_id = existing_rev.candidate_bus_id
            candidate_bus_number = existing_rev.candidate_bus_number
            score = existing_rev.score
            priority = existing_rev.priority

        # Strategy D: Parse structured recommendation ID (REC-{target_num}-{source_num}-{bus_num})
        if not target_route_id and clean_rec_id.startswith("REC-"):
            parts = clean_rec_id.split("-")
            if len(parts) >= 4:
                parsed_target_num = parts[1]
                parsed_source_num = parts[2]
                parsed_bus_num = parts[3] if parts[3] != "NOBUS" else None

                routes = db.query(Route).filter(Route.route_number.in_([parsed_target_num, parsed_source_num])).all()
                routes_by_num = {r.route_number: r for r in routes}
                t_route = routes_by_num.get(parsed_target_num)
                s_route = routes_by_num.get(parsed_source_num)

                if t_route and s_route:
                    target_route_id = t_route.id
                    target_route_number = t_route.route_number
                    source_route_id = s_route.id
                    source_route_number = s_route.route_number
                    if parsed_bus_num:
                        matched_bus = db.query(Bus).filter(Bus.bus_number == parsed_bus_num).first()
                        if matched_bus:
                            candidate_bus_id = matched_bus.id
                            candidate_bus_number = matched_bus.bus_number
                    score = review_data.score or 75.0
                    priority = review_data.priority or "MEDIUM"

        # Strategy E: Fallback to generate_recommendations only if all fast paths failed
        if not target_route_id:
            active_recs = cls.generate_recommendations(db, best_only=False)
            matched_rec = next((r for r in active_recs if r.id == clean_rec_id), None)
            if matched_rec:
                target_route_id = matched_rec.target_route_id
                target_route_number = matched_rec.target_route_number
                source_route_id = matched_rec.source_route_id
                source_route_number = matched_rec.source_route_number
                candidate_bus_id = matched_rec.candidate_bus_id
                candidate_bus_number = matched_rec.candidate_bus_number
                score = matched_rec.score
                priority = matched_rec.priority
            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Reallocation recommendation '{clean_rec_id}' not found.",
                )

        # 4. Create persistent review record
        review_record = ReallocationReview(
            recommendation_id=clean_rec_id,
            decision=decision_clean,
            dispatcher_id=(review_data.dispatcher_id or "DISPATCHER-1").strip(),
            target_route_id=target_route_id,
            target_route_number=target_route_number,
            source_route_id=source_route_id,
            source_route_number=source_route_number,
            candidate_bus_id=candidate_bus_id,
            candidate_bus_number=candidate_bus_number,
            score=score,
            priority=priority,
            notes=review_data.notes.strip() if review_data.notes else None,
        )

        db.add(review_record)
        db.commit()
        db.refresh(review_record)

        # Invalidate recommendation cache so subsequent queries fetch updated status
        cls._recommendations_cache_time = None
        if clean_rec_id in cls._cached_recommendations_by_id:
            cls._cached_recommendations_by_id[clean_rec_id].review_status = decision_clean
            cls._cached_recommendations_by_id[clean_rec_id].latest_review = ReallocationReviewResponse.model_validate(review_record)

        return ReallocationReviewResponse.model_validate(review_record)

    @classmethod
    def get_reviews(
        cls,
        db: Session,
        decision: Optional[str] = None,
        recommendation_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ReallocationReviewResponse]:
        """Retrieve historical dispatcher review records with optional filters."""
        if db is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database connection not available",
            )

        query = db.query(ReallocationReview)
        if decision:
            query = query.filter(ReallocationReview.decision == decision.strip().upper())
        if recommendation_id:
            query = query.filter(ReallocationReview.recommendation_id == recommendation_id.strip())

        reviews = (
            query.order_by(ReallocationReview.created_at.desc(), ReallocationReview.id.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        return [ReallocationReviewResponse.model_validate(r) for r in reviews]

    @classmethod
    def get_recommendation_history(
        cls,
        db: Session,
        recommendation_id: str,
    ) -> List[ReallocationReviewResponse]:
        """Retrieve full audit review history for a specific recommendation ID."""
        if db is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database connection not available",
            )

        clean_id = (recommendation_id or "").strip()
        reviews = (
            db.query(ReallocationReview)
            .filter(ReallocationReview.recommendation_id == clean_id)
            .order_by(ReallocationReview.created_at.desc(), ReallocationReview.id.desc())
            .all()
        )

        return [ReallocationReviewResponse.model_validate(r) for r in reviews]

    @classmethod
    def execute_reassignment(
        cls,
        db: Session,
        recommendation_id: str,
        execution_data: ReallocationExecutionCreate,
    ) -> ReallocationExecutionResponse:
        """Execute an approved fleet reallocation recommendation.

        Enforces all operational safety criteria:
        1. Validates that recommendation exists and is currently APPROVED.
        2. Prevents duplicate execution of already executed recommendations.
        3. Validates candidate bus presence, operational availability (ACTIVE/IDLE), and current assignment.
        4. Validates source route service coverage (ensuring minimum 1 active bus remains).
        5. Validates passenger occupancy safety (rejecting if bus is overcrowded >85%).
        6. Updates bus's persisted current_route_id in the database.
        7. Records execution audit record in reallocation_executions and updates review record.
        8. Creates operational transit alert notification.
        9. On safety check failure, audits the failure in reallocation_executions and raises HTTP 400.
        """
        if db is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database connection not available",
            )

        clean_rec_id = (recommendation_id or "").strip()
        if not clean_rec_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Recommendation ID cannot be empty.",
            )

        dispatcher_id = (execution_data.dispatcher_id or "DISPATCHER-1").strip()
        now = datetime.now(timezone.utc)

        # 1. Fetch latest review for this recommendation
        latest_review = (
            db.query(ReallocationReview)
            .filter(ReallocationReview.recommendation_id == clean_rec_id)
            .order_by(ReallocationReview.created_at.desc(), ReallocationReview.id.desc())
            .first()
        )

        if not latest_review:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No dispatcher review found for recommendation '{clean_rec_id}'. Recommendations must be reviewed and approved before execution.",
            )

        # 2. Enforce approval requirement
        if latest_review.decision.upper() != "APPROVED":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Recommendation '{clean_rec_id}' is marked as {latest_review.decision}. Only APPROVED recommendations can be executed.",
            )

        # 3. Prevent duplicate execution
        if (latest_review.execution_status or "").upper() == "EXECUTED":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Recommendation '{clean_rec_id}' has already been executed at {latest_review.executed_at}.",
            )

        existing_exec = (
            db.query(ReallocationExecution)
            .filter(
                ReallocationExecution.recommendation_id == clean_rec_id,
                ReallocationExecution.status == "EXECUTED",
            )
            .first()
        )
        if existing_exec:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Recommendation '{clean_rec_id}' has already been successfully executed at {existing_exec.created_at}.",
            )

        # 4. Resolve candidate bus and routes
        bus_id = latest_review.candidate_bus_id
        source_route_id = latest_review.source_route_id
        target_route_id = latest_review.target_route_id

        if not bus_id or not source_route_id or not target_route_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Recommendation lacks essential candidate bus or route identifiers.",
            )

        # Query bus with row locking to prevent concurrent conflicting assignments
        bus = db.query(Bus).filter(Bus.id == bus_id).with_for_update().first()
        if not bus:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Candidate Bus ID {bus_id} ({latest_review.candidate_bus_number}) not found.",
            )

        source_route = db.query(Route).filter(Route.id == source_route_id).first()
        target_route = db.query(Route).filter(Route.id == target_route_id).first()

        def record_failure(error_msg: str, status_code: int = status.HTTP_400_BAD_REQUEST):
            failed_record = ReallocationExecution(
                recommendation_id=clean_rec_id,
                review_id=latest_review.id,
                bus_id=bus.id,
                bus_number=bus.bus_number,
                source_route_id=source_route_id,
                source_route_number=latest_review.source_route_number or (source_route.route_number if source_route else "UNKNOWN"),
                target_route_id=target_route_id,
                target_route_number=latest_review.target_route_number or (target_route.route_number if target_route else "UNKNOWN"),
                dispatcher_id=dispatcher_id,
                status="FAILED",
                error_message=error_msg,
                notes=execution_data.notes.strip() if execution_data.notes else None,
            )
            db.add(failed_record)
            try:
                db.commit()
            except Exception:
                db.rollback()
            raise HTTPException(status_code=status_code, detail=error_msg)

        # 5. Check bus status availability
        if bus.status not in ("ACTIVE", "IDLE", "IN_SERVICE"):
            record_failure(f"Bus {bus.bus_number} status is {bus.status}. Only ACTIVE, IDLE, or IN_SERVICE buses can be reallocated.")

        # 6. Check bus route assignment consistency
        if bus.current_route_id == target_route_id:
            record_failure(f"Bus {bus.bus_number} is already assigned to target Route {target_route.route_number if target_route else target_route_id}.")

        if bus.current_route_id != source_route_id:
            current_r_num = bus.current_route.route_number if bus.current_route else str(bus.current_route_id)
            record_failure(f"Bus {bus.bus_number} is currently assigned to Route {current_r_num}, not expected source Route {latest_review.source_route_number}.")

        # 7. Check target route validity
        if not target_route or not target_route.is_active:
            record_failure("Target route does not exist or is inactive.")

        if not target_route.stops:
            record_failure(f"Target Route {target_route.route_number} has no configured stops.")

        # 8. Check source route service coverage and exclude broken buses
        from app.models.bus_breakdown import BusBreakdown
        broken_bus_ids = {
            bb.bus_id for bb in db.query(BusBreakdown.bus_id).filter(
                BusBreakdown.status.in_(("REPORTED", "CONFIRMED", "UNDER_REPAIR"))
            ).all()
        }

        # Check if candidate bus itself has an active breakdown
        if bus.id in broken_bus_ids or bus.status in ("BROKEN_DOWN", "MAINTENANCE"):
            record_failure(f"Cannot reassign Bus {bus.bus_number}: Vehicle is currently broken down or under repair.")

        source_active_count = (
            db.query(Bus)
            .filter(
                Bus.current_route_id == source_route_id,
                Bus.status.in_(("ACTIVE", "IDLE", "IN_SERVICE")),
                ~Bus.id.in_(broken_bus_ids) if broken_bus_ids else True,
            )
            .count()
        )
        if source_active_count <= 1:
            record_failure(
                f"Cannot reassign Bus {bus.bus_number}: Source Route {source_route.route_number if source_route else source_route_id} "
                f"has only {source_active_count} active operational bus(es). Reassignment would violate minimum service coverage."
            )

        # 9. Check passenger occupancy safety
        latest_load = (
            db.query(PassengerLoad)
            .filter(PassengerLoad.bus_id == bus.id)
            .order_by(PassengerLoad.timestamp.desc(), PassengerLoad.id.desc())
            .first()
        )
        if latest_load and latest_load.load_factor > 0.85:
            record_failure(
                f"Bus {bus.bus_number} currently has high passenger occupancy "
                f"({latest_load.current_load}/{latest_load.capacity} pax, {int(round(latest_load.load_factor * 100))}%). "
                f"Passenger alighting required before deadhead transfer."
            )

        # 10. Execute reassignment: update bus persisted route
        bus.current_route_id = target_route_id
        bus.updated_at = now

        # Update review record
        latest_review.execution_status = "EXECUTED"
        latest_review.executed_at = now

        # Create execution record
        exec_record = ReallocationExecution(
            recommendation_id=clean_rec_id,
            review_id=latest_review.id,
            bus_id=bus.id,
            bus_number=bus.bus_number,
            source_route_id=source_route_id,
            source_route_number=source_route.route_number if source_route else str(source_route_id),
            target_route_id=target_route_id,
            target_route_number=target_route.route_number if target_route else str(target_route_id),
            dispatcher_id=dispatcher_id,
            status="EXECUTED",
            notes=execution_data.notes.strip() if execution_data.notes else None,
            created_at=now,
            updated_at=now,
        )
        db.add(exec_record)

        # Create operational alert / notification
        try:
            notif = Notification(
                alert_type="REALLOCATION_OPPORTUNITY",
                severity="INFO",
                title=f"Fleet Reassignment Executed: Bus {bus.bus_number}",
                description=(
                    f"Bus {bus.bus_number} successfully reassigned from Route "
                    f"{source_route.route_number if source_route else source_route_id} to Route "
                    f"{target_route.route_number if target_route else target_route_id} by {dispatcher_id}."
                ),
                source="LIVE",
                status="ACTIVE",
                dedup_key=f"REALLOC_EXEC_{clean_rec_id}_{now.timestamp()}",
                route_id=target_route_id,
                bus_id=bus.id,
            )
            db.add(notif)
        except Exception:
            pass

        db.commit()
        db.refresh(exec_record)

        # Invalidate recommendation cache so subsequent queries reflect executed status
        cls._recommendations_cache_time = None
        if clean_rec_id in cls._cached_recommendations_by_id:
            cls._cached_recommendations_by_id[clean_rec_id].execution_status = "EXECUTED"
            cls._cached_recommendations_by_id[clean_rec_id].executed_at = now

        # Synchronize in-memory simulation fleet immediately if simulation is active
        try:
            from app.simulator.manager import simulation_manager
            simulation_manager.notify_route_reassignment(
                bus_id=bus.id,
                target_route_id=target_route_id,
                target_route_number=target_route.route_number if target_route else "",
                stops=target_route.stops if target_route else None,
            )
        except Exception:
            pass

        return ReallocationExecutionResponse.model_validate(exec_record)

    @classmethod
    def get_executions(
        cls,
        db: Session,
        recommendation_id: Optional[str] = None,
        bus_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ReallocationExecutionResponse]:
        """Retrieve historical reallocation execution records with optional filters."""
        if db is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database connection not available",
            )

        query = db.query(ReallocationExecution)
        if recommendation_id:
            query = query.filter(ReallocationExecution.recommendation_id == recommendation_id.strip())
        if bus_id:
            query = query.filter(ReallocationExecution.bus_id == bus_id)
        if status:
            query = query.filter(ReallocationExecution.status == status.strip().upper())

        executions = (
            query.order_by(ReallocationExecution.created_at.desc(), ReallocationExecution.id.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        return [ReallocationExecutionResponse.model_validate(e) for e in executions]

    @classmethod
    def get_recommendation_executions(
        cls,
        db: Session,
        recommendation_id: str,
    ) -> List[ReallocationExecutionResponse]:
        """Retrieve execution audit history for a specific recommendation ID."""
        if db is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database connection not available",
            )

        clean_id = (recommendation_id or "").strip()
        executions = (
            db.query(ReallocationExecution)
            .filter(ReallocationExecution.recommendation_id == clean_id)
            .order_by(ReallocationExecution.created_at.desc(), ReallocationExecution.id.desc())
            .all()
        )

        return [ReallocationExecutionResponse.model_validate(e) for e in executions]

    @classmethod
    def execute_manual_reassignment(
        cls,
        db: Session,
        bus_id: int,
        manual_data: ManualReassignmentCreate,
    ) -> ReallocationExecutionResponse:
        """Execute a manual dispatcher route reassignment.

        Adheres strictly to the operational safety lifecycle:
        1. Validates that the bus exists and is in an operational state (ACTIVE, IDLE, IN_SERVICE).
        2. Validates that target route exists, is active, and possesses configured stops.
        3. Prevents redundant assignment if bus is already assigned to target route.
        4. Rejects conflicting transfers if the bus is currently in an active transfer.
        5. Persists the route update in the database so the simulator initiates continuous deadheading.
        6. Audits the dispatcher identity, source route, target route, timestamp, and justification.
        7. Creates an operational alert notification.
        """
        if db is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database connection not available",
            )

        now = datetime.now(timezone.utc)
        dispatcher_id = (manual_data.dispatcher_id or "DISPATCHER-1").strip()

        # 1. Fetch bus with row-level lock
        bus = db.query(Bus).filter(Bus.id == bus_id).with_for_update().first()
        if not bus:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Bus with ID {bus_id} not found.",
            )

        if bus.status not in ("ACTIVE", "IDLE", "IN_SERVICE"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Bus {bus.bus_number} status is {bus.status}. Only ACTIVE, IDLE, or IN_SERVICE buses can be reassigned.",
            )

        # 2. Fetch and validate target route
        target_route = db.query(Route).filter(Route.id == manual_data.target_route_id).first()
        if not target_route or not target_route.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Target Route ID {manual_data.target_route_id} does not exist or is inactive.",
            )
        if not target_route.stops:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Target Route {target_route.route_number} has no configured stops.",
            )

        # 3. Check redundant assignment
        if bus.current_route_id == target_route.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Bus {bus.bus_number} is already assigned to Route {target_route.route_number}.",
            )

        # 4. Check conflicting active transfer
        recent_exec = (
            db.query(ReallocationExecution)
            .filter(
                ReallocationExecution.bus_id == bus.id,
                ReallocationExecution.status.in_(("IN_PROGRESS", "EXECUTED")),
            )
            .order_by(ReallocationExecution.created_at.desc(), ReallocationExecution.id.desc())
            .first()
        )
        if recent_exec and recent_exec.created_at:
            tz = recent_exec.created_at.tzinfo or timezone.utc
            time_since = (now - recent_exec.created_at.replace(tzinfo=tz)).total_seconds()
            if time_since < 180:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Bus {bus.bus_number} is currently in an active transfer to Route {recent_exec.target_route_number} "
                        f"(initiated {int(time_since)}s ago). Conflicting transfer rejected."
                    ),
                )

        # 5. Source route details
        source_route = db.query(Route).filter(Route.id == bus.current_route_id).first()
        source_route_id = source_route.id if source_route else (bus.current_route_id or 0)
        source_route_number = source_route.route_number if source_route else "UNKNOWN"

        rec_id = f"MANUAL-{bus.bus_number}-{target_route.route_number}-{int(now.timestamp())}"
        reason_text = (manual_data.reason or "").strip() or "Manual dispatcher route reassignment"

        # 6. Update bus persisted route assignment
        bus.current_route_id = target_route.id
        bus.updated_at = now

        # 7. Record execution audit
        exec_record = ReallocationExecution(
            recommendation_id=rec_id,
            review_id=None,
            bus_id=bus.id,
            bus_number=bus.bus_number,
            source_route_id=source_route_id,
            source_route_number=source_route_number,
            target_route_id=target_route.id,
            target_route_number=target_route.route_number,
            dispatcher_id=dispatcher_id,
            status="EXECUTED",
            notes=reason_text,
            created_at=now,
            updated_at=now,
        )
        db.add(exec_record)

        # 8. Create operational alert / notification
        try:
            notif = Notification(
                alert_type="MANUAL_REASSIGNMENT",
                severity="INFO",
                title=f"Manual Route Reassignment: Bus {bus.bus_number}",
                description=(
                    f"Bus {bus.bus_number} manually reassigned from Route {source_route_number} to Route "
                    f"{target_route.route_number} by {dispatcher_id}. Rationale: {reason_text}."
                ),
                source="LIVE",
                status="ACTIVE",
                dedup_key=f"MANUAL_REASSIGN_{rec_id}",
                route_id=target_route.id,
                bus_id=bus.id,
            )
            db.add(notif)
        except Exception:
            pass

        db.commit()
        db.refresh(exec_record)

        # Synchronize in-memory simulation fleet immediately if simulation is active
        try:
            from app.simulator.manager import simulation_manager
            simulation_manager.notify_route_reassignment(
                bus_id=bus.id,
                target_route_id=target_route.id,
                target_route_number=target_route.route_number,
                stops=target_route.stops if target_route else None,
            )
        except Exception:
            pass

        return ReallocationExecutionResponse.model_validate(exec_record)

