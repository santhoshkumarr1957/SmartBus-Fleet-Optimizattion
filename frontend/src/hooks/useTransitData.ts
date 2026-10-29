import { useEffect, useRef, useState, useCallback } from 'react';
import {
  HealthStatusResponse,
  IntelligenceOverview,
  OptimizationOverview,
  BusLive,
  RouteLive,
  RouteIntelligence,
  BusIntelligence,
  ReallocationRecommendation,
  ConnectionState,
  RouteDetailed,
} from '../types';
import {
  fetchHealth,
  fetchIntelligenceOverview,
  fetchOptimizationOverview,
  fetchLiveBuses,
  fetchLiveRoutes,
  fetchRouteIntelligence,
  fetchBusIntelligence,
  fetchOptimizationRecommendations,
  fetchRoutesDetailed,
} from '../services/api';

const TELEMETRY_POLL_INTERVAL_MS = 1500;
const ANALYTICS_POLL_INTERVAL_MS = 6000;

export interface UseTransitDataReturn {
  health: HealthStatusResponse | null;
  intelligenceOverview: IntelligenceOverview | null;
  optimizationOverview: OptimizationOverview | null;
  liveBuses: BusLive[];
  liveRoutes: RouteLive[];
  routesDetailed: RouteDetailed[];
  routeIntelligence: RouteIntelligence[];
  busIntelligence: BusIntelligence[];
  recommendations: ReallocationRecommendation[];
  connectionStatus: ConnectionState;
  lastUpdated: string | null;
  isInitialLoading: boolean;
  isRefreshing: boolean;
  error: string | null;
  isAutoRefresh: boolean;
  toggleAutoRefresh: () => void;
  refreshNow: () => Promise<void>;
}

export function useTransitData(): UseTransitDataReturn {
  const [health, setHealth] = useState<HealthStatusResponse | null>(null);
  const [intelligenceOverview, setIntelligenceOverview] = useState<IntelligenceOverview | null>(null);
  const [optimizationOverview, setOptimizationOverview] = useState<OptimizationOverview | null>(null);
  const [liveBuses, setLiveBuses] = useState<BusLive[]>([]);
  const [liveRoutes, setLiveRoutes] = useState<RouteLive[]>([]);
  const [routesDetailed, setRoutesDetailed] = useState<RouteDetailed[]>([]);
  const [routeIntelligence, setRouteIntelligence] = useState<RouteIntelligence[]>([]);
  const [busIntelligence, setBusIntelligence] = useState<BusIntelligence[]>([]);
  const [recommendations, setRecommendations] = useState<ReallocationRecommendation[]>([]);

  const [connectionStatus, setConnectionStatus] = useState<ConnectionState>('Checking...');
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [isInitialLoading, setIsInitialLoading] = useState<boolean>(true);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [isAutoRefresh, setIsAutoRefresh] = useState<boolean>(true);

  const isFetchingTelemetryRef = useRef<boolean>(false);
  const isFetchingAnalyticsRef = useRef<boolean>(false);
  const isMountedRef = useRef<boolean>(true);

  // Fast telemetry polling: live buses and active routes (every 1.5s)
  const fetchTelemetry = useCallback(async () => {
    if (isFetchingTelemetryRef.current || !isMountedRef.current) return;
    isFetchingTelemetryRef.current = true;

    try {
      const [liveBusesRes, liveRoutesRes] = await Promise.allSettled([
        fetchLiveBuses(),
        fetchLiveRoutes(),
      ]);

      if (!isMountedRef.current) return;

      if (liveBusesRes.status === 'fulfilled') {
        setLiveBuses(liveBusesRes.value);
      }
      if (liveRoutesRes.status === 'fulfilled') {
        setLiveRoutes(liveRoutesRes.value);
      }
      setLastUpdated(new Date().toLocaleTimeString());
    } catch (err: any) {
      // Non-fatal telemetry polling failure does not permanently freeze polling
      console.warn('[useTransitData] Telemetry poll failed:', err?.message);
    } finally {
      isFetchingTelemetryRef.current = false;
    }
  }, []);

  // Periodic analytics polling: health, overview, intelligence, recommendations (every 6s)
  const fetchAnalytics = useCallback(async () => {
    if (isFetchingAnalyticsRef.current || !isMountedRef.current) return;
    isFetchingAnalyticsRef.current = true;

    try {
      const healthData = await fetchHealth().catch(() => null);
      if (!isMountedRef.current) return;

      if (!healthData || healthData.status !== 'ok') {
        setConnectionStatus('Disconnected');
        setError('Backend service is unreachable or reporting unhealthy status.');
        return;
      }

      setHealth(healthData);
      setConnectionStatus('Connected');

      const [
        intelOverviewRes,
        optOverviewRes,
        routeIntelRes,
        busIntelRes,
        recommendationsRes,
        detailedRoutesRes,
      ] = await Promise.allSettled([
        fetchIntelligenceOverview(),
        fetchOptimizationOverview(),
        fetchRouteIntelligence(),
        fetchBusIntelligence(),
        fetchOptimizationRecommendations(),
        fetchRoutesDetailed(),
      ]);

      if (!isMountedRef.current) return;

      if (intelOverviewRes.status === 'fulfilled') {
        setIntelligenceOverview(intelOverviewRes.value);
      }
      if (optOverviewRes.status === 'fulfilled') {
        setOptimizationOverview(optOverviewRes.value);
      }
      if (routeIntelRes.status === 'fulfilled') {
        setRouteIntelligence(routeIntelRes.value);
      }
      if (busIntelRes.status === 'fulfilled') {
        setBusIntelligence(busIntelRes.value);
      }
      if (recommendationsRes.status === 'fulfilled') {
        setRecommendations(recommendationsRes.value);
      }
      if (detailedRoutesRes.status === 'fulfilled' && Array.isArray(detailedRoutesRes.value) && detailedRoutesRes.value.length > 0) {
        setRoutesDetailed(detailedRoutesRes.value);
      }

      setError(null);
    } catch (err: any) {
      console.warn('[useTransitData] Analytics poll failed:', err?.message);
    } finally {
      isFetchingAnalyticsRef.current = false;
      if (isMountedRef.current) {
        setIsInitialLoading(false);
      }
    }
  }, []);

  const refreshNow = useCallback(async () => {
    setIsRefreshing(true);
    await Promise.all([fetchTelemetry(), fetchAnalytics()]);
    if (isMountedRef.current) {
      setIsRefreshing(false);
    }
  }, [fetchTelemetry, fetchAnalytics]);

  // Periodic polling setup
  useEffect(() => {
    isMountedRef.current = true;
    // Initial fetch
    fetchAnalytics();
    fetchTelemetry();

    let telemetryInterval: ReturnType<typeof setInterval> | null = null;
    let analyticsInterval: ReturnType<typeof setInterval> | null = null;

    if (isAutoRefresh) {
      telemetryInterval = setInterval(fetchTelemetry, TELEMETRY_POLL_INTERVAL_MS);
      analyticsInterval = setInterval(fetchAnalytics, ANALYTICS_POLL_INTERVAL_MS);
    }

    return () => {
      isMountedRef.current = false;
      if (telemetryInterval) clearInterval(telemetryInterval);
      if (analyticsInterval) clearInterval(analyticsInterval);
    };
  }, [fetchTelemetry, fetchAnalytics, isAutoRefresh]);

  const toggleAutoRefresh = useCallback(() => {
    setIsAutoRefresh((prev) => !prev);
  }, []);

  return {
    health,
    intelligenceOverview,
    optimizationOverview,
    liveBuses,
    liveRoutes,
    routesDetailed,
    routeIntelligence,
    busIntelligence,
    recommendations,
    connectionStatus,
    lastUpdated,
    isInitialLoading,
    isRefreshing,
    error,
    isAutoRefresh,
    toggleAutoRefresh,
    refreshNow,
  };
}
