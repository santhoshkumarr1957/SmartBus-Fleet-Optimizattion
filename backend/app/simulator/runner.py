"""Transit simulator runner module.

Orchestrates real-time bus movements, GPS position updates, passenger loads,
and database persistence.

Usage:
    python -m app.simulator.runner
    python -m app.simulator.runner --scenario high_demand
    python -m app.simulator.runner --scenario normal --interval 5 --ticks 10
"""
import sys
import time
import signal
import logging
import argparse
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session, joinedload
from app.core.config import settings
from app.db.session import SessionLocal
from app.db.seed import seed_transit_data
from app.models.route import Route
from app.models.bus import Bus
from app.models.bus_position import BusPosition
from app.models.passenger_load import PassengerLoad
from app.simulator.bus_simulator import BusSimulator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("smartbus.simulator")


class SimulatorRunner:
    """Manages the lifecycle and execution loop of transit bus fleet simulation."""

    def __init__(
        self,
        scenario: Optional[str] = None,
        interval_seconds: Optional[float] = None,
        max_ticks: Optional[int] = None,
    ):
        self.scenario = scenario or settings.SIMULATION_SCENARIO
        self.interval_seconds = (
            float(interval_seconds)
            if interval_seconds is not None
            else float(settings.SIMULATION_INTERVAL_SECONDS)
        )
        self.max_ticks = max_ticks
        self.is_running = False
        self.bus_simulators: List[BusSimulator] = []
        self.routes: List[Route] = []
        self.route_demands: Dict[str, str] = {
            "101": "NORMAL",
            "202": "NORMAL",
            "303": "NORMAL",
            "404": "NORMAL",
            "505": "NORMAL",
            "606": "NORMAL",
        }
        self.last_tick_time: Optional[float] = None

    def setup(self, db: Session) -> bool:
        """Verify database data and initialize bus simulators."""
        # Ensure database has seeded routes, stops, and buses (fast-path completes in <50ms)
        seed_transit_data(db)

        # Query all active routes with eager-loaded stops and buses in a single round-trip
        routes = (
            db.query(Route)
            .options(joinedload(Route.stops), joinedload(Route.buses))
            .filter(Route.is_active == True)  # noqa: E712
            .all()
        )
        if not routes:
            logger.error("No active routes found in database. Simulator cannot start.")
            return False

        self.routes = routes
        self.bus_simulators.clear()

        total_buses = 0
        now_utc = datetime.now(timezone.utc)
        initial_positions: List[BusPosition] = []
        initial_loads: List[PassengerLoad] = []

        # Check existing positions to avoid duplicate initial inserts
        existing_pos_bus_ids = {
            b_id for (b_id,) in db.query(BusPosition.bus_id).distinct().all()
        }

        for route in routes:
            route_stops = sorted(route.stops, key=lambda s: s.sequence_order)
            if not route_stops:
                logger.warning(f"Route {route.route_number} has no stops. Skipping.")
                continue

            route_buses = [b for b in route.buses if b.status != "INACTIVE"]
            for idx, bus in enumerate(route_buses):
                # Stagger initial bus positions along route stops
                stagger_idx = (idx * max(1, len(route_stops) // max(1, len(route_buses)))) % len(route_stops)
                initial_dir = 1 if idx % 2 == 0 else -1
                r_num = route.route_number
                r_profile = self.route_demands.get(r_num, "NORMAL")
                sim = BusSimulator(
                    bus_id=bus.id,
                    bus_number=bus.bus_number,
                    route_id=route.id,
                    route_number=route.route_number,
                    capacity=bus.capacity,
                    stops=route_stops,
                    initial_stop_index=stagger_idx,
                    scenario=r_profile,
                    demand_profile=r_profile,
                    initial_direction=initial_dir,
                )
                self.bus_simulators.append(sim)
                total_buses += 1

                # If this bus has never had a position record, persist its initial location immediately
                if bus.id not in existing_pos_bus_ids:
                    init_stop = route_stops[stagger_idx]
                    initial_positions.append(
                        BusPosition(
                            bus_id=bus.id,
                            latitude=init_stop.latitude,
                            longitude=init_stop.longitude,
                            speed=0.0,
                            heading=0.0,
                            timestamp=now_utc,
                        )
                    )
                    initial_loads.append(
                        PassengerLoad(
                            bus_id=bus.id,
                            stop_id=init_stop.id,
                            current_load=sim.current_load,
                            capacity=sim.capacity,
                            load_factor=sim.load_factor,
                            timestamp=now_utc,
                        )
                    )

        if initial_positions or initial_loads:
            try:
                db.add_all(initial_positions + initial_loads)
                db.commit()
            except Exception as e:
                db.rollback()
                logger.error(f"[SIMULATOR] Failed to commit initial positions: {e}")

        logger.info(
            f"Initialized simulator with {total_buses} buses across {len(routes)} routes "
            f"[Scenario: {self.scenario.upper()}, Interval: {self.interval_seconds}s]"
        )
        return total_buses > 0

    def step(self, db: Session) -> None:
        """Execute one simulation cycle across all active buses using reliable wall-clock interval."""
        now_time = time.time()
        if self.last_tick_time is not None:
            elapsed = now_time - self.last_tick_time
            # Keep elapsed interval within safe bounds [0.2, 5.0] seconds
            effective_interval = max(0.2, min(5.0, elapsed))
        else:
            effective_interval = self.interval_seconds
        self.last_tick_time = now_time

        # Batch synchronize dynamic route reassignments from database (throttled every 3 ticks)
        self._sync_counter = getattr(self, "_sync_counter", 0) + 1
        if self._sync_counter % 3 == 0:
            try:
                db_buses = {b.id: b for b in db.query(Bus).all()}
                db_routes = {r.id: r for r in db.query(Route).all()}
                for bus_sim in self.bus_simulators:
                    db_bus = db_buses.get(bus_sim.bus_id)
                    current_assigned = getattr(bus_sim, "assigned_route_id", bus_sim.route_id)
                    if db_bus and db_bus.current_route_id and db_bus.current_route_id != current_assigned:
                        if not bus_sim.is_in_transfer():
                            target_route = db_routes.get(db_bus.current_route_id)
                            if target_route and target_route.stops:
                                logger.info(
                                    f"[SIMULATOR] Dynamic route reassignment detected for Bus {bus_sim.bus_number}: "
                                    f"Route {bus_sim.route_number} -> Route {target_route.route_number}"
                                )
                                bus_sim.reassign_route(
                                    new_route_id=target_route.id,
                                    new_route_number=target_route.route_number,
                                    target_stops=target_route.stops,
                                )
            except Exception as e:
                logger.error(f"[SIMULATOR] Error checking route synchronization: {e}")

        positions: List[BusPosition] = []
        loads: List[PassengerLoad] = []

        for bus_sim in self.bus_simulators:
            try:
                # Synchronize bus demand profile to match its actively served corridor
                active_r = bus_sim.active_route_number or bus_sim.route_number
                bus_sim.set_demand_profile(self.route_demands.get(active_r, "NORMAL"))

                state = bus_sim.tick(interval_seconds=effective_interval)

                # 1. BusPosition record
                position_record = BusPosition(
                    bus_id=state["bus_id"],
                    latitude=state["latitude"],
                    longitude=state["longitude"],
                    speed=state["speed"],
                    heading=state["heading"],
                    timestamp=state["timestamp"],
                )
                positions.append(position_record)

                # 2. PassengerLoad record
                load_record = PassengerLoad(
                    bus_id=state["bus_id"],
                    stop_id=state["current_stop_id"],
                    current_load=state["passenger_count"],
                    capacity=state["capacity"],
                    load_factor=state["load_factor"],
                    timestamp=state["timestamp"],
                )
                loads.append(load_record)

                # 3. Log events
                if state.get("event_message"):
                    logger.info(f"[SIMULATOR] {state['event_message']}")

            except Exception as e:
                logger.error(f"[SIMULATOR] Error processing bus {bus_sim.bus_number}: {e}")

        try:
            db.add_all(positions + loads)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"[SIMULATOR] Failed to commit simulation batch: {e}")

    def run(self) -> None:
        """Run the simulation loop until stopped or max_ticks reached."""
        self.is_running = True

        def handle_signal(sig, frame):
            logger.info("Received shutdown signal. Stopping simulator...")
            self.is_running = False

        try:
            signal.signal(signal.SIGINT, handle_signal)
            signal.signal(signal.SIGTERM, handle_signal)
        except Exception:
            pass

        db = SessionLocal()
        try:
            if not self.setup(db):
                logger.error("Simulator initialization failed.")
                return

            tick_count = 0
            logger.info("Simulator running. Press Ctrl+C to terminate.")

            while self.is_running:
                step_start = time.time()
                tick_count += 1
                logger.info(f"--- Simulation Tick #{tick_count} ---")
                self.step(db)

                if self.max_ticks is not None and tick_count >= self.max_ticks:
                    logger.info(f"Reached configured limit of {self.max_ticks} ticks. Exiting.")
                    break

                if self.is_running:
                    step_duration = time.time() - step_start
                    sleep_time = max(0.05, self.interval_seconds - step_duration)
                    time.sleep(sleep_time)

        except Exception as e:
            logger.error(f"Simulator encountered an unhandled exception: {e}")
        finally:
            db.close()
            logger.info("Simulator stopped.")


def check_server_simulation_running() -> bool:
    """Check if the backend server already has an active simulation running."""
    import json
    import urllib.request
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:8000/api/simulation/status",
            headers={"User-Agent": "SmartBus-CLI-Guard"},
        )
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode())
                if data.get("status") == "RUNNING":
                    return True
    except Exception:
        pass
    return False


def main():
    parser = argparse.ArgumentParser(description="SmartBus Fleet Simulation Engine")
    parser.add_argument(
        "--scenario",
        type=str,
        default=None,
        choices=["normal", "high_demand", "low_demand", "low", "high"],
        help="Simulation demand scenario (normal, high_demand, low_demand)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=None,
        help="Simulation interval in seconds (default: from .env or 5)",
    )
    parser.add_argument(
        "--ticks",
        type=int,
        default=None,
        help="Optional number of ticks to run before terminating",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force standalone runner even if in-process simulator is running",
    )

    args = parser.parse_args()

    if not args.force and check_server_simulation_running():
        logger.warning(
            "[SIMULATOR GUARD] In-process SimulationManager is already RUNNING on FastAPI server (http://127.0.0.1:8000). "
            "To prevent competing simulator loops and telemetry race conditions, the standalone runner will not start. "
            "Control the simulation via the web dashboard or use --force to override."
        )
        sys.exit(0)

    runner = SimulatorRunner(
        scenario=args.scenario,
        interval_seconds=args.interval,
        max_ticks=args.ticks,
    )
    runner.run()


if __name__ == "__main__":
    main()
