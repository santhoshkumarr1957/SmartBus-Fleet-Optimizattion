import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import L from 'leaflet';
import {
  RouteLive,
  RouteIntelligence,
  BusLive,
  BusIntelligence,
  SimulationStatus,
  SimulationKpi,
  SimulationEvent,
  SimulationSpeed,
  RouteDetailed,
  LoadStatus,
} from '../types';
import {
  fetchSimulationStatus,
  fetchSimulationKpis,
  fetchSimulationEvents,
  setSimulationDemand,
  setSimulationSpeed,
  setRouteDemand,
  fetchAllRouteDemands,
  startSimulation,
  pauseSimulation,
  resumeSimulation,
  stopSimulation,
  resetSimulation,
  fetchRoutesDetailed,
  fetchLiveBuses,
} from '../services/api';
import { StatusBadge } from './StatusBadge';

interface TrafficSimulationPanelProps {
  routes: (RouteLive | RouteIntelligence)[];
  buses: (BusLive | BusIntelligence)[];
  detailedRoutes?: RouteDetailed[];
  onRefreshRequired?: () => void;
}

// 6 distinct corridor colors for Coimbatore network
const ROUTE_COLORS: Record<string, string> = {
  '101': '#3b82f6', // Avinashi Rd corridor (Blue)
  '202': '#10b981', // Saibaba Colony / Town Hall (Emerald)
  '303': '#f59e0b', // Ukkadam / Trichy Rd (Amber)
  '404': '#8b5cf6', // Gandhipuram – Singanallur (Purple)
  '505': '#ec4899', // Gandhipuram – Ukkadam (Pink)
  '606': '#06b6d4', // Gandhipuram – Peelamedu – Hope College (Cyan)
};

function getLoadStatus(loadFactor: number | null): { status: LoadStatus; color: string; badgeClass: string } {
  if (loadFactor === null || isNaN(loadFactor)) {
    return { status: 'NORMAL', color: '#3B82F6', badgeClass: 'bg-blue-500/10 text-blue-400 border-blue-500/30' };
  }
  if (loadFactor >= 1.0) {
    return { status: 'CRITICAL', color: '#EF4444', badgeClass: 'bg-rose-500/10 text-rose-400 border-rose-500/30' };
  }
  if (loadFactor >= 0.8) {
    return { status: 'HIGH', color: '#F59E0B', badgeClass: 'bg-amber-500/10 text-amber-400 border-amber-500/30' };
  }
  if (loadFactor >= 0.5) {
    return { status: 'NORMAL', color: '#3B82F6', badgeClass: 'bg-blue-500/10 text-blue-400 border-blue-500/30' };
  }
  return { status: 'LOW', color: '#10B981', badgeClass: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30' };
}

function createBusIcon(bus: BusLive, isSelected: boolean) {
  const lf = bus.load_factor ?? (bus.capacity > 0 && bus.passenger_count !== null ? bus.passenger_count / bus.capacity : 0);
  const { color } = getLoadStatus(lf);
  const size = isSelected ? 40 : 32;
  const pulse = isSelected
    ? '<div class="absolute -inset-1.5 rounded-full border-2 border-white animate-ping opacity-75"></div>'
    : '';

  const html = `
    <div class="relative flex items-center justify-center cursor-pointer transition-transform hover:scale-110" style="width: ${size}px; height: ${size}px;">
      ${pulse}
      <div class="w-full h-full rounded-full shadow-lg flex items-center justify-center text-white font-bold border-2 border-white" style="background-color: ${color};">
        <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
        </svg>
      </div>
      <div class="absolute -bottom-4 bg-slate-900/90 text-[10px] font-mono px-1 py-0.2 rounded border border-slate-700 text-slate-200 shadow whitespace-nowrap">
        ${bus.bus_number}
      </div>
    </div>
  `;

  return L.divIcon({
    html,
    className: 'custom-bus-marker',
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -size / 2],
  });
}

export const TrafficSimulationPanel: React.FC<TrafficSimulationPanelProps> = ({
  routes,
  buses,
  detailedRoutes: propDetailedRoutes,
  onRefreshRequired,
}) => {
  // Simulation Engine State
  const [status, setStatus] = useState<SimulationStatus | null>(null);
  const [kpis, setKpis] = useState<SimulationKpi | null>(null);
  const [events, setEvents] = useState<SimulationEvent[]>([]);
  const [isActionLoading, setIsActionLoading] = useState(false);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // Route-Specific Demand Configuration State (Independent per corridor)
  const [routeDemands, setRouteDemands] = useState<Record<string, 'LOW' | 'NORMAL' | 'HIGH'>>({
    '101': 'NORMAL',
    '202': 'NORMAL',
    '303': 'NORMAL',
    '404': 'NORMAL',
    '505': 'NORMAL',
    '606': 'NORMAL',
  });
  const [updatingRoute, setUpdatingRoute] = useState<string | null>(null);
  const [globalPreset, setGlobalPreset] = useState<'LOW' | 'NORMAL' | 'HIGH'>('NORMAL');

  // Map & Live Telemetry State
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);
  const routesLayerRef = useRef<L.LayerGroup | null>(null);
  const markersLayerRef = useRef<L.LayerGroup | null>(null);
  const markersByBusIdRef = useRef<Map<number, L.Marker>>(new Map());
  const initialFitDoneRef = useRef(false);

  const [mapReady, setMapReady] = useState(false);
  const [detailedRoutes, setDetailedRoutes] = useState<RouteDetailed[]>(
    propDetailedRoutes && propDetailedRoutes.length > 0 ? propDetailedRoutes : []
  );
  const [liveBusList, setLiveBusList] = useState<BusLive[]>(
    Array.isArray(buses) && buses.length > 0 ? (buses as BusLive[]) : []
  );
  const [selectedBusId, setSelectedBusId] = useState<number | null>(null);
  const [filterRoute, setFilterRoute] = useState<string>('ALL');

  // Sync internal bus telemetry when parent provides fresh buses
  useEffect(() => {
    if (Array.isArray(buses) && buses.length > 0) {
      setLiveBusList(buses as BusLive[]);
    }
  }, [buses]);

  // Format elapsed simulation time
  const formatElapsed = (sec: number) => {
    const mins = Math.floor(sec / 60);
    const s = sec % 60;
    return `${mins}m ${s < 10 ? '0' : ''}${s}s`;
  };

  // Sync detailedRoutes with parent prop if provided
  useEffect(() => {
    if (propDetailedRoutes && propDetailedRoutes.length > 0) {
      setDetailedRoutes(propDetailedRoutes);
    }
  }, [propDetailedRoutes]);

  // Sync simulation status, KPIs, events, and route demand configurations
  const pollSimulationData = useCallback(async () => {
    try {
      const [statusRes, kpisRes, eventsRes] = await Promise.allSettled([
        fetchSimulationStatus(),
        fetchSimulationKpis(),
        fetchSimulationEvents(35),
      ]);
      if (statusRes.status === 'fulfilled' && statusRes.value) {
        setStatus(statusRes.value);
        if (statusRes.value.route_demands) {
          setRouteDemands((prev) => ({
            ...prev,
            ...(statusRes.value.route_demands as Record<string, 'LOW' | 'NORMAL' | 'HIGH'>),
          }));
        }
      }
      if (kpisRes.status === 'fulfilled' && kpisRes.value) {
        setKpis(kpisRes.value);
      }
      if (eventsRes.status === 'fulfilled' && Array.isArray(eventsRes.value)) {
        setEvents(eventsRes.value);
      }
    } catch {
      // Backend may be starting or offline
    }
  }, []);

  // Fetch initial route demands on mount
  useEffect(() => {
    fetchAllRouteDemands()
      .then((demands) => {
        if (Array.isArray(demands) && demands.length > 0) {
          const mapped: Record<string, 'LOW' | 'NORMAL' | 'HIGH'> = {};
          demands.forEach((d) => {
            mapped[d.route_number] = d.demand_profile as 'LOW' | 'NORMAL' | 'HIGH';
          });
          setRouteDemands((prev) => ({ ...prev, ...mapped }));
        }
      })
      .catch(() => {});
  }, []);

  // Poll simulation status and events every 3s
  useEffect(() => {
    pollSimulationData();
    const interval = setInterval(pollSimulationData, 3000);
    return () => clearInterval(interval);
  }, [pollSimulationData]);

  // Fetch detailed route geometries once if not provided via props
  useEffect(() => {
    let isMounted = true;
    if (detailedRoutes.length >= 6) return;

    fetchRoutesDetailed()
      .then((data) => {
        if (isMounted && Array.isArray(data) && data.length > 0) {
          setDetailedRoutes(data);
        }
      })
      .catch(() => {});

    return () => {
      isMounted = false;
    };
  }, []);

  // Poll live buses for the map every 1.5s
  useEffect(() => {
    const updateBuses = async () => {
      try {
        const fresh = await fetchLiveBuses();
        if (Array.isArray(fresh) && fresh.length > 0) {
          setLiveBusList(fresh);
        }
      } catch {
        // Non-blocking
      }
    };
    updateBuses();
    const busInterval = setInterval(updateBuses, 1500);
    return () => clearInterval(busInterval);
  }, []);

  // Leaflet Map Initialization centered on Coimbatore with strict container re-use guards
  useEffect(() => {
    if (!mapContainerRef.current || mapInstanceRef.current) return;

    // Clear stale Leaflet container property if component remounts
    if ((mapContainerRef.current as any)._leaflet_id) {
      (mapContainerRef.current as any)._leaflet_id = null;
    }

    let map: L.Map | null = null;
    try {
      map = L.map(mapContainerRef.current, {
        center: [11.008, 76.975],
        zoom: 13,
        zoomControl: true,
        attributionControl: true,
      });

      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors',
      }).addTo(map);

      const routesLayer = L.layerGroup().addTo(map);
      const markersLayer = L.layerGroup().addTo(map);

      mapInstanceRef.current = map;
      routesLayerRef.current = routesLayer;
      markersLayerRef.current = markersLayer;
      setMapReady(true);
    } catch (err) {
      console.warn('[TrafficSimulationPanel] Leaflet map init error:', err);
      return;
    }

    const timer1 = setTimeout(() => {
      mapInstanceRef.current?.invalidateSize();
    }, 150);
    const timer2 = setTimeout(() => {
      mapInstanceRef.current?.invalidateSize();
    }, 500);

    return () => {
      clearTimeout(timer1);
      clearTimeout(timer2);
      try {
        if (mapInstanceRef.current) {
          mapInstanceRef.current.remove();
        }
      } catch {
        // Safe cleanup
      }
      mapInstanceRef.current = null;
      routesLayerRef.current = null;
      markersLayerRef.current = null;
      markersByBusIdRef.current.clear();
      initialFitDoneRef.current = false;
      setMapReady(false);
    };
  }, []);

  // Draw all 6 route polylines and stop markers safely
  useEffect(() => {
    const map = mapInstanceRef.current;
    const routesLayer = routesLayerRef.current;
    if (!map || !routesLayer || !mapReady) return;

    routesLayer.clearLayers();

    detailedRoutes.forEach((route) => {
      if (filterRoute !== 'ALL' && filterRoute !== route.route_number) return;

      const color = ROUTE_COLORS[route.route_number] || '#8b5cf6';
      if (!route.stops || !Array.isArray(route.stops) || route.stops.length < 2) return;

      const sortedStops = [...route.stops].sort((a, b) => a.sequence_order - b.sequence_order);

      const validStops = sortedStops.filter(
        (s) =>
          typeof s.latitude === 'number' &&
          typeof s.longitude === 'number' &&
          !isNaN(s.latitude) &&
          !isNaN(s.longitude) &&
          s.latitude !== 0 &&
          s.longitude !== 0
      );

      if (validStops.length > 1) {
        const coords: L.LatLngTuple[] = validStops.map((s) => [s.latitude, s.longitude]);
        const polyline = L.polyline(coords, {
          color,
          weight: 4,
          opacity: 0.85,
        });
        polyline.bindTooltip(`Route ${route.route_number}: ${route.name}`, { sticky: true });
        routesLayer.addLayer(polyline);
      }

      validStops.forEach((stop) => {
        const stopMarker = L.circleMarker([stop.latitude, stop.longitude], {
          radius: 4,
          fillColor: '#0f172a',
          color,
          weight: 2,
          opacity: 0.95,
          fillOpacity: 0.9,
        });
        stopMarker.bindTooltip(
          `<strong>${stop.name}</strong><br/><span style="color:${color}">Route ${route.route_number}</span> (Stop #${stop.sequence_order})`,
          { direction: 'top', offset: [0, -4] }
        );
        routesLayer.addLayer(stopMarker);
      });
    });
  }, [detailedRoutes, filterRoute, mapReady]);

  // Update bus markers imperatively without flickering or losing viewport
  useEffect(() => {
    const map = mapInstanceRef.current;
    const markersLayer = markersLayerRef.current;
    if (!map || !markersLayer) return;

    const activeBusIds = new Set<number>();
    const bounds = L.latLngBounds([]);

    const filteredBuses = liveBusList.filter((b) => {
      if (
        b.latitude === null ||
        b.latitude === undefined ||
        b.longitude === null ||
        b.longitude === undefined ||
        isNaN(b.latitude) ||
        isNaN(b.longitude) ||
        (b.latitude === 0 && b.longitude === 0)
      ) {
        return false;
      }
      if (filterRoute !== 'ALL' && b.route_number !== filterRoute) return false;
      return true;
    });

    filteredBuses.forEach((bus) => {
      activeBusIds.add(bus.bus_id);
      const lat = bus.latitude!;
      const lon = bus.longitude!;
      bounds.extend([lat, lon]);

      const isSelected = bus.bus_id === selectedBusId;
      const icon = createBusIcon(bus, isSelected);
      const existing = markersByBusIdRef.current.get(bus.bus_id);

      if (existing) {
        existing.setLatLng([lat, lon]);
        existing.setIcon(icon);
      } else {
        const marker = L.marker([lat, lon], { icon, title: `Bus ${bus.bus_number}` });
        marker.on('click', () => setSelectedBusId(bus.bus_id));
        markersLayer.addLayer(marker);
        markersByBusIdRef.current.set(bus.bus_id, marker);
      }
    });

    // Remove deleted/filtered markers
    markersByBusIdRef.current.forEach((marker, busId) => {
      if (!activeBusIds.has(busId)) {
        markersLayer.removeLayer(marker);
        markersByBusIdRef.current.delete(busId);
      }
    });

    // Auto-fit bounds once on initial load
    if (!initialFitDoneRef.current && bounds.isValid()) {
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 });
      initialFitDoneRef.current = true;
    }
  }, [liveBusList, selectedBusId, filterRoute]);

  // Fit map viewport to fleet
  const handleFitFleet = () => {
    const map = mapInstanceRef.current;
    if (!map) return;
    const bounds = L.latLngBounds([]);
    liveBusList.forEach((b) => {
      if (b.latitude && b.longitude) bounds.extend([b.latitude, b.longitude]);
    });
    if (bounds.isValid()) {
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 });
    }
  };

  // Simulation Controls Actions with strict in-progress locking to prevent duplicate requests
  // Route-Specific Demand Change Action (Independent per corridor)
  const handleSingleRouteDemandChange = async (
    routeNumber: string,
    profile: 'LOW' | 'NORMAL' | 'HIGH'
  ) => {
    if (isActionLoading || updatingRoute) return;
    setUpdatingRoute(routeNumber);
    setFeedback(null);
    try {
      const res = await setRouteDemand(routeNumber, profile);
      setRouteDemands((prev) => ({
        ...prev,
        [routeNumber]: profile,
      }));
      setFeedback({
        type: 'success',
        message: res.message || `Route ${routeNumber} demand profile set to ${profile} DEMAND. Simulator updated boarding dynamics for this corridor.`,
      });
      pollSimulationData();
      fetchLiveBuses()
        .then((fresh) => {
          if (Array.isArray(fresh) && fresh.length > 0) setLiveBusList(fresh);
        })
        .catch(() => {});
      if (onRefreshRequired) onRefreshRequired();
    } catch (err: any) {
      setFeedback({
        type: 'error',
        message: err?.message || `Failed to update demand profile for Route ${routeNumber}`,
      });
      pollSimulationData();
    } finally {
      setUpdatingRoute(null);
    }
  };

  // Convenience tool to apply a baseline preset across all corridors
  const handleApplyGlobalPreset = async () => {
    if (isActionLoading) return;
    setIsActionLoading(true);
    setFeedback(null);
    try {
      const res = await setSimulationDemand(globalPreset);
      if (res && res.status) {
        setStatus(res);
        if (res.route_demands) {
          setRouteDemands(res.route_demands as Record<string, 'LOW' | 'NORMAL' | 'HIGH'>);
        } else {
          setRouteDemands({
            '101': globalPreset,
            '202': globalPreset,
            '303': globalPreset,
            '404': globalPreset,
            '505': globalPreset,
            '606': globalPreset,
          });
        }
      }
      setFeedback({
        type: 'success',
        message: `Network-wide preset applied: all 6 corridors set to ${globalPreset} DEMAND.`,
      });
      pollSimulationData();
      fetchLiveBuses()
        .then((fresh) => {
          if (Array.isArray(fresh) && fresh.length > 0) setLiveBusList(fresh);
        })
        .catch(() => {});
      if (onRefreshRequired) onRefreshRequired();
    } catch (err: any) {
      setFeedback({
        type: 'error',
        message: err?.message || `Failed to apply global preset`,
      });
      pollSimulationData();
    } finally {
      setIsActionLoading(false);
    }
  };

  const handleLifecycleAction = async (action: 'start' | 'pause' | 'resume' | 'stop' | 'reset') => {
    if (isActionLoading) return;
    setIsActionLoading(true);
    setFeedback(null);
    try {
      let res: SimulationStatus;
      if (action === 'start') res = await startSimulation();
      else if (action === 'pause') res = await pauseSimulation();
      else if (action === 'resume') res = await resumeSimulation();
      else if (action === 'stop') res = await stopSimulation();
      else res = await resetSimulation();

      if (res && res.status) {
        setStatus(res);
      }
      setFeedback({
        type: 'success',
        message: `Simulation ${action.toUpperCase()} action executed successfully. Engine state is now ${res.status}.`,
      });
      pollSimulationData();
      fetchLiveBuses().then((fresh) => {
        if (Array.isArray(fresh) && fresh.length > 0) setLiveBusList(fresh);
      }).catch(() => {});
      if (onRefreshRequired) onRefreshRequired();
    } catch (err: any) {
      setFeedback({
        type: 'error',
        message: err?.message || `Failed to execute ${action} simulation`,
      });
      pollSimulationData();
    } finally {
      setIsActionLoading(false);
    }
  };

  const handleSpeedChange = async (spd: SimulationSpeed) => {
    if (isActionLoading) return;
    setIsActionLoading(true);
    setFeedback(null);
    try {
      const res = await setSimulationSpeed(spd);
      if (res && res.status) {
        setStatus(res);
      }
      setFeedback({
        type: 'success',
        message: `Simulation progression speed set to ${spd}x.`,
      });
      pollSimulationData();
      fetchLiveBuses().then((fresh) => {
        if (Array.isArray(fresh) && fresh.length > 0) setLiveBusList(fresh);
      }).catch(() => {});
      if (onRefreshRequired) onRefreshRequired();
    } catch (err: any) {
      setFeedback({
        type: 'error',
        message: err?.message || `Failed to set simulation speed`,
      });
      pollSimulationData();
    } finally {
      setIsActionLoading(false);
    }
  };

  // Selected bus details
  const activeSelectedBus = useMemo(() => {
    if (!selectedBusId) return null;
    return liveBusList.find((b) => b.bus_id === selectedBusId) || null;
  }, [liveBusList, selectedBusId]);

  // Default Coimbatore corridor naming map as reliable fallback
  const CORRIDOR_METADATA: Record<string, { name: string; origin: string; destination: string }> = {
    '101': { name: 'Gandhipuram – Avinashi Road Express', origin: 'Gandhipuram Central', destination: 'Hope College' },
    '202': { name: 'Saibaba Colony – Railway Station Loop', origin: 'Saibaba Colony', destination: 'Town Hall' },
    '303': { name: 'Ukkadam – Trichy Road – Singanallur', origin: 'Ukkadam Bus Terminus', destination: 'Singanallur' },
    '404': { name: 'Gandhipuram – Singanallur Express', origin: 'Gandhipuram Central', destination: 'Singanallur' },
    '505': { name: 'Gandhipuram – Ukkadam Direct', origin: 'Gandhipuram Central', destination: 'Ukkadam' },
    '606': { name: 'Gandhipuram – Peelamedu – Hope College Shuttle', origin: 'Gandhipuram Central', destination: 'Hope College' },
  };

  // Aggregate route information across 6 routes
  const monitoredRoutes = useMemo(() => {
    const list = detailedRoutes.length > 0 ? detailedRoutes : routes;
    return list.map((r: any) => {
      const routeNum = String(r.route_number);
      const meta = CORRIDOR_METADATA[routeNum];
      const assignedBuses = liveBusList.filter(
        (b) => String(b.assigned_route_number) === routeNum || String(b.route_number) === routeNum
      );
      const totalPassengers = assignedBuses.reduce((sum, b) => sum + (b.passenger_count || 0), 0);
      const totalCap = assignedBuses.reduce((sum, b) => sum + (b.capacity || 60), 0);
      const lf = totalCap > 0 ? Math.round((totalPassengers / totalCap) * 100) / 100 : (r.load_factor ?? 0.0);
      const freeSeats = Math.max(0, totalCap - totalPassengers);
      const classification = getLoadStatus(lf);
      const currentDemandProfile = routeDemands[routeNum] || (r.demand_profile as 'LOW' | 'NORMAL' | 'HIGH') || 'NORMAL';

      return {
        id: r.id || r.route_id,
        route_number: routeNum,
        name: r.name || meta?.name || `Route ${routeNum}`,
        origin: r.origin || meta?.origin || 'Origin Terminal',
        destination: r.destination || meta?.destination || 'Destination Terminal',
        assignedBuses,
        passengerDemand: totalPassengers,
        capacity: totalCap,
        loadFactor: lf,
        availableSeats: freeSeats,
        classification,
        demandProfile: currentDemandProfile,
        isActive: r.is_active ?? true,
      };
    });
  }, [detailedRoutes, routes, liveBusList, routeDemands]);

  const simState = status?.status || 'RUNNING';
  const isRunning = simState === 'RUNNING';
  const isPaused = simState === 'PAUSED';
  const isStopped = simState === 'STOPPED';
  const activeProfile = status?.active_profile || 'NORMAL';
  const currentSpeed = status?.speed || 1;

  return (
    <div className="space-y-6">
      {/* 1. Header Banner with Status, Demand Profile, and Elapsed Time */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg relative overflow-hidden">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2.5 flex-wrap">
              <h2 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-pulse"></span>
                Traffic Simulation Control Room
              </h2>
              <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-cyan-500/10 text-cyan-400 border border-cyan-500/30">
                Coimbatore Transit Network (6 Routes • 12 Buses)
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Interactive fleet dynamics control: Switch between LOW, NORMAL, and HIGH demand profiles and monitor real-time passenger loads across all corridors.
            </p>
          </div>

          {/* Engine Status Indicators */}
          <div className="flex items-center gap-2 sm:gap-3 flex-wrap">
            {/* Status Pill */}
            <div className="bg-slate-950/80 px-3 py-1.5 rounded-lg border border-slate-800 flex items-center gap-2 text-xs">
              <span className="text-slate-400">Status:</span>
              <span
                className={`font-semibold flex items-center gap-1.5 ${
                  isRunning
                    ? 'text-emerald-400'
                    : isPaused
                    ? 'text-amber-400'
                    : 'text-rose-400'
                }`}
              >
                <span
                  className={`w-2 h-2 rounded-full ${
                    isRunning
                      ? 'bg-emerald-400 animate-pulse'
                      : isPaused
                      ? 'bg-amber-400'
                      : 'bg-rose-400'
                  }`}
                ></span>
                {simState}
              </span>
            </div>

            {/* Active Demand Badge */}
            <div className="bg-slate-950/80 px-3 py-1.5 rounded-lg border border-slate-800 flex items-center gap-2 text-xs">
              <span className="text-slate-400">Demand:</span>
              <span
                className={`font-bold px-2 py-0.5 rounded text-[11px] ${
                  activeProfile === 'HIGH'
                    ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                    : activeProfile === 'LOW'
                    ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                    : activeProfile === 'NORMAL'
                    ? 'bg-blue-500/20 text-blue-300 border border-blue-500/30'
                    : 'bg-purple-500/20 text-purple-300 border border-purple-500/30'
                }`}
              >
                {activeProfile === 'CUSTOM' ? 'INDEPENDENT (PER-ROUTE)' : `${activeProfile} DEMAND`}
              </span>
            </div>

            {/* Speed Badge */}
            <div className="bg-slate-950/80 px-3 py-1.5 rounded-lg border border-slate-800 text-xs">
              <span className="text-slate-400">Speed: </span>
              <span className="font-bold text-cyan-400">{currentSpeed}x</span>
            </div>

            {/* Elapsed Time */}
            {status?.elapsed_seconds !== undefined && (
              <div className="bg-slate-950/80 px-3 py-1.5 rounded-lg border border-slate-800 text-xs text-slate-300 font-mono">
                <span className="text-slate-400 font-sans">Elapsed: </span>
                {formatElapsed(status.elapsed_seconds)}
              </div>
            )}
          </div>
        </div>

        {/* Action Feedback Banner */}
        {feedback && (
          <div
            className={`mt-4 p-3 rounded-lg border text-xs flex items-center justify-between ${
              feedback.type === 'success'
                ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
                : 'bg-rose-500/10 border-rose-500/30 text-rose-300'
            }`}
          >
            <span>{feedback.message}</span>
            <button
              onClick={() => setFeedback(null)}
              className="text-slate-400 hover:text-white text-sm font-bold ml-2"
            >
              &times;
            </button>
          </div>
        )}
      </div>

      {/* 2. Primary Simulation Controls Card */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg space-y-5">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <h3 className="text-sm font-semibold tracking-wide text-white uppercase flex items-center gap-2">
            <svg className="w-4 h-4 text-cyan-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
            </svg>
            Interactive Simulation Controls
          </h3>
          <span className="text-xs text-slate-400">Changes immediately persist to backend engine</span>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* A. Global Network Preset (Convenience Tool) */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider block">
                Network-Wide Preset
              </label>
              <span className="text-[10px] text-slate-500 font-mono">Mass-Apply</span>
            </div>
            <div className="flex flex-col sm:flex-row gap-2">
              <select
                value={globalPreset}
                onChange={(e) => setGlobalPreset(e.target.value as 'LOW' | 'NORMAL' | 'HIGH')}
                disabled={isActionLoading}
                className="flex-1 text-xs bg-slate-950/80 border border-slate-700 rounded-lg px-2.5 py-2 text-slate-200 focus:outline-none focus:border-cyan-500 font-semibold"
              >
                <option value="LOW">LOW DEMAND (Off-Peak 20–40%)</option>
                <option value="NORMAL">NORMAL DEMAND (Standard 50–70%)</option>
                <option value="HIGH">HIGH DEMAND (Peak Surge 85–115%)</option>
              </select>
              <button
                type="button"
                onClick={handleApplyGlobalPreset}
                disabled={isActionLoading}
                className="px-3 py-2 text-xs font-bold rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white disabled:opacity-40 transition-colors shadow-sm whitespace-nowrap"
                title="Apply selected preset across all 6 corridors"
              >
                Apply to All Routes
              </button>
            </div>
            <p className="text-[11px] text-slate-500 leading-tight">
              Optional convenience action. Per-route controls in the section below are authoritative and can be adjusted independently.
            </p>
          </div>

          {/* B. Lifecycle Controls (Start, Pause, Resume, Stop, Reset) */}
          <div className="space-y-2">
            <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider block">
              Simulation Progression Lifecycle
            </label>
            <div className="flex flex-wrap gap-2">
              {/* Start button: enabled when stopped */}
              <button
                type="button"
                onClick={() => handleLifecycleAction('start')}
                disabled={isActionLoading || isRunning}
                className="px-3 py-2 text-xs font-medium rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center gap-1.5 shadow"
                title="Start fleet simulation"
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                </svg>
                Start
              </button>

              {/* Pause button: enabled when running */}
              <button
                type="button"
                onClick={() => handleLifecycleAction('pause')}
                disabled={isActionLoading || !isRunning}
                className="px-3 py-2 text-xs font-medium rounded-lg bg-amber-600 hover:bg-amber-500 text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center gap-1.5 shadow"
                title="Freeze movement temporarily"
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                Pause
              </button>

              {/* Resume button: enabled when paused */}
              <button
                type="button"
                onClick={() => handleLifecycleAction('resume')}
                disabled={isActionLoading || !isPaused}
                className="px-3 py-2 text-xs font-medium rounded-lg bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center gap-1.5 shadow"
                title="Continue paused simulation"
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                </svg>
                Resume
              </button>

              {/* Stop button: enabled when running or paused */}
              <button
                type="button"
                onClick={() => handleLifecycleAction('stop')}
                disabled={isActionLoading || isStopped}
                className="px-3 py-2 text-xs font-medium rounded-lg bg-rose-600 hover:bg-rose-500 text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center gap-1.5 shadow"
                title="Stop simulation loop cleanly"
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z M9 10a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z" />
                </svg>
                Stop
              </button>

              {/* Reset safely button */}
              <button
                type="button"
                onClick={() => handleLifecycleAction('reset')}
                disabled={isActionLoading}
                className="px-3 py-2 text-xs font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 transition-colors flex items-center gap-1.5"
                title="Safely reset bus positions and loads to initial terminals"
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                Reset Fleet
              </button>
            </div>
            <p className="text-[11px] text-slate-500">
              Safe state preservation: Pausing or resetting preserves dispatcher audit history, execution logs, and database integrity.
            </p>
          </div>

          {/* C. Simulation Speed Controls */}
          <div className="space-y-2">
            <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider block">
              Simulation Speed
            </label>
            <div className="flex gap-2">
              {([1, 2, 5] as SimulationSpeed[]).map((spd) => (
                <button
                  key={spd}
                  type="button"
                  onClick={() => handleSpeedChange(spd)}
                  disabled={isActionLoading}
                  className={`flex-1 py-2 rounded-lg text-xs font-bold border transition-all ${
                    currentSpeed === spd
                      ? 'bg-cyan-500/20 border-cyan-500 text-cyan-300 shadow-md ring-1 ring-cyan-500/30'
                      : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-slate-200'
                  }`}
                >
                  {spd}x Speed
                </button>
              ))}
            </div>
            <div className="text-[11px] text-slate-500">
              Progression interval: <span className="font-mono text-slate-400">{status?.effective_interval ?? 4}s</span> per cycle.
            </div>
          </div>
        </div>
      </div>

      {/* 3. Route Demand Configuration Section (Independent per Corridor) */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
          <div>
            <h3 className="text-sm font-semibold tracking-wide text-white uppercase flex items-center gap-2">
              <svg className="w-4 h-4 text-cyan-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
              </svg>
              Route Demand Configuration
            </h3>
            <p className="text-xs text-slate-400">
              Configure independent passenger arrival and boarding pressures per corridor. Changing one route operates independently without altering other corridors.
            </p>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse"></span>
            <span className="text-cyan-400 font-mono">Independent Corridors</span>
          </div>
        </div>

        {/* Route Demand Rows / Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-slate-300">
            <thead className="bg-slate-950/70 uppercase text-[10px] tracking-wider text-slate-400 border-b border-slate-800">
              <tr>
                <th className="py-2.5 px-3">Route Corridor</th>
                <th className="py-2.5 px-3 text-right">Current Load</th>
                <th className="py-2.5 px-3 text-center">Passenger Load</th>
                <th className="py-2.5 px-3 text-center">Active Demand</th>
                <th className="py-2.5 px-3 text-center min-w-[280px]">Demand Selector</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {monitoredRoutes.map((r) => {
                const color = ROUTE_COLORS[r.route_number] || '#8b5cf6';
                const currentDemand = routeDemands[r.route_number] || 'NORMAL';
                const isUpdating = updatingRoute === r.route_number;

                return (
                  <tr key={r.route_number} className="hover:bg-slate-800/30 transition-colors">
                    {/* Route number & corridor name */}
                    <td className="py-3 px-3">
                      <div className="flex items-center gap-2.5">
                        <span className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: color }}></span>
                        <div>
                          <div className="font-bold text-white font-mono flex items-center gap-1.5">
                            Route {r.route_number}
                          </div>
                          <div className="text-[11px] text-slate-400 line-clamp-1">{r.name}</div>
                        </div>
                      </div>
                    </td>

                    {/* Current Load % & Progress Bar */}
                    <td className="py-3 px-3 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <span className="font-mono font-bold text-white text-sm">
                          {Math.round(r.loadFactor * 100)}%
                        </span>
                        <div className="w-16 bg-slate-800 rounded-full h-2 overflow-hidden hidden sm:block">
                          <div
                            className="h-full rounded-full transition-all duration-300"
                            style={{
                              backgroundColor: r.classification.color,
                              width: `${Math.min(100, Math.round(r.loadFactor * 100))}%`,
                            }}
                          />
                        </div>
                        <StatusBadge status={r.classification.status} />
                      </div>
                    </td>

                    {/* Passenger count and capacity */}
                    <td className="py-3 px-3 text-center font-mono">
                      <span className="font-semibold text-slate-200">{r.passengerDemand}</span>
                      <span className="text-slate-500"> / {r.capacity} seats</span>
                      <div className="text-[10px] text-emerald-400 font-sans">{r.availableSeats} available</div>
                    </td>

                    {/* Current Demand Profile Badge */}
                    <td className="py-3 px-3 text-center">
                      <span
                        className={`inline-block font-bold px-2.5 py-1 rounded text-[11px] uppercase tracking-wider ${
                          currentDemand === 'HIGH'
                            ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30 shadow-sm shadow-rose-500/10'
                            : currentDemand === 'LOW'
                            ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 shadow-sm shadow-emerald-500/10'
                            : 'bg-blue-500/20 text-blue-300 border border-blue-500/30 shadow-sm shadow-blue-500/10'
                        }`}
                      >
                        {currentDemand} DEMAND
                      </span>
                    </td>

                    {/* Demand Selector Buttons with Immediate Apply */}
                    <td className="py-3 px-3 text-center">
                      <div className="inline-flex rounded-lg p-1 bg-slate-950/80 border border-slate-800 gap-1">
                        {(['LOW', 'NORMAL', 'HIGH'] as const).map((profileOpt) => {
                          const isSelected = currentDemand === profileOpt;
                          return (
                            <button
                              key={profileOpt}
                              type="button"
                              onClick={() => handleSingleRouteDemandChange(r.route_number, profileOpt)}
                              disabled={isActionLoading || isUpdating}
                              className={`px-3 py-1.5 rounded-md text-[11px] font-bold transition-all flex items-center gap-1 ${
                                isSelected
                                  ? profileOpt === 'HIGH'
                                    ? 'bg-rose-500 text-white shadow-md shadow-rose-500/20 ring-1 ring-rose-400'
                                    : profileOpt === 'LOW'
                                    ? 'bg-emerald-500 text-white shadow-md shadow-emerald-500/20 ring-1 ring-emerald-400'
                                    : 'bg-blue-500 text-white shadow-md shadow-blue-500/20 ring-1 ring-blue-400'
                                  : 'text-slate-400 hover:text-white hover:bg-slate-800/80'
                              } disabled:opacity-50`}
                              title={`Set Route ${r.route_number} to ${profileOpt} DEMAND`}
                            >
                              {isUpdating && isSelected && (
                                <span className="w-2 h-2 rounded-full border border-white border-t-transparent animate-spin"></span>
                              )}
                              {profileOpt}
                            </button>
                          );
                        })}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* 3. Live Traffic KPIs Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3.5">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">Active Fleet</div>
          <div className="text-2xl font-bold text-white mt-1">{kpis?.total_active_buses ?? 12} Buses</div>
          <div className="text-[10px] text-slate-500 mt-0.5">Across {kpis?.total_routes ?? 6} corridors</div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">Avg Load Factor</div>
          <div className="text-2xl font-bold text-cyan-400 mt-1">
            {kpis ? Math.round(kpis.average_load_factor * 100) : 55}%
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">
            {kpis?.total_passengers ?? 0} / {kpis?.total_fleet_capacity ?? 720} pass.
          </div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">Normal Load Corridors</div>
          <div className="text-2xl font-bold text-blue-400 mt-1">{kpis?.normal_load_routes_count ?? 4}</div>
          <div className="text-[10px] text-slate-500 mt-0.5">Load factor 50%–80%</div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">High / Critical Load</div>
          <div className="text-2xl font-bold text-amber-400 mt-1">
            {(kpis?.high_load_routes_count ?? 0) + (kpis?.critical_load_routes_count ?? 0)}
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">
            {kpis?.critical_load_routes_count ?? 0} critical overcrowding
          </div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <div className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">Available Capacity</div>
          <div className="text-2xl font-bold text-emerald-400 mt-1">
            {kpis?.available_capacity_seats ?? 324}
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">Seats available in network</div>
        </div>
      </div>

      {/* 4. Live Transit Map & Selected Bus Details */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Map Container */}
        <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-lg flex flex-col">
          <div className="p-3.5 border-b border-slate-800 flex items-center justify-between bg-slate-900/90 gap-2 flex-wrap">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse"></span>
              <h3 className="text-sm font-semibold text-white">Coimbatore Network Telemetry Map</h3>
              <span className="text-xs text-slate-500 hidden sm:inline">
                ({liveBusList.length} buses live)
              </span>
            </div>

            <div className="flex items-center gap-2">
              {/* Route Filter Dropdown */}
              <select
                value={filterRoute}
                onChange={(e) => setFilterRoute(e.target.value)}
                className="text-xs bg-slate-800 border border-slate-700 rounded-lg px-2.5 py-1 text-slate-200 focus:outline-none focus:border-cyan-500"
              >
                <option value="ALL">All 6 Corridors</option>
                <option value="101">Route 101 (Avinashi Rd)</option>
                <option value="202">Route 202 (Saibaba Colony)</option>
                <option value="303">Route 303 (Trichy Rd)</option>
                <option value="404">Route 404 (Singanallur Exp)</option>
                <option value="505">Route 505 (Ukkadam Direct)</option>
                <option value="606">Route 606 (Peelamedu Shuttle)</option>
              </select>

              {/* Fit Fleet Button */}
              <button
                type="button"
                onClick={handleFitFleet}
                className="px-2.5 py-1 text-xs font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg transition-colors"
                title="Fit viewport to all 12 buses"
              >
                Fit Fleet
              </button>
            </div>
          </div>

          <div className="relative flex-1 min-h-[460px] bg-slate-950">
            <div ref={mapContainerRef} className="absolute inset-0 z-10 w-full h-full" />
          </div>

          {/* Route Legend Bar */}
          <div className="p-2.5 bg-slate-950/90 border-t border-slate-800 flex items-center justify-between text-[11px] overflow-x-auto gap-3">
            <span className="text-slate-500 uppercase font-semibold">Corridors:</span>
            {Object.entries(ROUTE_COLORS).map(([rNum, color]) => (
              <div key={rNum} className="flex items-center gap-1.5 whitespace-nowrap">
                <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: color }}></span>
                <span className="text-slate-300 font-mono">Route {rNum}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Selected Bus Inspection Card */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg flex flex-col justify-between">
          <div className="space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-sm font-semibold text-white uppercase tracking-wider flex items-center gap-2">
                <svg className="w-4 h-4 text-cyan-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                Bus Telemetry Inspector
              </h3>
              {activeSelectedBus && (
                <span className="text-xs font-mono px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/30">
                  {activeSelectedBus.bus_number}
                </span>
              )}
            </div>

            {activeSelectedBus ? (
              <div className="space-y-3.5 text-xs">
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Assigned Route:</span>
                  <span className="font-semibold text-white">
                    Route {activeSelectedBus.route_number || activeSelectedBus.assigned_route_number}
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Current Speed:</span>
                  <span className="font-mono text-cyan-300">{activeSelectedBus.speed?.toFixed(1) || '0.0'} km/h</span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Passenger Load:</span>
                  <span className="font-semibold text-white">
                    {activeSelectedBus.passenger_count ?? 0} / {activeSelectedBus.capacity} passengers
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Available Seats:</span>
                  <span className="font-semibold text-emerald-400">
                    {Math.max(0, activeSelectedBus.capacity - (activeSelectedBus.passenger_count ?? 0))} seats
                  </span>
                </div>

                {/* Load Factor Progress Bar */}
                <div className="space-y-1">
                  <div className="flex justify-between text-[11px]">
                    <span className="text-slate-400">Load Factor:</span>
                    <span className="font-bold text-white">
                      {Math.round(((activeSelectedBus.passenger_count ?? 0) / (activeSelectedBus.capacity || 60)) * 100)}%
                    </span>
                  </div>
                  <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-300 ${
                        (activeSelectedBus.load_factor ?? 0) >= 1.0
                          ? 'bg-rose-500'
                          : (activeSelectedBus.load_factor ?? 0) >= 0.8
                          ? 'bg-amber-500'
                          : 'bg-emerald-500'
                      }`}
                      style={{
                        width: `${Math.min(100, Math.round(((activeSelectedBus.passenger_count ?? 0) / (activeSelectedBus.capacity || 60)) * 100))}%`,
                      }}
                    />
                  </div>
                </div>

                <div className="flex items-center justify-between pt-2 border-t border-slate-800">
                  <span className="text-slate-400">Status:</span>
                  <StatusBadge status={getLoadStatus(activeSelectedBus.load_factor ?? 0).status} />
                </div>

                {activeSelectedBus.is_transferring && (
                  <div className="p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-300 text-[11px]">
                    Deadhead Transfer Active: Moving to Route {activeSelectedBus.target_route_number} entry stop.
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center py-12 text-slate-500 text-xs">
                <svg className="w-8 h-8 mx-auto text-slate-600 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122" />
                </svg>
                Click any bus marker on the map to inspect its real-time speed, passenger load, and route telemetry.
              </div>
            )}
          </div>

          <div className="text-[11px] text-slate-500 border-t border-slate-800 pt-3 mt-4">
            Authoritative simulation tick #{status?.tick_count ?? 0} • Telemetry synced
          </div>
        </div>
      </div>

      {/* 5. Route Monitoring: All 6 Coimbatore Routes */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div>
            <h3 className="text-sm font-semibold text-white uppercase tracking-wider flex items-center gap-2">
              <svg className="w-4 h-4 text-cyan-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
              Coimbatore Transit Corridors (6 Routes)
            </h3>
            <p className="text-xs text-slate-400">Live operational load classification and bus assignments</p>
          </div>
          <span className="text-xs font-mono text-cyan-400 bg-cyan-500/10 px-2.5 py-1 rounded border border-cyan-500/30">
            6 Routes • 12 Buses
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-slate-300">
            <thead className="bg-slate-950/60 uppercase text-[10px] tracking-wider text-slate-400 border-b border-slate-800">
              <tr>
                <th className="py-2.5 px-3">Route #</th>
                <th className="py-2.5 px-3">Corridor Name</th>
                <th className="py-2.5 px-3">Assigned Buses</th>
                <th className="py-2.5 px-3">Passenger Demand</th>
                <th className="py-2.5 px-3">Demand Profile</th>
                <th className="py-2.5 px-3">Load Factor</th>
                <th className="py-2.5 px-3">Classification</th>
                <th className="py-2.5 px-3">Available Seats</th>
                <th className="py-2.5 px-3">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {monitoredRoutes.map((r) => {
                const color = ROUTE_COLORS[r.route_number] || '#8b5cf6';
                const currentDemand = routeDemands[r.route_number] || 'NORMAL';
                return (
                  <tr key={r.route_number} className="hover:bg-slate-800/40 transition-colors">
                    <td className="py-3 px-3 font-mono font-bold text-white flex items-center gap-1.5">
                      <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: color }}></span>
                      Route {r.route_number}
                    </td>
                    <td className="py-3 px-3">
                      <div className="font-medium text-slate-200">{r.name}</div>
                      <div className="text-[10px] text-slate-500">{r.origin} → {r.destination}</div>
                    </td>
                    <td className="py-3 px-3">
                      <div className="flex gap-1 flex-wrap">
                        {r.assignedBuses.map((b) => (
                          <span
                            key={b.bus_id}
                            className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-slate-800 text-slate-300 border border-slate-700 cursor-pointer hover:border-cyan-500"
                            onClick={() => setSelectedBusId(b.bus_id)}
                          >
                            {b.bus_number}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="py-3 px-3 font-semibold text-white">
                      {r.passengerDemand} / {r.capacity} pass.
                    </td>
                    <td className="py-3 px-3">
                      <span
                        className={`font-mono font-bold px-2 py-0.5 rounded text-[10px] ${
                          currentDemand === 'HIGH'
                            ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                            : currentDemand === 'LOW'
                            ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                            : 'bg-blue-500/20 text-blue-300 border border-blue-500/30'
                        }`}
                      >
                        {currentDemand}
                      </span>
                    </td>
                    <td className="py-3 px-3">
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-bold text-white">
                          {Math.round(r.loadFactor * 100)}%
                        </span>
                        <div className="w-16 bg-slate-800 rounded-full h-1.5 overflow-hidden hidden sm:block">
                          <div
                            className="h-full rounded-full"
                            style={{
                              backgroundColor: r.classification.color,
                              width: `${Math.min(100, Math.round(r.loadFactor * 100))}%`,
                            }}
                          />
                        </div>
                      </div>
                    </td>
                    <td className="py-3 px-3">
                      <StatusBadge status={r.classification.status} />
                    </td>
                    <td className="py-3 px-3 font-semibold text-emerald-400">
                      {r.availableSeats} seats
                    </td>
                    <td className="py-3 px-3">
                      <span className="inline-flex items-center gap-1 text-[11px] text-emerald-400">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
                        Active
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* 6. Simulation Event Log */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg space-y-3">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2">
            <svg className="w-4 h-4 text-cyan-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <h3 className="text-sm font-semibold text-white uppercase tracking-wider">
              Simulation Event Audit Log
            </h3>
          </div>
          <span className="text-xs text-slate-500 font-mono">
            {events.length} recorded events
          </span>
        </div>

        <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
          {Array.isArray(events) && events.length > 0 ? (
            events.map((evt) => {
              let timeStr = '—';
              try {
                if (evt.timestamp) timeStr = new Date(evt.timestamp).toLocaleTimeString();
              } catch {
                timeStr = '—';
              }
              return (
                <div
                  key={evt.id || `${evt.type}-${Math.random()}`}
                  className="p-2.5 rounded-lg bg-slate-950/70 border border-slate-800/80 flex items-start justify-between gap-3 text-xs"
                >
                  <div className="space-y-0.5">
                    <div className="flex items-center gap-2">
                      <span
                        className={`px-1.5 py-0.2 rounded text-[10px] font-bold uppercase tracking-wider ${
                          evt.level === 'critical'
                            ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                            : evt.level === 'warning'
                            ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                            : evt.level === 'success'
                            ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                            : 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30'
                        }`}
                      >
                        {evt.type}
                      </span>
                      <span className="text-slate-200 font-medium">{evt.message}</span>
                    </div>
                  </div>
                  <span className="text-[10px] text-slate-500 font-mono whitespace-nowrap">
                    {timeStr}
                  </span>
                </div>
              );
            })
          ) : (
            <div className="text-center py-6 text-slate-500 text-xs">
              No simulation events logged yet.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
