"""Bus Breakdown Management Service (Phase 4).

Provides full lifecycle management for vehicle mechanical breakdowns:
REPORTED -> CONFIRMED -> UNDER_REPAIR -> AVAILABLE.
Coordinates database persistence, alert creation, vehicle operational status,
immediate simulation halt/resume, and replacement bus candidate evaluation.
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Dict, Any
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.bus import Bus
from app.models.route import Route
from app.models.bus_position import BusPosition
from app.models.notification import Notification
from app.models.bus_breakdown import BusBreakdown
from app.schemas.breakdown import (
    BreakdownReportRequest,
    BreakdownStatusUpdateRequest,
    BreakdownResponse,
    BreakdownSummaryResponse,
    ReplacementCandidateResponse,
)
from app.schemas.optimization import BusBrief, RouteBrief
from app.services.load_intelligence import LoadIntelligenceService

logger = logging.getLogger("smartbus.breakdown")


class BreakdownService:
    """Manages breakdown incident lifecycle, fleet unavailability, and replacement planning."""

    @classmethod
    def report_breakdown(
        cls, db: Session, request: BreakdownReportRequest
    ) -> BreakdownResponse:
        """Report a bus breakdown incident and immediately remove the vehicle from service."""
        if db is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database connection unavailable",
            )

        now = datetime.now(timezone.utc)

        # 1. Resolve bus
        bus: Optional[Bus] = None
        if request.bus_id:
            bus = db.query(Bus).filter(Bus.id == request.bus_id).first()
        elif request.bus_number:
            bus = db.query(Bus).filter(Bus.bus_number == request.bus_number.strip().upper()).first()

        if not bus:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Bus not found (id={request.bus_id}, number={request.bus_number}).",
            )

        # 2. Check if bus already has an active breakdown incident
        existing_active = (
            db.query(BusBreakdown)
            .filter(
                BusBreakdown.bus_id == bus.id,
                BusBreakdown.status.in_(("REPORTED", "CONFIRMED", "UNDER_REPAIR")),
            )
            .order_by(BusBreakdown.created_at.desc())
            .first()
        )
        if existing_active:
            # Update notes or return existing
            if request.notes:
                existing_active.notes = (existing_active.notes or "") + f" | Update: {request.notes}"
                db.commit()
                db.refresh(existing_active)
            return BreakdownResponse.model_validate(existing_active)

        # 3. Resolve route
        route_id = request.route_id or bus.current_route_id
        route = db.query(Route).filter(Route.id == route_id).first() if route_id else None
        route_number = request.route_number or (route.route_number if route else None)

        # 4. Resolve location coordinates
        lat = request.latitude
        lon = request.longitude
        loc_name = request.location_name

        if lat is None or lon is None:
            # Check latest recorded GPS position
            latest_pos = (
                db.query(BusPosition)
                .filter(BusPosition.bus_id == bus.id)
                .order_by(BusPosition.timestamp.desc(), BusPosition.id.desc())
                .first()
            )
            if latest_pos and latest_pos.latitude is not None:
                lat = latest_pos.latitude
                lon = latest_pos.longitude
                loc_name = loc_name or f"Corridor Stop near GPS ({round(lat, 4)}, {round(lon, 4)})"
            elif route and route.stops:
                origin_stop = sorted(route.stops, key=lambda s: s.sequence_order)[0]
                lat = origin_stop.latitude
                lon = origin_stop.longitude
                loc_name = loc_name or f"{origin_stop.name} (Route {route.route_number})"
            else:
                lat = 11.0168
                lon = 76.9558
                loc_name = loc_name or "Coimbatore Transit Central"

        clean_status = (request.status or "REPORTED").strip().upper()
        if clean_status not in ("REPORTED", "CONFIRMED"):
            clean_status = "REPORTED"

        dispatcher = (request.dispatcher_id or "DISPATCHER-1").strip()
        source = (request.source or "LIVE").strip().upper()

        # 5. Create breakdown record
        incident = BusBreakdown(
            bus_id=bus.id,
            bus_number=bus.bus_number,
            route_id=route_id,
            route_number=route_number,
            latitude=lat,
            longitude=lon,
            location_name=loc_name,
            status=clean_status,
            severity=(request.severity or "HIGH").strip().upper(),
            notes=request.notes.strip() if request.notes else None,
            source=source,
            reported_by=dispatcher,
            reported_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(incident)

        # 6. Mark bus status as BROKEN_DOWN in database
        bus.status = "BROKEN_DOWN"
        bus.updated_at = now

        # 7. Create notification alert
        try:
            notif = Notification(
                alert_type="BUS_BREAKDOWN",
                severity="CRITICAL" if incident.severity == "CRITICAL" else "HIGH",
                title=f"Vehicle Breakdown: Bus {bus.bus_number}",
                description=(
                    f"Bus {bus.bus_number} experienced mechanical failure on Route {route_number or 'UNKNOWN'} "
                    f"at {loc_name}. Reported by {dispatcher}. Vehicle halted and taken out of active service."
                ),
                source=source,
                status="ACTIVE",
                dedup_key=f"BREAKDOWN_{bus.bus_number}_{now.timestamp()}",
                route_id=route_id,
                bus_id=bus.id,
            )
            db.add(notif)
        except Exception as e:
            logger.warning(f"Could not emit breakdown notification: {e}")

        db.commit()
        db.refresh(incident)

        # 8. Immediately halt vehicle in authoritative in-memory simulator
        try:
            from app.simulator.manager import simulation_manager
            simulation_manager.notify_bus_breakdown(
                bus_id=bus.id,
                is_broken=True,
                notes=request.notes or "Mechanical fault reported",
            )
        except Exception as e:
            logger.warning(f"Could not notify simulation manager of breakdown: {e}")

        logger.info(f"[BREAKDOWN] Bus {bus.bus_number} reported broken down on Route {route_number}.")
        return BreakdownResponse.model_validate(incident)

    @classmethod
    def update_status(
        cls, db: Session, incident_id: int, request: BreakdownStatusUpdateRequest
    ) -> BreakdownResponse:
        """Advance breakdown lifecycle: REPORTED -> CONFIRMED -> UNDER_REPAIR -> AVAILABLE."""
        if db is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database connection unavailable",
            )

        incident = db.query(BusBreakdown).filter(BusBreakdown.id == incident_id).first()
        if not incident:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Breakdown incident #{incident_id} not found.",
            )

        target_status = (request.status or "").strip().upper()
        valid_statuses = {"REPORTED", "CONFIRMED", "UNDER_REPAIR", "AVAILABLE"}
        if target_status not in valid_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status '{request.status}'. Must be one of: {', '.join(sorted(valid_statuses))}.",
            )

        now = datetime.now(timezone.utc)
        dispatcher = (request.dispatcher_id or "DISPATCHER-1").strip()
        bus = db.query(Bus).filter(Bus.id == incident.bus_id).first()

        incident.status = target_status
        incident.updated_at = now
        if request.notes:
            incident.notes = (incident.notes or "") + f" | [{target_status}] {request.notes}"

        # Handle recovery: status == AVAILABLE
        if target_status == "AVAILABLE":
            incident.recovered_at = now
            incident.recovered_by = dispatcher
            if bus:
                bus.status = "ACTIVE"
                bus.updated_at = now

            # Emit recovery notification
            try:
                notif = Notification(
                    alert_type="FLEET_RECOVERY",
                    severity="INFO",
                    title=f"Vehicle Repaired & Restored: Bus {incident.bus_number}",
                    description=(
                        f"Bus {incident.bus_number} repairs completed and verified by {dispatcher}. "
                        f"Vehicle restored to ACTIVE operational service on Route {incident.route_number or 'assigned corridor'}."
                    ),
                    source=incident.source,
                    status="RESOLVED",
                    dedup_key=f"RECOVERY_{incident.bus_number}_{now.timestamp()}",
                    route_id=incident.route_id,
                    bus_id=incident.bus_id,
                )
                db.add(notif)
            except Exception:
                pass

            # Resume movement in simulation manager
            try:
                from app.simulator.manager import simulation_manager
                simulation_manager.notify_bus_breakdown(
                    bus_id=incident.bus_id,
                    is_broken=False,
                    notes="Vehicle repaired and returned to service",
                )
            except Exception:
                pass

            logger.info(f"[BREAKDOWN] Bus {incident.bus_number} marked AVAILABLE and restored to service.")
        elif target_status == "UNDER_REPAIR":
            if bus:
                bus.status = "MAINTENANCE"
                bus.updated_at = now
            logger.info(f"[BREAKDOWN] Bus {incident.bus_number} advanced to UNDER_REPAIR.")
        elif target_status == "CONFIRMED":
            if bus:
                bus.status = "BROKEN_DOWN"
                bus.updated_at = now
            logger.info(f"[BREAKDOWN] Bus {incident.bus_number} confirmed as BROKEN_DOWN.")

        db.commit()
        db.refresh(incident)
        return BreakdownResponse.model_validate(incident)

    @classmethod
    def get_breakdowns(
        cls, db: Session, active_only: bool = False
    ) -> List[BreakdownResponse]:
        """Fetch all breakdown records or active only."""
        if db is None:
            return []

        query = db.query(BusBreakdown)
        if active_only:
            query = query.filter(BusBreakdown.status.in_(("REPORTED", "CONFIRMED", "UNDER_REPAIR")))
        incidents = query.order_by(BusBreakdown.created_at.desc(), BusBreakdown.id.desc()).all()
        return [BreakdownResponse.model_validate(i) for i in incidents]

    @classmethod
    def get_breakdown_summary(cls, db: Session) -> BreakdownSummaryResponse:
        """Consolidated overview of fleet availability, breakdowns, and lost capacity."""
        if db is None:
            return BreakdownSummaryResponse(
                total_breakdowns=0,
                active_breakdowns=0,
                under_repair_count=0,
                recovered_count=0,
                affected_routes=[],
                fleet_availability_pct=100.0,
                total_capacity_lost=0,
                incidents=[],
            )

        all_incidents = db.query(BusBreakdown).order_by(BusBreakdown.created_at.desc()).all()
        active = [i for i in all_incidents if i.status in ("REPORTED", "CONFIRMED", "UNDER_REPAIR")]
        under_repair = [i for i in active if i.status == "UNDER_REPAIR"]
        recovered = [i for i in all_incidents if i.status == "AVAILABLE"]

        all_buses = db.query(Bus).all()
        total_buses = len(all_buses) or 12
        broken_bus_ids = {i.bus_id for i in active}

        # Calculate lost capacity
        lost_capacity = sum(b.capacity for b in all_buses if b.id in broken_bus_ids)
        operational_count = max(0, total_buses - len(broken_bus_ids))
        availability_pct = round((operational_count / total_buses) * 100.0, 1)

        affected_routes = sorted(
            list({i.route_number for i in active if i.route_number})
        )

        return BreakdownSummaryResponse(
            total_breakdowns=len(all_incidents),
            active_breakdowns=len(active),
            under_repair_count=len(under_repair),
            recovered_count=len(recovered),
            affected_routes=affected_routes,
            fleet_availability_pct=availability_pct,
            total_capacity_lost=lost_capacity,
            incidents=[BreakdownResponse.model_validate(i) for i in active],
        )

    @classmethod
    def get_replacement_candidates(
        cls, db: Session, broken_bus_id: int
    ) -> ReplacementCandidateResponse:
        """Evaluate feasible donor buses to replace a broken-down vehicle (Phase 4)."""
        bus = db.query(Bus).filter(Bus.id == broken_bus_id).first()
        if not bus:
            raise HTTPException(status_code=404, detail=f"Bus ID {broken_bus_id} not found.")

        route_id = bus.current_route_id
        route = db.query(Route).filter(Route.id == route_id).first() if route_id else None
        route_number = route.route_number if route else "UNKNOWN"

        bus_intel_list = LoadIntelligenceService.get_bus_intelligence(db)
        route_intel_list = LoadIntelligenceService.get_route_intelligence_from_buses(db, bus_intel_list)

        candidate_buses: List[BusBrief] = []
        eligible_donor_routes: List[RouteBrief] = []
        binding_constraints: List[str] = []

        all_db_buses = {b.id: b for b in db.query(Bus).all()}

        # Active breakdowns to exclude
        active_breakdown_bus_ids = {
            bb.bus_id
            for bb in db.query(BusBreakdown)
            .filter(BusBreakdown.status.in_(("REPORTED", "CONFIRMED", "UNDER_REPAIR")))
            .all()
        }

        # Evaluate routes that could donate a replacement vehicle
        for r_intel in route_intel_list:
            if r_intel.route_id == route_id:
                continue

            # Minimum coverage constraint: donor route must retain at least 1 operational bus
            operational_on_route = [
                b for b in bus_intel_list
                if b.route_id == r_intel.route_id
                and b.bus_id not in active_breakdown_bus_ids
                and all_db_buses.get(b.bus_id, Bus()).status in ("ACTIVE", "IDLE", "IN_SERVICE")
            ]

            if len(operational_on_route) <= 1:
                binding_constraints.append(
                    f"Route {r_intel.route_number} has only {len(operational_on_route)} active bus(es); "
                    f"donating a replacement would leave route unserviced (minimum coverage bound)."
                )
                continue

            if r_intel.load_factor >= 0.80:
                binding_constraints.append(
                    f"Route {r_intel.route_number} is experiencing {r_intel.status} passenger demand "
                    f"({round(r_intel.load_factor * 100, 1)}% load); cannot donate without severe degradation."
                )
                continue

            eligible_donor_routes.append(
                RouteBrief(
                    route_id=r_intel.route_id,
                    route_number=r_intel.route_number,
                    name=r_intel.route_name,
                    load_factor=r_intel.load_factor,
                    status=r_intel.status,
                )
            )

            for b_intel in operational_on_route:
                if b_intel.available_seats > 0 and b_intel.load_factor < 0.80:
                    candidate_buses.append(
                        BusBrief(
                            bus_id=b_intel.bus_id,
                            bus_number=b_intel.bus_number,
                            capacity=b_intel.capacity,
                            current_occupancy=b_intel.passenger_count,
                            available_capacity=b_intel.available_seats,
                            load_factor=b_intel.load_factor,
                        )
                    )

        # Select best replacement if available
        rec_bus_id = None
        rec_bus_num = None
        rec_src_route = None
        explanation = ""

        from app.services.weather import WeatherService
        weather_obs = WeatherService.get_current_weather()
        travel_mult = getattr(weather_obs, "travel_time_multiplier", 1.0) or 1.0

        if candidate_buses:
            # Sort by highest available seats, then lowest occupancy
            candidate_buses.sort(key=lambda b: (-b.available_capacity, b.current_occupancy))
            best = candidate_buses[0]
            rec_bus_id = best.bus_id
            rec_bus_num = best.bus_number
            db_b = all_db_buses.get(best.bus_id)
            if db_b and db_b.current_route:
                rec_src_route = db_b.current_route.route_number

            nominal_min = 6.0
            weather_min = round(nominal_min * travel_mult, 1)

            explanation = (
                f"Recommended replacement: Bus {rec_bus_num} from Route {rec_src_route or 'donor corridor'} "
                f"possesses {best.available_capacity} available seats to offset Bus {bus.bus_number}'s {bus.capacity} lost capacity. "
                f"Est. transfer arrival: ~{weather_min} min ({weather_obs.condition} weather, {travel_mult}x multiplier)."
            )
        else:
            explanation = (
                f"No feasible replacement bus currently available without violating minimum coverage (>=1 bus/route) "
                f"or exceeding 80% load factor on remaining corridors ({weather_obs.condition} weather conditions active)."
            )

        return ReplacementCandidateResponse(
            broken_bus_id=bus.id,
            broken_bus_number=bus.bus_number,
            route_id=route_id,
            route_number=route_number,
            capacity_lost=bus.capacity,
            candidate_donor_buses=candidate_buses,
            eligible_donor_routes=eligible_donor_routes,
            recommended_bus_id=rec_bus_id,
            recommended_bus_number=rec_bus_num,
            recommended_source_route=rec_src_route,
            binding_constraints=binding_constraints,
            explanation=explanation,
        )
