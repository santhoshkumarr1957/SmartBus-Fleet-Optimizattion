# TRANSIGHT — Stage 5: Fleet Reallocation Optimization Module

## 1. Executive Summary

Stage 5 introduces the rule-based **Fleet Reallocation Optimization Module** for the SmartBus (TRANSIGHT) transit management platform. Building directly on the foundation of the Stage 4 Load Intelligence Engine, Stage 5 analyzes real-time route congestion, identifies underutilized routes with surplus capacity, evaluates individual candidate buses, and synthesizes prioritized, explainable reallocation recommendations.

### Core Principles & Constraints
- **Purely Advisory**: Automated route mutations are strictly prohibited. Every recommendation is stamped with `is_advisory = true` and an explicit disclaimer requiring manual dispatcher authorization.
- **Rule-Based & Deterministic**: No black-box machine learning models or paid third-party APIs are used. All calculations rely on deterministic formulas with stable sorting.
- **Zero Schema Alterations**: Operates entirely upon existing tables (`routes`, `stops`, `buses`, `bus_positions`, `passenger_loads`). No Alembic migrations or schema changes were required.
- **Data Integrity**: If telemetry (such as GPS coordinates) is missing or unverified, the system reports the limitation instead of fabricating artificial coordinates or travel times.

---

## 2. Recommendation Algorithm & Scoring Formula

### Mathematical Model
Each potential reallocation of a candidate bus $B$ from an underutilized source route $S$ to an overloaded target route $T$ receives a normalized composite score $S \in [0.0, 100.0]$:

$$S = S_{\text{target}} + S_{\text{source}} + S_{\text{bus}} + S_{\text{proximity}}$$

```
┌────────────────────────────────────────────────────────────────────────┐
│                        COMPOSITE SCORE (100 pts)                       │
├────────────────────┬────────────────────┬───────────────┬──────────────┤
│ Target Need (35%)  │ Source Spare (25%) │ Bus Suit (25%)│ Prox (15%)   │
│ CRITICAL: 30-35 pts│ Headroom: 0-20 pts │ Occ: 0-15 pts │ <=2km: 15 pts│
│ HIGH:     20-30 pts│ Fleet:   0 or 5 pts│ Cap: 0-10 pts │ Decays >2km  │
│ (0 if not overloaded) (0 if not low load) (0 if crowded)│ (7.5 if no GPS)│
└────────────────────┴────────────────────┴───────────────┴──────────────┘
```

### Component Details

#### 1. Target Route Need Severity Component ($S_{\text{target}} \in [0.0, 35.0]$)
Measures the urgency of passenger overcrowding on the target route:
- **`CRITICAL`** ($LF_T \ge 1.00$):
  $$S_{\text{target}} = 30.0 + \min(5.0, (LF_T - 1.00) \times 10.0)$$
  Yields a base of 30.0 points plus up to 5.0 bonus points for extreme overcrowding (capped at 35.0).
- **`HIGH`** ($0.80 \le LF_T < 1.00$):
  $$S_{\text{target}} = 20.0 + \left(\frac{LF_T - 0.80}{0.20}\right) \times 10.0$$
  Linearly scales from 20.0 to 30.0 points.
- **`NORMAL` / `LOW`**: $0.0$ points (routes operating safely do not require incoming bus reallocations).

#### 2. Source Route Spare Capacity Component ($S_{\text{source}} \in [0.0, 25.0]$)
Measures whether the donor route has sufficient surplus capacity to donate a vehicle without becoming degraded:
- **Headroom Component** ($0.0 \text{ to } 20.0$ points):
  $$S_{\text{headroom}} = \max\left(0.0, 1.0 - \frac{LF_S}{0.50}\right) \times 20.0$$
  A route with $LF_S = 0.0$ yields 20.0 points; a route near threshold $LF_S = 0.45$ yields 2.0 points.
- **Fleet Resilience Bonus** ($5.0$ points):
  Awarded if source route has $> 1$ active buses. If source route has only $1$ bus, reallocating it would leave the source route unserviced; hence, 0.0 bonus is awarded and an operational warning is logged.

#### 3. Candidate Bus Availability & Suitability Component ($S_{\text{bus}} \in [0.0, 25.0]$)
Evaluates the physical readiness and capacity of the specific candidate bus $B$:
- **Occupancy Factor** ($0.0 \text{ to } 15.0$ points):
  Let bus load factor $LF_B = \frac{\text{passenger\_count}}{\text{capacity}}$.
  If $LF_B < 0.80$:
  $$S_{\text{occ}} = (1.0 - LF_B) \times 15.0$$
  An empty bus receives the full 15.0 points.
  If $LF_B \ge 0.80$: Bus is crowded and deemed unsuitable ($S_{\text{bus}} = 0.0$).
- **Available Capacity Factor** ($0.0 \text{ to } 10.0$ points):
  $$S_{\text{cap}} = \min\left(10.0, \frac{\text{available\_seats}}{60.0} \times 10.0\right)$$

#### 4. Geographic Deadhead Proximity Component ($S_{\text{proximity}} \in [0.0, 15.0]$)
Evaluates deadhead transit distance from the bus's latest reported GPS position to the target route's origin terminal stop (`sequence_order = 1`), calculated using the Haversine great-circle distance formula:
- **Distance $\le 2.0$ km**: Full $15.0$ points (short deadhead, immediate deployment).
- **Distance $> 2.0$ km**: Decays linearly:
  $$S_{\text{prox}} = \max(2.0, 15.0 - (d_{\text{km}} - 2.0) \times 1.3)$$
- **Telemetry Missing / Unavailable**:
  When live GPS position is missing, the system **does not invent distance values**. Instead, it assigns a neutral baseline of $7.5$ points (50% of the category weight), sets `distance_meters = null`, `estimated_travel_time_minutes = null`, and records a limitation notice.

---

## 3. Operational Feasibility & Limitations Logic

The module enforces strict operational plausibility checks:
1. **Target Assignment Exclusion**: A bus currently operating on the target route cannot be recommended for that same route.
2. **Maintenance Status Exclusion**: Buses with status `MAINTENANCE` or `INACTIVE` are excluded.
3. **Passenger Drop-Off Condition**: If a candidate bus has passengers on board (`current_occupancy > 0`), it is classified as `CONDITIONALLY_FEASIBLE`, with the requirement that passengers must alight at terminal before deadhead transfer.
4. **Service Abandonment Guard**: If the source route has only 1 bus, reallocating it would leave the route with 0 buses. The recommendation flags this operational limitation: `"Source route has only 1 active bus; reallocation will leave source route unserviced."`
5. **Post-Reallocation Projections**:
   - Projected Target Load Factor:
     $$LF_{T, \text{proj}} = \frac{\text{passengers}_T}{\text{capacity}_T + \text{capacity}_B}$$
   - Projected Source Load Factor:
     $$LF_{S, \text{proj}} = \frac{\text{passengers}_S}{\text{capacity}_S - \text{capacity}_B}$$
   If projected source load factor would exceed 80%, a limitation is recorded.

### Priority Tiers
- **`HIGH`**: Composite score $\ge 75.0$, or target is `CRITICAL` with score $\ge 65.0$.
- **`MEDIUM`**: $50.0 \le \text{Score} < 75.0$.
- **`LOW`**: $\text{Score} < 50.0$.

### Deterministic Tie-Breaking
Recommendations are sorted deterministically:
1. Score descending
2. Target route load factor descending
3. Available capacity descending
4. Route & Bus IDs ascending (`target_route_id`, `source_route_id`, `candidate_bus_id`)

---

## 4. API Specification

### Endpoint: `GET /api/optimization/recommendations`

#### Query Parameters
| Parameter | Type | Default | Description |
|---|---|---|---|
| `target_route_id` | `integer` | `None` | Filter recommendations for a specific overloaded target route |
| `source_route_id` | `integer` | `None` | Filter recommendations for a specific source route |
| `min_score` | `float` | `None` | Minimum score threshold (0.0 to 100.0) |
| `best_only` | `boolean` | `false` | If `true`, returns only the single highest-scoring bus per route pair |

#### Response Format: `List[ReallocationRecommendationResponse]`
```json
[
  {
    "id": "REC-101-202-202A",
    "source_route_id": 2,
    "source_route_number": "202",
    "source_route_name": null,
    "source_route_load_factor": 0.3333,
    "source_route_status": "LOW",
    "source_route": {
      "route_id": 2,
      "route_number": "202",
      "name": null,
      "load_factor": 0.3333,
      "status": "LOW"
    },
    "target_route_id": 1,
    "target_route_number": "101",
    "target_route_name": null,
    "target_route_load_factor": 0.9500,
    "target_route_status": "HIGH",
    "target_route": {
      "route_id": 1,
      "route_number": "101",
      "name": null,
      "load_factor": 0.9500,
      "status": "HIGH"
    },
    "candidate_bus_id": 3,
    "candidate_bus_number": "202A",
    "bus_capacity": 60,
    "current_occupancy": 15,
    "available_capacity": 45,
    "bus_load_factor": 0.25,
    "candidate_bus": {
      "bus_id": 3,
      "bus_number": "202A",
      "capacity": 60,
      "current_occupancy": 15,
      "available_capacity": 45,
      "load_factor": 0.25
    },
    "distance_meters": 1420.5,
    "estimated_travel_time_minutes": 2.8,
    "projected_target_load_factor": 0.6333,
    "projected_source_load_factor": 0.6667,
    "score": 83.15,
    "priority": "HIGH",
    "feasibility_status": "CONDITIONALLY_FEASIBLE",
    "limitations": [
      "Candidate bus has 15 passengers on board; requires passenger alighting at route terminal prior to transfer."
    ],
    "reason": "Target Route 101 is experiencing HIGH passenger demand (95.0% load factor), requiring additional capacity. Source Route 202 is underutilized (33.3% load factor) with spare capacity. Candidate Bus 202A has 45 available seats (projected 63.3% post-addition). Deadhead transfer distance: 1.42 km (est. 2.8 min).",
    "is_advisory": true,
    "advisory_note": "Advisory only. Rule-based recommendation requires transit controller review and authorization before dispatch. No automated reassignments have been made."
  }
]
```

### Endpoint: `GET /api/optimization/overview`
Returns summary statistics across the active fleet:
```json
{
  "total_recommendations": 2,
  "high_priority_count": 2,
  "medium_priority_count": 0,
  "low_priority_count": 0,
  "feasible_count": 0,
  "conditionally_feasible_count": 2,
  "infeasible_count": 0,
  "is_advisory": true,
  "disclaimer": "All optimization recommendations are strictly advisory. Final dispatch authority remains with human transit controllers."
}
```

---

## 5. Known Assumptions & Limitations
1. **Deadhead Routing Model**: Great-circle distance (Haversine) is used to approximate travel distance. Turn-by-turn road network routing would require external GIS or routing APIs, which are intentionally excluded by project constraints.
2. **Nominal Speed**: Deadhead transfer time assumes nominal urban bus transit deadhead speed of $30.0$ km/h.
3. **Route Insertion Point**: Deadhead distance is calculated to the target route's origin terminal stop (`sequence_order = 1`).
4. **Advisory Scope**: The module intentionally provides decision support; dispatch controllers retain full operational authority.
