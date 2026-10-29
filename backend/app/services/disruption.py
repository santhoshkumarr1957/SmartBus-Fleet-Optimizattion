"""Rule-based Transit Disruption Simulation and Resilience Analysis Engine (Stage 8).

Provides isolated in-memory service disruption simulations and calculates
network resilience metrics without altering operational data, bus assignments,
or telemetry history.
"""
import math
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Tuple
from collections import OrderedDict
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.route import Route
from app.models.bus import Bus
from app.models.stop import Stop
from app.models.passenger_load import PassengerLoad
from app.models.bus_position import BusPosition
from app.services.load_intelligence import (
    classify_load_factor,
    calculate_load_factor,
    calculate_available_seats,
)
from app.schemas.disruption import (
    DisruptionTypeInfo,
    DisruptionSimulationRequest,
    RouteImpactSummary,
    BusImpactSummary,
    ResilienceMetrics,
    DisruptionSimulationResponse,
    DisruptionScenarioBrief,
)
from app.schemas.optimization import (
    ReallocationRecommendationResponse,
    RouteBrief,
    BusBrief,
)
from app.services.optimization import (
    calculate_target_severity_score,
    calculate_source_spare_score,
    calculate_bus_suitability_score,
    calculate_proximity_score,
    determine_priority,
)

# In-memory LRU scenario cache (capped at 50 scenarios)
MAX_CACHED_SCENARIOS = 50
_SCENARIO_CACHE: OrderedDict[str, DisruptionSimulationResponse] = OrderedDict()


class DisruptionService:
    """Manages isolated disruption simulations and resilience analyses."""

    SUPPORTED_DISRUPTIONS: Dict[str, DisruptionTypeInfo] = {
        "BUS_BREAKDOWN": DisruptionTypeInfo(
            type="BUS_BREAKDOWN",
            name="Bus Breakdown",
            description="Simulates sudden mechanical breakdown of a vehicle, taking it out of service on its assigned corridor.",
            required_parameters=["bus_id or bus_number"],
            optional_parameters=["notes"],
            example_parameters={"bus_number": "101A", "notes": "Engine overheating simulation"},
        ),
        "ROUTE_CLOSURE": DisruptionTypeInfo(
            type="ROUTE_CLOSURE",
            name="Route Closure",
            description="Simulates complete corridor shutdown due to infrastructure maintenance, road obstruction, or civic emergencies.",
            required_parameters=["route_id or route_number"],
            optional_parameters=["notes"],
            example_parameters={"route_number": "202", "notes": "Roadwork closure simulation"},
        ),
        "DEMAND_SPIKE": DisruptionTypeInfo(
            type="DEMAND_SPIKE",
            name="Passenger Demand Surge",
            description="Simulates an unexpected surge in passenger volume (e.g. sporting event, festival, or train cancellation).",
            required_parameters=["spike_percentage (5.0 to 300.0%) or demand_multiplier (1.05 to 4.0)"],
            optional_parameters=["route_id or route_number", "notes"],
            example_parameters={"route_number": "101", "spike_percentage": 50.0, "notes": "Concert surge"},
        ),
        "DEMAND_SURGE": DisruptionTypeInfo(
            type="DEMAND_SURGE",
            name="Passenger Demand Surge",
            description="Simulates an unexpected surge in passenger volume (e.g. sporting event, festival, or train cancellation).",
            required_parameters=["spike_percentage (5.0 to 300.0%) or demand_multiplier (1.05 to 4.0)"],
            optional_parameters=["route_id or route_number", "notes"],
            example_parameters={"route_number": "101", "spike_percentage": 50.0, "notes": "Concert surge"},
        ),
        "SERVICE_DELAY": DisruptionTypeInfo(
            type="SERVICE_DELAY",
            name="Service Delay & Headway Expansion",
            description="Simulates transit corridor traffic delays, causing stop passenger queues to accumulate and effective vehicle turnaround to drop.",
            required_parameters=["delay_minutes (1.0 to 240.0)"],
            optional_parameters=["route_id or route_number", "bus_id or bus_number", "notes"],
            example_parameters={"route_number": "101", "delay_minutes": 25.0, "notes": "Arterial traffic delay"},
        ),
    }

    @classmethod
    def get_supported_types(cls) -> List[DisruptionTypeInfo]:
        """Return metadata describing all supported disruption simulation types."""
        # Return unique catalog representations
        return [
            cls.SUPPORTED_DISRUPTIONS["BUS_BREAKDOWN"],
            cls.SUPPORTED_DISRUPTIONS["ROUTE_CLOSURE"],
            cls.SUPPORTED_DISRUPTIONS["DEMAND_SPIKE"],
            cls.SUPPORTED_DISRUPTIONS["SERVICE_DELAY"],
        ]

    @classmethod
    def get_cached_scenarios(cls) -> List[DisruptionScenarioBrief]:
        """Return concise summaries of all actively cached in-memory scenarios."""
        summaries: List[DisruptionScenarioBrief] = []
        for s in reversed(_SCENARIO_CACHE.values()):
            target_desc = s.summary_headline
            summaries.append(
                DisruptionScenarioBrief(
                    scenario_id=s.scenario_id,
                    disruption_type=s.disruption_type,
                    target_description=target_desc,
                    simulated_at=s.simulated_at,
                    resilience_score=s.resilience_metrics.resilience_score,
                    resilience_rating=s.resilience_metrics.resilience_rating,
                    routes_affected_count=s.resilience_metrics.routes_affected_count,
                    capacity_lost=s.resilience_metrics.capacity_lost,
                )
            )
        return summaries

    @classmethod
    def get_scenario_by_id(cls, scenario_id: str) -> Optional[DisruptionSimulationResponse]:
        """Retrieve full simulated scenario details from in-memory cache if available."""
        return _SCENARIO_CACHE.get(scenario_id)

    @classmethod
    def simulate_disruption(
        cls,
        db: Session,
        request: DisruptionSimulationRequest,
    ) -> DisruptionSimulationResponse:
        """Execute a rule-based disruption simulation on an isolated in-memory snapshot.

        Guarantees:
        - Absolute read-only query of database.
        - Zero mutations to bus.current_route_id, bus.status, or live telemetry tables.
        - Returns before-and-after impact comparisons, resilience metrics, and reallocation recommendations.
        """
        if db is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database connection not available",
            )

        raw_type = (request.disruption_type or "").strip().upper()
        dtype = "DEMAND_SPIKE" if raw_type in ("DEMAND_SPIKE", "DEMAND_SURGE") else raw_type
        if dtype not in cls.SUPPORTED_DISRUPTIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Unsupported disruption type '{request.disruption_type}'. "
                    f"Supported types: BUS_BREAKDOWN, ROUTE_CLOSURE, DEMAND_SPIKE, SERVICE_DELAY."
                ),
            )

        # 1. Fetch current operational baseline (read-only)
        routes = db.query(Route).filter(Route.is_active == True).order_by(Route.id).all()  # noqa: E712
        if not routes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No active routes found in transit network to simulate.",
            )

        all_buses = db.query(Bus).filter(Bus.status != "INACTIVE").order_by(Bus.id).all()

        # Build latest passenger load mapping
        latest_loads: Dict[int, int] = {}
        for bus in all_buses:
            latest_rec = (
                db.query(PassengerLoad)
                .filter(PassengerLoad.bus_id == bus.id)
                .order_by(PassengerLoad.timestamp.desc(), PassengerLoad.id.desc())
                .first()
            )
            latest_loads[bus.id] = latest_rec.current_load if latest_rec else 0

        # Build baseline route and bus states
        baseline_routes: Dict[int, Dict[str, Any]] = {}
        baseline_buses: Dict[int, Dict[str, Any]] = {}

        for b in all_buses:
            pax = latest_loads.get(b.id, 0)
            lf = round(pax / b.capacity, 4) if b.capacity > 0 else 0.0
            baseline_buses[b.id] = {
                "bus_id": b.id,
                "bus_number": b.bus_number,
                "route_id": b.current_route_id,
                "route_number": b.current_route.route_number if b.current_route else None,
                "capacity": b.capacity,
                "passengers": pax,
                "load_factor": lf,
                "status": b.status,
            }

        for r in routes:
            route_buses = [b for b in all_buses if b.current_route_id == r.id and b.status != "INACTIVE"]
            tot_pax = sum(baseline_buses[b.id]["passengers"] for b in route_buses)
            tot_cap = sum(b.capacity for b in route_buses)
            lf = round(tot_pax / tot_cap, 4) if tot_cap > 0 else 0.0
            status_cls = classify_load_factor(lf) if tot_cap > 0 else "NO_SERVICE"
            avail = max(0, tot_cap - tot_pax)

            baseline_routes[r.id] = {
                "route_id": r.id,
                "route_number": r.route_number,
                "name": r.name,
                "buses_count": len(route_buses),
                "total_passengers": tot_pax,
                "total_capacity": tot_cap,
                "available_seats": avail,
                "load_factor": lf,
                "status": status_cls,
            }

        # 2. Deep clone baseline into simulated snapshot
        sim_routes: Dict[int, Dict[str, Any]] = {
            r_id: dict(data) for r_id, data in baseline_routes.items()
        }
        sim_buses: Dict[int, Dict[str, Any]] = {
            b_id: dict(data) for b_id, data in baseline_buses.items()
        }

        # 3. Apply disruption mutation on the isolated snapshot
        resolved_params: Dict[str, Any] = {}
        summary_headline = ""
        executive_summary = ""

        if request.notes and str(request.notes).strip():
            resolved_params["notes"] = str(request.notes).strip()

        if dtype == "BUS_BREAKDOWN":
            target_bus_id, target_bus = cls._resolve_bus(all_buses, request.bus_id, request.bus_number)
            resolved_params["bus_id"] = target_bus.id
            resolved_params["bus_number"] = target_bus.bus_number
            resolved_params["route_number"] = target_bus.current_route.route_number if target_bus.current_route else None

            # Mark target bus as broken down in scenario
            sim_b = sim_buses[target_bus.id]
            sim_b["status"] = "BROKEN_DOWN"
            sim_b["is_operational"] = False

            # Recalculate route capacity
            route_id = target_bus.current_route_id
            if route_id and route_id in sim_routes:
                r_data = sim_routes[route_id]
                r_data["buses_count"] = max(0, r_data["buses_count"] - 1)
                r_data["total_capacity"] = max(0, r_data["total_capacity"] - target_bus.capacity)
                if r_data["total_capacity"] > 0:
                    r_data["load_factor"] = round(r_data["total_passengers"] / r_data["total_capacity"], 4)
                    r_data["status"] = classify_load_factor(r_data["load_factor"])
                    r_data["available_seats"] = max(0, r_data["total_capacity"] - r_data["total_passengers"])
                else:
                    r_data["load_factor"] = 1.0 if r_data["total_passengers"] > 0 else 0.0
                    r_data["status"] = "CRITICAL" if r_data["total_passengers"] > 0 else "NO_SERVICE"
                    r_data["available_seats"] = 0

            summary_headline = f"Vehicle Breakdown: Bus {target_bus.bus_number} on Route {resolved_params.get('route_number') or 'Unassigned'}"
            executive_summary = (
                f"Simulated mechanical failure of Bus {target_bus.bus_number} removes {target_bus.capacity} seats "
                f"from Route {resolved_params.get('route_number')}. Route load factor adjusted to {sim_routes[route_id]['load_factor'] * 100:.1f}%."
                if route_id and route_id in sim_routes
                else f"Simulated breakdown of Bus {target_bus.bus_number}."
            )

        elif dtype == "ROUTE_CLOSURE":
            clean_route_str = str(request.route_number).strip().upper() if request.route_number is not None else ""
            if clean_route_str == "ALL":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Route closure requires selecting a specific corridor; 'ALL' is not permitted for closure.",
                )

            target_route_id, target_route = cls._resolve_route(routes, request.route_id, request.route_number)
            resolved_params["route_id"] = target_route.id
            resolved_params["route_number"] = target_route.route_number

            # Mark route as closed
            r_data = sim_routes[target_route.id]
            r_data["status"] = "CLOSED"
            r_data["total_capacity"] = 0
            r_data["available_seats"] = 0
            r_data["load_factor"] = 0.0
            r_data["buses_count"] = 0

            # Buses on this route become stranded
            for b_id, b_data in sim_buses.items():
                if b_data["route_id"] == target_route.id:
                    b_data["status"] = "STRANDED_ON_CLOSED_ROUTE"
                    b_data["is_operational"] = False

            summary_headline = f"Corridor Closure: Route {target_route.route_number} ({target_route.name})"
            executive_summary = (
                f"Simulated closure of Route {target_route.route_number} completely eliminates transit service along "
                f"{target_route.origin} → {target_route.destination}. {baseline_routes[target_route.id]['total_capacity']} passenger seats are displaced."
            )

        elif dtype == "DEMAND_SPIKE":
            # Support spike_percentage, demand_multiplier, or demand_percentage
            spike_pct = None
            if request.demand_multiplier is not None:
                if request.demand_multiplier < 1.05 or request.demand_multiplier > 4.0:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="demand_multiplier must be between 1.05 and 4.0 (representing +5% to +300% surge).",
                    )
                spike_pct = round((request.demand_multiplier - 1.0) * 100.0, 1)
            elif request.demand_percentage is not None:
                spike_pct = request.demand_percentage
            elif request.spike_percentage is not None:
                spike_pct = request.spike_percentage
            else:
                spike_pct = 50.0

            if spike_pct < 5.0 or spike_pct > 300.0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="spike_percentage must be between 5.0% and 300.0%.",
                )
            resolved_params["spike_percentage"] = spike_pct

            is_all_routes = (
                (not request.route_id)
                and (not request.route_number or str(request.route_number).strip().upper() == "ALL")
            )
            if not is_all_routes:
                target_route_id, target_route = cls._resolve_route(routes, request.route_id, request.route_number)
                resolved_params["route_id"] = target_route.id
                resolved_params["route_number"] = target_route.route_number
                target_routes_to_spike = [target_route.id]
                summary_headline = f"Passenger Surge: +{spike_pct:.0f}% Demand on Route {target_route.route_number}"
            else:
                target_routes_to_spike = list(sim_routes.keys())
                summary_headline = f"System-Wide Passenger Surge: +{spike_pct:.0f}% Demand"

            for r_id in target_routes_to_spike:
                r_data = sim_routes[r_id]
                base_pax = r_data["total_passengers"]
                if base_pax > 0:
                    added_pax = int(round(base_pax * (spike_pct / 100.0)))
                else:
                    added_pax = max(10, int(round(r_data["total_capacity"] * 0.40)))
                new_pax = base_pax + added_pax
                r_data["total_passengers"] = new_pax

                if r_data["total_capacity"] > 0:
                    r_data["load_factor"] = round(new_pax / r_data["total_capacity"], 4)
                    r_data["status"] = classify_load_factor(r_data["load_factor"])
                    r_data["available_seats"] = max(0, r_data["total_capacity"] - new_pax)

                # Proportionately update buses on this route
                for b_id, b_data in sim_buses.items():
                    if b_data["route_id"] == r_id and b_data.get("is_operational", True):
                        base_b_pax = b_data["passengers"]
                        added_b_pax = (
                            int(round(base_b_pax * (spike_pct / 100.0)))
                            if base_b_pax > 0
                            else int(round(b_data["capacity"] * (spike_pct / 100.0) * 0.4))
                        )
                        b_data["passengers"] = base_b_pax + added_b_pax
                        b_data["load_factor"] = (
                            round(b_data["passengers"] / b_data["capacity"], 4)
                            if b_data["capacity"] > 0
                            else 0.0
                        )

            executive_summary = (
                f"Simulated passenger surge of +{spike_pct:.0f}% elevates passenger loading across targeted corridors. "
                f"Evaluates network buffering headroom under acute congestion."
            )

        elif dtype == "SERVICE_DELAY":
            delay_mins = request.delay_minutes if request.delay_minutes is not None else 20.0
            if delay_mins < 1.0 or delay_mins > 240.0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="delay_minutes must be between 1.0 and 240.0 minutes.",
                )
            resolved_params["delay_minutes"] = delay_mins

            is_all_corridors = (
                (not request.route_id)
                and (not request.route_number or str(request.route_number).strip().upper() == "ALL")
                and (not request.bus_id)
                and (not request.bus_number or not str(request.bus_number).strip())
            )

            if not is_all_corridors:
                if request.route_id or (request.route_number and str(request.route_number).strip().upper() != "ALL"):
                    target_route_id, target_route = cls._resolve_route(routes, request.route_id, request.route_number)
                    resolved_params["route_id"] = target_route.id
                    resolved_params["route_number"] = target_route.route_number
                    target_routes_to_delay = [target_route.id]
                    summary_headline = f"Traffic Delay: {delay_mins:.0f} Minutes on Route {target_route.route_number}"
                elif request.bus_id or request.bus_number:
                    _, target_bus = cls._resolve_bus(all_buses, request.bus_id, request.bus_number)
                    resolved_params["bus_id"] = target_bus.id
                    resolved_params["bus_number"] = target_bus.bus_number
                    target_routes_to_delay = [target_bus.current_route_id] if target_bus.current_route_id else []
                    summary_headline = f"Vehicle Delay: {delay_mins:.0f} Minutes on Bus {target_bus.bus_number}"
                else:
                    target_routes_to_delay = list(sim_routes.keys())
                    summary_headline = f"Network-Wide Arterial Delay: {delay_mins:.0f} Minutes"
            else:
                target_routes_to_delay = list(sim_routes.keys())
                summary_headline = f"Network-Wide Arterial Delay: {delay_mins:.0f} Minutes"

            # Headway expansion and passenger accumulation formula
            # Delay causes passengers to accumulate at bus stops over time (+8% per 10 mins delay, capped at +60%)
            demand_multiplier = 1.0 + min(0.60, (delay_mins / 10.0) * 0.08)
            # Effective throughput capacity drops due to longer cycle times (-5% per 10 mins delay, capped at -35%)
            capacity_multiplier = max(0.65, 1.0 - (delay_mins / 10.0) * 0.05)

            for r_id in target_routes_to_delay:
                r_data = sim_routes[r_id]
                base_pax = r_data["total_passengers"]
                new_pax = int(round(base_pax * demand_multiplier))
                r_data["total_passengers"] = new_pax

                base_cap = r_data["total_capacity"]
                effective_cap = int(round(base_cap * capacity_multiplier))
                r_data["total_capacity"] = effective_cap

                if effective_cap > 0:
                    r_data["load_factor"] = round(new_pax / effective_cap, 4)
                    r_data["status"] = classify_load_factor(r_data["load_factor"])
                    r_data["available_seats"] = max(0, effective_cap - new_pax)

                # Update buses on this delayed route
                for b_id, b_data in sim_buses.items():
                    if b_data["route_id"] == r_id and b_data.get("is_operational", True):
                        b_pax = int(round(b_data["passengers"] * demand_multiplier))
                        b_cap = max(1, int(round(b_data["capacity"] * capacity_multiplier)))
                        b_data["passengers"] = b_pax
                        b_data["load_factor"] = round(b_pax / b_cap, 4) if b_cap > 0 else 0.0
                        if b_data["status"] not in ("BROKEN_DOWN", "STRANDED_ON_CLOSED_ROUTE"):
                            b_data["status"] = "DELAYED"

            if "bus_id" in resolved_params:
                d_bus = sim_buses.get(resolved_params["bus_id"])
                if d_bus and d_bus["status"] not in ("BROKEN_DOWN", "STRANDED_ON_CLOSED_ROUTE"):
                    d_bus["status"] = "DELAYED"

            executive_summary = (
                f"Simulated {delay_mins:.0f}-minute delay models headway expansion and stop queuing. "
                f"Passenger demand accumulated by {(demand_multiplier - 1.0) * 100:.1f}%, while effective turnaround capacity degraded by {(1.0 - capacity_multiplier) * 100:.1f}%."
            )

        # 4. Generate Comparative Entity Summaries
        affected_routes_list: List[RouteImpactSummary] = []
        for r_id, b_route in baseline_routes.items():
            s_route = sim_routes[r_id]
            is_direct = (
                r_id == resolved_params.get("route_id")
                or (dtype == "BUS_BREAKDOWN" and sim_buses.get(resolved_params.get("bus_id", -1), {}).get("route_id") == r_id)
                or (dtype == "SERVICE_DELAY" and sim_buses.get(resolved_params.get("bus_id", -1), {}).get("route_id") == r_id)
                or (dtype in ("DEMAND_SPIKE", "SERVICE_DELAY") and "route_id" not in resolved_params and "bus_id" not in resolved_params)
            )

            # Severity change classification
            if s_route["status"] == "CLOSED":
                sev_change = "CLOSED"
            elif s_route["load_factor"] > b_route["load_factor"] + 0.15:
                sev_change = "SEVERELY_DEGRADED"
            elif s_route["load_factor"] > b_route["load_factor"] + 0.02 or s_route["total_capacity"] < b_route["total_capacity"]:
                sev_change = "DEGRADED"
            else:
                sev_change = "UNCHANGED"

            assessment_text = cls._generate_scenario_route_assessment(b_route, s_route)

            affected_routes_list.append(
                RouteImpactSummary(
                    route_id=r_id,
                    route_number=b_route["route_number"],
                    name=b_route["name"],
                    status_before=b_route["status"],
                    status_after=s_route["status"],
                    load_factor_before=b_route["load_factor"],
                    load_factor_after=s_route["load_factor"],
                    passengers_before=b_route["total_passengers"],
                    passengers_after=s_route["total_passengers"],
                    capacity_before=b_route["total_capacity"],
                    capacity_after=s_route["total_capacity"],
                    available_seats_before=b_route["available_seats"],
                    available_seats_after=s_route["available_seats"],
                    buses_count_before=b_route["buses_count"],
                    buses_count_after=s_route["buses_count"],
                    is_directly_affected=is_direct,
                    severity_change=sev_change,
                    assessment=assessment_text,
                )
            )

        affected_buses_list: List[BusImpactSummary] = []
        for b_id, b_bus in baseline_buses.items():
            s_bus = sim_buses[b_id]
            is_op = s_bus.get("is_operational", True) and s_bus["status"] in ("ACTIVE", "IDLE", "DELAYED")

            note = "Operating normally."
            if s_bus["status"] == "BROKEN_DOWN":
                note = "Vehicle disabled due to simulated breakdown."
            elif s_bus["status"] == "STRANDED_ON_CLOSED_ROUTE":
                note = "Vehicle stranded due to route closure; unable to service stops."
            elif s_bus["status"] == "DELAYED":
                delay_str = f" ({resolved_params.get('delay_minutes', 0):.0f}m)" if 'delay_minutes' in resolved_params else ""
                note = f"Vehicle impacted by simulated delay{delay_str}; headway expanded."

            affected_buses_list.append(
                BusImpactSummary(
                    bus_id=b_id,
                    bus_number=b_bus["bus_number"],
                    route_id=b_bus["route_id"],
                    route_number=b_bus["route_number"],
                    status_before=b_bus["status"],
                    status_after=s_bus["status"],
                    is_operational_after=is_op,
                    passenger_count_before=b_bus["passengers"],
                    passenger_count_after=s_bus["passengers"],
                    capacity=b_bus["capacity"],
                    load_factor_before=b_bus["load_factor"],
                    load_factor_after=s_bus["load_factor"],
                    impact_note=note,
                )
            )

        # 5. Calculate Comprehensive Resilience Metrics
        baseline_total_cap = sum(r["total_capacity"] for r in baseline_routes.values())
        sim_total_cap = sum(r["total_capacity"] for r in sim_routes.values())
        cap_lost = max(0, baseline_total_cap - sim_total_cap)
        cap_retention_pct = round((sim_total_cap / baseline_total_cap * 100.0), 1) if baseline_total_cap > 0 else 0.0
        cap_loss_pct = round((cap_lost / baseline_total_cap * 100.0), 1) if baseline_total_cap > 0 else 0.0

        baseline_active_buses = len([b for b in baseline_buses.values() if b["status"] != "INACTIVE"])
        sim_active_buses = len([b for b in affected_buses_list if b.is_operational_after])
        fleet_avail_pct = round((sim_active_buses / baseline_active_buses * 100.0), 1) if baseline_active_buses > 0 else 0.0

        baseline_op_routes = len([r for r in baseline_routes.values() if r["status"] != "NO_SERVICE"])
        sim_op_routes = len([r for r in sim_routes.values() if r["status"] not in ("CLOSED", "NO_SERVICE")])
        service_continuity_pct = round((sim_op_routes / baseline_op_routes * 100.0), 1) if baseline_op_routes > 0 else 0.0

        crit_count = sum(1 for r in sim_routes.values() if r["status"] == "CRITICAL")
        high_count = sum(1 for r in sim_routes.values() if r["status"] == "HIGH")
        overloaded_ratio = (crit_count + high_count) / max(1, len(sim_routes))

        rem_available_cap = sum(r["available_seats"] for r in sim_routes.values())
        routes_affected_count = sum(1 for r in affected_routes_list if r.severity_change != "UNCHANGED" or r.is_directly_affected)

        # Composite resilience formula (0.0 to 100.0)
        # Weights: Capacity Retention (40%), Fleet Availability (30%), Route Continuity (20%), Overload Penalty (10%)
        overload_score_component = max(0.0, 1.0 - overloaded_ratio) * 100.0
        composite_resilience = (
            (0.40 * cap_retention_pct)
            + (0.30 * fleet_avail_pct)
            + (0.20 * service_continuity_pct)
            + (0.10 * overload_score_component)
        )
        composite_resilience = round(max(0.0, min(100.0, composite_resilience)), 1)

        if composite_resilience >= 85.0:
            rating = "EXCELLENT"
        elif composite_resilience >= 70.0:
            rating = "ADEQUATE"
        elif composite_resilience >= 50.0:
            rating = "VULNERABLE"
        else:
            rating = "CRITICAL"

        resilience = ResilienceMetrics(
            fleet_availability_pct=fleet_avail_pct,
            capacity_retention_pct=cap_retention_pct,
            capacity_lost=cap_lost,
            capacity_loss_pct=cap_loss_pct,
            service_continuity_pct=service_continuity_pct,
            routes_affected_count=routes_affected_count,
            routes_critical_count=crit_count,
            routes_high_count=high_count,
            remaining_available_capacity=rem_available_cap,
            resilience_score=composite_resilience,
            resilience_rating=rating,
        )

        # 6. Generate Operational Warnings and Safety Alerts
        warnings_list: List[str] = []
        if dtype == "BUS_BREAKDOWN":
            warnings_list.append(f"Vehicle Bus {target_bus.bus_number} disabled; removed from active corridor service.")
            route_id = target_bus.current_route_id
            if route_id and route_id in sim_routes:
                r_sim = sim_routes[route_id]
                if r_sim["status"] == "CRITICAL":
                    warnings_list.append(
                        f"Overcrowding alert: Route {r_sim['route_number']} projected at {r_sim['load_factor']*100:.1f}% load factor (CRITICAL)."
                    )
                if r_sim["buses_count"] == 0:
                    warnings_list.append(
                        f"Service warning: Route {r_sim['route_number']} has 0 active buses remaining in service."
                    )
        elif dtype == "ROUTE_CLOSURE":
            warnings_list.append(f"Corridor Route {target_route.route_number} is completely closed; all corridor stops suspended.")
            stranded_count = sum(1 for b in affected_buses_list if b.status_after == "STRANDED_ON_CLOSED_ROUTE")
            if stranded_count > 0:
                warnings_list.append(f"{stranded_count} transit vehicle(s) stranded on closed corridor and unavailable for dispatch.")
            warnings_list.append(f"{baseline_routes[target_route.id]['total_capacity']} passenger seats eliminated from network.")
        elif dtype == "DEMAND_SPIKE":
            for r in affected_routes_list:
                if r.status_after == "CRITICAL":
                    warnings_list.append(
                        f"Critical surge alert: Route {r.route_number} load escalated to {r.load_factor_after*100:.1f}% (CRITICAL, {r.passengers_after} passengers)."
                    )
                elif r.status_after == "HIGH" and r.status_before not in ("HIGH", "CRITICAL"):
                    warnings_list.append(
                        f"High congestion alert: Route {r.route_number} reached {r.load_factor_after*100:.1f}% load factor."
                    )
        elif dtype == "SERVICE_DELAY":
            warnings_list.append(
                f"Headway expanded by {delay_mins:.0f} minutes; stop queue demand accumulated by +{(demand_multiplier - 1.0) * 100:.1f}%."
            )
            for r in affected_routes_list:
                if r.status_after == "CRITICAL":
                    warnings_list.append(
                        f"Delay severe impact: Route {r.route_number} operating at {r.load_factor_after*100:.1f}% (CRITICAL)."
                    )

        # 7. Generate Simulated Reallocation Recommendations (Stage 5 adapted)
        simulated_recommendations = cls._generate_simulated_reallocations(
            db=db,
            sim_routes=sim_routes,
            sim_buses=sim_buses,
            all_buses=all_buses,
        )

        # 8. Package and cache scenario
        scenario_id = f"SCEN-{dtype}-{uuid.uuid4().hex[:8].upper()}"
        now_utc = datetime.now(timezone.utc)

        response = DisruptionSimulationResponse(
            scenario_id=scenario_id,
            disruption_type=raw_type,
            parameters=resolved_params,
            simulated_at=now_utc,
            summary_headline=summary_headline,
            executive_summary=executive_summary,
            resilience_metrics=resilience,
            affected_routes=affected_routes_list,
            affected_buses=affected_buses_list,
            suggested_reallocations=simulated_recommendations,
            warnings=warnings_list,
            notes=resolved_params.get("notes"),
            is_simulated=True,
        )

        # Store in LRU cache
        _SCENARIO_CACHE[scenario_id] = response
        if len(_SCENARIO_CACHE) > MAX_CACHED_SCENARIOS:
            _SCENARIO_CACHE.popitem(last=False)

        return response

    @classmethod
    def clear_cache(cls) -> None:
        """Clear all cached simulated scenarios."""
        _SCENARIO_CACHE.clear()

    @classmethod
    def _resolve_bus(
        cls, buses: List[Bus], bus_id: Optional[int], bus_number: Optional[str]
    ) -> Tuple[int, Bus]:
        """Validate and resolve target bus by ID or bus number."""
        if bus_id is not None and bus_id <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid bus_id '{bus_id}'. Bus ID must be a positive integer.",
            )
        if bus_id is None and (bus_number is None or not str(bus_number).strip()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Target bus must be specified using bus_id or bus_number.",
            )
        target = None
        if bus_id is not None:
            target = next((b for b in buses if b.id == bus_id), None)
        elif bus_number is not None:
            clean_num = bus_number.strip().upper()
            target = next((b for b in buses if b.bus_number.upper() == clean_num), None)

        if not target:
            identifier = f"ID '{bus_id}'" if bus_id is not None else f"number '{bus_number}'"
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Bus with {identifier} not found in fleet.",
            )
        return target.id, target

    @classmethod
    def _resolve_route(
        cls, routes: List[Route], route_id: Optional[int], route_number: Optional[str]
    ) -> Tuple[int, Route]:
        """Validate and resolve target route by ID or route number."""
        if route_id is not None and route_id <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid route_id '{route_id}'. Route ID must be a positive integer.",
            )
        if route_id is None and (route_number is None or not str(route_number).strip()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Target route must be specified using route_id or route_number.",
            )
        target = None
        if route_id is not None:
            target = next((r for r in routes if r.id == route_id), None)
        elif route_number is not None:
            clean_num = route_number.strip().upper()
            target = next((r for r in routes if r.route_number.upper() == clean_num), None)

        if not target:
            identifier = f"ID '{route_id}'" if route_id is not None else f"number '{route_number}'"
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Route with {identifier} not found in transit network.",
            )
        return target.id, target

    @classmethod
    def _generate_scenario_route_assessment(
        cls, b_route: Dict[str, Any], s_route: Dict[str, Any]
    ) -> str:
        """Generate human-readable comparative assessment text for a route."""
        if s_route["status"] == "CLOSED":
            return f"Corridor closed. All service discontinued; {b_route['total_capacity']} capacity eliminated."

        lf_before_pct = round(b_route["load_factor"] * 100, 1)
        lf_after_pct = round(s_route["load_factor"] * 100, 1)
        delta_pct = round(lf_after_pct - lf_before_pct, 1)

        if s_route["status"] == "CRITICAL" and b_route["status"] != "CRITICAL":
            return (
                f"Disruption pushed route into CRITICAL overcrowding: load factor surged from {lf_before_pct}% to {lf_after_pct}% "
                f"(+{delta_pct}%). Urgent relief required."
            )
        elif delta_pct > 0:
            return (
                f"Service degraded: load factor increased from {lf_before_pct}% to {lf_after_pct}% (+{delta_pct}%). "
                f"{s_route['available_seats']} seats remaining."
            )
        else:
            return f"Route operating with stable load factor at {lf_after_pct}% ({s_route['status']})."

    @classmethod
    def _generate_simulated_reallocations(
        cls,
        db: Session,
        sim_routes: Dict[int, Dict[str, Any]],
        sim_buses: Dict[int, Dict[str, Any]],
        all_buses: List[Bus],
    ) -> List[ReallocationRecommendationResponse]:
        """Adapt Stage 5 rule-based reallocation logic to simulated corridor states."""
        # Find overloaded target routes in scenario (HIGH or CRITICAL)
        overloaded_targets = [
            r for r in sim_routes.values() if r["status"] in ("HIGH", "CRITICAL")
        ]
        # Find underutilized donor routes in scenario (LOW, operational, or load factor < 0.50)
        underutilized_donors = [
            r for r in sim_routes.values()
            if (r["status"] == "LOW" or r["load_factor"] < 0.50) and r["buses_count"] >= 1
        ]

        if not overloaded_targets or not underutilized_donors:
            return []

        sim_recommendations: List[ReallocationRecommendationResponse] = []
        db_buses_map = {b.id: b for b in all_buses}

        for target in overloaded_targets:
            for donor in underutilized_donors:
                # Target and donor must not be the same corridor
                if target["route_id"] == donor["route_id"]:
                    continue

                # Find candidate buses on donor route that remain operational
                candidate_buses = [
                    b
                    for b in sim_buses.values()
                    if b["route_id"] == donor["route_id"]
                    and b.get("is_operational", True)
                    and b["status"] in ("ACTIVE", "IDLE")
                ]

                for c_bus in candidate_buses:
                    target_lf = target["load_factor"]
                    source_lf = donor["load_factor"]

                    target_score = calculate_target_severity_score(target_lf, target["status"])
                    source_score = calculate_source_spare_score(source_lf, donor["buses_count"])
                    bus_score = calculate_bus_suitability_score(
                        passenger_count=c_bus["passengers"],
                        capacity=c_bus["capacity"],
                        available_seats=max(0, c_bus["capacity"] - c_bus["passengers"]),
                    )
                    # Baseline neutral proximity score for in-memory scenario
                    prox_score = 7.5

                    comp_score = round(target_score + source_score + bus_score + prox_score, 1)
                    comp_score = max(0.0, min(100.0, comp_score))
                    priority = determine_priority(comp_score, target["status"])

                    # Feasibility
                    limitations = [
                        f"Simulated advisory proposal to mitigate {target['status']} status on Route {target['route_number']}."
                    ]
                    feasibility = "FEASIBLE"
                    if donor["buses_count"] <= 1:
                        feasibility = "CONDITIONALLY_FEASIBLE"
                        limitations.append(
                            f"Source Route {donor['route_number']} has only 1 active vehicle; reallocating will leave corridor without active service."
                        )
                    if c_bus["passengers"] > 0:
                        feasibility = "CONDITIONALLY_FEASIBLE"
                        limitations.append(f"Candidate Bus {c_bus['bus_number']} has {c_bus['passengers']} passengers on board.")

                    # Post-reallocation projections
                    proj_target_lf = round(
                        target["total_passengers"] / (target["total_capacity"] + c_bus["capacity"]), 4
                    )
                    rem_donor_cap = donor["total_capacity"] - c_bus["capacity"]
                    proj_donor_lf = round(donor["total_passengers"] / rem_donor_cap, 4) if rem_donor_cap > 0 else 1.0

                    rec_id = f"SIM-REC-{target['route_number']}-{donor['route_number']}-{c_bus['bus_number']}"

                    reason_text = (
                        f"Simulated mitigation: Target Route {target['route_number']} is {target['status']} "
                        f"(Load: {target_lf * 100:.1f}%). Reallocating candidate Bus {c_bus['bus_number']} from "
                        f"underutilized Route {donor['route_number']} ({source_lf * 100:.1f}%) would reduce target load factor to {proj_target_lf * 100:.1f}%."
                    )

                    sim_recommendations.append(
                        ReallocationRecommendationResponse(
                            id=rec_id,
                            source_route_id=donor["route_id"],
                            source_route_number=donor["route_number"],
                            source_route_name=donor["name"],
                            source_route_load_factor=source_lf,
                            source_route_status=donor["status"],
                            source_route=RouteBrief(
                                route_id=donor["route_id"],
                                route_number=donor["route_number"],
                                name=donor["name"],
                                load_factor=source_lf,
                                status=donor["status"],
                            ),
                            target_route_id=target["route_id"],
                            target_route_number=target["route_number"],
                            target_route_name=target["name"],
                            target_route_load_factor=target_lf,
                            target_route_status=target["status"],
                            target_route=RouteBrief(
                                route_id=target["route_id"],
                                route_number=target["route_number"],
                                name=target["name"],
                                load_factor=target_lf,
                                status=target["status"],
                            ),
                            candidate_bus_id=c_bus["bus_id"],
                            candidate_bus_number=c_bus["bus_number"],
                            bus_capacity=c_bus["capacity"],
                            current_occupancy=c_bus["passengers"],
                            available_capacity=max(0, c_bus["capacity"] - c_bus["passengers"]),
                            bus_load_factor=c_bus["load_factor"],
                            candidate_bus=BusBrief(
                                bus_id=c_bus["bus_id"],
                                bus_number=c_bus["bus_number"],
                                capacity=c_bus["capacity"],
                                current_occupancy=c_bus["passengers"],
                                available_capacity=max(0, c_bus["capacity"] - c_bus["passengers"]),
                                load_factor=c_bus["load_factor"],
                            ),
                            distance_meters=None,
                            estimated_travel_time_minutes=None,
                            projected_target_load_factor=proj_target_lf,
                            projected_source_load_factor=proj_donor_lf,
                            score=comp_score,
                            priority=priority,
                            feasibility_status=feasibility,
                            limitations=limitations,
                            reason=reason_text,
                            is_advisory=True,
                            advisory_note="Simulated scenario recommendation only. No vehicle dispatch performed.",
                        )
                    )

        # Sort recommendations by score descending
        sim_recommendations.sort(key=lambda r: (-r.score, -r.target_route_load_factor))
        return sim_recommendations[:5]
