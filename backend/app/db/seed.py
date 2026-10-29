"""Database seeder for SmartBus transit entities (Routes, Stops, Buses).

Populates and localizes transit routes, stops, and buses for Coimbatore, Tamil Nadu, India.
Supports full 6-route and 12-bus transit network with idempotent operations.
"""
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.route import Route
from app.models.stop import Stop
from app.models.bus import Bus
from app.models.bus_position import BusPosition
from app.models.passenger_load import PassengerLoad

logger = logging.getLogger("smartbus.seed")

# Coimbatore, Tamil Nadu Transit Demonstration Network
# 6 distinct corridors connecting key hubs (Gandhipuram, Saibaba Colony, Railway Junction, Ukkadam, Singanallur, Hope College, Peelamedu)
SEED_ROUTES: List[Dict[str, Any]] = [
    {
        "route_number": "101",
        "name": "Gandhipuram – Avinashi Road Express",
        "description": "High-density arterial transit corridor along Avinashi Road connecting Gandhipuram Bus Stand to Peelamedu and Hope College",
        "origin": "Gandhipuram Central Bus Stand",
        "destination": "Hope College",
        "is_active": True,
        "stops": [
            {"name": "Gandhipuram Central Bus Stand", "stop_code": "101-1", "sequence_order": 1, "latitude": 11.0175, "longitude": 76.9675},
            {"name": "Lakshmi Mills Junction", "stop_code": "101-2", "sequence_order": 2, "latitude": 11.0135, "longitude": 76.9830},
            {"name": "Nava India", "stop_code": "101-3", "sequence_order": 3, "latitude": 11.0205, "longitude": 76.9940},
            {"name": "Peelamedu (PSG Tech)", "stop_code": "101-4", "sequence_order": 4, "latitude": 11.0270, "longitude": 77.0060},
            {"name": "Hope College", "stop_code": "101-5", "sequence_order": 5, "latitude": 11.0320, "longitude": 77.0195},
        ],
        "buses": [
            {"bus_number": "101A", "license_plate": "TN-38-N-1011", "capacity": 60, "status": "ACTIVE"},
            {"bus_number": "101B", "license_plate": "TN-38-N-1012", "capacity": 60, "status": "ACTIVE"},
        ],
    },
    {
        "route_number": "202",
        "name": "Saibaba Colony – Railway Station Loop",
        "description": "North-central connector linking Saibaba Colony via Cross Cut Road to Coimbatore Railway Junction and Town Hall",
        "origin": "Saibaba Colony",
        "destination": "Town Hall",
        "is_active": True,
        "stops": [
            {"name": "Saibaba Colony", "stop_code": "202-1", "sequence_order": 1, "latitude": 11.0335, "longitude": 76.9460},
            {"name": "Cross Cut Road", "stop_code": "202-2", "sequence_order": 2, "latitude": 11.0220, "longitude": 76.9600},
            {"name": "Gandhipuram South", "stop_code": "202-3", "sequence_order": 3, "latitude": 11.0150, "longitude": 76.9670},
            {"name": "Coimbatore Railway Junction", "stop_code": "202-4", "sequence_order": 4, "latitude": 10.9980, "longitude": 76.9635},
            {"name": "Town Hall", "stop_code": "202-5", "sequence_order": 5, "latitude": 10.9965, "longitude": 76.9580},
        ],
        "buses": [
            {"bus_number": "202A", "license_plate": "TN-38-N-2021", "capacity": 60, "status": "ACTIVE"},
            {"bus_number": "202B", "license_plate": "TN-38-N-2022", "capacity": 60, "status": "ACTIVE"},
        ],
    },
    {
        "route_number": "303",
        "name": "Ukkadam – Trichy Road – Singanallur",
        "description": "South-eastern transit arterial connecting Ukkadam Bus Terminus via Trichy Road and Ramanathapuram to Singanallur Bus Terminal",
        "origin": "Ukkadam Bus Terminus",
        "destination": "Singanallur Bus Terminus",
        "is_active": True,
        "stops": [
            {"name": "Ukkadam Bus Terminus", "stop_code": "303-1", "sequence_order": 1, "latitude": 10.9885, "longitude": 76.9565},
            {"name": "Town Hall East", "stop_code": "303-2", "sequence_order": 2, "latitude": 10.9975, "longitude": 76.9645},
            {"name": "Sungam Junction", "stop_code": "303-3", "sequence_order": 3, "latitude": 10.9995, "longitude": 76.9850},
            {"name": "Ramanathapuram", "stop_code": "303-4", "sequence_order": 4, "latitude": 11.0000, "longitude": 77.0040},
            {"name": "Singanallur Bus Terminus", "stop_code": "303-5", "sequence_order": 5, "latitude": 10.9990, "longitude": 77.0270},
        ],
        "buses": [
            {"bus_number": "303A", "license_plate": "TN-38-N-3031", "capacity": 60, "status": "ACTIVE"},
            {"bus_number": "303B", "license_plate": "TN-38-N-3032", "capacity": 60, "status": "ACTIVE"},
        ],
    },
    {
        "route_number": "404",
        "name": "Gandhipuram – Singanallur Express",
        "description": "Direct eastern arterial corridor connecting Gandhipuram Central Bus Stand to Singanallur Bus Terminus via Puliakulam and Ramanathapuram",
        "origin": "Gandhipuram Central Bus Stand",
        "destination": "Singanallur Bus Terminus",
        "is_active": True,
        "stops": [
            {"name": "Gandhipuram Central Bus Stand", "stop_code": "404-1", "sequence_order": 1, "latitude": 11.0175, "longitude": 76.9675},
            {"name": "Lakshmi Mills South", "stop_code": "404-2", "sequence_order": 2, "latitude": 11.0115, "longitude": 76.9840},
            {"name": "Puliakulam", "stop_code": "404-3", "sequence_order": 3, "latitude": 11.0040, "longitude": 76.9930},
            {"name": "Ramanathapuram Junction", "stop_code": "404-4", "sequence_order": 4, "latitude": 11.0005, "longitude": 77.0045},
            {"name": "Singanallur Bus Terminus", "stop_code": "404-5", "sequence_order": 5, "latitude": 10.9990, "longitude": 77.0270},
        ],
        "buses": [
            {"bus_number": "404A", "license_plate": "TN-38-N-4041", "capacity": 60, "status": "ACTIVE"},
            {"bus_number": "404B", "license_plate": "TN-38-N-4042", "capacity": 60, "status": "ACTIVE"},
        ],
    },
    {
        "route_number": "505",
        "name": "Gandhipuram – Ukkadam Direct",
        "description": "Central north-south transit connector linking Gandhipuram Central Bus Stand directly to Ukkadam Bus Terminus via Park Gate and Town Hall",
        "origin": "Gandhipuram Central Bus Stand",
        "destination": "Ukkadam Bus Terminus",
        "is_active": True,
        "stops": [
            {"name": "Gandhipuram Central Bus Stand", "stop_code": "505-1", "sequence_order": 1, "latitude": 11.0175, "longitude": 76.9675},
            {"name": "Park Gate / VOC Park", "stop_code": "505-2", "sequence_order": 2, "latitude": 11.0070, "longitude": 76.9680},
            {"name": "Railway Station North", "stop_code": "505-3", "sequence_order": 3, "latitude": 10.9985, "longitude": 76.9640},
            {"name": "Oppanakara Street / Town Hall", "stop_code": "505-4", "sequence_order": 4, "latitude": 10.9935, "longitude": 76.9605},
            {"name": "Ukkadam Bus Terminus", "stop_code": "505-5", "sequence_order": 5, "latitude": 10.9885, "longitude": 76.9565},
        ],
        "buses": [
            {"bus_number": "505A", "license_plate": "TN-38-N-5051", "capacity": 60, "status": "ACTIVE"},
            {"bus_number": "505B", "license_plate": "TN-38-N-5052", "capacity": 60, "status": "ACTIVE"},
        ],
    },
    {
        "route_number": "606",
        "name": "Gandhipuram – Peelamedu – Hope College Shuttle",
        "description": "High-frequency feeder corridor connecting Gandhipuram through Avarampalayam, Peelamedu, and PSG Tech to Hope College",
        "origin": "Gandhipuram Central Bus Stand",
        "destination": "Hope College",
        "is_active": True,
        "stops": [
            {"name": "Gandhipuram Central Bus Stand", "stop_code": "606-1", "sequence_order": 1, "latitude": 11.0175, "longitude": 76.9675},
            {"name": "Avarampalayam Junction", "stop_code": "606-2", "sequence_order": 2, "latitude": 11.0250, "longitude": 76.9810},
            {"name": "New Siddhapudur", "stop_code": "606-3", "sequence_order": 3, "latitude": 11.0275, "longitude": 76.9950},
            {"name": "Peelamedu Station", "stop_code": "606-4", "sequence_order": 4, "latitude": 11.0260, "longitude": 77.0090},
            {"name": "Hope College", "stop_code": "606-5", "sequence_order": 5, "latitude": 11.0320, "longitude": 77.0195},
        ],
        "buses": [
            {"bus_number": "606A", "license_plate": "TN-38-N-6061", "capacity": 60, "status": "ACTIVE"},
            {"bus_number": "606B", "license_plate": "TN-38-N-6062", "capacity": 60, "status": "ACTIVE"},
        ],
    },
]


def seed_transit_data(db: Session, force: bool = False) -> bool:
    """Seed or update transit entities idempotently for Coimbatore network (6 routes, 12 buses).

    Preserves existing operational state, position history, reassignments, and dispatcher reviews.
    """
    if not force:
        active_routes_count = db.query(Route).filter(Route.is_active == True).count()
        active_buses_count = db.query(Bus).filter(Bus.status != "INACTIVE").count()
        if active_routes_count >= len(SEED_ROUTES) and active_buses_count >= 12:
            pos_count = db.query(BusPosition.bus_id).distinct().count()
            if pos_count >= active_buses_count:
                logger.info("Coimbatore transit network already verified (6 routes, 12 buses). Fast startup complete.")
                return False

    logger.info("Verifying / synchronizing Coimbatore transit network (6 routes, 12 buses)...")
    now_utc = datetime.now(timezone.utc)
    changes_made = False

    for r_data in SEED_ROUTES:
        route = db.query(Route).filter(Route.route_number == r_data["route_number"]).first()
        if not route:
            route = Route(
                route_number=r_data["route_number"],
                name=r_data["name"],
                description=r_data["description"],
                origin=r_data["origin"],
                destination=r_data["destination"],
                is_active=r_data["is_active"],
            )
            db.add(route)
            db.flush()
            changes_made = True
            logger.info(f"Created new Route {route.route_number}: {route.name}")
        else:
            # Update existing route metadata in place
            route.name = r_data["name"]
            route.description = r_data["description"]
            route.origin = r_data["origin"]
            route.destination = r_data["destination"]
            route.is_active = r_data["is_active"]
            db.flush()

        # Seed or update stops for route
        existing_stops = {s.sequence_order: s for s in route.stops}
        for s_data in r_data["stops"]:
            seq = s_data["sequence_order"]
            if seq in existing_stops:
                stop = existing_stops[seq]
                stop.name = s_data["name"]
                stop.stop_code = s_data["stop_code"]
                stop.latitude = s_data["latitude"]
                stop.longitude = s_data["longitude"]
            else:
                stop = Stop(
                    route_id=route.id,
                    name=s_data["name"],
                    stop_code=s_data["stop_code"],
                    sequence_order=seq,
                    latitude=s_data["latitude"],
                    longitude=s_data["longitude"],
                )
                db.add(stop)
                changes_made = True

        db.flush()
        sorted_stops = sorted(route.stops, key=lambda s: s.sequence_order)

        # Seed buses for route if not yet existing
        for b_idx, b_data in enumerate(r_data["buses"]):
            existing_bus = db.query(Bus).filter(Bus.bus_number == b_data["bus_number"]).first()
            if not existing_bus:
                bus = Bus(
                    bus_number=b_data["bus_number"],
                    license_plate=b_data["license_plate"],
                    capacity=b_data["capacity"],
                    current_route_id=route.id,
                    status=b_data["status"],
                )
                db.add(bus)
                db.flush()
                changes_made = True
                logger.info(f"Created new Bus {bus.bus_number} on Route {route.route_number}")

                # Initialize initial position and passenger load at a staggered stop on its route
                if sorted_stops:
                    stagger_idx = (b_idx * max(1, len(sorted_stops) // max(1, len(r_data["buses"])))) % len(sorted_stops)
                    initial_stop = sorted_stops[stagger_idx]

                    init_pos = BusPosition(
                        bus_id=bus.id,
                        latitude=initial_stop.latitude,
                        longitude=initial_stop.longitude,
                        speed=0.0,
                        heading=0.0,
                        timestamp=now_utc,
                    )
                    db.add(init_pos)

                    init_load = PassengerLoad(
                        bus_id=bus.id,
                        stop_id=initial_stop.id,
                        current_load=int(round(0.55 * bus.capacity)),
                        capacity=bus.capacity,
                        load_factor=0.55,
                        timestamp=now_utc,
                    )
                    db.add(init_load)
            else:
                # Ensure bus has valid current_route_id if unset
                if not existing_bus.current_route_id:
                    existing_bus.current_route_id = route.id
                if "TN-38" in b_data["license_plate"] and not existing_bus.license_plate.startswith("TN-"):
                    existing_bus.license_plate = b_data["license_plate"]

    db.commit()
    logger.info("Coimbatore transit network synchronized successfully (6 routes, 12 buses).")
    return changes_made


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SmartBus Transit Network Seeder")
    parser.add_argument("--force", action="store_true", help="Force update/reseed transit network")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    db = SessionLocal()
    try:
        seed_transit_data(db, force=args.force)
    finally:
        db.close()
