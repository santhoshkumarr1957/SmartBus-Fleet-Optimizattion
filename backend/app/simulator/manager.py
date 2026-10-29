"""Simulation Manager Module for SmartBus / TRANSIGHT.

Authoritative singleton simulation manager that orchestrates the transit fleet
progression, dynamic demand profiles (LOW, NORMAL, HIGH), simulation speed (1x, 2x, 5x),
and safe lifecycle transitions (Start, Pause, Resume, Stop, Reset).
"""
import time
import uuid
import logging
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.simulator.runner import SimulatorRunner

logger = logging.getLogger("smartbus.simulation_manager")


ROUTE_METADATA: Dict[int, Dict[str, Any]] = {
    1: {"number": "101", "name": "Gandhipuram – Avinashi Road Express"},
    2: {"number": "202", "name": "Saibaba Colony – Railway Station Loop"},
    3: {"number": "303", "name": "Ukkadam – Trichy Road – Singanallur"},
    4: {"number": "404", "name": "Gandhipuram – Singanallur Express"},
    5: {"number": "505", "name": "Gandhipuram – Ukkadam Direct"},
    6: {"number": "606", "name": "Gandhipuram – Peelamedu – Hope College Shuttle"},
}


class SimulationManager:
    """Authoritative singleton owner for transit bus simulation lifecycle and demand control."""

    _instance: Optional["SimulationManager"] = None
    _lock = threading.Lock()

    def __init__(self):
        self.runner = SimulatorRunner(scenario="normal", interval_seconds=4.0)
        self.is_running = False
        self.is_paused = False
        self.scenario = "normal"  # "low_demand", "normal", "high_demand"
        self.speed = 1  # 1, 2, or 5
        self.tick_count = 0
        self.started_at: Optional[datetime] = None
        self.last_tick_time: Optional[datetime] = None

        # Route-specific independent demand profiles (authoritative state)
        self.route_demands: Dict[str, str] = {
            "101": "NORMAL",
            "202": "NORMAL",
            "303": "NORMAL",
            "404": "NORMAL",
            "505": "NORMAL",
            "606": "NORMAL",
        }
        self.runner.route_demands = dict(self.route_demands)

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._events: deque = deque(maxlen=80)
        self._last_route_statuses: Dict[str, str] = {}

        # Database and operational resilience health indicators
        self.is_db_connected: bool = False
        self.initialization_error: Optional[str] = None
        self.weather_speed_factor: float = 1.0

        # Log initial system ready event
        self._record_event(
            event_type="SYSTEM",
            level="info",
            message="Traffic Simulation Engine initialized for Coimbatore transit network.",
        )

    @classmethod
    def get_instance(cls) -> "SimulationManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _record_event(self, event_type: str, level: str, message: str) -> Dict[str, Any]:
        """Record an in-memory simulation event entry."""
        evt = {
            "id": f"evt-{uuid.uuid4().hex[:8]}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            "level": level,  # info, warning, critical, success
            "message": message,
        }
        self._events.appendleft(evt)
        return evt

    @property
    def active_profile(self) -> str:
        """Return standardized user-facing profile string: LOW, NORMAL, HIGH, or CUSTOM."""
        profiles = set(self.route_demands.values())
        if len(profiles) == 1:
            return next(iter(profiles))
        return "CUSTOM"

    def _resolve_route(self, route_id_or_number: Any) -> Tuple[int, str, str]:
        """Resolve route identifier (integer ID or string route number) to (id, number, name)."""
        key_str = str(route_id_or_number).strip()

        # 1. Check in runner cached routes if available
        if self.runner and getattr(self.runner, "routes", None):
            for r in self.runner.routes:
                if str(r.id) == key_str or str(r.route_number).strip() == key_str:
                    return r.id, str(r.route_number).strip(), r.name

        # 2. Check predefined Coimbatore network metadata
        for r_id, meta in ROUTE_METADATA.items():
            if str(r_id) == key_str or meta["number"] == key_str:
                return r_id, meta["number"], meta["name"]

        raise KeyError(f"Route '{route_id_or_number}' not found. Supported routes: 101, 202, 303, 404, 505, 606.")

    def set_route_demand(self, route_id_or_number: Any, profile: str) -> Dict[str, Any]:
        """Configure independent demand profile (LOW, NORMAL, HIGH) for a specific route corridor."""
        clean = (profile or "").strip().upper()
        if clean not in ("LOW", "NORMAL", "HIGH"):
            raise ValueError(f"Invalid demand profile '{profile}'. Must be 'LOW', 'NORMAL', or 'HIGH'.")

        route_id, route_number, route_name = self._resolve_route(route_id_or_number)

        with self._lock:
            prev = self.route_demands.get(route_number, "NORMAL")
            self.route_demands[route_number] = clean
            self.runner.route_demands[route_number] = clean

            # Immediately synchronize active bus simulators serving this route
            for bus_sim in self.runner.bus_simulators:
                active_r = bus_sim.active_route_number or bus_sim.route_number
                if active_r == route_number:
                    bus_sim.set_demand_profile(clean)

            level = "critical" if clean == "HIGH" else ("info" if clean == "NORMAL" else "success")
            self._record_event(
                event_type="DEMAND_CHANGE",
                level=level,
                message=f"Route {route_number} ({route_name}) demand set to {clean} DEMAND (was {prev}).",
            )
            logger.info(f"[SIMULATOR] Route {route_number} demand profile updated: {prev} -> {clean}")

            return {
                "route_id": route_id,
                "route_number": route_number,
                "route_name": route_name,
                "demand_profile": clean,
                "status": self.get_status(),
                "message": f"Route {route_number} demand profile updated to {clean} DEMAND successfully.",
            }

    def get_route_demands(self) -> List[Dict[str, Any]]:
        """Return demand profiles for all 6 Coimbatore routes in standard order."""
        items: List[Dict[str, Any]] = []
        for r_id in sorted(ROUTE_METADATA.keys()):
            meta = ROUTE_METADATA[r_id]
            r_num = meta["number"]
            r_name = meta["name"]
            if self.runner and getattr(self.runner, "routes", None):
                matched = next((r for r in self.runner.routes if str(r.route_number) == r_num), None)
                if matched:
                    r_id = matched.id
                    r_name = matched.name

            items.append({
                "route_id": r_id,
                "route_number": r_num,
                "route_name": r_name,
                "demand_profile": self.route_demands.get(r_num, "NORMAL"),
            })
        return items

    def get_route_demand(self, route_id_or_number: Any) -> Dict[str, Any]:
        """Return demand profile for a specific route."""
        route_id, route_number, route_name = self._resolve_route(route_id_or_number)
        return {
            "route_id": route_id,
            "route_number": route_number,
            "route_name": route_name,
            "demand_profile": self.route_demands.get(route_number, "NORMAL"),
        }

    def get_status(self) -> Dict[str, Any]:
        """Return comprehensive status of the simulation engine."""
        now_utc = datetime.now(timezone.utc)
        if self.is_running and not self.is_paused:
            status_str = "RUNNING"
        elif self.is_running and self.is_paused:
            status_str = "PAUSED"
        else:
            status_str = "STOPPED"

        elapsed_sec = 0
        if self.started_at:
            elapsed_sec = int((now_utc - self.started_at).total_seconds())

        is_initialized = bool(self.runner and self.runner.bus_simulators)
        return {
            "status": status_str,
            "active_profile": self.active_profile,
            "scenario": self.scenario,
            "speed": self.speed,
            "interval_seconds": self.runner.interval_seconds,
            "effective_interval": round(self.runner.interval_seconds / self.speed, 2),
            "is_running": self.is_running,
            "is_paused": self.is_paused,
            "is_initialized": is_initialized,
            "db_connected": self.is_db_connected,
            "weather_speed_factor": self.weather_speed_factor,
            "initialization_error": self.initialization_error,
            "tick_count": self.tick_count,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "elapsed_seconds": elapsed_sec,
            "last_updated": (self.last_tick_time or now_utc).isoformat(),
            "total_buses": len(self.runner.bus_simulators) if self.runner.bus_simulators else 12,
            "total_routes": 6,
            "route_demands": dict(self.route_demands),
            "route_demand_list": self.get_route_demands(),
            "message": f"Simulation is {status_str.lower()} under {self.active_profile} DEMAND profile at {self.speed}x speed.",
        }

    def get_profiles(self) -> List[Dict[str, Any]]:
        """Return available demand profiles with active indicator."""
        current = self.active_profile
        return [
            {
                "id": "LOW",
                "name": "Low Demand",
                "description": "Off-peak travel conditions with lower passenger arrivals, ample spare capacity, and lower load factors (20%–40%).",
                "is_active": current == "LOW",
                "tag": "Off-Peak",
            },
            {
                "id": "NORMAL",
                "name": "Normal Demand",
                "description": "Balanced urban transit operations with realistic passenger arrival and departure rates (48%–72% load factor).",
                "is_active": current == "NORMAL",
                "tag": "Standard",
            },
            {
                "id": "HIGH",
                "name": "High Demand",
                "description": "Peak-hour congestion conditions where high-demand corridors (101, 404) reach heavy or critical loads, prompting reallocation recommendations.",
                "is_active": current == "HIGH",
                "tag": "Peak Hours",
            },
        ]

    def get_events(self, limit: int = 40) -> List[Dict[str, Any]]:
        """Return recent simulation events."""
        return list(self._events)[:limit]

    def start(self) -> Dict[str, Any]:
        """Start or resume the simulation progression thread."""
        with self._lock:
            if self.is_running and not self.is_paused:
                return self.get_status()

            if self.is_running and self.is_paused:
                self.is_paused = False
                self._record_event(
                    event_type="LIFECYCLE",
                    level="info",
                    message=f"Simulation resumed under {self.active_profile} DEMAND.",
                )
                return self.get_status()

            # Attempt runner setup safely without crashing start()
            if SessionLocal is not None:
                try:
                    db = SessionLocal()
                    try:
                        self.runner.scenario = self.scenario
                        success = self.runner.setup(db)
                        if success:
                            self.is_db_connected = True
                            self.initialization_error = None
                        else:
                            self.initialization_error = "No active routes found in database during setup."
                    finally:
                        db.close()
                except Exception as exc:
                    from app.db.session import sanitize_db_error
                    clean_err = sanitize_db_error(str(exc))
                    self.is_db_connected = False
                    self.initialization_error = clean_err
                    logger.warning(
                        f"[SIMULATOR] Initial database setup encountered error: {clean_err}. "
                        f"Background worker will self-heal and retry connecting automatically."
                    )

            if self._thread and self._thread.is_alive():
                self._stop_event.set()
                self._thread.join(timeout=1.0)

            self.is_running = True
            self.is_paused = False
            self._stop_event.clear()
            if not self.started_at:
                self.started_at = datetime.now(timezone.utc)

            self._thread = threading.Thread(target=self._run_loop, daemon=True, name="TransitSimWorker")
            self._thread.start()

            status_msg = (
                f"Simulation started: 12 buses active across 6 corridors under {self.active_profile} DEMAND."
                if self.runner.bus_simulators
                else f"Simulation worker started (waiting for database connection: {self.initialization_error or 'connecting'})."
            )
            self._record_event(
                event_type="LIFECYCLE",
                level="success" if self.runner.bus_simulators else "warning",
                message=status_msg,
            )
            return self.get_status()

    def pause(self) -> Dict[str, Any]:
        """Pause progression temporarily without corrupting positions or passenger counts."""
        with self._lock:
            if not self.is_running or self.is_paused:
                return self.get_status()

            self.is_paused = True
            self._record_event(
                event_type="LIFECYCLE",
                level="warning",
                message="Simulation paused. Fleet positions and passenger loads frozen.",
            )
            return self.get_status()

    def resume(self) -> Dict[str, Any]:
        """Resume progression from paused state."""
        with self._lock:
            if not self.is_running:
                return self.start()

            if self.is_paused:
                self.is_paused = False
                self._record_event(
                    event_type="LIFECYCLE",
                    level="info",
                    message="Simulation resumed from paused state.",
                )
            return self.get_status()

    def stop(self) -> Dict[str, Any]:
        """Stop simulation progression cleanly."""
        with self._lock:
            if not self.is_running:
                return self.get_status()

            self.is_running = False
            self.is_paused = False
            self._stop_event.set()

            self._record_event(
                event_type="LIFECYCLE",
                level="warning",
                message="Simulation stopped cleanly by operator.",
            )
            return self.get_status()

    def set_demand(self, profile: str) -> Dict[str, Any]:
        """Apply a network-wide demand preset (LOW, NORMAL, HIGH) across all 6 corridors."""
        clean = (profile or "").strip().upper()
        if clean not in ("LOW", "NORMAL", "HIGH"):
            raise ValueError(f"Invalid demand profile '{profile}'. Must be 'LOW', 'NORMAL', or 'HIGH'.")

        scenario_map = {
            "LOW": "low_demand",
            "NORMAL": "normal",
            "HIGH": "high_demand",
        }
        target_scenario = scenario_map[clean]

        with self._lock:
            prev_profile = self.active_profile
            self.scenario = target_scenario
            self.runner.scenario = target_scenario

            # Apply to all routes in authoritative dictionary
            for r_num in self.route_demands:
                self.route_demands[r_num] = clean
            self.runner.route_demands = dict(self.route_demands)

            # Immediately synchronize all active bus simulators
            for bus_sim in self.runner.bus_simulators:
                bus_sim.set_demand_profile(clean)

            level = "critical" if clean == "HIGH" else ("info" if clean == "NORMAL" else "success")
            self._record_event(
                event_type="DEMAND_CHANGE",
                level=level,
                message=f"Global demand preset applied: all 6 corridors set to {clean} DEMAND (was {prev_profile}).",
            )
            logger.info(f"[SIMULATOR] Global demand preset applied: {clean} ({target_scenario})")
            return self.get_status()

    def set_speed(self, speed: int) -> Dict[str, Any]:
        """Update simulation progression speed multiplier (1x, 2x, 5x)."""
        if speed not in (1, 2, 5):
            raise ValueError(f"Invalid speed {speed}. Supported speeds: 1, 2, 5.")

        with self._lock:
            self.speed = speed
            self._record_event(
                event_type="SPEED_CHANGE",
                level="info",
                message=f"Simulation speed updated to {speed}x.",
            )
            return self.get_status()

    def reset(self) -> Dict[str, Any]:
        """Safely reset simulation fleet positions and passenger loads to baseline.

        Guaranteed non-destructive: keeps all dispatcher reviews, reallocations, and notification records.
        """
        with self._lock:
            was_running = self.is_running and not self.is_paused
            db = SessionLocal()
            try:
                self.runner.setup(db)
                self.tick_count = 0
                self.started_at = datetime.now(timezone.utc)
                self.last_tick_time = self.started_at
                self._last_route_statuses.clear()
            finally:
                db.close()

            self._record_event(
                event_type="RESET",
                level="info",
                message="Fleet positions and passenger loads reset safely to initial route terminals.",
            )
            return self.get_status()

    def _run_loop(self) -> None:
        """Continuous simulation execution loop executed in background daemon thread with self-healing DB connection."""
        logger.info("[SIMULATOR] Background worker loop started.")
        while self.is_running and not self._stop_event.is_set():
            if self.is_paused:
                time.sleep(0.4)
                continue

            # Self-healing setup if initial DB connection failed during startup
            if not self.runner.bus_simulators:
                if SessionLocal is not None:
                    try:
                        db = SessionLocal()
                        try:
                            self.runner.scenario = self.scenario
                            success = self.runner.setup(db)
                            if success:
                                self.is_db_connected = True
                                self.initialization_error = None
                                logger.info(
                                    f"[SIMULATOR] Database setup succeeded! {len(self.runner.bus_simulators)} buses initialized."
                                )
                                self._record_event(
                                    event_type="LIFECYCLE",
                                    level="success",
                                    message=f"Simulation initialized: {len(self.runner.bus_simulators)} buses active across 6 corridors.",
                                )
                        finally:
                            db.close()
                    except Exception as exc:
                        from app.db.session import sanitize_db_error
                        clean_err = sanitize_db_error(str(exc))
                        self.is_db_connected = False
                        self.initialization_error = clean_err
                        logger.warning(f"[SIMULATOR] Setup retry failed: {clean_err}. Retrying in 4s.")
                self._stop_event.wait(4.0)
                continue

            base_interval = self.runner.interval_seconds  # e.g. 4.0s
            effective_sleep = max(0.2, base_interval / self.speed)

            tick_start = time.time()
            if SessionLocal is not None:
                db = SessionLocal()
                try:
                    self.runner.step(db)
                    self.tick_count += 1
                    self.last_tick_time = datetime.now(timezone.utc)
                    self.is_db_connected = True
                    self._audit_route_loads(db)
                except Exception as e:
                    from app.db.session import sanitize_db_error
                    logger.error(f"[SIMULATOR] Error in simulation loop tick: {sanitize_db_error(str(e))}")
                    self.is_db_connected = False
                finally:
                    db.close()

            step_duration = time.time() - tick_start
            sleep_time = max(0.05, effective_sleep - step_duration)
            self._stop_event.wait(sleep_time)

        logger.info("[SIMULATOR] Background worker loop terminated.")

    def set_weather_speed_factor(self, factor: float) -> None:
        """Dynamically update weather speed multiplier across all active simulated buses."""
        with self._lock:
            self.weather_speed_factor = float(factor)
            if self.runner and self.runner.bus_simulators:
                for b in self.runner.bus_simulators:
                    b.set_weather_speed_factor(factor)
            logger.info(f"[SIMULATOR] Applied weather speed factor {factor} to all active buses.")

    def get_active_buses_telemetry(self) -> Optional[List[Dict[str, Any]]]:
        """Return authoritative bus telemetry directly from active bus simulators.

        Provides zero-latency, moving coordinates and passenger loads matching
        the persisted records.
        """
        if not self.runner.bus_simulators:
            return None

        telemetry: List[Dict[str, Any]] = []
        now = datetime.now(timezone.utc)
        for b in self.runner.bus_simulators:
            in_transfer = b.is_in_transfer()
            transfer_status = "IN_PROGRESS" if in_transfer else "IDLE"
            target_route_id = (
                b.transfer_state.get("target_route_id") if in_transfer and b.transfer_state else None
            )
            target_route_number = (
                b.transfer_state.get("target_route_number") if in_transfer and b.transfer_state else None
            )

            # Home route derived from fleet convention (e.g. 101A -> 101)
            home_num = "".join([c for c in b.bus_number if c.isdigit()]) or b.assigned_route_number

            telemetry.append({
                "bus_id": b.bus_id,
                "bus_number": b.bus_number,
                "route_id": b.assigned_route_id,
                "route_number": b.assigned_route_number,
                "home_route_id": b.route_id,
                "home_route_number": home_num,
                "assigned_route_id": b.assigned_route_id,
                "assigned_route_number": b.assigned_route_number,
                "active_route_id": b.active_route_id,
                "active_route_number": b.active_route_number,
                "latitude": b.latitude,
                "longitude": b.longitude,
                "speed": b.speed,
                "heading": b.heading,
                "direction": getattr(b, "direction_name", "FORWARD"),
                "passenger_count": b.current_load,
                "capacity": b.capacity,
                "load_factor": b.load_factor,
                "is_transferring": in_transfer,
                "transfer_status": transfer_status,
                "target_route_id": target_route_id,
                "target_route_number": target_route_number,
                "is_broken_down": getattr(b, "is_broken_down", False),
                "status": "BROKEN_DOWN" if getattr(b, "is_broken_down", False) else ("IN_TRANSFER" if in_transfer else "ACTIVE"),
                "timestamp": now,
            })
        return telemetry

    def get_active_routes_telemetry(self) -> Optional[List[Dict[str, Any]]]:
        """Aggregate route-level statistics directly from authoritative bus simulators."""
        if not self.runner.bus_simulators:
            return None

        # Group by route_number
        buses_by_route: Dict[str, List[Any]] = {}
        for b in self.runner.bus_simulators:
            r_num = b.assigned_route_number or b.route_number
            buses_by_route.setdefault(r_num, []).append(b)

        results: List[Dict[str, Any]] = []
        # Predefined Coimbatore routes in order
        route_meta = [
            ("101", 1),
            ("202", 2),
            ("303", 3),
            ("404", 4),
            ("505", 5),
            ("606", 6),
        ]

        routes_by_num = {r.route_number: r for r in getattr(self.runner, "routes", [])}

        for r_num, default_id in route_meta:
            buses = buses_by_route.get(r_num, [])
            matched_r = routes_by_num.get(r_num)
            r_id = buses[0].assigned_route_id if buses and buses[0].assigned_route_id else (matched_r.id if matched_r else default_id)
            operational_buses = [b for b in buses if not getattr(b, "is_broken_down", False)]
            tot_p = sum(b.current_load for b in operational_buses)
            tot_c = sum(b.capacity for b in operational_buses)
            lf = round(tot_p / tot_c, 4) if tot_c > 0 else (1.0 if buses and tot_c == 0 else 0.0)

            if tot_c == 0 and buses:
                route_status = "CRITICAL"  # All assigned buses broken down
            elif lf < 0.50:
                route_status = "LOW"
            elif lf < 0.80:
                route_status = "NORMAL"
            elif lf < 1.00:
                route_status = "HIGH"
            else:
                route_status = "CRITICAL"

            results.append({
                "route_id": r_id,
                "route_number": r_num,
                "number_of_buses": len(operational_buses),
                "total_passengers": tot_p,
                "total_capacity": tot_c,
                "load_factor": lf,
                "status": route_status,
                "demand_profile": self.route_demands.get(r_num, "NORMAL"),
            })
        return results

    def notify_bus_breakdown(self, bus_id: int, is_broken: bool, notes: str = "") -> bool:
        """Immediately update in-memory simulator when a bus breakdown or recovery is recorded."""
        with self._lock:
            if not self.runner or not self.runner.bus_simulators:
                return False

            bus_sim = next((b for b in self.runner.bus_simulators if b.bus_id == bus_id), None)
            if not bus_sim:
                return False

            bus_sim.set_breakdown_state(is_broken)
            if is_broken:
                self._record_event(
                    event_type="BUS_BREAKDOWN",
                    level="critical",
                    message=f"Bus {bus_sim.bus_number} marked BROKEN_DOWN and halted at lat {round(bus_sim.latitude, 4)}, lon {round(bus_sim.longitude, 4)}. {notes}".strip(),
                )
            else:
                self._record_event(
                    event_type="FLEET_RECOVERY",
                    level="success",
                    message=f"Bus {bus_sim.bus_number} recovered and returned to active service on Route {bus_sim.assigned_route_number}.",
                )
            return True

    def notify_route_reassignment(
        self,
        bus_id: int,
        target_route_id: int,
        target_route_number: str = "",
        stops: Optional[List[Any]] = None,
    ) -> bool:
        """Immediately update in-memory simulator when a bus is reassigned by dispatcher or optimization."""
        with self._lock:
            if not self.runner or not self.runner.bus_simulators:
                return False

            bus_sim = next((b for b in self.runner.bus_simulators if b.bus_id == bus_id), None)
            if not bus_sim:
                return False

            # Resolve stops from runner's cached routes if not provided
            if not stops and getattr(self.runner, "routes", None):
                tr = next((r for r in self.runner.routes if r.id == target_route_id), None)
                if tr and tr.stops:
                    stops = tr.stops
                    if not target_route_number:
                        target_route_number = tr.route_number

            if not stops:
                # If still not found, fetch from DB
                db = SessionLocal()
                try:
                    from app.models.route import Route
                    from sqlalchemy.orm import joinedload
                    tr = db.query(Route).options(joinedload(Route.stops)).filter(Route.id == target_route_id).first()
                    if tr and tr.stops:
                        stops = tr.stops
                        if not target_route_number:
                            target_route_number = tr.route_number
                finally:
                    db.close()

            if stops:
                logger.info(
                    f"[SIMULATOR] Immediate route reassignment for Bus {bus_sim.bus_number}: "
                    f"Route {bus_sim.route_number} -> Route {target_route_number}"
                )
                success = bus_sim.reassign_route(
                    new_route_id=target_route_id,
                    new_route_number=target_route_number,
                    target_stops=stops,
                )
                if success:
                    self._record_event(
                        event_type="REASSIGNMENT",
                        level="info",
                        message=f"Bus {bus_sim.bus_number} executing transfer from Route {bus_sim.transfer_state.get('source_route_number', '?')} to Route {target_route_number}.",
                    )
                return success
            return False

    def _audit_route_loads(self, db: Optional[Session] = None) -> None:
        """Monitor route load state transitions in-memory with zero database latency."""
        try:
            buses_by_route: Dict[str, List[Any]] = {}
            for b in self.runner.bus_simulators:
                r_num = b.assigned_route_number or b.route_number
                buses_by_route.setdefault(r_num, []).append(b)

            for r_num, buses in buses_by_route.items():
                tot_p = sum(b.current_load for b in buses)
                tot_c = sum(b.capacity for b in buses)
                lf = round(tot_p / tot_c, 4) if tot_c > 0 else 0.0

                if lf < 0.50:
                    curr_status = "LOW"
                elif lf < 0.80:
                    curr_status = "NORMAL"
                elif lf < 1.00:
                    curr_status = "HIGH"
                else:
                    curr_status = "CRITICAL"

                prev_status = self._last_route_statuses.get(r_num)

                if prev_status is not None and prev_status != curr_status:
                    pct = round(lf * 100)
                    free_seats = max(0, tot_c - tot_p)
                    if curr_status in ("HIGH", "CRITICAL"):
                        self._record_event(
                            event_type="ROUTE_LOAD",
                            level="warning" if curr_status == "HIGH" else "critical",
                            message=f"Route {r_num} entered {curr_status} load ({pct}% load, {free_seats} seats free).",
                        )
                    elif curr_status == "NORMAL" and prev_status in ("HIGH", "CRITICAL"):
                        self._record_event(
                            event_type="ROUTE_LOAD",
                            level="success",
                            message=f"Route {r_num} normalized to {curr_status} load ({pct}% load).",
                        )
                    elif curr_status == "LOW" and prev_status != "LOW":
                        self._record_event(
                            event_type="ROUTE_LOAD",
                            level="info",
                            message=f"Route {r_num} transitioned to LOW load ({pct}% load, ample capacity).",
                        )

                self._last_route_statuses[r_num] = curr_status
        except Exception as e:
            logger.debug(f"Non-critical load auditing exception: {e}")


# Global singleton instance
simulation_manager = SimulationManager.get_instance()
