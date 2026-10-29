# TRANSIGHT — Stage 8: Transit Disruption Simulation and Resilience Analysis

## 1. Executive Summary

Stage 8 introduces the rule-based **Transit Disruption Simulation and Resilience Analysis Module** for the SmartBus (TRANSIGHT) transit management platform. Designed specifically for transit operators and dispatchers, Stage 8 provides an isolated in-memory "what-if" simulation sandbox to model sudden service disruptions (vehicle mechanical breakdowns, corridor closures, passenger demand spikes, and service delays) and quantify their impacts across transit corridors and fleet resilience metrics.

### Core Principles & Non-Mutation Invariants
1. **Strict Scenario Isolation**: All simulations operate exclusively on in-memory clones of read-only database queries. Database tables, bus route assignments (`bus.current_route_id`), live vehicle statuses, telemetry histories (`bus_positions`, `passenger_loads`), and Stage 7 dispatcher reviews (`reallocation_reviews`) are **never mutated**.
2. **Deterministic & Rule-Based**: 100% deterministic logic. No black-box machine learning models or paid third-party APIs are utilized.
3. **Zero Database Migrations**: Operates entirely upon existing database schemas with in-memory LRU scenario caching (capped at 50 scenarios). No Alembic schema migrations were created.
4. **Advisory Reallocation Mitigation**: Integrates Stage 5 fleet optimization algorithms to suggest hypothetical reallocation mitigation options based on simulated corridor imbalances, explicitly tagged as simulated advisory recommendations with automated vehicle dispatching strictly disabled.
5. **Clear Operational Separation**: All API responses and UI panels display a prominent `SIMULATED DATA — NO LIVE CHANGES` indicator to eliminate confusion with live operations.

---

## 2. Supported Disruption Scenarios

The module supports four configurable scenario archetypes:

| Scenario Type | Identifier | Target Scope | Required Parameters | Optional Parameters | Real-World Operational Condition |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Bus Breakdown** | `BUS_BREAKDOWN` | Specific Vehicle | `bus_id` or `bus_number` | `notes` | Mechanical breakdown, engine failure, or collision taking a bus out of service. Removes vehicle capacity from its assigned corridor. |
| **Route Closure** | `ROUTE_CLOSURE` | Specific Corridor | `route_id` or `route_number` | `notes` | Full corridor shutdown due to road construction, sinkholes, flooding, or police activity. Eliminates corridor service; vehicles on the corridor become stranded. |
| **Demand Surge** | `DEMAND_SPIKE` | Corridor or Network | `spike_percentage` (5.0% to 300.0%) | `route_id` / `route_number`, `notes` | Sudden passenger volume surge due to stadium events, concerts, or commuter rail disruptions. |
| **Service Delay** | `SERVICE_DELAY` | Corridor, Bus, or Network | `delay_minutes` (1.0 to 240.0 min) | `route_id` / `route_number`, `bus_id` / `bus_number`, `notes` | Arterial traffic delays expanding headway, causing passenger stop queues to accumulate and vehicle turnaround to drop. |

---

## 3. Mathematical Models & Metric Formulas

### 3.1 Network Resilience Metrics

Resilience metrics evaluate how effectively the transit network buffers and withstands the simulated disruption.

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 COMPOSITE RESILIENCE SCORE (100 pts)                            │
├──────────────────────────┬──────────────────────────┬─────────────────────┬─────────────────────┤
│ Capacity Retention (40%) │ Fleet Availability (30%) │ Route Continuity(20%)│ Overload Pen. (10%) │
│ Cap_Sim / Cap_Base * 100 │ Active_Sim / Active_Base │ Routes_Sim / Routes │ (1 - Overload_Ratio)│
└──────────────────────────┴──────────────────────────┴─────────────────────┴─────────────────────┘
```

#### 1. Fleet Availability Percentage ($F_{\text{avail}}$)
Measures the proportion of operational vehicles remaining in service:
$$F_{\text{avail}} = \left(\frac{N_{\text{active, sim}}}{N_{\text{active, base}}}\right) \times 100.0$$
- If baseline active buses is 0, defaults to $100.0\%$.

#### 2. Capacity Retention Percentage ($C_{\text{ret}}$) and Capacity Lost ($C_{\text{lost}}$)
Measures baseline seat capacity retained across all operational routes:
$$C_{\text{lost}} = \max\left(0, \sum \text{Cap}_{\text{base}} - \sum \text{Cap}_{\text{sim}}\right)$$
$$C_{\text{ret}} = \left(\frac{\sum \text{Cap}_{\text{sim}}}{\sum \text{Cap}_{\text{base}}}\right) \times 100.0$$
$$C_{\text{loss\_pct}} = \left(\frac{C_{\text{lost}}}{\sum \text{Cap}_{\text{base}}}\right) \times 100.0$$

#### 3. Service Continuity Percentage ($S_{\text{cont}}$)
Measures the proportion of transit routes that maintain service (not `CLOSED` or `NO_SERVICE`):
$$S_{\text{cont}} = \left(\frac{R_{\text{operational, sim}}}{R_{\text{operational, base}}}\right) \times 100.0$$

#### 4. Corridor Overload Ratio ($O_{\text{ratio}}$)
Measures the fraction of routes pushed to `HIGH` ($0.80 \le LF < 1.00$) or `CRITICAL` ($LF \ge 1.00$):
$$O_{\text{ratio}} = \frac{N_{\text{critical}} + N_{\text{high}}}{\max(1, N_{\text{routes}})}$$

#### 5. Composite Resilience Score ($R_{\text{score}} \in [0.0, 100.0]$)
Combines capacity, fleet, route continuity, and congestion headroom into a normalized composite score:
$$R_{\text{score}} = \text{round}\Big(0.40 \cdot C_{\text{ret}} + 0.30 \cdot F_{\text{avail}} + 0.20 \cdot S_{\text{cont}} + 0.10 \cdot \max(0, 1.0 - O_{\text{ratio}}) \cdot 100.0, 1\Big)$$

#### 6. Qualitative Resilience Rating
- **`EXCELLENT`**: $R_{\text{score}} \ge 85.0$ (High buffering capacity; minor operational degradation)
- **`ADEQUATE`**: $70.0 \le R_{\text{score}} < 85.0$ (Service sustained with localized crowding)
- **`VULNERABLE`**: $50.0 \le R_{\text{score}} < 70.0$ (Significant fleet reduction; multiple critical corridors)
- **`CRITICAL`**: $R_{\text{score}} < 50.0$ (Catastrophic network impairment; acute overcrowding)

---

### 3.2 Corridor Degradation & Accumulation Formulas

#### A. Bus Breakdown
- Vehicle marked `BROKEN_DOWN` and `is_operational = False`.
- Target route capacity drops: $\text{Cap}_{\text{new}} = \max(0, \text{Cap}_{\text{old}} - \text{Cap}_{\text{bus}})$.
- Active buses count drops: $N_{\text{buses, new}} = \max(0, N_{\text{buses, old}} - 1)$.
- New load factor: $LF_{\text{new}} = \frac{\text{Pax}}{\text{Cap}_{\text{new}}}$ if $\text{Cap}_{\text{new}} > 0$ else $1.0$.

#### B. Route Closure
- Route status marked `CLOSED`.
- Route capacity set to $0$, available seats set to $0$, load factor set to $0.0$.
- Buses assigned to the route marked `STRANDED_ON_CLOSED_ROUTE` and `is_operational = False`.

#### C. Passenger Demand Spike
- For targeted routes:
  $$\text{Pax}_{\text{new}} = \text{Pax}_{\text{old}} + \text{round}\left(\text{Pax}_{\text{old}} \times \frac{\text{Spike\%}}{100.0}\right)$$
  (If baseline passengers is 0, models a baseline surge of $40\%$ of route capacity).
- Proportionately adjusts onboard passenger counts and load factors on operating vehicles.

#### D. Service Delay & Headway Expansion
Simulates passenger accumulation at stops and throughput decay due to expanded cycle times:
- **Passenger Demand Multiplier**:
  $$M_{\text{demand}} = 1.0 + \min\left(0.60, \frac{\text{DelayMinutes}}{10.0} \times 0.08\right)$$
  *(+8% passenger queue accumulation per 10 minutes delay, capped at +60%)*
- **Turnaround Capacity Multiplier**:
  $$M_{\text{capacity}} = \max\left(0.65, 1.0 - \frac{\text{DelayMinutes}}{10.0} \times 0.05\right)$$
  *(-5% throughput degradation per 10 minutes delay, capped at -35%)*

---

## 4. Isolation & Non-Mutation Guarantees

Stage 8 guarantees that zero operational data is mutated during scenario execution:

1. **Read-Only Database Access**: SQL queries retrieve current `Route`, `Bus`, `PassengerLoad`, and `BusPosition` records in read-only mode.
2. **In-Memory Deep Cloning**: All calculation dictionaries (`sim_routes`, `sim_buses`) are deep-cloned before applying disruption mutations.
3. **No Database Writes**: The simulation engine executes **zero** `db.add()`, `db.commit()`, `db.flush()`, or `db.delete()` calls.
4. **Telemetry Invariant**: Production telemetry tables (`bus_positions`, `passenger_loads`) remain 100% unaltered.
5. **Dispatcher Review Invariant**: Stage 7 review records (`reallocation_reviews`) and recommendation states are strictly isolated and preserved.
6. **In-Memory LRU Cache**: Simulated scenarios are retained in an in-memory LRU cache (`_SCENARIO_CACHE`) capped at 50 records. Server restarts automatically purge all simulated scenarios without leaving orphaned database rows.

---

## 5. API Endpoints Specification

### 1. `GET /api/disruption/types`
Returns the catalog of supported disruption types, descriptions, and parameter requirements.

### 2. `POST /api/disruption/simulate`
Executes an isolated transit disruption scenario on an in-memory snapshot and returns impact analyses, entity comparisons, resilience metrics, and advisory reallocations.

**Request Schema (`DisruptionSimulationRequest`)**:
- `disruption_type` (string, required): `BUS_BREAKDOWN`, `ROUTE_CLOSURE`, `DEMAND_SPIKE`, or `SERVICE_DELAY`.
- `bus_id` (integer, optional): Target vehicle ID.
- `bus_number` (string, optional): Target vehicle number (e.g. `"101A"`).
- `route_id` (integer, optional): Target corridor ID.
- `route_number` (string, optional): Target corridor number (e.g. `"101"`).
- `spike_percentage` (float, optional, 5.0 to 300.0): Surge percentage for `DEMAND_SPIKE`.
- `delay_minutes` (float, optional, 1.0 to 240.0): Delay duration for `SERVICE_DELAY`.
- `notes` (string, optional): Operator remarks.

### 3. `GET /api/disruption/scenarios`
Returns concise brief summaries of recently simulated in-memory scenarios.

### 4. `GET /api/disruption/scenarios/{scenario_id}`
Retrieves the complete impact analysis and resilience assessment for a previously executed scenario by ID.

---

## 6. Request and Response Examples

### Example 1: Simulate Bus Breakdown
**Request**:
```http
POST /api/disruption/simulate
Content-Type: application/json

{
  "disruption_type": "BUS_BREAKDOWN",
  "bus_number": "101A",
  "notes": "Downtown engine failure simulation"
}
```

**Response**:
```json
{
  "scenario_id": "SCEN-BUS_BREAKDOWN-89F1A42C",
  "disruption_type": "BUS_BREAKDOWN",
  "parameters": {
    "bus_id": 1,
    "bus_number": "101A",
    "route_number": "101"
  },
  "simulated_at": "2026-10-12T15:20:00Z",
  "summary_headline": "Vehicle Breakdown: Bus 101A on Route 101",
  "executive_summary": "Simulated mechanical failure of Bus 101A removes 60 seats from Route 101. Route load factor adjusted to 125.0%.",
  "resilience_metrics": {
    "fleet_availability_pct": 85.7,
    "capacity_retention_pct": 82.9,
    "capacity_lost": 60,
    "capacity_loss_pct": 17.1,
    "service_continuity_pct": 100.0,
    "routes_affected_count": 1,
    "routes_critical_count": 1,
    "routes_high_count": 0,
    "remaining_available_capacity": 105,
    "resilience_score": 82.1,
    "resilience_rating": "ADEQUATE"
  },
  "affected_routes": [
    {
      "route_id": 1,
      "route_number": "101",
      "name": "Downtown Express",
      "status_before": "NORMAL",
      "status_after": "CRITICAL",
      "load_factor_before": 0.625,
      "load_factor_after": 1.25,
      "passengers_before": 75,
      "passengers_after": 75,
      "capacity_before": 120,
      "capacity_after": 60,
      "available_seats_before": 45,
      "available_seats_after": 0,
      "buses_count_before": 2,
      "buses_count_after": 1,
      "is_directly_affected": true,
      "severity_change": "SEVERELY_DEGRADED",
      "assessment": "Disruption pushed route into CRITICAL overcrowding: load factor surged from 62.5% to 125.0% (+62.5%). Urgent relief required."
    }
  ],
  "affected_buses": [
    {
      "bus_id": 1,
      "bus_number": "101A",
      "route_id": 1,
      "route_number": "101",
      "status_before": "ACTIVE",
      "status_after": "BROKEN_DOWN",
      "is_operational_after": false,
      "passenger_count_before": 40,
      "passenger_count_after": 40,
      "capacity": 60,
      "load_factor_before": 0.6667,
      "load_factor_after": 0.6667,
      "impact_note": "Vehicle disabled due to simulated breakdown."
    }
  ],
  "suggested_reallocations": [
    {
      "id": "SIM-REC-101-202-202B",
      "source_route_number": "202",
      "target_route_number": "101",
      "candidate_bus_number": "202B",
      "bus_capacity": 60,
      "score": 83.5,
      "priority": "HIGH",
      "projected_target_load_factor": 0.625,
      "is_advisory": true,
      "advisory_note": "Simulated scenario recommendation only. No vehicle dispatch performed.",
      "reason": "Simulated mitigation: Target Route 101 is CRITICAL (Load: 125.0%). Reallocating candidate Bus 202B from underutilized Route 202 (12.5%) would reduce target load factor to 62.5%."
    }
  ],
  "is_simulated": true,
  "disclaimer": "SIMULATED DATA — NO LIVE CHANGES. Calculated in-memory on scenario snapshot; live telemetry, bus assignments, and review records remain completely unaltered."
}
```

---

## 7. Assumptions & Missing Data Handling

1. **Non-Predictive Physics**: The module does not predict future real-world events. It evaluates rule-based mathematical headroom on current snapshot values.
2. **Missing Passenger Telemetry**: If a bus lacks historical passenger records, its baseline passenger load defaults to `0` with load factor `0.0`.
3. **Missing GPS Telemetry**: If candidate buses have missing GPS telemetry, geographic proximity scoring assigns a neutral baseline score ($7.5$ pts out of $15.0$) with `distance_meters = null`, allowing ranking without failing.
4. **Zero Capacity Boundary**: If a bus or route has $0$ capacity, load factors evaluate safely to $0.0$ or $1.0$ (if passengers exist) without raising `ZeroDivisionError`.
5. **Non-Negative Available Seats**: Calculated available seats are strictly bounded by $\max(0, \text{Capacity} - \text{Passengers})$.

---

## 8. Known Limitations

1. **In-Memory Cache Volatility**: Scenarios are cached in memory (LRU cap 50). Application server restarts clear previous simulation snapshots.
2. **No Automated Dispatch**: Simulation recommendations are strictly advisory and cannot execute physical dispatches.
3. **Single Scenario Focus**: Multi-day macro-simulations across dynamic weather models are beyond the scope of Stage 8 rule-based calculations.
