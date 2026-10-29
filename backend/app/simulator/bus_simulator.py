"""Individual bus transit simulator.

Tracks real-time bus movement along assigned route stops, GPS positions,
speed, heading, and passenger load.
Supports bidirectional (forward and reverse) route progression along the exact
stop geometry with seamless terminal turnaround.
"""
import random
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from app.simulator.route_simulator import (
    calculate_distance_meters,
    calculate_bearing,
    step_towards,
)
from app.simulator.passenger_simulator import PassengerSimulator


class BusSimulator:
    """Simulates an active bus traveling sequentially along its assigned route stops.

    Supports continuous round-trip journeys:
    Stop 0 -> Stop 1 -> ... -> Stop N-1 -> Stop N-2 -> ... -> Stop 0 -> Stop 1 ...
    At terminal stops, the direction automatically reverses without jumping or cutting off-route.
    """

    def __init__(
        self,
        bus_id: int,
        bus_number: str,
        route_id: int,
        route_number: str,
        capacity: int,
        stops: List[Any],
        initial_stop_index: int = 0,
        scenario: str = "normal",
        base_speed_kmh: float = 32.0,
        initial_direction: int = 1,
        demand_profile: str = "NORMAL",
    ):
        self.bus_id = bus_id
        self.bus_number = bus_number
        self.route_id = route_id
        self.route_number = route_number
        self.capacity = capacity
        self.scenario = scenario
        self.demand_profile = (demand_profile or "NORMAL").strip().upper()
        self.base_speed_kmh = base_speed_kmh

        if not stops:
            raise ValueError(f"Bus {bus_number} cannot simulate on route without stops.")
        self.stops = sorted(stops, key=lambda s: s.sequence_order)
        num_stops = len(self.stops)

        # Stop indices and direction initialization:
        # Direction: 1 = forward (outbound), -1 = reverse (inbound)
        self.current_stop_idx = initial_stop_index % num_stops
        if self.current_stop_idx >= num_stops - 1:
            self.direction = -1
            self.next_stop_idx = max(0, num_stops - 2)
        elif self.current_stop_idx <= 0:
            self.direction = 1
            self.next_stop_idx = min(num_stops - 1, 1)
        else:
            self.direction = initial_direction if initial_direction in (1, -1) else 1
            self.next_stop_idx = self.current_stop_idx + self.direction

        # Initial location starts at the initial stop
        initial_stop = self.stops[self.current_stop_idx]
        self.latitude = initial_stop.latitude
        self.longitude = initial_stop.longitude
        self.speed = 0.0

        target_stop = self.stops[self.next_stop_idx]
        self.heading = calculate_bearing(
            self.latitude, self.longitude, target_stop.latitude, target_stop.longitude
        )

        # Distance traveled along current segment (meters)
        self.distance_along_segment_meters: float = 0.0

        # Route assignment states: active route currently being served vs assigned route
        self.active_route_id = route_id
        self.active_route_number = route_number
        self.assigned_route_id = route_id
        self.assigned_route_number = route_number

        # Passenger load state
        initial_load, unmet = PassengerSimulator.get_initial_load(
            self.route_number, self.capacity, self.get_active_demand_profile()
        )
        self.current_load = initial_load
        self.unmet_demand = unmet

        # Dwell state (stops at a station to exchange passengers)
        self.is_dwelling = True
        self.dwell_ticks_remaining = 1

        # Breakdown operational state
        self.is_broken_down = False

        # Weather operational speed multiplier (NORMAL: 1.0, LIGHT_RAIN: 0.90, HEAVY_RAIN: 0.75, SEVERE: 0.55)
        self.weather_speed_factor: float = 1.0

        # Transfer journey state for runtime route reassignment
        self.transfer_state: Optional[Dict[str, Any]] = None

    def set_weather_speed_factor(self, factor: float) -> None:
        """Update active weather speed factor to deterministically scale operating speeds."""
        self.weather_speed_factor = max(0.2, min(1.5, float(factor)))

    @property
    def current_stop(self) -> Any:
        return self.stops[self.current_stop_idx]

    @property
    def next_stop(self) -> Any:
        return self.stops[self.next_stop_idx]

    @property
    def direction_name(self) -> str:
        return "FORWARD" if self.direction == 1 else "REVERSE"

    @property
    def load_factor(self) -> float:
        if self.capacity <= 0:
            return 0.0
        return round(self.current_load / self.capacity, 4)

    @property
    def available_seats(self) -> int:
        return max(self.capacity - self.current_load, 0)

    def is_in_transfer(self) -> bool:
        """Check whether bus is currently deadheading in a route transfer journey."""
        return bool(self.transfer_state and self.transfer_state.get("in_transfer"))

    def set_scenario(self, scenario: str) -> None:
        """Dynamically update demand scenario profile at runtime."""
        self.scenario = scenario
        self.demand_profile = scenario.strip().upper()

    def set_demand_profile(self, profile: str) -> None:
        """Dynamically update route-specific demand profile at runtime."""
        self.demand_profile = (profile or "NORMAL").strip().upper()
        self.scenario = self.demand_profile

    def get_active_demand_profile(self) -> str:
        """Return the active demand profile for the corridor currently being served."""
        return (self.demand_profile or self.scenario or "NORMAL").strip().upper()

    def reassign_route(
        self,
        new_route_id: int,
        new_route_number: str,
        target_stops: List[Any],
    ) -> bool:
        """Safely reassign bus to a target route at runtime.

        Prepares a continuous transfer journey:
        1. Preserves existing passenger load during deadhead transfer.
        2. Selects the nearest stop on the target route as entry point.
        3. Initializes deadhead transit state towards the entry stop without teleportation.
        4. Switches assigned route identity and continues simulator movement.
        """
        if not target_stops:
            return False
        if self.route_id == new_route_id and not self.is_in_transfer():
            return False

        sorted_stops = sorted(target_stops, key=lambda s: s.sequence_order)

        # Select closest target route stop as arrival entry point
        entry_idx, entry_stop = min(
            enumerate(sorted_stops),
            key=lambda item: calculate_distance_meters(
                self.latitude, self.longitude, item[1].latitude, item[1].longitude
            ),
        )

        source_r_id = self.active_route_id
        source_r_num = self.active_route_number

        # Setup continuous transfer state
        self.transfer_state = {
            "in_transfer": True,
            "source_route_id": source_r_id,
            "source_route_number": source_r_num,
            "target_route_id": new_route_id,
            "target_route_number": new_route_number,
            "target_stops": sorted_stops,
            "entry_stop_idx": entry_idx,
            "entry_stop": entry_stop,
        }

        # Update assigned route identity (active route switches upon arrival at entry stop)
        self.assigned_route_id = new_route_id
        self.assigned_route_number = new_route_number
        self.route_id = new_route_id
        self.route_number = new_route_number
        self.is_dwelling = False
        self.dwell_ticks_remaining = 0

        return True

    def set_breakdown_state(self, is_broken: bool) -> None:
        """Update breakdown state; broken down buses immediately stop moving."""
        self.is_broken_down = bool(is_broken)
        if self.is_broken_down:
            self.speed = 0.0

    def tick(self, interval_seconds: float = 5.0) -> Dict[str, Any]:
        """Perform one simulation tick.

        Advances bus position gradually along route stop geometry using distance-based
        interpolation, calculates speed, heading, and triggers passenger boarding/alighting at stops.
        Reverses direction at route endpoints to follow the same geometry in reverse.
        """
        now = datetime.now(timezone.utc)

        # 0. Handle broken-down bus state (halts immediately and retains last coordinates)
        if self.is_broken_down:
            self.speed = 0.0
            return {
                "bus_id": self.bus_id,
                "bus_number": self.bus_number,
                "route_id": self.assigned_route_id,
                "route_number": self.assigned_route_number,
                "latitude": self.latitude,
                "longitude": self.longitude,
                "speed": 0.0,
                "heading": self.heading,
                "passenger_count": self.current_load,
                "capacity": self.capacity,
                "load_factor": self.load_factor,
                "event": "BUS_BREAKDOWN_HALTED",
                "message": f"Bus {self.bus_number} is BROKEN_DOWN and halted at last known location.",
                "is_broken_down": True,
                "timestamp": now,
            }

        # 1. Handle active transfer journey (deadheading to new assigned route entry stop)
        if self.is_in_transfer():
            entry_stop = self.transfer_state["entry_stop"]
            target_lat = entry_stop.latitude
            target_lon = entry_stop.longitude

            speed_variation = random.uniform(-3.0, 3.0)
            target_speed = max(12.0, min(50.0, (self.base_speed_kmh + speed_variation) * self.weather_speed_factor))
            step_distance = (target_speed / 3.6) * interval_seconds

            self.heading = calculate_bearing(
                self.latitude, self.longitude, target_lat, target_lon
            )

            new_lat, new_lon, reached = step_towards(
                self.latitude, self.longitude, target_lat, target_lon, step_distance
            )

            self.latitude = new_lat
            self.longitude = new_lon
            self.speed = round(target_speed, 1)

            event_type = "TRANSFER"
            event_message = (
                f"Bus {self.bus_number} deadheading from Route {self.transfer_state['source_route_number']} "
                f"to Route {self.route_number} entry stop {entry_stop.sequence_order} ({entry_stop.name})"
            )

            if reached:
                # Arrived at entry stop on target route!
                self.stops = self.transfer_state["target_stops"]
                num_stops = len(self.stops)
                self.current_stop_idx = self.transfer_state["entry_stop_idx"]

                # Initialize direction safely from entry stop
                if self.current_stop_idx >= num_stops - 1:
                    self.direction = -1
                    self.next_stop_idx = max(0, num_stops - 2)
                elif self.current_stop_idx <= 0:
                    self.direction = 1
                    self.next_stop_idx = min(num_stops - 1, 1)
                else:
                    self.direction = 1
                    self.next_stop_idx = self.current_stop_idx + 1

                self.distance_along_segment_meters = 0.0
                self.active_route_id = self.route_id
                self.active_route_number = self.route_number
                self.transfer_state = None
                self.is_dwelling = True
                self.dwell_ticks_remaining = 1
                self.speed = 0.0

                next_target = self.next_stop
                self.heading = calculate_bearing(
                    self.latitude, self.longitude, next_target.latitude, next_target.longitude
                )

                # Exchange passengers on target route starting from preserved load
                new_load, boarding, alighting, unmet = PassengerSimulator.simulate_stop_exchange(
                    current_load=self.current_load,
                    capacity=self.capacity,
                    route_number=self.route_number,
                    stop_seq=entry_stop.sequence_order,
                    total_stops=len(self.stops),
                    scenario=self.get_active_demand_profile(),
                )
                self.current_load = new_load
                self.unmet_demand = unmet

                event_type = "TRANSFER_ARRIVED"
                event_message = (
                    f"Bus {self.bus_number} entered service on Route {self.route_number} "
                    f"at Stop {entry_stop.sequence_order} ({entry_stop.name}) [Boarded: +{boarding}, Alighted: -{alighting}]"
                )

            current_stop_item = entry_stop
            next_stop_item = entry_stop if self.is_in_transfer() else self.next_stop
            pct = int(round(self.load_factor * 100))

            return {
                "bus_id": self.bus_id,
                "bus_number": self.bus_number,
                "route_id": self.route_id,
                "route_number": self.route_number,
                "active_route_id": self.active_route_id,
                "active_route_number": self.active_route_number,
                "assigned_route_id": self.assigned_route_id,
                "assigned_route_number": self.assigned_route_number,
                "latitude": self.latitude,
                "longitude": self.longitude,
                "speed": self.speed,
                "heading": self.heading,
                "direction": self.direction_name,
                "direction_num": self.direction,
                "current_stop_id": current_stop_item.id,
                "current_stop_name": current_stop_item.name,
                "current_stop_seq": current_stop_item.sequence_order,
                "next_stop_id": next_stop_item.id,
                "next_stop_name": next_stop_item.name,
                "passenger_count": self.current_load,
                "capacity": self.capacity,
                "available_seats": self.available_seats,
                "load_factor": self.load_factor,
                "load_pct": pct,
                "demand_profile": self.get_active_demand_profile(),
                "unmet_demand": self.unmet_demand,
                "is_transferring": self.is_in_transfer(),
                "transfer_status": "IN_PROGRESS" if self.is_in_transfer() else ("COMPLETED" if event_type == "TRANSFER_ARRIVED" else None),
                "event_type": event_type,
                "event_message": event_message,
                "timestamp": now,
            }

        # 2. Regular route service along assigned corridor stops
        total_stops = len(self.stops)
        target = self.next_stop
        event_type = "MOVE"
        event_message = ""

        if self.is_dwelling:
            # Bus is dwelling at stop for passenger boarding/alighting
            self.speed = 0.0
            self.dwell_ticks_remaining -= 1
            if self.dwell_ticks_remaining <= 0:
                self.is_dwelling = False
                # Recompute bearing toward the next target stop
                self.heading = calculate_bearing(
                    self.latitude, self.longitude, target.latitude, target.longitude
                )
        else:
            # Transit speed scaled by active weather conditions and realistic jitter (+/- 3.5 km/h)
            speed_variation = random.uniform(-3.5, 3.5)
            target_speed = max(10.0, min(48.0, (self.base_speed_kmh + speed_variation) * self.weather_speed_factor))
            self.speed = round(target_speed, 1)

            # Available distance budget for this simulation tick in meters
            distance_budget = (target_speed / 3.6) * interval_seconds

            while distance_budget > 0.01:
                target = self.stops[self.next_stop_idx]
                dist_to_target = calculate_distance_meters(
                    self.latitude, self.longitude, target.latitude, target.longitude
                )

                if distance_budget < dist_to_target:
                    # Move partially along the segment towards target stop
                    self.heading = calculate_bearing(
                        self.latitude, self.longitude, target.latitude, target.longitude
                    )
                    new_lat, new_lon, _ = step_towards(
                        self.latitude, self.longitude, target.latitude, target.longitude, distance_budget
                    )
                    self.latitude = new_lat
                    self.longitude = new_lon
                    self.distance_along_segment_meters += distance_budget
                    distance_budget = 0.0
                    break
                else:
                    # Covered remaining distance to target stop! Snap cleanly to stop coordinates
                    distance_budget -= dist_to_target
                    self.latitude = target.latitude
                    self.longitude = target.longitude
                    self.distance_along_segment_meters = 0.0

                    arrived_stop = target
                    arrived_idx = self.next_stop_idx
                    self.current_stop_idx = arrived_idx

                    # Arrived at stop: perform passenger exchange
                    event_type = "ARRIVE"
                    new_load, boarding, alighting, unmet = PassengerSimulator.simulate_stop_exchange(
                        current_load=self.current_load,
                        capacity=self.capacity,
                        route_number=self.route_number,
                        stop_seq=arrived_stop.sequence_order,
                        total_stops=total_stops,
                        scenario=self.get_active_demand_profile(),
                    )
                    self.current_load = new_load
                    self.unmet_demand = unmet

                    event_message = (
                        f"Bus {self.bus_number} reached Stop {arrived_stop.sequence_order} "
                        f"({arrived_stop.name}) [Boarded: +{boarding}, Alighted: -{alighting}]"
                    )

                    # Update direction and next stop index:
                    # When reaching final stop, reverse direction to -1 (inbound)
                    # When reaching first stop, reverse direction to 1 (outbound)
                    if arrived_idx >= total_stops - 1:
                        self.direction = -1
                        self.next_stop_idx = max(0, total_stops - 2)
                        event_type = "TERMINAL_TURNAROUND"
                        event_message += " | Terminus reached, reversing direction to INBOUND."
                    elif arrived_idx <= 0:
                        self.direction = 1
                        self.next_stop_idx = min(total_stops - 1, 1)
                        event_type = "TERMINAL_TURNAROUND"
                        event_message += " | Origin reached, reversing direction to OUTBOUND."
                    else:
                        self.next_stop_idx = arrived_idx + self.direction

                    # Update heading toward next stop
                    new_target = self.stops[self.next_stop_idx]
                    self.heading = calculate_bearing(
                        self.latitude, self.longitude, new_target.latitude, new_target.longitude
                    )

                    # Dwell at this stop for 1 tick to allow passenger exchange
                    self.is_dwelling = True
                    self.dwell_ticks_remaining = 1
                    self.speed = 0.0
                    break

        pct = int(round(self.load_factor * 100))

        return {
            "bus_id": self.bus_id,
            "bus_number": self.bus_number,
            "route_id": self.route_id,
            "route_number": self.route_number,
            "active_route_id": self.active_route_id,
            "active_route_number": self.active_route_number,
            "assigned_route_id": self.assigned_route_id,
            "assigned_route_number": self.assigned_route_number,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "speed": self.speed,
            "heading": self.heading,
            "direction": self.direction_name,
            "direction_num": self.direction,
            "current_stop_id": self.current_stop.id,
            "current_stop_name": self.current_stop.name,
            "current_stop_seq": self.current_stop.sequence_order,
            "next_stop_id": self.next_stop.id,
            "next_stop_name": self.next_stop.name,
            "passenger_count": self.current_load,
            "capacity": self.capacity,
            "available_seats": self.available_seats,
            "load_factor": self.load_factor,
            "load_pct": pct,
            "demand_profile": self.get_active_demand_profile(),
            "unmet_demand": self.unmet_demand,
            "is_transferring": False,
            "transfer_status": None,
            "event_type": event_type,
            "event_message": event_message,
            "timestamp": now,
        }

