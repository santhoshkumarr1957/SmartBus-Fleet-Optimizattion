export interface HealthStatusResponse {
  status: string;
  timestamp?: string;
  service?: string;
}

export type ConnectionState = 'Checking...' | 'Connected' | 'Disconnected' | 'Degraded';

export type LoadStatus = 'LOW' | 'NORMAL' | 'HIGH' | 'CRITICAL' | string;

export type PriorityTier = 'HIGH' | 'MEDIUM' | 'LOW' | string;

export type FeasibilityStatus =
  | 'FEASIBLE'
  | 'CONDITIONALLY_FEASIBLE'
  | 'LIMITED_DATA'
  | 'INFEASIBLE'
  | string;

export type ReviewDecision = 'APPROVED' | 'REJECTED' | 'DEFERRED' | string;

export interface BusLive {
  bus_id: number;
  bus_number: string;
  route_id: number | null;
  route_number: string | null;
  latitude: number | null;
  longitude: number | null;
  speed: number | null;
  heading: number | null;
  passenger_count: number | null;
  capacity: number;
  load_factor: number | null;
  home_route_id?: number | null;
  home_route_number?: string | null;
  assigned_route_id?: number | null;
  assigned_route_number?: string | null;
  active_route_id?: number | null;
  active_route_number?: string | null;
  is_transferring?: boolean;
  transfer_status?: string | null;
  target_route_id?: number | null;
  target_route_number?: string | null;
  direction?: string | null;
  timestamp: string | null;
}

export interface RouteLive {
  route_id: number;
  route_number: string;
  number_of_buses: number;
  total_passengers: number;
  total_capacity: number;
  load_factor: number;
  status: LoadStatus;
  demand_profile?: DemandProfile;
}

export interface IntelligenceOverview {
  total_routes: number;
  total_buses: number;
  low_routes: number;
  normal_routes: number;
  high_routes: number;
  critical_routes: number;
  routes_needing_attention: number;
  potential_reallocation_opportunities: number;
}

export interface RouteIntelligence {
  route_id: number;
  route_number: string;
  number_of_buses: number;
  total_passengers: number;
  total_capacity: number;
  available_seats: number;
  load_factor: number;
  status: LoadStatus;
  assessment: string;
  demand_profile?: DemandProfile;
}

export interface BusIntelligence {
  bus_id: number;
  bus_number: string;
  route_id: number | null;
  route_number: string | null;
  home_route_id?: number | null;
  home_route_number?: string | null;
  assigned_route_id?: number | null;
  assigned_route_number?: string | null;
  active_route_id?: number | null;
  active_route_number?: string | null;
  is_transferring?: boolean;
  transfer_status?: string | null;
  target_route_id?: number | null;
  target_route_number?: string | null;
  passenger_count: number;
  capacity: number;
  available_seats: number;
  load_factor: number;
  status: LoadStatus;
}

export interface RouteBrief {
  route_id: number;
  route_number: string;
  name?: string | null;
  load_factor: number;
  status: LoadStatus;
}

export interface BusBrief {
  bus_id: number;
  bus_number: string;
  capacity: number;
  current_occupancy: number;
  available_capacity: number;
  load_factor: number;
}

export interface TransitStop {
  id: number;
  route_id: number;
  name: string;
  stop_code?: string | null;
  sequence_order: number;
  latitude: number;
  longitude: number;
}

export interface RouteDetailed {
  id: number;
  route_number: string;
  name: string;
  description?: string | null;
  origin: string;
  destination: string;
  is_active: boolean;
  stops: TransitStop[];
}

export interface ReallocationExecutionCreate {
  dispatcher_id?: string;
  notes?: string;
}

export interface ReallocationExecution {
  id: number;
  recommendation_id: string;
  review_id?: number | null;
  bus_id: number;
  bus_number: string;
  source_route_id: number;
  source_route_number: string;
  target_route_id: number;
  target_route_number: string;
  dispatcher_id: string;
  status: 'EXECUTED' | 'IN_PROGRESS' | 'FAILED';
  error_message?: string | null;
  notes?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReallocationReviewCreate {
  decision: ReviewDecision;
  dispatcher_id?: string;
  notes?: string;
  target_route_id?: number;
  target_route_number?: string;
  source_route_id?: number;
  source_route_number?: string;
  candidate_bus_id?: number;
  candidate_bus_number?: string;
  score?: number;
  priority?: string;
}

export interface ReallocationReview {
  id: number;
  recommendation_id: string;
  decision: ReviewDecision;
  dispatcher_id?: string | null;
  target_route_id?: number | null;
  target_route_number?: string | null;
  source_route_id?: number | null;
  source_route_number?: string | null;
  candidate_bus_id?: number | null;
  candidate_bus_number?: string | null;
  score?: number | null;
  priority?: string | null;
  notes?: string | null;
  execution_status?: string | null;
  executed_at?: string | null;
  created_at: string;
  updated_at: string;
  is_advisory: boolean;
  advisory_note: string;
}

export interface ReallocationRecommendation {
  id: string;
  source_route_id: number;
  source_route_number: string;
  source_route_name?: string | null;
  source_route_load_factor: number;
  source_route_status: LoadStatus;
  source_route?: RouteBrief | null;

  target_route_id: number;
  target_route_number: string;
  target_route_name?: string | null;
  target_route_load_factor: number;
  target_route_status: LoadStatus;
  target_route?: RouteBrief | null;

  candidate_bus_id: number | null;
  candidate_bus_number: string | null;
  bus_capacity: number | null;
  current_occupancy: number | null;
  available_capacity: number | null;
  bus_load_factor: number | null;
  candidate_bus?: BusBrief | null;

  distance_meters: number | null;
  estimated_travel_time_minutes: number | null;
  projected_target_load_factor: number | null;
  projected_source_load_factor: number | null;

  score: number;
  priority: PriorityTier;
  feasibility_status: FeasibilityStatus;
  limitations: string[];
  reason: string;
  is_advisory: boolean;
  advisory_note: string;

  // Stage 7 Dispatcher Review
  review_status?: ReviewDecision | null;
  latest_review?: ReallocationReview | null;

  // Execution status
  execution_status?: string | null;
  executed_at?: string | null;
  latest_execution?: ReallocationExecution | null;
}

export interface OptimizationOverview {
  total_recommendations: number;
  high_priority_count: number;
  medium_priority_count: number;
  low_priority_count: number;
  feasible_count: number;
  conditionally_feasible_count: number;
  infeasible_count: number;
  approved_count?: number;
  rejected_count?: number;
  deferred_count?: number;
  pending_count?: number;
  executed_count?: number;
  is_advisory: boolean;
  disclaimer: string;
  diagnostic_reasons?: string[];
}

export interface ManualReassignmentPayload {
  target_route_id: number;
  dispatcher_id?: string;
  reason?: string;
}

export interface DashboardTransitData {
  health: HealthStatusResponse | null;
  intelligenceOverview: IntelligenceOverview | null;
  optimizationOverview: OptimizationOverview | null;
  liveBuses: BusLive[];
  liveRoutes: RouteLive[];
  routeIntelligence: RouteIntelligence[];
  busIntelligence: BusIntelligence[];
  recommendations: ReallocationRecommendation[];
}

// ----------------------------------------------------------------------------
// Stage 8: Transit Disruption Simulation and Resilience Analysis Types
// ----------------------------------------------------------------------------

export type DisruptionType =
  | 'BUS_BREAKDOWN'
  | 'ROUTE_CLOSURE'
  | 'DEMAND_SPIKE'
  | 'SERVICE_DELAY'
  | string;

export interface DisruptionTypeInfo {
  type: DisruptionType;
  name: string;
  description: string;
  required_parameters: string[];
  optional_parameters: string[];
  example_parameters: Record<string, any>;
}

export interface DisruptionSimulationRequest {
  disruption_type: DisruptionType;
  bus_id?: number | null;
  bus_number?: string | null;
  route_id?: number | null;
  route_number?: string | null;
  spike_percentage?: number | null;
  demand_multiplier?: number | null;
  demand_percentage?: number | null;
  delay_minutes?: number | null;
  notes?: string | null;
}

export interface RouteImpactSummary {
  route_id: number;
  route_number: string;
  name?: string | null;
  status_before: string;
  status_after: string;
  load_factor_before: number;
  load_factor_after: number;
  passengers_before: number;
  passengers_after: number;
  capacity_before: number;
  capacity_after: number;
  available_seats_before: number;
  available_seats_after: number;
  buses_count_before: number;
  buses_count_after: number;
  is_directly_affected: boolean;
  severity_change: 'UNCHANGED' | 'DEGRADED' | 'SEVERELY_DEGRADED' | 'CLOSED' | string;
  assessment: string;
}

export interface BusImpactSummary {
  bus_id: number;
  bus_number: string;
  route_id?: number | null;
  route_number?: string | null;
  status_before: string;
  status_after: string;
  is_operational_after: boolean;
  passenger_count_before: number;
  passenger_count_after: number;
  capacity: number;
  load_factor_before: number;
  load_factor_after: number;
  impact_note: string;
}

export interface ResilienceMetrics {
  fleet_availability_pct: number;
  capacity_retention_pct: number;
  capacity_lost: number;
  capacity_loss_pct: number;
  service_continuity_pct: number;
  routes_affected_count: number;
  routes_critical_count: number;
  routes_high_count: number;
  remaining_available_capacity: number;
  resilience_score: number;
  resilience_rating: 'EXCELLENT' | 'ADEQUATE' | 'VULNERABLE' | 'CRITICAL' | string;
}

export interface DisruptionSimulationResponse {
  scenario_id: string;
  disruption_type: DisruptionType;
  parameters: Record<string, any>;
  simulated_at: string;
  summary_headline: string;
  executive_summary: string;
  resilience_metrics: ResilienceMetrics;
  affected_routes: RouteImpactSummary[];
  affected_buses: BusImpactSummary[];
  suggested_reallocations: ReallocationRecommendation[];
  warnings?: string[];
  notes?: string | null;
  is_simulated: boolean;
  disclaimer: string;
}

export interface DisruptionScenarioBrief {
  scenario_id: string;
  disruption_type: DisruptionType;
  target_description: string;
  simulated_at: string;
  resilience_score: number;
  resilience_rating: string;
  routes_affected_count: number;
  capacity_lost: number;
}

// ----------------------------------------------------------------------------
// Stage 9: Notifications & Alert Management Types
// ----------------------------------------------------------------------------

export type AlertSeverity = 'CRITICAL' | 'HIGH' | 'WARNING' | 'INFO';
export type AlertStatus = 'ACTIVE' | 'ACKNOWLEDGED' | 'RESOLVED';
export type AlertSource = 'LIVE' | 'SIMULATION';
export type AlertType =
  | 'CRITICAL_ROUTE_LOAD'
  | 'HIGH_ROUTE_LOAD'
  | 'BUS_BREAKDOWN'
  | 'ROUTE_DISRUPTION'
  | 'REALLOCATION_OPPORTUNITY'
  | 'SIMULATION_NOTICE'
  | string;

export interface NotificationItem {
  id: number;
  alert_type: AlertType;
  severity: AlertSeverity;
  title: string;
  description: string;
  source: AlertSource;
  status: AlertStatus;
  dedup_key: string;
  route_id?: number | null;
  route_number?: string | null;
  bus_id?: number | null;
  bus_number?: string | null;
  acknowledged_by?: string | null;
  acknowledged_at?: string | null;
  resolved_by?: string | null;
  resolved_at?: string | null;
  notes?: string | null;
  created_at: string;
  updated_at: string;
}

export interface NotificationSummary {
  total_alerts: number;
  active_alerts: number;
  acknowledged_alerts: number;
  resolved_alerts: number;
  critical_alerts: number;
  high_alerts: number;
  warning_alerts: number;
  info_alerts: number;
  live_active_alerts: number;
  simulation_alerts: number;
}

export interface NotificationRefreshResponse {
  message: string;
  total_active_alerts: number;
  new_alerts_created: number;
  existing_alerts_updated: number;
  summary: NotificationSummary;
}

export interface NotificationActionPayload {
  dispatcher_id?: string;
  notes?: string;
}

// ----------------------------------------------------------------------------
// Stage 10: Reports & Performance Analytics Types
// ----------------------------------------------------------------------------

export interface BusUtilizationBrief {
  bus_id: number;
  bus_number: string;
  license_plate: string;
  status: string;
  capacity: number;
  current_load: number;
  available_seats: number;
  load_factor: number;
  current_route_id?: number | null;
  current_route_number?: string | null;
}

export interface FleetUtilizationReport {
  generated_at: string;
  time_scope: string;
  total_buses: number;
  operational_buses: number;
  inactive_buses: number;
  broken_down_buses: number;
  maintenance_buses: number;
  fleet_availability_pct: number;
  total_passenger_capacity: number;
  total_current_passengers: number;
  available_seats: number;
  fleet_load_factor: number;
  load_distribution: {
    LOW: number;
    NORMAL: number;
    HIGH: number;
    CRITICAL: number;
  };
  buses: BusUtilizationBrief[];
}

export interface RoutePerformanceItem {
  route_id: number;
  route_number: string;
  name?: string | null;
  origin?: string | null;
  destination?: string | null;
  is_active: boolean;
  assigned_bus_count: number;
  total_capacity: number;
  total_passengers: number;
  available_seats: number;
  load_factor: number;
  status: 'LOW' | 'NORMAL' | 'HIGH' | 'CRITICAL' | 'CLOSED' | string;
  overcrowding_level: string;
}

export interface RoutePerformanceReport {
  generated_at: string;
  time_scope: string;
  total_routes: number;
  active_routes: number;
  inactive_routes: number;
  overloaded_routes_count: number;
  underutilized_routes_count: number;
  highest_load_route?: string | null;
  lowest_load_route?: string | null;
  routes: RoutePerformanceItem[];
}

export interface DisruptionEventBrief {
  alert_id: number;
  alert_type: string;
  severity: string;
  title: string;
  description: string;
  source: 'LIVE' | 'SIMULATION' | string;
  status: string;
  route_number?: string | null;
  bus_number?: string | null;
  created_at: string;
  resolved_at?: string | null;
  acknowledged_by?: string | null;
  resolved_by?: string | null;
}

export interface DisruptionReport {
  generated_at: string;
  live_incidents_total: number;
  live_active_count: number;
  live_acknowledged_count: number;
  live_resolved_count: number;
  live_breakdowns_count: number;
  live_route_disruptions_count: number;
  live_overcrowding_alerts_count: number;
  live_events: DisruptionEventBrief[];
  simulation_scenarios_count: number;
  simulated_events: DisruptionEventBrief[];
  is_simulation_isolated: boolean;
  disclaimer: string;
}

export interface ReviewOutcomeBrief {
  id: number;
  recommendation_id: string;
  decision: string;
  dispatcher_id?: string | null;
  target_route_number?: string | null;
  source_route_number?: string | null;
  candidate_bus_number?: string | null;
  created_at: string;
  notes?: string | null;
}

export interface ReallocationReport {
  generated_at: string;
  active_proposals_count: number;
  high_priority_count: number;
  medium_priority_count: number;
  low_priority_count: number;
  total_reviews_recorded: number;
  approved_count: number;
  rejected_count: number;
  deferred_count: number;
  pending_count: number;
  recent_reviews: ReviewOutcomeBrief[];
  operational_limitation_statement: string;
}

export interface TrendDataPoint {
  timestamp: string;
  average_load_factor: number;
  total_passengers: number;
  peak_load_factor: number;
  sample_count: number;
}

export interface TrendsReport {
  generated_at: string;
  time_range: '1h' | '24h' | '7d' | string;
  bucket_interval: string;
  start_time: string;
  end_time: string;
  total_samples: number;
  overall_average_load_factor: number;
  peak_observed_load_factor: number;
  datapoints: TrendDataPoint[];
  data_density_note: string;
}

export interface ReportsOverview {
  generated_at: string;
  fleet: FleetUtilizationReport;
  routes: RoutePerformanceReport;
  disruptions_summary: {
    live_incidents_total: number;
    live_active: number;
    live_breakdowns: number;
    live_closures: number;
    simulated_scenarios: number;
  };
  reviews_summary: {
    total_reviews: number;
    approved: number;
    rejected: number;
    deferred: number;
    pending: number;
  };
  trends_preview: TrendsReport;
}

// ----------------------------------------------------------------------------
// Traffic Simulation Control & Monitoring Types
// ----------------------------------------------------------------------------

export type SimulationState = 'RUNNING' | 'PAUSED' | 'STOPPED';
export type DemandProfile = 'LOW' | 'NORMAL' | 'HIGH' | 'CUSTOM' | 'MIXED' | string;
export type SimulationSpeed = 1 | 2 | 5;

export interface RouteDemand {
  route_id: number;
  route_number: string;
  route_name?: string | null;
  demand_profile: DemandProfile;
  message?: string;
}

export interface SimulationStatus {
  status: SimulationState;
  active_profile: DemandProfile;
  scenario: string;
  speed: SimulationSpeed;
  interval_seconds: number;
  effective_interval: number;
  is_running: boolean;
  is_paused: boolean;
  tick_count: number;
  started_at: string | null;
  elapsed_seconds: number;
  last_updated: string | null;
  total_buses: number;
  total_routes: number;
  route_demands?: Record<string, DemandProfile>;
  route_demand_list?: RouteDemand[];
  message: string;
}

export interface SimulationProfile {
  id: DemandProfile;
  name: string;
  description: string;
  is_active: boolean;
  tag?: string;
}

export interface SimulationEvent {
  id: string;
  timestamp: string;
  type: string;
  level: 'info' | 'warning' | 'critical' | 'success';
  message: string;
}

export interface SimulationKpi {
  total_active_buses: number;
  total_routes: number;
  average_load_factor: number;
  low_load_routes_count: number;
  normal_load_routes_count: number;
  high_load_routes_count: number;
  critical_load_routes_count: number;
  attention_required_count: number;
  total_fleet_capacity: number;
  total_passengers: number;
  available_capacity_seats: number;
  active_profile: DemandProfile;
  simulation_status: SimulationState;
}

// -----------------------------------------------------------------------------
// Phases 1, 2, 3, 4, 5, 6: Weather, Breakdown, Hybrid Optimization Types
// -----------------------------------------------------------------------------

export interface WeatherObservation {
  condition: 'NORMAL' | 'LIGHT_RAIN' | 'HEAVY_RAIN' | 'SEVERE_WEATHER' | string;
  description: string;
  temperature_c: number;
  precipitation_mm: number;
  relative_humidity_pct?: number | null;
  wind_speed_kmh?: number | null;
  visibility_km?: number | null;
  location: string;
  latitude: number;
  longitude: number;
  observed_at: string;
  source: string;
  is_live: boolean;
  freshness_seconds: number;
  speed_factor: number;
  travel_time_multiplier: number;
  delay_minutes_per_corridor: number;
  impact_summary: string;
  affected_corridors: string[];
}

export type BreakdownStatus = 'REPORTED' | 'CONFIRMED' | 'UNDER_REPAIR' | 'AVAILABLE';

export interface BusBreakdown {
  id: number;
  bus_id: number;
  bus_number: string;
  route_id?: number | null;
  route_number?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  location_name?: string | null;
  status: BreakdownStatus;
  severity: string;
  notes?: string | null;
  source: string;
  reported_by: string;
  recovered_by?: string | null;
  reported_at: string;
  recovered_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface BreakdownSummary {
  total_breakdowns: number;
  active_breakdowns: number;
  under_repair_count: number;
  recovered_count: number;
  affected_routes: string[];
  fleet_availability_pct: number;
  total_capacity_lost: number;
  incidents: BusBreakdown[];
}

export interface ReplacementCandidate {
  broken_bus_id: number;
  broken_bus_number: string;
  route_id?: number | null;
  route_number?: string | null;
  capacity_lost: number;
  candidate_donor_buses: BusBrief[];
  eligible_donor_routes: RouteBrief[];
  recommended_bus_id?: number | null;
  recommended_bus_number?: string | null;
  recommended_source_route?: string | null;
  binding_constraints: string[];
  explanation: string;
}

export interface OptimizationAllocationItem {
  candidate_id: string;
  bus_id: number;
  bus_number: string;
  source_route_id: number;
  source_route_number: string;
  target_route_id: number;
  target_route_number: string;
  bus_capacity: number;
  current_occupancy: number;
  available_seats: number;
  transfer_distance_km: number;
  nominal_travel_time_min: number;
  weather_adjusted_travel_time_min: number;
  utility_score: number;
  priority: string;
  status: string;
  explanation: string;
}

export interface NetworkMetricsSnapshot {
  overloaded_routes_count: number;
  overloaded_route_numbers: string[];
  underutilized_routes_count: number;
  underutilized_route_numbers: string[];
  total_passengers: number;
  total_capacity: number;
  fleet_load_factor: number;
  total_unmet_demand_proxy: number;
  routes_below_minimum_coverage: number;
  operational_buses_count: number;
  unavailable_buses_count: number;
}

export interface OptimizationPlan {
  plan_id: string;
  created_at: string;
  status: string;
  solver_engine: string;
  solver_status: string;
  objective_value?: number | null;
  solver_time_ms: number;
  weather_condition: string;
  weather_delay_factor: number;
  weather_summary: string;
  allocations: OptimizationAllocationItem[];
  total_allocations_count: number;
  baseline_metrics: NetworkMetricsSnapshot;
  predicted_metrics: NetworkMetricsSnapshot;
  predicted_improvement_pct: number;
  total_transfer_distance_km: number;
  total_transfer_time_min: number;
  capacity_reallocated_seats: number;
  binding_constraints: string[];
  summary_notes: string;
  is_advisory: boolean;
  advisory_disclaimer: string;
}

export interface ScenarioEvaluation {
  scenario_id: string;
  scenario_name: string;
  evaluated_at: string;
  is_simulation: boolean;
  demand_profiles: Record<string, string>;
  broken_down_buses: string[];
  weather_scenario: string;
  weather_speed_factor: number;
  weather_impact_description: string;
  baseline_metrics: NetworkMetricsSnapshot;
  scenario_metrics: NetworkMetricsSnapshot;
  resilience_score: number;
  resilience_rating: string;
  recommended_plan?: OptimizationPlan | null;
  key_findings: string[];
}

