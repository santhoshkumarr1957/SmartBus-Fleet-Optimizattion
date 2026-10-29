# TRANSIGHT — Stage 9: Notifications & Alert Management Documentation

## 1. Overview and Objective
Stage 9 implements a deterministic, rule-based notification and alert management system for TRANSIGHT. It continuously monitors live transit telemetry and operational metrics, dynamically detecting transit incidents, displaying them on a dedicated dispatcher dashboard panel, and enabling dispatchers to acknowledge and resolve alerts with full audit logging.

### Key Architecture Guarantees
- **Purely Informational & Non-Mutating:** Alerts never trigger automatic vehicle dispatches, never modify bus route assignments, and never alter live telemetry or Stage 7 review history.
- **No Machine Learning / No Paid APIs:** All alert classifications and detections use pure deterministic logic and threshold boundaries.
- **Strict Deduplication & Recurrence Support:** Repeated telemetry polling updates existing ongoing alerts rather than creating duplicates. If an incident is resolved and later recurs, a distinct new alert is generated.
- **Isolation of Simulation Scenarios:** Disruption simulation notices are strictly tagged with `source="SIMULATION"` and distinguished from live operational alerts (`source="LIVE"`).

---

## 2. Alert Rules & Severity Hierarchy

The engine evaluates 6 deterministic alert conditions during each polling/evaluation cycle:

| Rule # | Alert Type | Severity | Trigger Condition | Target Entity | Source |
|---|---|---|---|---|---|
| **Rule 1** | `CRITICAL_ROUTE_LOAD` | **CRITICAL** | Route passenger load factor $\ge 1.00$ ($\ge 100\%$) across active operational buses | Route (`route_id`, `route_number`) | `LIVE` |
| **Rule 2** | `HIGH_ROUTE_LOAD` | **HIGH** | Route passenger load factor $0.80 \le \text{LF} < 1.00$ ($80\% - 99.9\%$) | Route (`route_id`, `route_number`) | `LIVE` |
| **Rule 3** | `BUS_BREAKDOWN` | **CRITICAL** | Bus reported with `status in ('BROKEN_DOWN', 'MAINTENANCE')` or `is_operational == False` | Bus (`bus_id`, `bus_number`, route) | `LIVE` |
| **Rule 4** | `ROUTE_DISRUPTION` | **CRITICAL** | Route marked inactive (`is_active == False`), closed, or suspended | Route (`route_id`, `route_number`) | `LIVE` |
| **Rule 5** | `REALLOCATION_OPPORTUNITY` | **HIGH** / **WARNING** | Actionable Stage 5 advisory recommendation exists to relieve a HIGH or CRITICAL route | Route & Candidate Bus | `LIVE` |
| **Rule 6** | `SIMULATION_NOTICE` | **CRITICAL** / **HIGH** / **INFO** | Cached disruption simulation scenario outcome (labeled clearly as simulated) | Scenario Target / Corridor | `SIMULATION` |

### Severity Levels
1. **`CRITICAL`:** Demands immediate dispatcher intervention (e.g., severe overcrowding $\ge 100\%$, bus mechanical breakdown, closed transit corridor).
2. **`HIGH`:** Impending service degradation requiring operational attention (e.g., heavy overcrowding $80\% - 99.9\%$, high-priority bus reallocation opportunity).
3. **`WARNING`:** Moderate operational opportunity or service variance (e.g., medium-priority bus reallocation advisory).
4. **`INFO`:** Informational advisories and normal simulation notices.

---

## 3. Deduplication Strategy & Alert Recurrence

### Stable Alert Identity Fingerprint (`dedup_key`)
Alerts use a deterministic fingerprint string based on source, alert type, and target entity:
- Critical Route Load: `LIVE:CRITICAL_ROUTE_LOAD:ROUTE_{route_id}`
- High Route Load: `LIVE:HIGH_ROUTE_LOAD:ROUTE_{route_id}`
- Bus Breakdown: `LIVE:BUS_BREAKDOWN:BUS_{bus_id}`
- Route Disruption: `LIVE:ROUTE_DISRUPTION:ROUTE_{route_id}`
- Reallocation Opportunity: `LIVE:REALLOCATION_OPPORTUNITY:REC_{recommendation_id}`
- Simulation Notice: `SIMULATION:SIMULATION_NOTICE:{scenario_id}`

### Lifecycle & State Transitions
1. **Creation:** When an incident condition is first detected, an alert record is created with `status="ACTIVE"`.
2. **Repeated Evaluation (Deduplication):** If the condition persists across subsequent polling cycles:
   - If the alert is currently `ACTIVE` or `ACKNOWLEDGED`, the existing record is updated (`updated_at=now()`, title/description refreshed) without creating a duplicate record.
3. **Dispatcher Acknowledgement:** Dispatcher transitions alert from `ACTIVE` to `ACKNOWLEDGED`, recording `acknowledged_by` and `acknowledged_at`.
4. **Dispatcher Resolution:** Dispatcher transitions alert to `RESOLVED`, recording `resolved_by`, `resolved_at`, and optional operational notes.
5. **Recurrence Detection:** If an alert is in `RESOLVED` status and the underlying condition is detected again in operational telemetry, the deduplication engine treats it as a genuine recurrence:
   - The resolved record remains untouched for audit integrity.
   - A new, distinct alert record is created with `status="ACTIVE"`.

---

## 4. Database Schema & Alembic Migration

### Model: `Notification` (`notifications` table)
- `id` (Integer, Primary Key, autoincrement)
- `alert_type` (String(50), indexed)
- `severity` (String(20), indexed: `CRITICAL`, `HIGH`, `WARNING`, `INFO`)
- `title` (String(255))
- `description` (Text)
- `source` (String(20), indexed: `LIVE`, `SIMULATION`)
- `status` (String(20), indexed: `ACTIVE`, `ACKNOWLEDGED`, `RESOLVED`)
- `dedup_key` (String(150), indexed)
- `route_id` (Integer, Foreign Key -> `routes.id`, nullable)
- `route_number` (String(50), nullable)
- `bus_id` (Integer, Foreign Key -> `buses.id`, nullable)
- `bus_number` (String(50), nullable)
- `acknowledged_by` (String(100), nullable)
- `acknowledged_at` (DateTime with timezone, nullable)
- `resolved_by` (String(100), nullable)
- `resolved_at` (DateTime with timezone, nullable)
- `notes` (Text, nullable)
- `created_at` (DateTime with timezone, server_default=now())
- `updated_at` (DateTime with timezone, server_default=now())

### Alembic Migration Details
- File: `backend/alembic/versions/0003_notifications_schema.py`
- Revision ID: `0003_notifications`
- Down Revision: `0002_reviews`
- Command to apply to live Supabase:
  ```bash
  cd E:\SmartBus\backend
  .\.venv\Scripts\alembic upgrade head
  ```
- Command to verify migration status:
  ```bash
  .\.venv\Scripts\alembic current
  ```
- **Migration Status Note:** In this environment, remote Supabase PostgreSQL connectivity times out over the network. Therefore, the migration has **not** been applied to the live remote Supabase database. Automated tests run against isolated in-memory SQLite instances where the schema is fully constructed and validated.

---

## 5. Backend REST API Reference

Prefix: `/api/notifications`

### 1. `GET /api/notifications`
Retrieve paginated alert records with filtering options.
- **Query Parameters:**
  - `status`: Filter by status (`ACTIVE`, `ACKNOWLEDGED`, `RESOLVED`, or `ALL`)
  - `severity`: Filter by severity (`CRITICAL`, `HIGH`, `WARNING`, `INFO`, or `ALL`)
  - `type`: Filter by alert type
  - `source`: Filter by source (`LIVE`, `SIMULATION`, or `ALL`)
  - `limit`: Maximum alerts to return (default: 50, max: 200)
  - `offset`: Pagination offset (default: 0)
- **Response:** Array of `NotificationResponse` objects.

### 2. `GET /api/notifications/summary`
Retrieve aggregate counts of alerts for dashboard KPI widgets.
- **Response:**
  ```json
  {
    "total_alerts": 8,
    "active_alerts": 5,
    "acknowledged_alerts": 2,
    "resolved_alerts": 1,
    "critical_alerts": 3,
    "high_alerts": 2,
    "warning_alerts": 0,
    "info_alerts": 0,
    "live_active_alerts": 4,
    "simulation_alerts": 1
  }
  ```

### 3. `POST /api/notifications/{alert_id}/acknowledge`
Acknowledge an active transit alert.
- **Request Body:**
  ```json
  {
    "dispatcher_id": "DISPATCHER-1",
    "notes": "Investigating Route 101 bus frequency"
  }
  ```
- **Validation:**
  - Alert must exist (404 if not found).
  - Alert must be in `ACTIVE` state (400 if already acknowledged or resolved).

### 4. `POST /api/notifications/{alert_id}/resolve`
Mark an alert as resolved.
- **Request Body:**
  ```json
  {
    "dispatcher_id": "DISPATCHER-1",
    "notes": "Route load stabilized; bus reassignment reviewed"
  }
  ```
- **Validation:**
  - Alert must exist (404 if not found).
  - Alert must not already be `RESOLVED` (400 if already resolved).

### 5. `POST /api/notifications/refresh`
Trigger deterministic evaluation of current operational telemetry and create/update alerts without duplicating unchanged incidents.
- **Query Parameter:** `include_simulation` (boolean, default: true)
- **Response:**
  ```json
  {
    "message": "Transit notifications evaluated successfully",
    "total_active_alerts": 5,
    "new_alerts_created": 2,
    "existing_alerts_updated": 3,
    "summary": { ... }
  }
  ```

---

## 6. Frontend Integration

1. **Dashboard Navigation:** Added "Alerts & Notifications" tab to `Navbar.tsx` with live badge counter and pulsing red indicator for critical alerts.
2. **Interactive Notifications Panel (`NotificationsPanel.tsx`):**
   - KPI aggregate counter cards (Active, Critical, High/Warning, Acknowledged, Resolved, Simulated).
   - "Refresh & Evaluate" button with live spinner and feedback banner.
   - Comprehensive filter bar for Severity, Status, and Source.
   - Rich alert cards displaying severity pills, status badges, live/simulation tags, affected corridor/bus tags, description, and audit history.
   - Acknowledge and Resolve action modals allowing dispatcher identification and operational notes.
   - Polished loading skeleton, error handling banner, and informative empty state.
3. **Non-Breaking Architecture:** Overview & Map, Live Transit Map, Route & Bus Monitoring, Reallocation Advisory, and Disruption Simulation screens remain fully intact and operational.

---

## 7. Testing Results

### Stage 9 Automated Test Suite (`backend/tests/test_stage9.py`)
Ran 11 targeted test methods covering all Stage 9 criteria:
- `test_01_alert_rules_detection`: Verified detection of Critical Load, High Load, Breakdown, Disruption, and Opportunity. (PASSED)
- `test_02_load_factor_threshold_boundaries`: Tested exact boundaries at 0.799, 0.80, and 1.00. (PASSED)
- `test_03_duplicate_suppression_on_repeated_polling`: Verified multiple sweeps produce 0 duplicate alerts. (PASSED)
- `test_04_alert_recurrence_after_resolution`: Verified resolved alerts allow new active alerts if condition recurs. (PASSED)
- `test_05_filtering_and_summary_counts`: Verified filtering and aggregate counts. (PASSED)
- `test_06_dispatcher_workflow_transitions`: Verified ACTIVE -> ACKNOWLEDGED -> RESOLVED transitions and timestamps. (PASSED)
- `test_07_invalid_ids_and_state_transitions`: Verified HTTP 404 for missing IDs and 400 for illegal state transitions. (PASSED)
- `test_08_missing_telemetry_graceful_handling`: Verified safety with null GPS and missing passenger load records. (PASSED)
- `test_09_simulation_and_live_alert_separation`: Verified strict isolation of `SIMULATION` source from `LIVE`. (PASSED)
- `test_10_strict_operational_data_non_mutation`: Verified notifications never mutate buses, routes, or telemetry. (PASSED)
- `test_11_api_route_handlers_via_dependency_injection`: Direct invocation of all 5 FastAPI route handlers. (PASSED)

### Regression Test Suite
Ran 55 total unit tests across Stages 5, 7, 8, and 9:
- `test_stage5.py`: 17/17 PASSED
- `test_stage7.py`: 12/12 PASSED
- `test_stage8.py`: 15/15 PASSED
- `test_stage9.py`: 11/11 PASSED
- **Total:** 55/55 PASSED in 1.18 seconds.

### Frontend Production Build
Executed `npm run build` in `frontend/`:
- TypeScript type checking (`tsc`): 0 errors.
- Vite production bundle: Generated successfully in 7.64s.

---

## 8. Known Limitations & Manual Verification Steps

### Limitations
1. **Dispatcher Authentication:** In the absence of a centralized authentication service (e.g. Supabase Auth JWT), dispatcher identities are passed as identifiers (e.g., `DISPATCHER-1`) rather than cryptographically verified tokens.
2. **Supabase Connectivity:** Direct connection to the remote Supabase PostgreSQL host times out in this local test environment; the migration has been prepared in Alembic (`0003_notifications`) but not executed against the live remote Supabase instance.

### Step-by-Step Manual Verification Procedure
1. **Start the Backend:**
   ```bash
   cd E:\SmartBus\backend
   .\.venv\Scripts\uvicorn app.main:app --reload --port 8000
   ```
2. **Start the Frontend:**
   ```bash
   cd E:\SmartBus\frontend
   npm run dev
   ```
3. **Open the Dashboard:** Navigate to `http://localhost:5173` in a web browser.
4. **Verify Alerts Navigation:**
   - Click on the new **Alerts & Notifications** tab in the navigation bar.
   - Confirm active and critical alert count badges in the tab button and KPI summary cards.
5. **Verify Telemetry Refresh:**
   - Click **Refresh & Evaluate**.
   - Verify that the notification list refreshes and the success banner appears.
6. **Verify Workflow Transitions:**
   - Click **Acknowledge** on an ACTIVE alert, enter notes, and confirm.
   - Verify the alert status changes to **ACKNOWLEDGED** and audit details appear.
   - Click **Resolve**, enter resolution notes, and confirm.
   - Verify the alert status changes to **RESOLVED** and the active count decreases.
7. **Verify Filters:**
   - Filter by severity (e.g., `CRITICAL`, `HIGH`).
   - Filter by status (`ACTIVE`, `ACKNOWLEDGED`, `RESOLVED`).
   - Filter by source (`LIVE`, `SIMULATION`).
8. **Verify Invariance:** Check the **Transit Map** and **Route & Bus Monitoring** tabs to confirm bus route assignments and telemetry remain completely unmodified.
