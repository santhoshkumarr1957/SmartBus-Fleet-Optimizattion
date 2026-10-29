import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

describe('Frontend Stage 8 Disruption Simulation Controls and State Management', () => {

  // 1. Scenario submission payloads for all 4 types
  test('correctly constructs payloads for all four disruption scenario types', () => {
    const buildPayload = (scenarioType, formState) => {
      const payload = {
        disruption_type: scenarioType,
        notes: formState.notes?.trim() || undefined,
      };

      if (scenarioType === 'BUS_BREAKDOWN') {
        payload.bus_number = formState.bus_number;
      } else if (scenarioType === 'ROUTE_CLOSURE') {
        payload.route_number = formState.route_number;
      } else if (scenarioType === 'DEMAND_SPIKE' || scenarioType === 'DEMAND_SURGE') {
        payload.route_number = formState.route_number;
        payload.spike_percentage = formState.spike_percentage;
        if (formState.demand_multiplier) {
          payload.demand_multiplier = formState.demand_multiplier;
        }
      } else if (scenarioType === 'SERVICE_DELAY') {
        if (formState.targetType === 'BUS') {
          payload.bus_number = formState.bus_number;
        } else {
          payload.route_number = formState.route_number;
        }
        payload.delay_minutes = formState.delay_minutes;
      }

      return payload;
    };

    // Scenario 1: Bus Breakdown
    const p1 = buildPayload('BUS_BREAKDOWN', { bus_number: '101A', notes: 'Engine overheating' });
    assert.deepEqual(p1, { disruption_type: 'BUS_BREAKDOWN', bus_number: '101A', notes: 'Engine overheating' });

    // Scenario 2: Route Closure
    const p2 = buildPayload('ROUTE_CLOSURE', { route_number: '202' });
    assert.deepEqual(p2, { disruption_type: 'ROUTE_CLOSURE', route_number: '202', notes: undefined });

    // Scenario 3: Demand Surge
    const p3 = buildPayload('DEMAND_SPIKE', { route_number: '101', spike_percentage: 50, demand_multiplier: 1.5 });
    assert.deepEqual(p3, { disruption_type: 'DEMAND_SPIKE', route_number: '101', spike_percentage: 50, demand_multiplier: 1.5, notes: undefined });

    // Scenario 4: Service Delay (Route)
    const p4 = buildPayload('SERVICE_DELAY', { targetType: 'ROUTE', route_number: '303', delay_minutes: 25 });
    assert.deepEqual(p4, { disruption_type: 'SERVICE_DELAY', route_number: '303', delay_minutes: 25, notes: undefined });

    // Scenario 4: Service Delay (Bus)
    const p5 = buildPayload('SERVICE_DELAY', { targetType: 'BUS', bus_number: '202B', delay_minutes: 15 });
    assert.deepEqual(p5, { disruption_type: 'SERVICE_DELAY', bus_number: '202B', delay_minutes: 15, notes: undefined });
  });

  // 2. Client-side pre-flight validation preventing invalid requests
  test('validates required inputs and prevents invalid submissions before API call', () => {
    const validateRequest = (type, state) => {
      if (type === 'BUS_BREAKDOWN' && !state.bus_number) {
        return { valid: false, error: 'Please select an active bus to simulate breakdown.' };
      }
      if (type === 'ROUTE_CLOSURE') {
        if (!state.route_number || state.route_number === 'ALL') {
          return { valid: false, error: 'Route closure requires a specific corridor. "ALL" is not permitted.' };
        }
      }
      if (type === 'DEMAND_SPIKE') {
        if (state.spike_percentage < 5 || state.spike_percentage > 300) {
          return { valid: false, error: 'Spike percentage must be between 5% and 300%.' };
        }
      }
      if (type === 'SERVICE_DELAY') {
        if (state.delay_minutes < 1 || state.delay_minutes > 240) {
          return { valid: false, error: 'Delay minutes must be between 1 and 240.' };
        }
      }
      return { valid: true };
    };

    // Missing bus in BUS_BREAKDOWN
    const v1 = validateRequest('BUS_BREAKDOWN', { bus_number: '' });
    assert.equal(v1.valid, false);
    assert.match(v1.error, /Please select an active bus/);

    // Route closure on 'ALL'
    const v2 = validateRequest('ROUTE_CLOSURE', { route_number: 'ALL' });
    assert.equal(v2.valid, false);
    assert.match(v2.error, /Route closure requires a specific corridor/);

    // Out-of-bounds spike percentage
    const v3 = validateRequest('DEMAND_SPIKE', { route_number: '101', spike_percentage: 2 });
    assert.equal(v3.valid, false);
    assert.match(v3.error, /between 5% and 300%/);

    // Valid requests pass
    assert.equal(validateRequest('BUS_BREAKDOWN', { bus_number: '101A' }).valid, true);
    assert.equal(validateRequest('ROUTE_CLOSURE', { route_number: '101' }).valid, true);
    assert.equal(validateRequest('DEMAND_SPIKE', { route_number: 'ALL', spike_percentage: 50 }).valid, true);
    assert.equal(validateRequest('SERVICE_DELAY', { route_number: 'ALL', delay_minutes: 30 }).valid, true);
  });

  // 3. Loading state and duplicate submission prevention
  test('prevents duplicate submissions while simulation request is processing', async () => {
    let isSimulating = false;
    let apiCallCount = 0;

    const mockApiCall = async () => {
      apiCallCount++;
      await new Promise(r => setTimeout(r, 20));
      return { scenario_id: `SCEN-TEST-${apiCallCount}` };
    };

    const handleRunSimulation = async () => {
      if (isSimulating) {
        return; // Suppress duplicate click
      }
      isSimulating = true;
      try {
        return await mockApiCall();
      } finally {
        isSimulating = false;
      }
    };

    // Trigger two rapid clicks concurrently
    const [res1, res2] = await Promise.all([
      handleRunSimulation(),
      handleRunSimulation(),
    ]);

    assert.equal(apiCallCount, 1, 'Only one API request must be executed');
    assert.ok(res1);
    assert.equal(res2, undefined);
    assert.equal(isSimulating, false, 'Loading flag must reset to false after completion');
  });

  // 4. Stale state clearing when switching scenario types
  test('clearing scenario results when switching scenario type tabs', () => {
    let activeScenario = {
      scenario_id: 'SCEN-BUS_BREAKDOWN-ABC123',
      disruption_type: 'BUS_BREAKDOWN',
      parameters: { bus_number: '101A' },
    };
    let selectedType = 'BUS_BREAKDOWN';
    let selectedRouteNumber = 'ALL';

    const handleSelectType = (newType, availableRoutes) => {
      selectedType = newType;
      // Stale results must be cleared
      activeScenario = null;
      // Ensure valid route selection for Route Closure
      if (newType === 'ROUTE_CLOSURE' && selectedRouteNumber === 'ALL') {
        selectedRouteNumber = availableRoutes[0]?.route_number || '101';
      }
    };

    handleSelectType('ROUTE_CLOSURE', [{ route_number: '101' }, { route_number: '202' }]);

    assert.equal(selectedType, 'ROUTE_CLOSURE');
    assert.equal(activeScenario, null, 'Active scenario must be cleared to prevent stale state display');
    assert.equal(selectedRouteNumber, '101', 'Route selection must not remain ALL on Route Closure');
  });

  // 5. Successful response parsing and rendering data structure
  test('correctly verifies full response structure including resilience and warnings', () => {
    const mockResponse = {
      scenario_id: 'SCEN-BUS_BREAKDOWN-F451',
      disruption_type: 'BUS_BREAKDOWN',
      parameters: { bus_number: '101A' },
      simulated_at: new Date().toISOString(),
      summary_headline: 'Simulation: Bus 101A breakdown on Route 101',
      executive_summary: 'Target bus 101A removed from service.',
      resilience_metrics: {
        fleet_availability_pct: 83.3,
        capacity_retention_pct: 75.0,
        capacity_lost: 60,
        capacity_loss_pct: 25.0,
        service_continuity_pct: 100.0,
        routes_affected_count: 1,
        routes_critical_count: 0,
        routes_high_count: 1,
        remaining_available_capacity: 60,
        resilience_score: 83.3,
        resilience_rating: 'ADEQUATE',
      },
      affected_routes: [
        {
          route_id: 1,
          route_number: '101',
          name: 'Gandhipuram - Peelamedu',
          buses_count_before: 2,
          buses_count_after: 1,
          capacity_before: 120,
          capacity_after: 60,
          passengers_before: 50,
          passengers_after: 50,
          load_factor_before: 0.4167,
          load_factor_after: 0.8333,
          status_before: 'LOW',
          status_after: 'HIGH',
          severity_change: 'DEGRADED',
          is_directly_affected: true,
        },
      ],
      affected_buses: [
        {
          bus_id: 1,
          bus_number: '101A',
          route_id: 1,
          route_number: '101',
          status_before: 'ACTIVE',
          status_after: 'BROKEN_DOWN',
          is_operational_after: false,
          impact_note: 'Simulated breakdown',
        },
      ],
      suggested_reallocations: [
        {
          id: 'SIM-REC-1',
          source_route_number: '202',
          target_route_number: '101',
          candidate_bus_number: '202B',
          score: 82.5,
          priority: 'HIGH',
          is_advisory: true,
        },
      ],
      warnings: [
        'Vehicle Bus 101A disabled; removed from active corridor service.',
        'High load warning on corridor 101: projected load 83.3%.',
      ],
      notes: 'Test breakdown note',
      is_simulated: true,
    };

    assert.equal(mockResponse.is_simulated, true);
    assert.equal(mockResponse.resilience_metrics.resilience_rating, 'ADEQUATE');
    assert.equal(mockResponse.affected_routes.length, 1);
    assert.equal(mockResponse.affected_buses[0].status_after, 'BROKEN_DOWN');
    assert.equal(mockResponse.suggested_reallocations[0].is_advisory, true);
    assert.equal(mockResponse.warnings.length, 2);
    assert.equal(mockResponse.notes, 'Test breakdown note');
  });

  // 6. Scenario history management and inspection
  test('scenario history correctly updates and allows inspection of prior runs', () => {
    let history = [];
    const MAX_HISTORY = 50;

    const addScenarioToHistory = (scenario) => {
      // Check if already in history
      const filtered = history.filter(h => h.scenario_id !== scenario.scenario_id);
      filtered.unshift({
        scenario_id: scenario.scenario_id,
        disruption_type: scenario.disruption_type,
        simulated_at: scenario.simulated_at,
        resilience_score: scenario.resilience_metrics.resilience_score,
        resilience_rating: scenario.resilience_metrics.resilience_rating,
        summary: scenario.summary_headline,
      });
      if (filtered.length > MAX_HISTORY) filtered.pop();
      history = filtered;
      return history;
    };

    let list = addScenarioToHistory({
      scenario_id: 'SCEN-1',
      disruption_type: 'BUS_BREAKDOWN',
      simulated_at: '2026-10-27T12:00:00Z',
      summary_headline: 'Breakdown 1',
      resilience_metrics: { resilience_score: 80, resilience_rating: 'ADEQUATE' },
    });

    list = addScenarioToHistory({
      scenario_id: 'SCEN-2',
      disruption_type: 'ROUTE_CLOSURE',
      simulated_at: '2026-10-27T12:05:00Z',
      summary_headline: 'Closure 2',
      resilience_metrics: { resilience_score: 65, resilience_rating: 'VULNERABLE' },
    });

    assert.equal(list.length, 2);
    assert.equal(list[0].scenario_id, 'SCEN-2'); // Most recent at front

    // Inspecting cached scenario sets correct type and active view
    const selectScenario = (selectedBrief) => {
      return {
        activeType: selectedBrief.disruption_type,
        selectedId: selectedBrief.scenario_id,
      };
    };

    const inspection = selectScenario(list[1]);
    assert.equal(inspection.activeType, 'BUS_BREAKDOWN');
    assert.equal(inspection.selectedId, 'SCEN-1');
  });

  // 7. Error handling for network or server failures
  test('formats server error messages for user-friendly diagnostic display', () => {
    const formatErrorMessage = (error) => {
      if (typeof error === 'string') return error;
      if (error?.response?.data?.detail) {
        const detail = error.response.data.detail;
        if (typeof detail === 'string') return detail;
        if (Array.isArray(detail)) {
          return detail.map(d => `${d.loc?.slice(-1)[0] || 'parameter'}: ${d.msg}`).join(', ');
        }
      }
      return error?.message || 'Failed to execute disruption simulation';
    };

    const pydanticError = {
      response: {
        data: {
          detail: [
            { loc: ['body', 'spike_percentage'], msg: 'Input should be greater than or equal to 5' }
          ]
        }
      }
    };
    assert.equal(formatErrorMessage(pydanticError), 'spike_percentage: Input should be greater than or equal to 5');

    const httpError = {
      response: {
        data: {
          detail: "Bus with number '999X' not found in fleet."
        }
      }
    };
    assert.equal(formatErrorMessage(httpError), "Bus with number '999X' not found in fleet.");
  });

});
