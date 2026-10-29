"""Passenger dynamics and demand scenario simulator.

Simulates realistic passenger boarding, alighting, capacity clamping,
and scenario-driven route loads without random teleports.
Supports LOW, NORMAL, and HIGH demand profiles across the 6-route Coimbatore network.
"""
import random
from typing import Tuple, Dict, Any, Optional


class PassengerSimulator:
    """Manages passenger demand profiles and stop passenger exchanges."""

    @staticmethod
    def get_demand_profile(
        route_number: str,
        scenario: str = "normal",
        route_demands: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Determine target load factor range and demand category for a route.

        Supports independent route-specific demand profiles (LOW, NORMAL, HIGH)
        configured per corridor. Also supports legacy global scenarios.
        """
        r_num = str(route_number).strip()

        # 1. Prefer explicit route-specific configuration if available
        if route_demands and r_num in route_demands:
            prof = route_demands[r_num].strip().upper()
            if prof == "LOW":
                return {"level": "LOW", "target_min": 0.20, "target_max": 0.40}
            elif prof == "HIGH":
                return {"level": "HIGH", "target_min": 0.85, "target_max": 1.15}
            else:
                return {"level": "NORMAL", "target_min": 0.48, "target_max": 0.72}

        # 2. Check profile passed directly via scenario string
        scenario_clean = (scenario or "normal").strip().upper()

        if scenario_clean in ("LOW", "LOW_DEMAND"):
            return {"level": "LOW", "target_min": 0.20, "target_max": 0.40}
        elif scenario_clean in ("HIGH", "HIGH_DEMAND"):
            # If explicit "HIGH" is passed for this route, activate HIGH demand profile
            if scenario_clean == "HIGH":
                return {"level": "HIGH", "target_min": 0.85, "target_max": 1.15}

            # Legacy global scenario fallback when "high_demand" string is supplied without route_demands
            if r_num in ("101", "404"):
                return {"level": "HIGH", "target_min": 0.85, "target_max": 1.15}
            elif r_num in ("202", "505"):
                return {"level": "LOW", "target_min": 0.25, "target_max": 0.45}
            elif r_num in ("303", "606"):
                return {"level": "NORMAL", "target_min": 0.50, "target_max": 0.72}
            else:
                return {"level": "NORMAL", "target_min": 0.50, "target_max": 0.75}
        else:
            # Normal balanced operations across routes
            return {"level": "NORMAL", "target_min": 0.48, "target_max": 0.72}

    @classmethod
    def get_initial_load(
        cls,
        route_number: str,
        capacity: int,
        scenario: str = "normal",
        route_demands: Optional[Dict[str, str]] = None,
    ) -> Tuple[int, int]:
        """Generate realistic initial passenger load and unmet demand upon bus startup.

        Returns:
            (current_load, unmet_demand)
        """
        profile = cls.get_demand_profile(route_number, scenario, route_demands)
        target_factor = random.uniform(profile["target_min"], profile["target_max"])
        attempted_load = int(round(target_factor * capacity))

        current_load = max(0, min(attempted_load, capacity))
        unmet_demand = max(0, attempted_load - capacity)
        return current_load, unmet_demand

    @classmethod
    def simulate_stop_exchange(
        cls,
        current_load: int,
        capacity: int,
        route_number: str,
        stop_seq: int,
        total_stops: int,
        scenario: str = "normal",
        route_demands: Optional[Dict[str, str]] = None,
    ) -> Tuple[int, int, int, int]:
        """Simulate boarding and alighting at a transit stop based on the route demand profile.

        Rules:
        - current_load never falls below 0.
        - current_load never exceeds capacity.
        - Excess demand is preserved in unmet_demand.

        Returns:
            (new_current_load, boarding, alighting, unmet_demand)
        """
        profile = cls.get_demand_profile(route_number, scenario, route_demands)
        level = profile["level"]

        # 1. Alighting logic
        if stop_seq >= total_stops or stop_seq == 1:
            # Terminal / turnaround stops: significant turnover
            alight_pct = random.uniform(0.40, 0.70)
        else:
            # Intermediate stops: turnover depends on route demand profile
            if level == "LOW":
                alight_pct = random.uniform(0.20, 0.35)
            else:
                alight_pct = random.uniform(0.10, 0.25)

        alighting = int(round(current_load * alight_pct))
        if current_load > 0 and alighting == 0:
            alighting = min(current_load, random.randint(1, 2))
        alighting = min(current_load, max(0, alighting))

        passengers_remaining = current_load - alighting

        # 2. Boarding logic based on route demand profile
        target_min = profile["target_min"]
        target_max = profile["target_max"]
        target_ratio = random.uniform(target_min, target_max)
        desired_passengers = int(round(target_ratio * capacity))

        needed_passengers = desired_passengers - passengers_remaining

        if level == "HIGH":
            # High demand: heavy passenger arrivals at stops
            base_boarding = random.randint(14, 26)
            boarding = max(base_boarding, needed_passengers + random.randint(3, 8))
        elif level == "LOW":
            # Low demand: sparse passenger arrivals, off-peak
            if needed_passengers > 0:
                boarding = max(1, min(needed_passengers, random.randint(1, 4)))
            else:
                boarding = random.randint(0, 2)
        else:
            # Normal demand: balanced arrivals
            base_boarding = random.randint(6, 14)
            boarding = max(base_boarding, needed_passengers)

        boarding = max(0, boarding)

        # 3. Calculate final physical load and unmet demand
        attempted_load = passengers_remaining + boarding
        new_current_load = max(0, min(attempted_load, capacity))
        unmet_demand = max(0, attempted_load - capacity)

        return new_current_load, boarding, alighting, unmet_demand

