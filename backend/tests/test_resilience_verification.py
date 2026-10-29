import unittest
from types import SimpleNamespace
from app.services.weather import WeatherService
from app.simulator.bus_simulator import BusSimulator
from app.simulator.passenger_simulator import PassengerSimulator

class TestResilienceVerification(unittest.TestCase):
    def test_weather_speed_factors_and_multipliers(self):
        """Verify deterministic weather factors."""
        norm = WeatherService._calculate_impacts("NORMAL")
        self.assertEqual(norm["speed_factor"], 1.00)
        self.assertEqual(norm["travel_time_multiplier"], 1.00)

        light = WeatherService._calculate_impacts("LIGHT_RAIN")
        self.assertEqual(light["speed_factor"], 0.90)
        self.assertEqual(light["travel_time_multiplier"], 1.11)

        heavy = WeatherService._calculate_impacts("HEAVY_RAIN")
        self.assertEqual(heavy["speed_factor"], 0.75)
        self.assertEqual(heavy["travel_time_multiplier"], 1.33)

        severe = WeatherService._calculate_impacts("SEVERE_WEATHER")
        self.assertEqual(severe["speed_factor"], 0.55)
        self.assertEqual(severe["travel_time_multiplier"], 1.82)

    def _create_mock_stops(self):
        return [
            SimpleNamespace(id=1, name="Stop A", latitude=11.00, longitude=76.95, sequence_order=1),
            SimpleNamespace(id=2, name="Stop B", latitude=11.05, longitude=76.98, sequence_order=2),
        ]

    def test_bus_simulator_broken_bus_speed_zero(self):
        """Verify broken bus is halted to 0 km/h and does not exchange passengers."""
        stops = self._create_mock_stops()
        bus = BusSimulator(
            bus_id=1,
            bus_number="606B",
            capacity=50,
            route_id=6,
            route_number="606",
            stops=stops,
            base_speed_kmh=30.0,
        )
        initial_load = bus.current_load
        # Mark broken
        bus.set_breakdown_state(True)
        self.assertTrue(bus.is_broken_down)
        self.assertEqual(bus.speed, 0.0)

        # Step simulation - broken bus should remain halted
        state = bus.tick(interval_seconds=5.0)
        self.assertEqual(state["speed"], 0.0)
        self.assertEqual(state["is_broken_down"], True)
        self.assertEqual(state["passenger_count"], initial_load)

        # Recover bus
        bus.set_breakdown_state(False)
        self.assertFalse(bus.is_broken_down)

    def test_bus_simulator_weather_speed_scaling(self):
        """Verify bus simulator cruising speed scales with weather speed factor."""
        stops = self._create_mock_stops()
        bus = BusSimulator(
            bus_id=2,
            bus_number="101A",
            capacity=50,
            route_id=1,
            route_number="101",
            stops=stops,
            base_speed_kmh=40.0,
        )
        # End initial dwell so bus is moving along route
        bus.is_dwelling = False
        bus.dwell_ticks_remaining = 0
        bus.set_weather_speed_factor(0.75)  # Heavy Rain
        state = bus.tick(interval_seconds=2.0)
        # Base speed 40 * 0.75 = 30.0 (with +/- 3 kmh variation)
        self.assertAlmostEqual(state["speed"], 30.0, delta=6.0)

    def test_passenger_simulator_capacity_clamping(self):
        """Verify passenger exchange clamps load at physical capacity and puts excess in unmet demand."""
        # Starting with 45 passengers in 50 capacity bus, simulate high exchange
        load, boarded, alighted, unmet = PassengerSimulator.simulate_stop_exchange(
            current_load=48,
            capacity=50,
            route_number="101",
            stop_seq=2,
            total_stops=5,
            scenario="HIGH",
        )
        self.assertLessEqual(load, 50)
        self.assertGreaterEqual(unmet, 0)
        self.assertGreaterEqual(boarded, 0)

    def test_reallocation_coverage_invariant(self):
        """Verify that a source route with only 1 bus is marked INFEASIBLE with coverage limitation."""
        from app.services.optimization import evaluate_bus_reallocation
        from app.schemas.intelligence import RouteIntelligenceResponse, BusIntelligenceResponse

        target_route = RouteIntelligenceResponse(
            route_id=1,
            route_number="101",
            route_name="Route 101",
            origin="Gandhipuram",
            destination="Airport",
            status="CRITICAL",
            load_factor=0.95,
            total_passengers=95,
            total_capacity=100,
            available_seats=5,
            assessment="OVERLOADED",
            number_of_buses=2,
            buses=[],
            recommended_action="REQUEST_ADDITIONAL_BUSES",
            reason="Overloaded",
        )
        # Source route with only 1 bus
        source_route = RouteIntelligenceResponse(
            route_id=6,
            route_number="606",
            route_name="Route 606",
            origin="Ondipudur",
            destination="Sulur",
            status="LOW",
            load_factor=0.30,
            total_passengers=15,
            total_capacity=50,
            available_seats=35,
            assessment="UNDERUTILIZED",
            number_of_buses=1,
            buses=[],
            recommended_action="SUITABLE_DONOR",
            reason="Underutilized",
        )
        candidate_bus = BusIntelligenceResponse(
            bus_id=12,
            bus_number="606B",
            route_id=6,
            route_number="606",
            status="LOW",
            capacity=50,
            passenger_count=15,
            available_seats=35,
            load_factor=0.30,
        )

        rec = evaluate_bus_reallocation(
            target_route=target_route,
            source_route=source_route,
            candidate_bus=candidate_bus,
            target_origin_stop=None,
            bus_position=None,
            db_bus=None,
        )

        self.assertEqual(rec.feasibility_status, "INFEASIBLE")
        self.assertTrue(any("Minimum Service Coverage" in lim for lim in rec.limitations))

    def test_candidate_discovery_under_high_demand(self):
        """Verify that a donor route with 45% load (54/120) is feasible for relieving a 100% overloaded route."""
        from app.services.optimization import evaluate_bus_reallocation
        from app.schemas.intelligence import RouteIntelligenceResponse, BusIntelligenceResponse

        target_route = RouteIntelligenceResponse(
            route_id=6,
            route_number="606",
            route_name="Route 606",
            origin="Gandhipuram",
            destination="Hope College",
            status="CRITICAL",
            load_factor=1.00,
            total_passengers=120,
            total_capacity=120,
            available_seats=0,
            assessment="CRITICAL",
            number_of_buses=2,
            buses=[],
        )
        source_route_101 = RouteIntelligenceResponse(
            route_id=1,
            route_number="101",
            route_name="Route 101",
            origin="Gandhipuram",
            destination="Airport",
            status="LOW",
            load_factor=0.45,
            total_passengers=54,
            total_capacity=120,
            available_seats=66,
            assessment="LOW",
            number_of_buses=2,
            buses=[],
        )
        candidate_bus_101a = BusIntelligenceResponse(
            bus_id=1,
            bus_number="101A",
            route_id=1,
            route_number="101",
            status="LOW",
            capacity=60,
            passenger_count=27,
            available_seats=33,
            load_factor=0.45,
        )

        rec = evaluate_bus_reallocation(
            target_route=target_route,
            source_route=source_route_101,
            candidate_bus=candidate_bus_101a,
            target_origin_stop=None,
            bus_position=None,
            db_bus=None,
        )

        # Candidate is discoverable, not INFEASIBLE
        self.assertIn(rec.feasibility_status, ("FEASIBLE", "CONDITIONALLY_FEASIBLE"))
        self.assertGreater(rec.score, 50.0)

    def test_weather_deadhead_travel_time_adjustment(self):
        """Verify that WeatherService multiplier adjusts deadhead travel time."""
        from types import SimpleNamespace
        from app.services.optimization import evaluate_bus_reallocation
        from app.services.weather import WeatherService
        from app.schemas.intelligence import RouteIntelligenceResponse, BusIntelligenceResponse

        # Set scenario to HEAVY_RAIN (1.33x multiplier)
        WeatherService.set_scenario("HEAVY_RAIN")

        target_route = RouteIntelligenceResponse(
            route_id=6, route_number="606", route_name="R606", origin="O", destination="D",
            status="CRITICAL", load_factor=1.0, total_passengers=100, total_capacity=100,
            available_seats=0, assessment="CRITICAL", number_of_buses=2, buses=[]
        )
        source_route = RouteIntelligenceResponse(
            route_id=1, route_number="101", route_name="R101", origin="O", destination="D",
            status="LOW", load_factor=0.3, total_passengers=30, total_capacity=120,
            available_seats=90, assessment="LOW", number_of_buses=2, buses=[]
        )
        candidate_bus = BusIntelligenceResponse(
            bus_id=1, bus_number="101A", route_id=1, route_number="101",
            status="LOW", capacity=60, passenger_count=10, available_seats=50, load_factor=0.17
        )

        pos = SimpleNamespace(latitude=11.00, longitude=76.95)
        stop = SimpleNamespace(latitude=11.05, longitude=76.98)

        rec = evaluate_bus_reallocation(
            target_route=target_route,
            source_route=source_route,
            candidate_bus=candidate_bus,
            target_origin_stop=stop,
            bus_position=pos,
            db_bus=None,
        )

        self.assertIsNotNone(rec.estimated_travel_time_minutes)
        self.assertTrue(any("Weather condition" in lim for lim in rec.limitations))

        # Reset weather scenario back to normal
        WeatherService.set_scenario("NORMAL")

if __name__ == "__main__":
    unittest.main()


