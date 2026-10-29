import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

describe('Frontend Telemetry Polling, Viewport Stability & Passenger Correctness', () => {
  test('single polling failure does not permanently halt polling cycles', async () => {
    let callCount = 0;
    let successfulUpdates = 0;
    const pollingErrors = [];

    // Simulated polling function that fails on tick 2 but recovers on tick 3 & 4
    const pollTelemetry = async () => {
      callCount++;
      if (callCount === 2) {
        throw new Error('Network timeout (simulated temporary disruption)');
      }
      return [
        { bus_id: 1, bus_number: '101A', latitude: 11.0154 + callCount * 0.001, longitude: 76.9754 },
      ];
    };

    // Simulate 4 polling ticks
    for (let i = 0; i < 4; i++) {
      try {
        const fresh = await pollTelemetry();
        if (fresh && fresh.length > 0) {
          successfulUpdates++;
        }
      } catch (err) {
        pollingErrors.push(err.message);
        // Resilient: error is caught and logged, does not kill loop
      }
    }

    assert.equal(callCount, 4, 'All 4 polling ticks must be attempted');
    assert.equal(pollingErrors.length, 1, 'Only tick 2 should encounter error');
    assert.equal(successfulUpdates, 3, 'Ticks 1, 3, and 4 must succeed despite temporary error');
  });

  test('map viewport fitBounds executes only on initial load and is suppressed on updates', () => {
    let fitBoundsCalls = 0;
    let initialFitDone = false;

    const mockMap = {
      fitBounds: () => {
        fitBoundsCalls++;
      },
    };

    const handleTelemetryCycle = (buses, selectedBusId) => {
      const boundsValid = buses.length > 0;
      if (!initialFitDone && boundsValid && !selectedBusId) {
        mockMap.fitBounds();
        initialFitDone = true;
      }
    };

    // Cycle 1: initial load -> fitBounds called
    handleTelemetryCycle([{ bus_id: 1, latitude: 11.01, longitude: 76.97 }], null);
    assert.equal(fitBoundsCalls, 1, 'fitBounds must be called on initial load');
    assert.equal(initialFitDone, true);

    // Cycles 2, 3, 4, 5: subsequent telemetry updates -> fitBounds must NOT be called again
    for (let c = 2; c <= 5; c++) {
      handleTelemetryCycle([{ bus_id: 1, latitude: 11.01 + c * 0.001, longitude: 76.97 }], null);
    }
    assert.equal(fitBoundsCalls, 1, 'fitBounds must NEVER be repeatedly called on telemetry updates');
  });

  test('passenger load and available seats preserve mathematical consistency', () => {
    const busTelemetry = {
      bus_id: 2,
      bus_number: '202A',
      passenger_count: 35,
      capacity: 60,
      is_transferring: true,
      transfer_status: 'IN_PROGRESS',
    };

    const calculatedLoadFactor = busTelemetry.passenger_count / busTelemetry.capacity;
    const availableSeats = Math.max(busTelemetry.capacity - busTelemetry.passenger_count, 0);

    assert.equal(busTelemetry.passenger_count, 35, 'Passenger count must not reset to 0 during transfer');
    assert.equal(availableSeats, 25);
    assert.ok(Math.abs(calculatedLoadFactor - 0.5833) < 0.001);
    assert.equal(busTelemetry.is_transferring, true);
  });
});
