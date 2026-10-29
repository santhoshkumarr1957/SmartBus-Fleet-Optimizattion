# TRANSIGHT — Stage 10: Reports & Performance Analytics Documentation

## 1. Overview and Objective
Stage 10 implements a deterministic, explainable transit operational reporting and performance analytics module for TRANSIGHT. It aggregates existing telemetry, passenger occupancy, vehicle availability, disruption alerts, and dispatcher reviews into comprehensive, structured reports and timeseries analytics, complete with RFC 4180 compliant CSV exports and an interactive dashboard analytics interface.

### Key Architectural Guarantees
- **Deterministic & Explainable:** All metrics, load factors, availability ratios, and trends are computed via transparent mathematical formulas. No machine learning, paid third-party APIs, or external analytics services are used.
- **Strict Read-Only & Non-Mutating:** Generating reports or exporting CSV files never alters bus assignments, route states, live telemetry, historical load logs, or dispatcher review audit records.
- **Data Integrity & Time Scope Transparency:** Every report explicitly declares its `time_scope` (`CURRENT_OPERATIONAL_SNAPSHOT` vs `HISTORICAL_TIMESERIES`). Telemetry samples are aggregated over explicit time windows without fabricating synthetic history.
- **Disruption Live vs. Simulation Isolation:** Real-world incident alerts from the `Notification` table (`source="LIVE"`) are strictly separated from hypothetical disruption simulation drills (`source="SIMULATION"`).
- **Supervisory Reallocation Oversight:** Clearly states that recorded review decisions represent dispatcher supervisory determinations and that approved recommendations do not imply automated vehicle reassignments or tracked physical vehicle deadheading.

---

## 2. Report Definitions, Data Sources, and Mathematical Formulas

### A. Fleet Utilization Report
- **Data Sources:** `Bus` table and the latest record for each vehicle from `PassengerLoad`.
- **Formulas & Classifications:**
  - **Operational Buses:** Count of buses where `(status).upper() not in ("INACTIVE", "BROKEN_DOWN", "MAINTENANCE")`.
  - **Fleet Availability Percentage:**
    $$\text{Fleet Availability (\%)} = \left(\frac{\text{Operational Buses}}{\text{Total Registered Buses}}\right) \times 100$$
  - **Total Passenger Capacity:**
    $$\text{Capacity} = \sum_{b \in \text{Operational Buses}} \text{capacity}_b$$
  - **Total Current Passengers:**
    $$\text{Passengers} = \sum_{b \in \text{Operational Buses}} \text{latest\_load}_b$$
  - **Available Seats:**
    $$\text{Available Seats} = \max(0, \text{Capacity} - \text{Passengers})$$
  - **Fleet Load Factor:**
    $$\text{Load Factor} = \frac{\text{Passengers}}{\text{Capacity}} \quad (\text{if Capacity} > 0, \text{ else } 0.0)$$
  - **Vehicle Load Distribution:**
    - `CRITICAL`: Load Factor $\ge 1.00$ ($\ge 100\%$)
    - `HIGH`: $0.80 \le \text{Load Factor} < 1.00$ ($80\% - 99.9\%$)
    - `NORMAL`: $0.50 \le \text{Load Factor} < 0.80$ ($50\% - 79.9\%$)
    - `LOW`: Load Factor $< 0.50$ ($< 50\%$)

### B. Route Performance Report
- **Data Sources:** `Route` table, `Bus` table (active operational vehicles assigned to route), and latest `PassengerLoad`.
- **Formulas & Classifications:**
  - **Assigned Bus Count:** Operational buses where `current_route_id == route.id`.
  - **Route Capacity:** Sum of capacities of assigned operational buses.
  - **Route Passengers:** Sum of latest passenger loads across assigned operational buses.
  - **Route Load Factor:**
    $$\text{Route LF} = \frac{\text{Route Passengers}}{\text{Route Capacity}} \quad (\text{if Route Capacity} > 0, \text{ else } 0.0)$$
  - **Status Classification:**
    - Inactive route (`is_active == False`): `CLOSED`
    - $\text{LF} \ge 1.00$: `CRITICAL` (Severe Overcrowding)
    - $0.80 \le \text{LF} < 1.00$: `HIGH` (Heavy Congestion)
    - $0.50 \le \text{LF} < 0.80$: `NORMAL` (Balanced Operational Load)
    - $\text{LF} < 0.50$: `LOW` (Underutilized Surplus Capacity)
  - **Network Summary:** Total active/inactive routes, count of overloaded routes (`HIGH` or `CRITICAL`), count of underutilized routes (`LOW`), highest load route, lowest load route.

### C. Disruption Analysis Report
- **Data Sources:** `Notification` records from Stage 9 (`source="LIVE"` and `source="SIMULATION"`) and cached simulation scenarios from Stage 8 `DisruptionService`.
- **Metrics:**
  - **Live Operational Incidents:** Breakdown counts (`BUS_BREAKDOWN`), route discontinuations (`ROUTE_DISRUPTION`), critical load alerts (`CRITICAL_ROUTE_LOAD`), active incidents count, acknowledged count, resolved count.
  - **Simulated Disruption Drills:** Isolated count of simulation scenarios tested, accompanied by explicit isolation flags and disclaimer text.

### D. Reallocation & Dispatcher Review Report
- **Data Sources:** Stage 5 `OptimizationService` advisory proposals and Stage 7 `ReallocationReview` table.
- **Metrics:**
  - Active advisory recommendations count and priority tiers (HIGH, MEDIUM, LOW).
  - Total dispatcher reviews logged, approved proposals count, rejected proposals count, deferred proposals count, pending unreviewed recommendations count.
  - **Operational Limitation Statement:** Explicit disclosure that approved recommendations represent human dispatcher concurrence and do not execute automated vehicle reassignments or track physical vehicle deadheading.

### E. Historical Trends Report
- **Data Sources:** Timestamped records in `PassengerLoad` within the requested time window.
- **Time Windows & Bucket Intervals:**
  - `1h`: 5-minute buckets (12 data points), window: $[now - 1\text{h}, now]$.
  - `24h`: 1-hour buckets (24 data points), window: $[now - 24\text{h}, now]$.
  - `7d`: 6-hour buckets (28 data points), window: $[now - 7\text{d}, now]$.
- **Aggregation Metrics per Bucket:**
  - Average load factor across records in the bucket.
  - Total passengers recorded across records in the bucket.
  - Peak observed load factor within the bucket.
  - Sample count of telemetry records in the bucket (empty buckets return `sample_count: 0`, `average_load_factor: 0.0` without fabricating fake data).

---

## 3. Backend REST API Reference

Prefix: `/api/reports`

### 1. `GET /api/reports/overview`
Returns consolidated executive performance overview linking fleet utilization, route performance, disruption counters, review outcomes, and 24-hour trend preview.

### 2. `GET /api/reports/fleet-utilization`
Returns detailed fleet asset availability, total seats, load factor distribution, and vehicle-level brief records.

### 3. `GET /api/reports/routes`
Returns route-level passenger demand, capacity headroom, load factors, and network extrema (highest/lowest load corridors).

### 4. `GET /api/reports/disruptions`
Returns operational breakdown and closure audits, live incident status counts, and isolated simulation scenario summaries.

### 5. `GET /api/reports/reallocation`
Returns advisory proposal counts, priority breakdowns, and dispatcher review decision audit metrics.

### 6. `GET /api/reports/trends?range=1h|24h|7d`
Returns timeseries telemetry buckets over configurable time windows (`1h`, `24h`, or `7d`).
- **Validation:** Invalid ranges raise HTTP 400 Bad Request.

### 7. `GET /api/reports/export?type={type}&range={range}&format=csv`
Streams RFC 4180 compliant CSV export with stable headers and safe comma/quote escaping.
- Supported `type` values: `fleet`, `routes`, `disruptions`, `reallocation`, `trends`.
- Supported `format` values: `csv`.
- Headers: `Content-Disposition: attachment; filename="transight_{type}_report_{timestamp}.csv"`.
- **Validation:** Unsupported types or formats raise HTTP 400 Bad Request.

---

## 4. Frontend Integration

1. **Dashboard Navigation (`Navbar.tsx`):**
   - Added **Reports & Analytics** tab button.
   - Updated header badge to `TRANSIGHT • Stage 10`.
2. **Interactive Reports Panel (`ReportsPanel.tsx`):**
   - **Overview & KPIs:** 6 executive KPI cards, fleet load distribution breakdown, and historical trend preview.
   - **Fleet Utilization:** Asset inventory table with status pills, seat headroom, and live load factor progress bars.
   - **Route Performance:** Corridor comparison table, terminal information, and overcrowding condition descriptors.
   - **Historical Trends:** Interactive SVG area/line chart with 1h / 24h / 7d range selector, hover tooltips, and sample density metrics.
   - **Disruption Analysis:** Real-world incident summary cards, live breakdown/closure counters, and prominent simulation isolation notice.
   - **Reallocation & Reviews:** Advisory proposals, priority breakdown, approval/rejection audit counts, and supervisory limitation notice.
   - **CSV Export:** Direct one-click download buttons for Fleet, Routes, Disruptions, Reallocation, and Trends CSVs.
3. **Responsive Architecture:** Preserves all existing screens (Overview & Map, Transit Map, Route & Bus Monitoring, Optimization, Dispatcher Review, Disruption Simulation, Alerts).

---

## 5. Testing Results

### Stage 10 Automated Test Suite (`backend/tests/test_stage10.py`)
9 focused test methods:
- `test_01_fleet_utilization_calculations`: Verified operational vehicle count, availability percentage, seat calculations, and load distribution. (PASSED)
- `test_02_route_performance_aggregation`: Verified route capacities, passenger counts, load factors, and overcrowding ratings. (PASSED)
- `test_03_disruption_analysis_and_simulation_isolation`: Verified live alerts and simulated scenarios remain isolated. (PASSED)
- `test_04_reallocation_and_dispatcher_review_summary`: Verified review breakdown counts and operational limitation statement. (PASSED)
- `test_05_historical_trends_time_windows`: Tested boundary filtering for 1h, 24h, and 7d windows and invalid parameter rejection. (PASSED)
- `test_06_empty_database_and_missing_telemetry`: Verified zero-division safety and empty dataset handling. (PASSED)
- `test_07_csv_export_headers_and_escaping`: Verified stable headers, field escaping, and CSV generation. (PASSED)
- `test_08_reports_do_not_mutate_operational_data`: Verified database immutability. (PASSED)
- `test_09_fastapi_route_handlers`: Verified direct route invocation via dependency injection. (PASSED)

### Regression Test Suite
Executed 64 unit tests across Stages 5, 7, 8, 9, and 10:
- `test_stage5.py`: 17 passed
- `test_stage7.py`: 12 passed
- `test_stage8.py`: 15 passed
- `test_stage9.py`: 11 passed
- `test_stage10.py`: 9 passed
- **Total:** 64/64 PASSED in 1.34s.

### Frontend Production Build
Executed `npm run build` in `frontend/`:
- TypeScript type check (`tsc`): 0 errors.
- Vite production bundle: Generated in 8.71s (`dist/index.html`, `dist/assets/index-*.css`, `dist/assets/index-*.js`).

---

## 6. Known Limitations & Manual Verification Steps

### Limitations
1. **No Real Vehicle Tracking of Completed Reallocations:** The schema records dispatcher approvals, but does not track physical deadhead vehicle repositioning or executed bus reassignments.
2. **Supabase Connectivity:** As in Stages 5–9, direct connection to the remote Supabase PostgreSQL instance times out in this local test environment; tests run self-contained against in-memory SQLite fixtures.
3. **No PDF Export:** Only RFC 4180 CSV export is implemented in accordance with requirements.

### Step-by-Step Manual Verification Procedure
1. **Start Backend Server:**
   ```bash
   cd E:\SmartBus\backend
   .\.venv\Scripts\uvicorn app.main:app --reload --port 8000
   ```
2. **Start Frontend Dev Server:**
   ```bash
   cd E:\SmartBus\frontend
   npm run dev
   ```
3. **Open the Dashboard:** Navigate to `http://localhost:5173`.
4. **Access Reports Tab:** Click on the **Reports & Analytics** tab in the navigation bar.
5. **Verify Executive Overview:** Review the 6 KPI cards (Fleet Availability, Load Factor, Available Seats, Active Corridors, Live Disruptions, Dispatcher Reviews).
6. **Verify Sub-Section Navigation:**
   - Click **Fleet Utilization**: Verify vehicle table with plate, status, and occupancy bars.
   - Click **Route Performance**: Verify route comparison table with load factors and condition descriptors.
   - Click **Historical Trends**: Toggle between `1H`, `24H`, and `7D`. Verify the SVG area/line chart updates with bucket labels and load percentages.
   - Click **Disruption Analysis**: Verify live breakdown and closure counts, and check the yellow isolation notice.
   - Click **Reallocation & Reviews**: Verify proposal counts, approval/rejection metrics, and supervisory limitation disclaimer.
7. **Test CSV Export:** Click **Export Fleet CSV**, **Export Routes CSV**, or **Export Trends CSV**. Verify that a `.csv` file downloads with clean tabular headers and properly formatted data rows.
8. **Verify Non-Interference:** Switch to other tabs (**Overview & Map**, **Transit Map**, **Monitoring**, **Reallocation**, **Simulation**, **Alerts**) to confirm all prior features remain fully intact.
