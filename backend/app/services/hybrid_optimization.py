"""Hybrid Intelligent Fleet Optimization Engine for TRANSIGHT (Phases 1, 2, 5, 6).

Combines deterministic rule-based candidate generation with Google OR-Tools CP-SAT
mathematical constraint programming to solve network-wide fleet reallocation.
Incorporates real-time weather travel penalties, breakdown vehicle exclusions,
minimum service coverage constraints, and produces explainable before-and-after impact metrics.
"""
import math
import uuid
import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy.orm import Session
from ortools.sat.python import cp_model

from app.models.bus import Bus
from app.models.route import Route
from app.models.stop import Stop
from app.models.bus_position import BusPosition
from app.models.passenger_load import PassengerLoad
from app.models.bus_breakdown import BusBreakdown
from app.models.reallocation_review import ReallocationReview
from app.models.reallocation_execution import ReallocationExecution
from app.models.optimization_plan import OptimizationPlan
from app.services.load_intelligence import LoadIntelligenceService
from app.services.weather import WeatherService
from app.simulator.route_simulator import calculate_distance_meters
from app.schemas.hybrid_optimization import (
    OptimizationRunRequest,
    OptimizationAllocationItem,
    NetworkMetricsSnapshot,
    OptimizationPlanResponse,
    ScenarioEvaluationRequest,
    ScenarioEvaluationResponse,
)

logger = logging.getLogger("smartbus.hybrid_optimization")

NOMINAL_DEADHEAD_SPEED_KMH = 30.0


class CandidateReallocation:
    """Internal candidate representation passed to the CP-SAT solver."""

    def __init__(
        self,
        candidate_id: str,
        bus_id: int,
        bus_number: str,
        source_route_id: int,
        source_route_number: str,
        target_route_id: int,
        target_route_number: str,
        bus_capacity: int,
        current_occupancy: int,
        available_seats: int,
        distance_meters: float,
        nominal_travel_time_min: float,
        weather_travel_time_min: float,
        utility_score: float,
        priority: str,
        explanation: str,
    ):
        self.candidate_id = candidate_id
        self.bus_id = bus_id
        self.bus_number = bus_number
        self.source_route_id = source_route_id
        self.source_route_number = source_route_number
        self.target_route_id = target_route_id
        self.target_route_number = target_route_number
        self.bus_capacity = bus_capacity
        self.current_occupancy = current_occupancy
        self.available_seats = available_seats
        self.distance_meters = distance_meters
        self.nominal_travel_time_min = nominal_travel_time_min
        self.weather_travel_time_min = weather_travel_time_min
        self.utility_score = utility_score
        self.priority = priority
        self.explanation = explanation


class HybridOptimizationEngine:
    """Hybrid Optimization Engine combining deterministic rules and Google OR-Tools CP-SAT."""

    @classmethod
    def calculate_network_snapshot(
        cls,
        route_intel_list: List[Any],
        bus_intel_list: List[Any],
        broken_bus_ids: set,
    ) -> NetworkMetricsSnapshot:
        """Compute comprehensive network performance metrics snapshot."""
        overloaded_routes: List[str] = []
        underutilized_routes: List[str] = []
        routes_below_coverage = 0
        total_pax = 0
        total_cap = 0
        unmet_demand_proxy = 0

        for r in route_intel_list:
            r_buses = [b for b in bus_intel_list if b.route_id == r.route_id and b.bus_id not in broken_bus_ids]
            op_buses_count = len(r_buses)

            if op_buses_count == 0:
                routes_below_coverage += 1

            if r.load_factor >= 0.80 or r.status in ("HIGH", "CRITICAL"):
                overloaded_routes.append(r.route_number)
                # Unmet demand proxy: passengers exceeding nominal 75% comfortable capacity
                comfort_cap = int(r.total_capacity * 0.75)
                if r.total_passengers > comfort_cap:
                    unmet_demand_proxy += (r.total_passengers - comfort_cap)
            elif r.load_factor < 0.50:
                underutilized_routes.append(r.route_number)

            total_pax += r.total_passengers
            total_cap += r.total_capacity

        fleet_lf = round(total_pax / total_cap, 4) if total_cap > 0 else 0.0
        operational_buses = sum(1 for b in bus_intel_list if b.bus_id not in broken_bus_ids)
        unavailable_buses = len(broken_bus_ids)

        return NetworkMetricsSnapshot(
            overloaded_routes_count=len(overloaded_routes),
            overloaded_route_numbers=sorted(overloaded_routes),
            underutilized_routes_count=len(underutilized_routes),
            underutilized_route_numbers=sorted(underutilized_routes),
            total_passengers=total_pax,
            total_capacity=total_cap,
            fleet_load_factor=fleet_lf,
            total_unmet_demand_proxy=unmet_demand_proxy,
            routes_below_minimum_coverage=routes_below_coverage,
            operational_buses_count=operational_buses,
            unavailable_buses_count=unavailable_buses,
        )

    @classmethod
    def generate_candidate_pool(
        cls,
        db: Session,
        route_intel_list: List[Any],
        bus_intel_list: List[Any],
        weather_obs: Any,
        broken_bus_ids: set,
    ) -> Tuple[List[CandidateReallocation], List[str]]:
        """Phase 2 Candidate Generation: Filter feasible donor buses and target deficits."""
        candidates: List[CandidateReallocation] = []
        binding_constraints: List[str] = []

        all_db_buses = {b.id: b for b in db.query(Bus).all()}

        # Active recent transfers in progress (last 5 minutes)
        active_transfer_bus_ids = set()
        try:
            recent_execs = (
                db.query(ReallocationExecution)
                .filter(ReallocationExecution.status.in_(("IN_PROGRESS", "EXECUTED")))
                .all()
            )
            now_utc = datetime.now(timezone.utc)
            for ex in recent_execs:
                if ex.created_at:
                    tz = ex.created_at.tzinfo or timezone.utc
                    if (now_utc - ex.created_at.replace(tzinfo=tz)).total_seconds() < 240:
                        active_transfer_bus_ids.add(ex.bus_id)
        except Exception:
            pass

        # 1. Identify overloaded target routes
        target_routes = [
            r for r in route_intel_list
            if r.status in ("HIGH", "CRITICAL") or r.load_factor >= 0.80
        ]
        if not target_routes:
            binding_constraints.append("No transit corridors are currently overloaded (all route load factors < 80%).")
            return candidates, binding_constraints

        # 2. Identify potential source donor routes
        source_routes = [
            r for r in route_intel_list
            if r.status == "LOW" or (r.number_of_buses > 1 and r.load_factor < 0.75)
        ]
        if not source_routes:
            binding_constraints.append("No underutilized corridors or routes with surplus fleet depth are available.")
            return candidates, binding_constraints

        # Group buses by route
        buses_by_route: Dict[int, List[Any]] = {}
        for b in bus_intel_list:
            if b.route_id is not None:
                buses_by_route.setdefault(b.route_id, []).append(b)

        # Pre-fetch origin stops
        origin_stops: Dict[int, Optional[Stop]] = {}
        for target in target_routes:
            origin_stops[target.route_id] = (
                db.query(Stop)
                .filter(Stop.route_id == target.route_id)
                .order_by(Stop.sequence_order.asc())
                .first()
            )

        speed_factor = getattr(weather_obs, "speed_factor", 1.0) or 1.0
        effective_speed = max(15.0, NOMINAL_DEADHEAD_SPEED_KMH * speed_factor)

        # Evaluate pairs
        for target in target_routes:
            target_stop = origin_stops.get(target.route_id)

            for source in source_routes:
                if source.route_id == target.route_id:
                    continue

                source_buses = buses_by_route.get(source.route_id, [])

                # Hard constraint: donor route must maintain minimum service coverage (>= 1 bus)
                operational_donor_buses = [
                    b for b in source_buses
                    if b.bus_id not in broken_bus_ids
                    and b.bus_id not in active_transfer_bus_ids
                    and all_db_buses.get(b.bus_id, Bus()).status in ("ACTIVE", "IDLE", "IN_SERVICE")
                ]

                if len(operational_donor_buses) <= 1:
                    binding_constraints.append(
                        f"Route {source.route_number} has only {len(operational_donor_buses)} active bus(es); "
                        f"reallocation rejected by Minimum Service Coverage Rule."
                    )
                    continue

                for b_intel in operational_donor_buses:
                    # Filter 1: Crowded buses cannot be transferred
                    if b_intel.load_factor >= 0.80 or b_intel.available_seats <= 0:
                        continue

                    # Filter 2: Source preservation constraint
                    rem_cap = source.total_capacity - b_intel.capacity
                    rem_pax = max(0, source.total_passengers - b_intel.passenger_count)
                    if rem_cap <= 0:
                        continue
                    if rem_pax > rem_cap or (source.total_passengers / rem_cap) > 1.00:
                        continue

                    # Distance & Weather-adjusted Travel Time
                    distance_meters = 2500.0  # default 2.5km
                    latest_pos = (
                        db.query(BusPosition)
                        .filter(BusPosition.bus_id == b_intel.bus_id)
                        .order_by(BusPosition.timestamp.desc(), BusPosition.id.desc())
                        .first()
                    )
                    if latest_pos and latest_pos.latitude and target_stop and target_stop.latitude:
                        distance_meters = round(
                            calculate_distance_meters(
                                latest_pos.latitude, latest_pos.longitude,
                                target_stop.latitude, target_stop.longitude
                            ), 1
                        )

                    dist_km = distance_meters / 1000.0
                    nom_time = round((dist_km / NOMINAL_DEADHEAD_SPEED_KMH) * 60.0, 1)
                    weather_time = round((dist_km / effective_speed) * 60.0, 1)

                    # Explainable Scoring Formula
                    # 1. Target relief score (0 to 35 pts)
                    if target.load_factor >= 1.00:
                        relief_score = 30.0 + min(5.0, (target.load_factor - 1.0) * 10.0)
                    else:
                        relief_score = 20.0 + ((target.load_factor - 0.80) / 0.20) * 10.0

                    # 2. Source spare score (0 to 25 pts)
                    headroom = max(0.0, min(1.0, 1.0 - (source.load_factor / 0.50))) * 20.0
                    fleet_depth = 5.0 if len(operational_donor_buses) > 1 else 0.0
                    spare_score = headroom + fleet_depth

                    # 3. Bus suitability score (0 to 20 pts)
                    occ_score = (1.0 - b_intel.load_factor) * 12.0
                    cap_score = min(8.0, (b_intel.available_seats / 60.0) * 8.0)
                    suitability_score = occ_score + cap_score

                    # 4. Distance penalty (0 to 15 pts)
                    dist_penalty = min(15.0, max(0.0, (dist_km / 8.0) * 15.0))

                    # 5. Weather penalty (0 to 10 pts)
                    weather_multiplier = getattr(weather_obs, "travel_time_multiplier", 1.0) or 1.0
                    weather_penalty = min(10.0, (weather_multiplier - 1.0) * 12.0)

                    # 6. Fleet churn friction (5 pts)
                    churn_penalty = 5.0

                    utility = round(
                        relief_score + spare_score + suitability_score - dist_penalty - weather_penalty - churn_penalty,
                        2
                    )

                    priority = "HIGH" if utility >= 60.0 else ("MEDIUM" if utility >= 40.0 else "LOW")

                    cid = f"OPT-{source.route_number}-{target.route_number}-{b_intel.bus_number}"
                    weather_note = (
                        f" Weather penalty: +{round((weather_time - nom_time), 1)} min transfer delay ({weather_obs.condition})."
                        if weather_time > nom_time else ""
                    )
                    explanation = (
                        f"Reallocate Bus {b_intel.bus_number} ({b_intel.available_seats} seats free) "
                        f"from Route {source.route_number} ({round(source.load_factor * 100, 1)}% LF) "
                        f"to Route {target.route_number} ({round(target.load_factor * 100, 1)}% LF). "
                        f"Deadhead distance: {round(dist_km, 2)} km (est. {weather_time} min).{weather_note}"
                    )

                    candidate = CandidateReallocation(
                        candidate_id=cid,
                        bus_id=b_intel.bus_id,
                        bus_number=b_intel.bus_number,
                        source_route_id=source.route_id,
                        source_route_number=source.route_number,
                        target_route_id=target.route_id,
                        target_route_number=target.route_number,
                        bus_capacity=b_intel.capacity,
                        current_occupancy=b_intel.passenger_count,
                        available_seats=b_intel.available_seats,
                        distance_meters=distance_meters,
                        nominal_travel_time_min=nom_time,
                        weather_travel_time_min=weather_time,
                        utility_score=utility,
                        priority=priority,
                        explanation=explanation,
                    )
                    candidates.append(candidate)

        return candidates, binding_constraints

    @classmethod
    def solve_hybrid_optimization(
        cls,
        candidates: List[CandidateReallocation],
        route_intel_list: List[Any],
        max_reallocations: int = 4,
    ) -> Tuple[List[CandidateReallocation], str, float, float]:
        """Phase 2 CP-SAT Mixed-Integer Mathematical Optimization Formulation."""
        if not candidates:
            return [], "NO_CANDIDATES", 0.0, 0.0

        model = cp_model.CpModel()

        # Decision variables: x_c in {0, 1}
        x_vars: Dict[str, cp_model.IntVar] = {}
        for c in candidates:
            x_vars[c.candidate_id] = model.NewBoolVar(f"x_{c.candidate_id}")

        # Constraint 1: Bus assignment uniqueness (each bus reallocated to at most 1 route)
        buses_map: Dict[int, List[CandidateReallocation]] = {}
        for c in candidates:
            buses_map.setdefault(c.bus_id, []).append(c)

        for b_id, c_list in buses_map.items():
            model.Add(sum(x_vars[c.candidate_id] for c in c_list) <= 1)

        # Constraint 2: Donor route minimum coverage preservation
        # Number of buses taken from source route cannot exceed (num_buses - 1)
        sources_map: Dict[int, List[CandidateReallocation]] = {}
        for c in candidates:
            sources_map.setdefault(c.source_route_id, []).append(c)

        for s_id, c_list in sources_map.items():
            matched_r = next((r for r in route_intel_list if r.route_id == s_id), None)
            num_buses = matched_r.number_of_buses if matched_r else 2
            max_donations = max(0, num_buses - 1)
            model.Add(sum(x_vars[c.candidate_id] for c in c_list) <= max_donations)

        # Constraint 3: Target route saturation bound (at most 2 incoming buses per target route)
        targets_map: Dict[int, List[CandidateReallocation]] = {}
        for c in candidates:
            targets_map.setdefault(c.target_route_id, []).append(c)

        for t_id, c_list in targets_map.items():
            model.Add(sum(x_vars[c.candidate_id] for c in c_list) <= 2)

        # Constraint 4: Global reallocation budget bound
        model.Add(sum(x_vars[c.candidate_id] for c in candidates) <= max_reallocations)

        # Objective Function: Maximize sum of utility scores (scaled to integer)
        objective_terms = []
        for c in candidates:
            scaled_utility = int(round(c.utility_score * 100))
            objective_terms.append(scaled_utility * x_vars[c.candidate_id])

        model.Maximize(sum(objective_terms))

        # Solve CP-SAT
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 4.0
        start_time = datetime.now()
        status_code = solver.Solve(model)
        solve_duration_ms = round((datetime.now() - start_time).total_seconds() * 1000.0, 1)

        selected_candidates: List[CandidateReallocation] = []
        status_name = "FEASIBLE"

        if status_code == cp_model.OPTIMAL:
            status_name = "OPTIMAL"
            for c in candidates:
                if solver.Value(x_vars[c.candidate_id]) == 1:
                    selected_candidates.append(c)
        elif status_code == cp_model.FEASIBLE:
            status_name = "FEASIBLE"
            for c in candidates:
                if solver.Value(x_vars[c.candidate_id]) == 1:
                    selected_candidates.append(c)
        elif status_code == cp_model.INFEASIBLE:
            status_name = "INFEASIBLE"
        else:
            status_name = "NO_SOLUTION"

        total_obj = round(solver.ObjectiveValue() / 100.0, 2) if status_code in (cp_model.OPTIMAL, cp_model.FEASIBLE) else 0.0

        return selected_candidates, status_name, total_obj, solve_duration_ms

    @classmethod
    def run_optimization(
        cls,
        db: Session,
        request: Optional[OptimizationRunRequest] = None,
    ) -> OptimizationPlanResponse:
        """Run the end-to-end hybrid fleet optimization pipeline (Phases 1, 2, 6)."""
        now = datetime.now(timezone.utc)
        req = request or OptimizationRunRequest()

        # 1. Weather observation & impacts
        if req.weather_scenario_override:
            weather_obs = WeatherService.set_scenario(req.weather_scenario_override)
        else:
            weather_obs = WeatherService.get_current_weather()

        # 2. Telemetry and Intelligence
        bus_intel_list = LoadIntelligenceService.get_bus_intelligence(db)
        route_intel_list = LoadIntelligenceService.get_route_intelligence_from_buses(db, bus_intel_list)

        # 3. Active breakdowns exclusion
        active_breakdowns = (
            db.query(BusBreakdown)
            .filter(BusBreakdown.status.in_(("REPORTED", "CONFIRMED", "UNDER_REPAIR")))
            .all()
        )
        broken_bus_ids = {bb.bus_id for bb in active_breakdowns}

        # Baseline snapshot
        baseline_snapshot = cls.calculate_network_snapshot(
            route_intel_list, bus_intel_list, broken_bus_ids
        )

        # 4. Candidate Generation
        candidates, binding_constraints = cls.generate_candidate_pool(
            db=db,
            route_intel_list=route_intel_list,
            bus_intel_list=bus_intel_list,
            weather_obs=weather_obs,
            broken_bus_ids=broken_bus_ids,
        )

        # 5. Solve CP-SAT model
        selected, solver_status, obj_value, solve_ms = cls.solve_hybrid_optimization(
            candidates=candidates,
            route_intel_list=route_intel_list,
            max_reallocations=req.max_reallocations or 4,
        )

        # 6. Build predicted metrics snapshot
        pred_routes = [r.model_copy() for r in route_intel_list]
        for sel in selected:
            # Add capacity to target route
            t_route = next((r for r in pred_routes if r.route_id == sel.target_route_id), None)
            if t_route:
                t_route.total_capacity += sel.bus_capacity
                t_route.number_of_buses += 1
                t_route.load_factor = round(t_route.total_passengers / t_route.total_capacity, 4)
                if t_route.load_factor < 0.80:
                    t_route.status = "NORMAL"

            # Remove capacity from source route
            s_route = next((r for r in pred_routes if r.route_id == sel.source_route_id), None)
            if s_route:
                s_route.total_capacity = max(1, s_route.total_capacity - sel.bus_capacity)
                s_route.number_of_buses = max(1, s_route.number_of_buses - 1)
                s_route.total_passengers = max(0, s_route.total_passengers - sel.current_occupancy)
                s_route.load_factor = round(s_route.total_passengers / s_route.total_capacity, 4)
                if s_route.load_factor < 0.50:
                    s_route.status = "LOW"
                elif s_route.load_factor < 0.80:
                    s_route.status = "NORMAL"
                elif s_route.load_factor < 1.00:
                    s_route.status = "HIGH"
                else:
                    s_route.status = "CRITICAL"

        predicted_snapshot = cls.calculate_network_snapshot(
            pred_routes, bus_intel_list, broken_bus_ids
        )

        # Metrics & Summary
        tot_dist_km = round(sum(s.distance_meters for s in selected) / 1000.0, 2)
        tot_time_min = round(sum(s.weather_travel_time_min for s in selected), 1)
        tot_seats = sum(s.bus_capacity for s in selected)

        # Calculate predicted improvement percentage
        baseline_overloaded = baseline_snapshot.overloaded_routes_count
        pred_overloaded = predicted_snapshot.overloaded_routes_count
        if baseline_overloaded > 0:
            improvement_pct = round(((baseline_overloaded - pred_overloaded) / baseline_overloaded) * 100.0, 1)
        else:
            improvement_pct = 0.0

        plan_id = f"PLAN-{now.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"

        allocations_output: List[OptimizationAllocationItem] = []
        for s in selected:
            allocations_output.append(
                OptimizationAllocationItem(
                    candidate_id=s.candidate_id,
                    bus_id=s.bus_id,
                    bus_number=s.bus_number,
                    source_route_id=s.source_route_id,
                    source_route_number=s.source_route_number,
                    target_route_id=s.target_route_id,
                    target_route_number=s.target_route_number,
                    bus_capacity=s.bus_capacity,
                    current_occupancy=s.current_occupancy,
                    available_seats=s.available_seats,
                    transfer_distance_km=round(s.distance_meters / 1000.0, 2),
                    nominal_travel_time_min=s.nominal_travel_time_min,
                    weather_adjusted_travel_time_min=s.weather_travel_time_min,
                    utility_score=s.utility_score,
                    priority=s.priority,
                    status="PROPOSED",
                    explanation=s.explanation,
                )
            )

        summary_notes = (
            f"CP-SAT solver produced {len(selected)} allocation(s) with net utility {obj_value}. "
            f"Overloaded corridors reduced from {baseline_overloaded} to {pred_overloaded} ({improvement_pct}% improvement). "
            f"Incorporated weather impacts ({weather_obs.condition}, speed factor {weather_obs.speed_factor})."
        )
        if binding_constraints:
            summary_notes += f" Binding constraints: {'; '.join(binding_constraints[:2])}."

        # 7. Persist OptimizationPlan in database
        try:
            db_plan = OptimizationPlan(
                id=plan_id,
                status="GENERATED",
                solver_status=solver_status,
                objective_value=obj_value,
                solver_time_ms=solve_ms,
                weather_condition=weather_obs.condition,
                weather_delay_factor=weather_obs.travel_time_multiplier,
                baseline_overloaded_routes=baseline_snapshot.overloaded_routes_count,
                predicted_overloaded_routes=predicted_snapshot.overloaded_routes_count,
                baseline_unmet_demand=baseline_snapshot.total_unmet_demand_proxy,
                predicted_unmet_demand=predicted_snapshot.total_unmet_demand_proxy,
                total_transfer_distance_km=tot_dist_km,
                total_transfer_time_min=tot_time_min,
                allocations_json=[a.model_dump() for a in allocations_output],
                binding_constraints_json=binding_constraints,
                summary_notes=summary_notes,
                created_at=now,
                updated_at=now,
            )
            db.add(db_plan)
            db.commit()
        except Exception as e:
            logger.warning(f"Could not persist optimization plan record: {e}")

        return OptimizationPlanResponse(
            plan_id=plan_id,
            created_at=now,
            status="GENERATED",
            solver_engine="Google OR-Tools CP-SAT (Hybrid MIP/Constraint Programming)",
            solver_status=solver_status,
            objective_value=obj_value,
            solver_time_ms=solve_ms,
            weather_condition=weather_obs.condition,
            weather_delay_factor=weather_obs.travel_time_multiplier,
            weather_summary=weather_obs.impact_summary,
            allocations=allocations_output,
            total_allocations_count=len(allocations_output),
            baseline_metrics=baseline_snapshot,
            predicted_metrics=predicted_snapshot,
            predicted_improvement_pct=improvement_pct,
            total_transfer_distance_km=tot_dist_km,
            total_transfer_time_min=tot_time_min,
            capacity_reallocated_seats=tot_seats,
            binding_constraints=binding_constraints,
            summary_notes=summary_notes,
            is_advisory=True,
        )

    @classmethod
    def evaluate_scenario(
        cls,
        db: Session,
        request: ScenarioEvaluationRequest,
    ) -> ScenarioEvaluationResponse:
        """Phase 5: Isolated Resilience Scenario Evaluation sandbox without mutating operational data."""
        now = datetime.now(timezone.utc)
        scenario_id = f"SCENARIO-{uuid.uuid4().hex[:8].upper()}"

        # Weather scenario impact
        weather_cond = (request.weather_scenario or "NORMAL").strip().upper()
        impacts = WeatherService._calculate_impacts(weather_cond)
        speed_factor = impacts["speed_factor"]

        # Base intelligence clones
        bus_intel_list = LoadIntelligenceService.get_bus_intelligence(db)
        route_intel_list = LoadIntelligenceService.get_route_intelligence_from_buses(db, bus_intel_list)

        # Baseline snapshot
        active_breakdowns = (
            db.query(BusBreakdown)
            .filter(BusBreakdown.status.in_(("REPORTED", "CONFIRMED", "UNDER_REPAIR")))
            .all()
        )
        broken_bus_ids = {bb.bus_id for bb in active_breakdowns}
        baseline_snapshot = cls.calculate_network_snapshot(
            route_intel_list, bus_intel_list, broken_bus_ids
        )

        # Apply simulated breakdowns
        sim_broken_numbers = set((request.simulated_breakdowns or []))
        sim_broken_ids = set(broken_bus_ids)
        for b in bus_intel_list:
            if b.bus_number in sim_broken_numbers:
                sim_broken_ids.add(b.bus_id)

        # Clone and mutate routes according to demand overrides and simulated breakdowns
        sim_routes = []
        demand_overrides = request.demand_overrides or {}

        for r in route_intel_list:
            r_clone = r.model_copy()
            # Apply route demand override
            if r.route_number in demand_overrides:
                profile = demand_overrides[r.route_number].strip().upper()
                if profile == "HIGH":
                    r_clone.total_passengers = int(r_clone.total_capacity * 0.95)
                    r_clone.load_factor = 0.95
                    r_clone.status = "HIGH"
                elif profile == "LOW":
                    r_clone.total_passengers = int(r_clone.total_capacity * 0.35)
                    r_clone.load_factor = 0.35
                    r_clone.status = "LOW"
                elif profile == "NORMAL":
                    r_clone.total_passengers = int(r_clone.total_capacity * 0.60)
                    r_clone.load_factor = 0.60
                    r_clone.status = "NORMAL"

            # Apply loss of capacity from simulated broken-down buses on this route
            r_broken_buses = [b for b in bus_intel_list if b.route_id == r.route_id and b.bus_id in sim_broken_ids]
            lost_cap = sum(b.capacity for b in r_broken_buses)
            r_clone.total_capacity = max(1, r_clone.total_capacity - lost_cap)
            r_clone.number_of_buses = max(0, r_clone.number_of_buses - len(r_broken_buses))
            r_clone.load_factor = round(r_clone.total_passengers / r_clone.total_capacity, 4)
            if r_clone.load_factor >= 1.0:
                r_clone.status = "CRITICAL"
            elif r_clone.load_factor >= 0.80:
                r_clone.status = "HIGH"

            sim_routes.append(r_clone)

        scenario_snapshot = cls.calculate_network_snapshot(
            sim_routes, bus_intel_list, sim_broken_ids
        )

        # Calculate network resilience score (0 to 100)
        # Factors: capacity retention (40%), fleet availability (30%), route continuity (20%), overload penalty (10%)
        cap_ret = min(100.0, (scenario_snapshot.total_capacity / max(1, baseline_snapshot.total_capacity)) * 100.0)
        avail_ratio = (scenario_snapshot.operational_buses_count / max(1, len(bus_intel_list))) * 100.0
        routes_cont = ((6 - scenario_snapshot.routes_below_minimum_coverage) / 6.0) * 100.0
        overload_penalty = (scenario_snapshot.overloaded_routes_count / 6.0) * 100.0

        resilience_score = round(
            max(0.0, min(100.0, (0.40 * cap_ret) + (0.30 * avail_ratio) + (0.20 * routes_cont) - (0.10 * overload_penalty))),
            1
        )
        if resilience_score >= 80.0:
            resilience_rating = "HIGH RESILIENCE"
        elif resilience_score >= 55.0:
            resilience_rating = "MODERATE RESILIENCE"
        else:
            resilience_rating = "VULNERABLE / IMPAIRED"

        findings: List[str] = [
            f"Resilience Score: {resilience_score}/100 ({resilience_rating}).",
            f"Overloaded corridors under drill: {scenario_snapshot.overloaded_routes_count}/6 corridors.",
            f"Capacity retention: {round(cap_ret, 1)}% of baseline seating capacity retained.",
            f"Weather operating speed penalty: {int((1.0 - speed_factor) * 100)}% reduction under {weather_cond}.",
        ]
        if sim_broken_numbers:
            findings.append(f"Simulated vehicle breakdowns: {', '.join(sorted(sim_broken_numbers))} removed from fleet.")

        return ScenarioEvaluationResponse(
            scenario_id=scenario_id,
            scenario_name=request.scenario_name or "Resilience Evaluation Drill",
            evaluated_at=now,
            is_simulation=True,
            demand_profiles=demand_overrides,
            broken_down_buses=sorted(list(sim_broken_numbers)),
            weather_scenario=weather_cond,
            weather_speed_factor=speed_factor,
            weather_impact_description=impacts["impact_summary"],
            baseline_metrics=baseline_snapshot,
            scenario_metrics=scenario_snapshot,
            resilience_score=resilience_score,
            resilience_rating=resilience_rating,
            recommended_plan=None,
            key_findings=findings,
        )
