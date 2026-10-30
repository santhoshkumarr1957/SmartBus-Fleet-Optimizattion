import {
  HealthStatusResponse,
  IntelligenceOverview,
  OptimizationOverview,
  BusLive,
  RouteLive,
  RouteIntelligence,
  BusIntelligence,
  ReallocationRecommendation,
  ReallocationReview,
  ReallocationReviewCreate,
  DisruptionTypeInfo,
  DisruptionSimulationRequest,
  DisruptionSimulationResponse,
  DisruptionScenarioBrief,
  NotificationItem,
  NotificationSummary,
  NotificationRefreshResponse,
  NotificationActionPayload,
  FleetUtilizationReport,
  RoutePerformanceReport,
  DisruptionReport,
  ReallocationReport,
  TrendsReport,
  ReportsOverview,
  RouteDetailed,
  ReallocationExecution,
  ReallocationExecutionCreate,
  ManualReassignmentPayload,
  SimulationStatus,
  SimulationProfile,
  SimulationEvent,
  SimulationKpi,
  DemandProfile,
  SimulationSpeed,
  RouteDemand,
  WeatherObservation,
  BusBreakdown,
  BreakdownSummary,
  ReplacementCandidate,
  OptimizationPlan,
  ScenarioEvaluation,
} from '../types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

async function fetchJson<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  const isMutation =
    options?.method && ['POST', 'PUT', 'DELETE', 'PATCH'].includes(options.method.toUpperCase());
  const timeoutMs = isMutation ? 30000 : 20000;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => {
    controller.abort(new Error(`Request to ${endpoint} timed out after ${timeoutMs}ms`));
  }, timeoutMs);

  if (options?.signal) {
    if (options.signal.aborted) {
      controller.abort(options.signal.reason);
    } else {
      options.signal.addEventListener(
        'abort',
        () => {
          controller.abort(options.signal?.reason);
        },
        { once: true }
      );
    }
  }

  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
      headers: {
        Accept: 'application/json',
        'Content-Type': options?.body ? 'application/json' : (undefined as any),
        ...options?.headers,
      },
    });

    if (!response.ok) {
      let errorDetail = `Status ${response.status}: ${response.statusText}`;
      try {
        const errBody = await response.json();
        if (errBody && errBody.detail) {
          errorDetail =
            typeof errBody.detail === 'string'
              ? errBody.detail
              : JSON.stringify(errBody.detail);
        }
      } catch {
        // Body not JSON
      }
      throw new Error(`API error at ${endpoint} (${errorDetail})`);
    }

    return (await response.json()) as T;
  } catch (err: any) {
    if (err?.name === 'AbortError' || controller.signal.aborted) {
      const reasonMsg =
        controller.signal.reason?.message ||
        (typeof controller.signal.reason === 'string' ? controller.signal.reason : null);
      throw new Error(
        reasonMsg ||
          `Transit server request to ${endpoint} timed out or was interrupted. Please verify backend connectivity and retry.`
      );
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function fetchHealth(): Promise<HealthStatusResponse> {
  return fetchJson<HealthStatusResponse>('/api/health');
}

export async function fetchIntelligenceOverview(): Promise<IntelligenceOverview> {
  return fetchJson<IntelligenceOverview>('/api/intelligence/overview');
}

export async function fetchOptimizationOverview(): Promise<OptimizationOverview> {
  return fetchJson<OptimizationOverview>('/api/optimization/overview');
}

export async function fetchLiveBuses(): Promise<BusLive[]> {
  return fetchJson<BusLive[]>('/api/buses/live');
}

export async function fetchLiveRoutes(): Promise<RouteLive[]> {
  return fetchJson<RouteLive[]>('/api/routes/live');
}

let cachedDetailedRoutes: RouteDetailed[] | null = null;

export async function fetchRoutesDetailed(): Promise<RouteDetailed[]> {
  try {
    const data = await fetchJson<RouteDetailed[]>('/api/routes');
    if (Array.isArray(data) && data.length > 0) {
      cachedDetailedRoutes = data;
      return data;
    }
  } catch (err) {
    if (cachedDetailedRoutes && cachedDetailedRoutes.length > 0) {
      return cachedDetailedRoutes;
    }
    throw err;
  }
  return cachedDetailedRoutes || [];
}

export async function fetchRouteIntelligence(): Promise<RouteIntelligence[]> {
  return fetchJson<RouteIntelligence[]>('/api/intelligence/routes');
}

export async function fetchBusIntelligence(): Promise<BusIntelligence[]> {
  return fetchJson<BusIntelligence[]>('/api/intelligence/buses');
}

export async function fetchOptimizationRecommendations(params?: {
  targetRouteId?: number;
  sourceRouteId?: number;
  minScore?: number;
  bestOnly?: boolean;
}): Promise<ReallocationRecommendation[]> {
  const searchParams = new URLSearchParams();
  if (params?.targetRouteId !== undefined) {
    searchParams.append('target_route_id', params.targetRouteId.toString());
  }
  if (params?.sourceRouteId !== undefined) {
    searchParams.append('source_route_id', params.sourceRouteId.toString());
  }
  if (params?.minScore !== undefined) {
    searchParams.append('min_score', params.minScore.toString());
  }
  if (params?.bestOnly !== undefined) {
    searchParams.append('best_only', params.bestOnly ? 'true' : 'false');
  }

  const query = searchParams.toString() ? `?${searchParams.toString()}` : '';
  return fetchJson<ReallocationRecommendation[]>(`/api/optimization/recommendations${query}`);
}

// ----------------------------------------------------------------------------
// Stage 7: Dispatcher Review API methods
// ----------------------------------------------------------------------------

export async function submitReallocationReview(
  recommendationId: string,
  payload: ReallocationReviewCreate
): Promise<ReallocationReview> {
  return fetchJson<ReallocationReview>(
    `/api/optimization/recommendations/${encodeURIComponent(recommendationId)}/review`,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    }
  );
}

export async function fetchReallocationReviews(params?: {
  decision?: string;
  recommendationId?: string;
  limit?: number;
  offset?: number;
}): Promise<ReallocationReview[]> {
  const searchParams = new URLSearchParams();
  if (params?.decision) {
    searchParams.append('decision', params.decision);
  }
  if (params?.recommendationId) {
    searchParams.append('recommendation_id', params.recommendationId);
  }
  if (params?.limit !== undefined) {
    searchParams.append('limit', params.limit.toString());
  }
  if (params?.offset !== undefined) {
    searchParams.append('offset', params.offset.toString());
  }

  const query = searchParams.toString() ? `?${searchParams.toString()}` : '';
  return fetchJson<ReallocationReview[]>(`/api/optimization/reviews${query}`);
}

export async function fetchRecommendationHistory(
  recommendationId: string
): Promise<ReallocationReview[]> {
  return fetchJson<ReallocationReview[]>(
    `/api/optimization/recommendations/${encodeURIComponent(recommendationId)}/history`
  );
}

export async function executeReallocation(
  recommendationId: string,
  payload: ReallocationExecutionCreate
): Promise<ReallocationExecution> {
  return fetchJson<ReallocationExecution>(
    `/api/optimization/recommendations/${encodeURIComponent(recommendationId)}/execute`,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    }
  );
}

export async function manualReassignBus(
  busId: number,
  payload: ManualReassignmentPayload
): Promise<ReallocationExecution> {
  return fetchJson<ReallocationExecution>(`/api/buses/${busId}/reassign`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function fetchReallocationExecutions(params?: {
  busId?: number;
  recommendationId?: string;
  status?: string;
  limit?: number;
  offset?: number;
}): Promise<ReallocationExecution[]> {
  const searchParams = new URLSearchParams();
  if (params?.busId !== undefined) {
    searchParams.append('bus_id', params.busId.toString());
  }
  if (params?.recommendationId) {
    searchParams.append('recommendation_id', params.recommendationId);
  }
  if (params?.status) {
    searchParams.append('status', params.status);
  }
  if (params?.limit !== undefined) {
    searchParams.append('limit', params.limit.toString());
  }
  if (params?.offset !== undefined) {
    searchParams.append('offset', params.offset.toString());
  }

  const query = searchParams.toString() ? `?${searchParams.toString()}` : '';
  return fetchJson<ReallocationExecution[]>(`/api/optimization/executions${query}`);
}

export async function fetchRecommendationExecutions(
  recommendationId: string
): Promise<ReallocationExecution[]> {
  return fetchJson<ReallocationExecution[]>(
    `/api/optimization/recommendations/${encodeURIComponent(recommendationId)}/executions`
  );
}

// ----------------------------------------------------------------------------
// Stage 8: Disruption Simulation and Resilience Analysis API methods
// ----------------------------------------------------------------------------

export async function fetchDisruptionTypes(): Promise<DisruptionTypeInfo[]> {
  return fetchJson<DisruptionTypeInfo[]>('/api/disruption/types');
}

export async function simulateDisruption(
  payload: DisruptionSimulationRequest
): Promise<DisruptionSimulationResponse> {
  return fetchJson<DisruptionSimulationResponse>('/api/disruption/simulate', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function fetchCachedScenarios(): Promise<DisruptionScenarioBrief[]> {
  return fetchJson<DisruptionScenarioBrief[]>('/api/disruption/scenarios');
}

export async function fetchScenarioImpact(
  scenarioId: string
): Promise<DisruptionSimulationResponse> {
  return fetchJson<DisruptionSimulationResponse>(
    `/api/disruption/scenarios/${encodeURIComponent(scenarioId)}`
  );
}

// ----------------------------------------------------------------------------
// Stage 9: Notifications and Alert Management API methods
// ----------------------------------------------------------------------------

export async function fetchNotifications(params?: {
  status?: string;
  severity?: string;
  type?: string;
  source?: string;
  limit?: number;
  offset?: number;
}): Promise<NotificationItem[]> {
  const query = new URLSearchParams();
  if (params?.status && params.status !== 'ALL') query.set('status', params.status);
  if (params?.severity && params.severity !== 'ALL') query.set('severity', params.severity);
  if (params?.type && params.type !== 'ALL') query.set('type', params.type);
  if (params?.source && params.source !== 'ALL') query.set('source', params.source);
  if (params?.limit) query.set('limit', params.limit.toString());
  if (params?.offset) query.set('offset', params.offset.toString());
  const queryString = query.toString() ? `?${query.toString()}` : '';
  return fetchJson<NotificationItem[]>(`/api/notifications${queryString}`);
}

export async function fetchNotificationSummary(): Promise<NotificationSummary> {
  return fetchJson<NotificationSummary>('/api/notifications/summary');
}

export async function acknowledgeNotification(
  alertId: number,
  payload?: NotificationActionPayload
): Promise<NotificationItem> {
  return fetchJson<NotificationItem>(`/api/notifications/${alertId}/acknowledge`, {
    method: 'POST',
    body: JSON.stringify(payload || { dispatcher_id: 'DISPATCHER-LIVE' }),
  });
}

export async function resolveNotification(
  alertId: number,
  payload?: NotificationActionPayload
): Promise<NotificationItem> {
  return fetchJson<NotificationItem>(`/api/notifications/${alertId}/resolve`, {
    method: 'POST',
    body: JSON.stringify(payload || { dispatcher_id: 'DISPATCHER-LIVE' }),
  });
}

export async function refreshNotifications(params?: {
  includeSimulation?: boolean;
}): Promise<NotificationRefreshResponse> {
  const query = new URLSearchParams();
  if (params?.includeSimulation !== undefined) {
    query.set('include_simulation', String(params.includeSimulation));
  }
  const queryString = query.toString() ? `?${query.toString()}` : '';
  return fetchJson<NotificationRefreshResponse>(`/api/notifications/refresh${queryString}`, {
    method: 'POST',
  });
}

// ----------------------------------------------------------------------------
// Stage 10: Reports and Performance Analytics API methods
// ----------------------------------------------------------------------------

export async function fetchReportsOverview(): Promise<ReportsOverview> {
  return fetchJson<ReportsOverview>('/api/reports/overview');
}

export async function fetchFleetUtilizationReport(): Promise<FleetUtilizationReport> {
  return fetchJson<FleetUtilizationReport>('/api/reports/fleet-utilization');
}

export async function fetchRoutePerformanceReport(): Promise<RoutePerformanceReport> {
  return fetchJson<RoutePerformanceReport>('/api/reports/routes');
}

export async function fetchDisruptionReport(): Promise<DisruptionReport> {
  return fetchJson<DisruptionReport>('/api/reports/disruptions');
}

export async function fetchReallocationReport(): Promise<ReallocationReport> {
  return fetchJson<ReallocationReport>('/api/reports/reallocation');
}

export async function fetchTrendsReport(
  range: '1h' | '24h' | '7d' = '24h'
): Promise<TrendsReport> {
  return fetchJson<TrendsReport>(`/api/reports/trends?range=${encodeURIComponent(range)}`);
}

export function getReportExportUrl(
  reportType: 'fleet' | 'routes' | 'disruptions' | 'reallocation' | 'trends',
  range: string = '24h'
): string {
  return `${API_BASE_URL}/api/reports/export?type=${encodeURIComponent(reportType)}&range=${encodeURIComponent(range)}&format=csv`;
}

export async function downloadReportCsv(
  reportType: 'fleet' | 'routes' | 'disruptions' | 'reallocation' | 'trends',
  range: string = '24h'
): Promise<void> {
  const url = getReportExportUrl(reportType, range);
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to export report CSV (Status ${response.status})`);
  }
  const blob = await response.blob();
  const downloadUrl = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = downloadUrl;
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  a.download = `transight_${reportType}_report_${timestamp}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.URL.revokeObjectURL(downloadUrl);
}

// ----------------------------------------------------------------------------
// Traffic Simulation Control & Monitoring API Methods
// ----------------------------------------------------------------------------

export async function fetchSimulationStatus(): Promise<SimulationStatus> {
  return fetchJson<SimulationStatus>('/api/simulation/status');
}

export async function fetchSimulationProfiles(): Promise<SimulationProfile[]> {
  return fetchJson<SimulationProfile[]>('/api/simulation/profiles');
}

export async function startSimulation(): Promise<SimulationStatus> {
  return fetchJson<SimulationStatus>('/api/simulation/start', { method: 'POST' });
}

export async function pauseSimulation(): Promise<SimulationStatus> {
  return fetchJson<SimulationStatus>('/api/simulation/pause', { method: 'POST' });
}

export async function resumeSimulation(): Promise<SimulationStatus> {
  return fetchJson<SimulationStatus>('/api/simulation/resume', { method: 'POST' });
}

export async function stopSimulation(): Promise<SimulationStatus> {
  return fetchJson<SimulationStatus>('/api/simulation/stop', { method: 'POST' });
}

export async function resetSimulation(): Promise<SimulationStatus> {
  return fetchJson<SimulationStatus>('/api/simulation/reset', { method: 'POST' });
}

export async function setSimulationDemand(profile: DemandProfile): Promise<SimulationStatus> {
  return fetchJson<SimulationStatus>('/api/simulation/demand', {
    method: 'POST',
    body: JSON.stringify({ profile }),
  });
}

export async function setSimulationSpeed(speed: SimulationSpeed): Promise<SimulationStatus> {
  return fetchJson<SimulationStatus>('/api/simulation/speed', {
    method: 'POST',
    body: JSON.stringify({ speed }),
  });
}

export async function fetchSimulationEvents(limit: number = 30): Promise<SimulationEvent[]> {
  return fetchJson<SimulationEvent[]>(`/api/simulation/events?limit=${limit}`);
}

export async function fetchSimulationKpis(): Promise<SimulationKpi> {
  return fetchJson<SimulationKpi>('/api/simulation/kpis');
}

export async function setRouteDemand(
  routeIdOrNumber: string | number,
  profile: 'LOW' | 'NORMAL' | 'HIGH'
): Promise<RouteDemand> {
  return fetchJson<RouteDemand>(
    `/api/simulation/routes/${encodeURIComponent(routeIdOrNumber)}/demand`,
    {
      method: 'PUT',
      body: JSON.stringify({ profile }),
    }
  );
}

export async function fetchAllRouteDemands(): Promise<RouteDemand[]> {
  return fetchJson<RouteDemand[]>('/api/simulation/routes/demand');
}

// -----------------------------------------------------------------------------
// Phase 3: Weather-Aware Transit Operations API
// -----------------------------------------------------------------------------

export async function fetchCurrentWeather(): Promise<WeatherObservation> {
  return fetchJson<WeatherObservation>('/api/weather/current');
}

export async function setWeatherScenario(
  scenario: string,
  notes?: string
): Promise<WeatherObservation> {
  return fetchJson<WeatherObservation>('/api/weather/scenario', {
    method: 'POST',
    body: JSON.stringify({ scenario, notes }),
  });
}

// -----------------------------------------------------------------------------
// Phase 4: Bus Breakdown Management API
// -----------------------------------------------------------------------------

export async function fetchBreakdowns(activeOnly: boolean = false): Promise<BusBreakdown[]> {
  return fetchJson<BusBreakdown[]>(`/api/breakdowns?active_only=${activeOnly}`);
}

export async function fetchBreakdownSummary(): Promise<BreakdownSummary> {
  return fetchJson<BreakdownSummary>('/api/breakdowns/summary');
}

export async function reportBreakdown(payload: {
  bus_id?: number;
  bus_number?: string;
  route_id?: number;
  route_number?: string;
  location_name?: string;
  severity?: string;
  notes?: string;
  source?: string;
  dispatcher_id?: string;
}): Promise<BusBreakdown> {
  return fetchJson<BusBreakdown>('/api/breakdowns', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function updateBreakdownStatus(
  incidentId: number,
  status: 'CONFIRMED' | 'UNDER_REPAIR' | 'AVAILABLE',
  notes?: string,
  dispatcherId?: string
): Promise<BusBreakdown> {
  return fetchJson<BusBreakdown>(`/api/breakdowns/${incidentId}/status`, {
    method: 'PUT',
    body: JSON.stringify({
      status,
      notes,
      dispatcher_id: dispatcherId || 'DISPATCHER-1',
    }),
  });
}

export async function fetchReplacementCandidates(
  busId: number
): Promise<ReplacementCandidate> {
  return fetchJson<ReplacementCandidate>(`/api/breakdowns/${busId}/replacement-candidates`);
}

// -----------------------------------------------------------------------------
// Phases 1, 2, 5, 6: Hybrid CP-SAT Optimization & Scenario Evaluation API
// -----------------------------------------------------------------------------

export async function runHybridOptimization(params?: {
  include_weather?: boolean;
  weather_scenario_override?: string;
  max_reallocations?: number;
}): Promise<OptimizationPlan> {
  return fetchJson<OptimizationPlan>('/api/optimization/run', {
    method: 'POST',
    body: JSON.stringify(params || {}),
  });
}

export async function fetchLatestOptimizationPlan(): Promise<OptimizationPlan> {
  return fetchJson<OptimizationPlan>('/api/optimization/latest-plan');
}

export async function evaluateResilienceScenario(payload: {
  scenario_name?: string;
  demand_overrides?: Record<string, string>;
  simulated_breakdowns?: string[];
  weather_scenario?: string;
  notes?: string;
}): Promise<ScenarioEvaluation> {
  return fetchJson<ScenarioEvaluation>('/api/optimization/scenarios/evaluate', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}



