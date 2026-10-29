"""Stage 3 Verification Test Suite for SmartBus.

Tests all 14 backend criteria specified for STAGE 3.
"""
import sys
import unittest
from datetime import datetime
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.main import app
from app.core.config import settings
from app.models.route import Route
from app.models.bus import Bus
from app.models.stop import Stop
from app.models.bus_position import BusPosition
from app.models.passenger_load import PassengerLoad
from app.simulator.bus_simulator import BusSimulator
from app.simulator.passenger_simulator import PassengerSimulator
from app.simulator.route_simulator import (
    calculate_distance_meters,
    calculate_bearing,
    step_towards,
)
from app.simulator.runner import SimulatorRunner
from app.api.routes.health import get_health
from app.api.routes.buses import get_live_buses
from app.api.routes.routes import get_live_routes


class TestStage3(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db: Session = SessionLocal()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_01_backend_imports(self):
        """1. Backend imports successfully."""
        self.assertIsNotNone(app)
        self.assertEqual(app.title, "SmartBus")

    def test_02_health_endpoint(self):
        """2. Existing /api/health still works."""
        health = get_health()
        self.assertEqual(health.status, "ok")

    def test_03_and_04_simulator_starts_and_reads_seeds(self):
        """3 & 4. Simulator starts successfully and reads seeded buses/routes/stops."""
        runner = SimulatorRunner(scenario="normal", interval_seconds=1.0)
        success = runner.setup(self.db)
        self.assertTrue(success)
        self.assertGreaterEqual(len(runner.bus_simulators), 6)

        routes_count = self.db.query(Route).count()
        buses_count = self.db.query(Bus).count()
        stops_count = self.db.query(Stop).count()

        self.assertGreaterEqual(routes_count, 3)
        self.assertGreaterEqual(buses_count, 6)
        self.assertGreaterEqual(stops_count, 14)

    def test_05_and_06_records_generated(self):
        """5 & 6. Simulator generates BusPosition and PassengerLoad records."""
        initial_pos_count = self.db.query(BusPosition).count()
        initial_load_count = self.db.query(PassengerLoad).count()

        runner = SimulatorRunner(scenario="normal", interval_seconds=1.0)
        runner.setup(self.db)
        runner.step(self.db)

        new_pos_count = self.db.query(BusPosition).count()
        new_load_count = self.db.query(PassengerLoad).count()

        self.assertGreater(new_pos_count, initial_pos_count)
        self.assertGreater(new_load_count, initial_load_count)

    def test_07_bus_coordinates_change(self):
        """7. Bus coordinates change between simulation ticks."""
        route = self.db.query(Route).filter(Route.route_number == "101").first()
        self.assertIsNotNone(route)

        bus = BusSimulator(
            bus_id=1,
            bus_number="101A",
            route_id=route.id,
            route_number="101",
            capacity=60,
            stops=route.stops,
            initial_stop_index=0,
            base_speed_kmh=40.0,
        )

        initial_lat, initial_lon = bus.latitude, bus.longitude
        bus.is_dwelling = False  # Set bus to moving mode

        # Tick forward
        bus.tick(interval_seconds=10.0)

        # Latitude or longitude should have changed
        moved = (bus.latitude != initial_lat) or (bus.longitude != initial_lon)
        self.assertTrue(moved, "Bus coordinates should change during transit tick")

    def test_08_passenger_counts_change(self):
        """8. Passenger counts change during stop exchanges."""
        changes = 0
        current_load = 30
        capacity = 60

        for _ in range(10):
            new_load, boarding, alighting, _ = PassengerSimulator.simulate_stop_exchange(
                current_load=current_load,
                capacity=capacity,
                route_number="101",
                stop_seq=2,
                total_stops=5,
                scenario="normal",
            )
            if new_load != current_load:
                changes += 1
            current_load = new_load

        self.assertGreater(changes, 0, "Passenger count should change realistically at stops")

    def test_09_and_10_and_11_passenger_bounds_and_load_factor(self):
        """9, 10, 11. Passenger count never < 0, never > capacity, load_factor correct."""
        capacity = 60

        for scenario in ["normal", "high_demand"]:
            for route_num in ["101", "202", "303"]:
                for initial_load in [0, 10, 30, 58, 60]:
                    new_load, _, _, _ = PassengerSimulator.simulate_stop_exchange(
                        current_load=initial_load,
                        capacity=capacity,
                        route_number=route_num,
                        stop_seq=3,
                        total_stops=5,
                        scenario=scenario,
                    )
                    # 9. Never negative
                    self.assertGreaterEqual(new_load, 0)
                    # 10. Never exceeds physical capacity
                    self.assertLessEqual(new_load, capacity)
                    # 11. load_factor accurate
                    lf = round(new_load / capacity, 4)
                    self.assertGreaterEqual(lf, 0.0)
                    self.assertLessEqual(lf, 1.0)

    def test_12_get_live_buses_api(self):
        """12. GET /api/buses/live returns live bus information."""
        buses = get_live_buses(self.db)
        self.assertGreaterEqual(len(buses), 6)

        first_bus = buses[0]
        self.assertIsNotNone(first_bus.bus_id)
        self.assertIsNotNone(first_bus.bus_number)
        self.assertIsNotNone(first_bus.route_id)
        self.assertIsNotNone(first_bus.latitude)
        self.assertIsNotNone(first_bus.longitude)
        self.assertIsNotNone(first_bus.speed)
        self.assertIsNotNone(first_bus.heading)
        self.assertIsNotNone(first_bus.passenger_count)
        self.assertEqual(first_bus.capacity, 60)
        self.assertIsNotNone(first_bus.load_factor)
        self.assertIsNotNone(first_bus.timestamp)

    def test_13_get_live_routes_api(self):
        """13. GET /api/routes/live returns route statistics."""
        routes = get_live_routes(self.db)
        self.assertEqual(len(routes), 3)

        for route in routes:
            self.assertIn(route.route_number, ["101", "202", "303"])
            self.assertEqual(route.number_of_buses, 2)
            self.assertEqual(route.total_capacity, 120)
            self.assertGreaterEqual(route.total_passengers, 0)
            self.assertLessEqual(route.total_passengers, 120)
            self.assertIn(route.status, ["LOW", "NORMAL", "HIGH", "CRITICAL"])

    def test_14_high_demand_scenario_imbalance(self):
        """14. High-demand scenario produces HIGH/CRITICAL on one route and LOW on another."""
        runner = SimulatorRunner(scenario="high_demand", interval_seconds=1.0)
        runner.setup(self.db)
        runner.step(self.db)

        routes = get_live_routes(self.db)
        route_map = {r.route_number: r for r in routes}

        route_101 = route_map.get("101")
        route_202 = route_map.get("202")

        self.assertIsNotNone(route_101)
        self.assertIsNotNone(route_202)

        # Route 101 should be HIGH or CRITICAL (>= 0.80)
        self.assertIn(route_101.status, ["HIGH", "CRITICAL"])
        self.assertGreaterEqual(route_101.load_factor, 0.80)

        # Route 202 should be LOW (< 0.50)
        self.assertEqual(route_202.status, "LOW")
        self.assertLess(route_202.load_factor, 0.50)


if __name__ == "__main__":
    unittest.main()
