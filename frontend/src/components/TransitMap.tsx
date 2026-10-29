import React, { useEffect, useRef, useState, useMemo, useCallback } from 'react';
import L from 'leaflet';
import { BusLive, RouteLive, RouteIntelligence, RouteDetailed, LoadStatus } from '../types';
import { StatusBadge } from './StatusBadge';
import { fetchRoutesDetailed, fetchLiveBuses, manualReassignBus } from '../services/api';

interface TransitMapProps {
  buses: BusLive[];
  routes: (RouteLive | RouteIntelligence)[];
  detailedRoutes?: RouteDetailed[];
  isLoading: boolean;
  selectedBusId?: number | null;
  onSelectBus?: (busId: number | null) => void;
  onReassignmentExecuted?: () => void;
}

// Helper to determine load status and color from bus data
function getBusLoadStatus(bus: BusLive): { status: LoadStatus; color: string; bgClass: string } {
  const lf = bus.load_factor ?? (bus.capacity > 0 && bus.passenger_count !== null ? bus.passenger_count / bus.capacity : null);

  if (lf === null) {
    return { status: 'NORMAL', color: '#3B82F6', bgClass: 'bg-blue-500' };
  }
  if (lf >= 1.0) {
    return { status: 'CRITICAL', color: '#EF4444', bgClass: 'bg-rose-500' };
  }
  if (lf >= 0.8) {
    return { status: 'HIGH', color: '#F59E0B', bgClass: 'bg-amber-500' };
  }
  if (lf >= 0.5) {
    return { status: 'NORMAL', color: '#3B82F6', bgClass: 'bg-blue-500' };
  }
  return { status: 'LOW', color: '#10B981', bgClass: 'bg-emerald-500' };
}

// Create custom SVG marker icon for Leaflet
function createBusDivIcon(bus: BusLive, isSelected: boolean) {
  const { color } = getBusLoadStatus(bus);
  const size = isSelected ? 42 : 34;
  const pulseRing = isSelected
    ? `<div class="absolute -inset-1.5 rounded-full border-2 border-white animate-ping opacity-75"></div>`
    : '';

  const html = `
    <div class="relative flex items-center justify-center cursor-pointer transition-transform hover:scale-110" style="width: ${size}px; height: ${size}px;">
      ${pulseRing}
      <div class="w-full h-full rounded-full shadow-lg flex items-center justify-center text-white font-bold border-2 border-white" style="background-color: ${color};">
        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
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

export const TransitMap: React.FC<TransitMapProps> = ({
  buses,
  routes,
  detailedRoutes: propDetailedRoutes,
  isLoading,
  selectedBusId: externalSelectedBusId,
  onSelectBus,
  onReassignmentExecuted,
}) => {
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);
  const markersLayerRef = useRef<L.LayerGroup | null>(null);
  const routesLayerRef = useRef<L.LayerGroup | null>(null);
  const markersByBusIdRef = useRef<Map<number, L.Marker>>(new Map());
  const initialFitDoneRef = useRef<boolean>(false);
  const onSelectBusRef = useRef(onSelectBus);
  onSelectBusRef.current = onSelectBus;

  const [mapReady, setMapReady] = useState<boolean>(false);
  const [detailedRoutes, setDetailedRoutes] = useState<RouteDetailed[]>(
    propDetailedRoutes && propDetailedRoutes.length > 0 ? propDetailedRoutes : []
  );
  const [internalSelectedBusId, setInternalSelectedBusId] = useState<number | null>(null);
  const [filterRoute, setFilterRoute] = useState<string | 'ALL'>('ALL');
  const [busList, setBusList] = useState<BusLive[]>(buses);

  // Manual route assignment state
  const [isReassignModalOpen, setIsReassignModalOpen] = useState(false);
  const [targetRouteId, setTargetRouteId] = useState<number | ''>('');
  const [dispatcherId, setDispatcherId] = useState('DISPATCHER-1');
  const [reassignReason, setReassignReason] = useState('');
  const [isSubmittingReassign, setIsSubmittingReassign] = useState(false);
  const [reassignFeedback, setReassignFeedback] = useState<{
    message: string;
    type: 'success' | 'error';
  } | null>(null);

  const selectedBusId = externalSelectedBusId ?? internalSelectedBusId;

  // Sync internal bus state whenever parent provides updated buses
  useEffect(() => {
    if (buses && buses.length > 0) {
      setBusList(buses);
    }
  }, [buses]);

  // Periodic polling for fresh bus telemetry using existing API client
  useEffect(() => {
    let isMounted = true;
    let isPolling = false;

    const pollBusTelemetry = async () => {
      if (isPolling) return;
      isPolling = true;
      try {
        const freshBuses = await fetchLiveBuses();
        if (isMounted && Array.isArray(freshBuses) && freshBuses.length > 0) {
          setBusList(freshBuses);
        }
      } catch (err) {
        // Handle request errors without silently freezing the map
        console.warn('[TransitMap] Failed to poll live bus telemetry:', err);
      } finally {
        isPolling = false;
      }
    };

    // Dedicated periodic telemetry poll every 1500ms for continuous smooth movement
    pollBusTelemetry();
    const intervalId = setInterval(pollBusTelemetry, 1500);

    return () => {
      isMounted = false;
      clearInterval(intervalId);
    };
  }, []);

  // Sync detailedRoutes with parent prop if provided
  useEffect(() => {
    if (propDetailedRoutes && propDetailedRoutes.length > 0) {
      setDetailedRoutes(propDetailedRoutes);
    }
  }, [propDetailedRoutes]);

  // Load detailed routes with ordered stops on mount if not provided via props
  useEffect(() => {
    let isMounted = true;
    if (detailedRoutes.length >= 6) return;

    fetchRoutesDetailed()
      .then((data) => {
        if (isMounted && Array.isArray(data) && data.length > 0) {
          setDetailedRoutes(data);
        }
      })
      .catch((err) => console.warn('Could not load detailed routes for map overlays:', err));

    return () => {
      isMounted = false;
    };
  }, []);

  const handleSelectBus = useCallback((busId: number | null) => {
    setInternalSelectedBusId(busId);
    if (onSelectBusRef.current) {
      onSelectBusRef.current(busId);
    }
  }, []);

  // Segregate buses with valid GPS telemetry vs missing telemetry
  const validGpsBuses = useMemo(() => {
    return busList.filter((b) => {
      const hasCoords =
        b.latitude !== null &&
        b.longitude !== null &&
        !isNaN(b.latitude) &&
        !isNaN(b.longitude) &&
        b.latitude !== 0 &&
        b.longitude !== 0;

      if (!hasCoords) return false;
      if (filterRoute !== 'ALL' && b.route_number !== filterRoute) return false;
      return true;
    });
  }, [busList, filterRoute]);

  const unmappedBuses = useMemo(() => {
    return busList.filter(
      (b) =>
        b.latitude === null ||
        b.longitude === null ||
        isNaN(b.latitude) ||
        isNaN(b.longitude) ||
        (b.latitude === 0 && b.longitude === 0)
    );
  }, [busList]);

  const activeSelectedBus = useMemo(() => {
    if (!selectedBusId) return null;
    return busList.find((b) => b.bus_id === selectedBusId) || null;
  }, [busList, selectedBusId]);

  const handleExecuteReassign = async () => {
    if (!activeSelectedBus || !targetRouteId) return;
    setIsSubmittingReassign(true);
    setReassignFeedback(null);
    try {
      const res = await manualReassignBus(activeSelectedBus.bus_id, {
        target_route_id: Number(targetRouteId),
        dispatcher_id: dispatcherId.trim() || 'DISPATCHER-1',
        reason: reassignReason.trim() || 'Manual dispatcher route reassignment',
      });
      setReassignFeedback({
        type: 'success',
        message: `Bus ${activeSelectedBus.bus_number} successfully reassigned to Route ${res.target_route_number}. Simulator initiated continuous transfer.`,
      });
      setIsReassignModalOpen(false);
      if (onReassignmentExecuted) {
        onReassignmentExecuted();
      }
      const fresh = await fetchLiveBuses();
      if (fresh) setBusList(fresh);
    } catch (err: any) {
      setReassignFeedback({
        type: 'error',
        message: err?.response?.data?.detail || err?.message || 'Failed to reassign route',
      });
    } finally {
      setIsSubmittingReassign(false);
    }
  };

  // 1. Initialize Map centered on Coimbatore
  useEffect(() => {
    if (!mapContainerRef.current || mapInstanceRef.current) return;

    // Clear any stale Leaflet instance ID to avoid container re-initialization crashes
    if ((mapContainerRef.current as any)._leaflet_id) {
      (mapContainerRef.current as any)._leaflet_id = null;
    }

    // Default center (Coimbatore central transit area: Gandhipuram / Avinashi Rd)
    const initialLat = 11.0070;
    const initialLon = 76.9750;

    let map: L.Map | null = null;
    try {
      map = L.map(mapContainerRef.current, {
        center: [initialLat, initialLon],
        zoom: 13,
        zoomControl: true,
        attributionControl: true,
      });

      // Free OpenStreetMap tiles
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
      console.warn('[TransitMap] Leaflet map initialization warning:', err);
      return;
    }

    const resizeTimer1 = setTimeout(() => {
      mapInstanceRef.current?.invalidateSize();
    }, 150);
    const resizeTimer2 = setTimeout(() => {
      mapInstanceRef.current?.invalidateSize();
    }, 500);

    return () => {
      clearTimeout(resizeTimer1);
      clearTimeout(resizeTimer2);
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

  // 2. Render route paths and stop markers for all 6 corridors
  useEffect(() => {
    const map = mapInstanceRef.current;
    const routesLayer = routesLayerRef.current;
    if (!map || !routesLayer || !mapReady) return;

    routesLayer.clearLayers();

    const routeColors: Record<string, string> = {
      '101': '#3b82f6', // Avinashi Rd corridor (Blue)
      '202': '#10b981', // Saibaba Colony / Town Hall (Emerald)
      '303': '#f59e0b', // Ukkadam / Trichy Rd (Amber)
      '404': '#8b5cf6', // Gandhipuram – Singanallur (Purple)
      '505': '#ec4899', // Gandhipuram – Ukkadam (Pink)
      '606': '#06b6d4', // Gandhipuram – Peelamedu – Hope College (Cyan)
    };

    detailedRoutes.forEach((route) => {
      if (filterRoute !== 'ALL' && filterRoute !== route.route_number) {
        return;
      }

      const color = routeColors[route.route_number] || '#8b5cf6';
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
        const polylineCoords: L.LatLngTuple[] = validStops.map((s) => [s.latitude, s.longitude]);
        const polyline = L.polyline(polylineCoords, {
          color,
          weight: 4,
          opacity: 0.85,
        });
        polyline.bindTooltip(`Route ${route.route_number}: ${route.name}`, { sticky: true });
        routesLayer.addLayer(polyline);
      }

      validStops.forEach((stop) => {
        const stopMarker = L.circleMarker([stop.latitude, stop.longitude], {
          radius: 5,
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

  // 3. Render and sync Bus Markers imperatively
  useEffect(() => {
    const map = mapInstanceRef.current;
    const markersLayer = markersLayerRef.current;
    if (!map || !markersLayer) return;

    const currentBusIds = new Set<number>();
    const bounds = L.latLngBounds([]);

    validGpsBuses.forEach((bus) => {
      currentBusIds.add(bus.bus_id);
      const lat = bus.latitude!;
      const lon = bus.longitude!;
      bounds.extend([lat, lon]);

      const isSelected = bus.bus_id === selectedBusId;
      const icon = createBusDivIcon(bus, isSelected);

      const existingMarker = markersByBusIdRef.current.get(bus.bus_id);

      if (existingMarker) {
        // Retain marker reference keyed by bus ID and update position imperatively
        existingMarker.setLatLng([lat, lon]);
        existingMarker.setIcon(icon);
      } else {
        // Create marker once and avoid creating duplicate markers on every polling cycle
        const marker = L.marker([lat, lon], { icon, title: `Bus ${bus.bus_number}` });

        marker.on('click', () => {
          handleSelectBus(bus.bus_id);
        });

        markersLayer.addLayer(marker);
        markersByBusIdRef.current.set(bus.bus_id, marker);
      }
    });

    // Remove markers for buses that are no longer active or are filtered out
    markersByBusIdRef.current.forEach((marker, busId) => {
      if (!currentBusIds.has(busId)) {
        markersLayer.removeLayer(marker);
        markersByBusIdRef.current.delete(busId);
      }
    });

    // Auto-fit bounds on initial population only, avoiding constant jumps
    if (!initialFitDoneRef.current && bounds.isValid() && validGpsBuses.length > 0 && !selectedBusId) {
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 });
      initialFitDoneRef.current = true;
    }
  }, [validGpsBuses, selectedBusId, handleSelectBus]);

  // Focus map when selected bus changes
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || !activeSelectedBus) return;

    if (
      activeSelectedBus.latitude !== null &&
      activeSelectedBus.longitude !== null &&
      !isNaN(activeSelectedBus.latitude) &&
      !isNaN(activeSelectedBus.longitude)
    ) {
      map.setView([activeSelectedBus.latitude, activeSelectedBus.longitude], 15, {
        animate: true,
      });
    }
  }, [selectedBusId]);

  const fitAllBuses = () => {
    const map = mapInstanceRef.current;
    if (!map || validGpsBuses.length === 0) return;

    const bounds = L.latLngBounds(validGpsBuses.map((b) => [b.latitude!, b.longitude!]));
    if (bounds.isValid()) {
      map.fitBounds(bounds, { padding: [50, 50], maxZoom: 15 });
    }
  };

  return (
    <section className="mb-8">
      {/* Section Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-bold text-white tracking-tight">Live Transit Map</h2>
            <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 font-mono">
              {validGpsBuses.length} active GPS
            </span>
          </div>
          <p className="text-xs text-slate-400">
            Real-time geospatial fleet positioning with live load factor telemetry
          </p>
        </div>

        {/* Map Toolbar Controls */}
        <div className="flex items-center gap-2">
          {isLoading && (
            <span className="text-[11px] text-blue-400 flex items-center gap-1 font-mono">
              <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-ping"></span>
              Tracking...
            </span>
          )}
          {/* Route Filter Dropdown */}
          <select
            value={filterRoute}
            onChange={(e) => setFilterRoute(e.target.value)}
            className="bg-slate-800 text-slate-200 text-xs rounded-lg px-2.5 py-1.5 border border-slate-700 focus:outline-none focus:border-blue-500"
          >
            <option value="ALL">All Routes ({routes.length})</option>
            {routes.map((r) => (
              <option key={r.route_id} value={r.route_number}>
                Route {r.route_number} ({r.number_of_buses} buses)
              </option>
            ))}
          </select>

          {/* Reset View Button */}
          <button
            onClick={fitAllBuses}
            className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium rounded-lg border border-slate-700 flex items-center gap-1.5 transition-colors"
            title="Recenter and fit all active buses in viewport"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"
              />
            </svg>
            Fit Fleet
          </button>
        </div>
      </div>

      {/* Main Map & Detail Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        {/* Map Container (3 cols) */}
        <div className="lg:col-span-3 bg-slate-900 border border-slate-800 rounded-xl overflow-hidden relative shadow-lg h-[500px] flex flex-col">
          <div ref={mapContainerRef} className="w-full h-full z-10" />

          {/* Map Overlay: Legend */}
          <div className="absolute bottom-3 left-3 z-20 bg-slate-900/90 backdrop-blur-md border border-slate-800 rounded-lg p-2.5 text-xs shadow-md">
            <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block mb-1.5">
              Load Factor Status
            </span>
            <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
              <div className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-500"></span>
                <span className="text-slate-300">LOW (&lt;50%)</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full bg-blue-500"></span>
                <span className="text-slate-300">NORMAL (50-80%)</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full bg-amber-500"></span>
                <span className="text-slate-300">HIGH (80-100%)</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full bg-rose-500"></span>
                <span className="text-slate-300">CRITICAL (&gt;=100%)</span>
              </div>
            </div>

            {/* Coimbatore Routes legend - All 6 Corridors */}
            <div className="pt-2 mt-2 border-t border-slate-800">
              <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block mb-1">
                Coimbatore Corridors (6 Routes)
              </span>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-2 gap-y-1 text-[10px]">
                <div className="flex items-center gap-1.5">
                  <span className="w-2.5 h-1 bg-[#3b82f6] rounded"></span>
                  <span className="text-slate-300 font-medium">Route 101</span>
                  <span className="text-slate-500">(Avinashi Rd)</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="w-2.5 h-1 bg-[#10b981] rounded"></span>
                  <span className="text-slate-300 font-medium">Route 202</span>
                  <span className="text-slate-500">(Saibaba–Jct)</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="w-2.5 h-1 bg-[#f59e0b] rounded"></span>
                  <span className="text-slate-300 font-medium">Route 303</span>
                  <span className="text-slate-500">(Trichy Rd)</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="w-2.5 h-1 bg-[#8b5cf6] rounded"></span>
                  <span className="text-slate-300 font-medium">Route 404</span>
                  <span className="text-slate-500">(Singanallur Exp)</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="w-2.5 h-1 bg-[#ec4899] rounded"></span>
                  <span className="text-slate-300 font-medium">Route 505</span>
                  <span className="text-slate-500">(Ukkadam Direct)</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="w-2.5 h-1 bg-[#06b6d4] rounded"></span>
                  <span className="text-slate-300 font-medium">Route 606</span>
                  <span className="text-slate-500">(Peelamedu Shuttle)</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Selected Bus Telemetry & Routes Sidebar (1 col) */}
        <div className="lg:col-span-1 space-y-4 flex flex-col">
          {/* Selected Bus Detail Card */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-sm flex-1">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                Vehicle Telemetry
              </span>
              {activeSelectedBus && (
                <button
                  onClick={() => handleSelectBus(null)}
                  className="text-xs text-slate-500 hover:text-slate-300"
                >
                  Clear
                </button>
              )}
            </div>

            {activeSelectedBus ? (
              <div className="mt-3 space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-lg font-bold text-white flex items-center gap-2">
                      Bus {activeSelectedBus.bus_number}
                    </h3>
                    <p className="text-xs text-blue-400 font-medium">
                      {activeSelectedBus.assigned_route_number
                        ? `Route ${activeSelectedBus.assigned_route_number}`
                        : (activeSelectedBus.route_number ? `Route ${activeSelectedBus.route_number}` : 'Unassigned Route')}
                    </p>
                  </div>
                  <StatusBadge
                    status={getBusLoadStatus(activeSelectedBus).status}
                    type="load"
                    size="sm"
                  />
                </div>

                {/* Route Assignment Distinction Block */}
                <div className="bg-slate-950/70 rounded-lg p-2.5 border border-slate-800/80 space-y-1.5 text-xs">
                  <div className="flex justify-between items-center text-[11px]">
                    <span className="text-slate-400">Home Corridor:</span>
                    <span className="font-semibold text-slate-200">
                      {activeSelectedBus.home_route_number ? `Route ${activeSelectedBus.home_route_number}` : '—'}
                    </span>
                  </div>
                  <div className="flex justify-between items-center text-[11px]">
                    <span className="text-slate-400">Persisted Assigned:</span>
                    <span className="font-semibold text-blue-300">
                      {activeSelectedBus.assigned_route_number ? `Route ${activeSelectedBus.assigned_route_number}` : (activeSelectedBus.route_number ? `Route ${activeSelectedBus.route_number}` : '—')}
                    </span>
                  </div>
                  <div className="flex justify-between items-center text-[11px]">
                    <span className="text-slate-400">Active Service:</span>
                    <span className="font-semibold text-emerald-300">
                      {activeSelectedBus.active_route_number ? `Route ${activeSelectedBus.active_route_number}` : (activeSelectedBus.route_number ? `Route ${activeSelectedBus.route_number}` : '—')}
                    </span>
                  </div>
                  {activeSelectedBus.direction && (
                    <div className="flex justify-between items-center text-[11px]">
                      <span className="text-slate-400">Travel Direction:</span>
                      <span className={`font-semibold ${activeSelectedBus.direction === 'FORWARD' ? 'text-cyan-300' : 'text-amber-300'}`}>
                        {activeSelectedBus.direction === 'FORWARD' ? 'Outbound ➔' : 'Inbound ⬅'}
                      </span>
                    </div>
                  )}

                  {/* Transfer status pill */}
                  {activeSelectedBus.is_transferring ? (
                    <div className="mt-2 p-1.5 rounded bg-purple-950/60 border border-purple-800 text-[11px] text-purple-300 flex items-center justify-between animate-pulse">
                      <span className="flex items-center gap-1 font-semibold">
                        ⚡ Transferring to Route {activeSelectedBus.target_route_number}
                      </span>
                      <span className="text-[10px] text-purple-400 font-mono">In Progress</span>
                    </div>
                  ) : activeSelectedBus.assigned_route_number && activeSelectedBus.home_route_number && activeSelectedBus.assigned_route_number !== activeSelectedBus.home_route_number ? (
                    <div className="mt-2 p-1.5 rounded bg-blue-950/40 border border-blue-800/60 text-[11px] text-blue-300 flex items-center justify-between">
                      <span>Reassigned from Home {activeSelectedBus.home_route_number}</span>
                      <span className="text-[10px] text-blue-400 font-mono">Serving Route {activeSelectedBus.assigned_route_number}</span>
                    </div>
                  ) : (
                    <div className="mt-1 p-1 rounded bg-slate-900/40 border border-slate-800/40 text-[10px] text-slate-400 flex items-center justify-between">
                      <span>Standard Home Corridor</span>
                      <span className="text-[10px] text-slate-500 font-mono">Normal</span>
                    </div>
                  )}

                  {/* Manual Reassign Action Button */}
                  <button
                    onClick={() => {
                      setTargetRouteId('');
                      setReassignReason('');
                      setReassignFeedback(null);
                      setIsReassignModalOpen(true);
                    }}
                    disabled={activeSelectedBus.is_transferring}
                    className={`w-full mt-2 py-1.5 px-3 rounded-lg font-semibold text-xs border flex items-center justify-center gap-1.5 transition-all ${
                      activeSelectedBus.is_transferring
                        ? 'bg-slate-800 text-slate-500 border-slate-700 cursor-not-allowed'
                        : 'bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white border-blue-400/50 shadow'
                    }`}
                    title={activeSelectedBus.is_transferring ? 'Bus is currently deadheading in transfer' : 'Dispatcher manual route assignment'}
                  >
                    <span>🔄</span>
                    <span>Change Route</span>
                  </button>
                </div>

                {/* Feedback Toast */}
                {reassignFeedback && (
                  <div
                    className={`p-2.5 rounded-lg border text-xs flex items-center justify-between transition-all ${
                      reassignFeedback.type === 'success'
                        ? 'bg-emerald-950/40 border-emerald-800 text-emerald-300'
                        : 'bg-rose-950/40 border-rose-800 text-rose-300'
                    }`}
                  >
                    <span>{reassignFeedback.message}</span>
                    <button
                      onClick={() => setReassignFeedback(null)}
                      className="text-xs opacity-60 hover:opacity-100 ml-2"
                    >
                      ✕
                    </button>
                  </div>
                )}

                {/* Occupancy and Capacity Progress */}
                <div className="bg-slate-950/60 rounded-lg p-3 border border-slate-800/80">
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-slate-400">Occupancy:</span>
                    <span className="font-semibold text-white">
                      {activeSelectedBus.passenger_count ?? '—'} / {activeSelectedBus.capacity} pax
                    </span>
                  </div>
                  <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden mb-1.5">
                    <div
                      className={`h-full transition-all ${
                        getBusLoadStatus(activeSelectedBus).bgClass
                      }`}
                      style={{
                        width: `${Math.min(
                          100,
                          Math.round(
                            (activeSelectedBus.load_factor ??
                              (activeSelectedBus.passenger_count || 0) /
                                (activeSelectedBus.capacity || 1)) * 100
                          )
                        )}%`,
                      }}
                    ></div>
                  </div>
                  <div className="flex justify-between text-[11px] text-slate-400">
                    <span>
                      Load Factor:{' '}
                      <strong className="text-slate-200">
                        {activeSelectedBus.load_factor !== null
                          ? `${Math.round(activeSelectedBus.load_factor * 100)}%`
                          : '—'}
                      </strong>
                    </span>
                    <span>
                      Available:{' '}
                      <strong className="text-emerald-400">
                        {Math.max(
                          0,
                          activeSelectedBus.capacity - (activeSelectedBus.passenger_count || 0)
                        )}{' '}
                        seats
                      </strong>
                    </span>
                  </div>
                </div>

                {/* GPS and Motion Specs */}
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div className="bg-slate-950/40 p-2 rounded border border-slate-800/60">
                    <span className="text-slate-500 block text-[10px] uppercase">Speed</span>
                    <span className="font-mono text-slate-200 font-semibold">
                      {activeSelectedBus.speed !== null
                        ? `${Math.round(activeSelectedBus.speed)} km/h`
                        : '—'}
                    </span>
                  </div>
                  <div className="bg-slate-950/40 p-2 rounded border border-slate-800/60">
                    <span className="text-slate-500 block text-[10px] uppercase">Heading</span>
                    <span className="font-mono text-slate-200 font-semibold">
                      {activeSelectedBus.heading !== null
                        ? `${Math.round(activeSelectedBus.heading)}°`
                        : '—'}
                    </span>
                  </div>
                  <div className="bg-slate-950/40 p-2 rounded border border-slate-800/60 col-span-2">
                    <span className="text-slate-500 block text-[10px] uppercase">GPS Coordinates</span>
                    <span className="font-mono text-xs text-slate-300">
                      {activeSelectedBus.latitude !== null && activeSelectedBus.longitude !== null
                        ? `${activeSelectedBus.latitude.toFixed(4)}, ${activeSelectedBus.longitude.toFixed(4)}`
                        : 'No GPS Signal'}
                    </span>
                  </div>
                </div>

                {/* Timestamp */}
                <p className="text-[10px] text-slate-500 pt-1">
                  Last Telemetry:{' '}
                  {activeSelectedBus.timestamp
                    ? new Date(activeSelectedBus.timestamp).toLocaleTimeString()
                    : 'Real-time simulator stream'}
                </p>
              </div>
            ) : (
              <div className="py-12 text-center text-slate-500 text-xs">
                <svg
                  className="w-8 h-8 mx-auto mb-2 opacity-40 text-slate-400"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="1.5"
                    d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"
                  />
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="1.5"
                    d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"
                  />
                </svg>
                Select any bus pin on the map to inspect live load and kinematic telemetry.
              </div>
            )}
          </div>

          {/* Unmapped Buses Fallback Panel */}
          {unmappedBuses.length > 0 && (
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-3.5 shadow-sm">
              <div className="flex items-center justify-between text-xs text-amber-400 font-semibold mb-2">
                <span className="flex items-center gap-1.5">
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth="2"
                      d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                    />
                  </svg>
                  Unmapped Buses ({unmappedBuses.length})
                </span>
                <span className="text-[10px] text-slate-500 font-normal">GPS Offline</span>
              </div>
              <p className="text-[11px] text-slate-400 mb-2">
                These active buses do not have live GPS coordinates reported:
              </p>
              <div className="space-y-1.5 max-h-32 overflow-y-auto pr-1">
                {unmappedBuses.map((ub) => (
                  <div
                    key={ub.bus_id}
                    onClick={() => handleSelectBus(ub.bus_id)}
                    className="p-1.5 rounded bg-slate-950/60 border border-slate-800/80 flex items-center justify-between text-xs cursor-pointer hover:border-slate-700"
                  >
                    <span className="font-semibold text-slate-300">Bus {ub.bus_number}</span>
                    <span className="text-[11px] text-slate-400">
                      Route {ub.route_number || '—'}
                    </span>
                    <span className="text-[10px] text-slate-500">No Signal</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Manual Route Assignment Modal Dialog */}
      {isReassignModalOpen && activeSelectedBus && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fade-in">
          <div className="max-w-lg w-full bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <span>🔄</span>
                <span>Manual Route Assignment — Bus {activeSelectedBus.bus_number}</span>
              </h3>
              <button
                onClick={() => setIsReassignModalOpen(false)}
                className="text-slate-400 hover:text-white text-lg p-1"
              >
                ✕
              </button>
            </div>

            {/* Vehicle context snapshot */}
            <div className="bg-slate-950/70 rounded-xl p-3 border border-slate-800 text-xs space-y-1.5 font-mono">
              <div className="flex justify-between text-slate-300">
                <span className="text-slate-500">Home Corridor:</span>
                <span className="font-semibold text-slate-200">
                  {activeSelectedBus.home_route_number ? `Route ${activeSelectedBus.home_route_number}` : '—'}
                </span>
              </div>
              <div className="flex justify-between text-slate-300">
                <span className="text-slate-500">Persisted Assigned:</span>
                <span className="font-semibold text-blue-400">
                  {activeSelectedBus.assigned_route_number ? `Route ${activeSelectedBus.assigned_route_number}` : (activeSelectedBus.route_number ? `Route ${activeSelectedBus.route_number}` : '—')}
                </span>
              </div>
              <div className="flex justify-between text-slate-300">
                <span className="text-slate-500">Active Service Route:</span>
                <span className="font-semibold text-emerald-400">
                  {activeSelectedBus.active_route_number ? `Route ${activeSelectedBus.active_route_number}` : (activeSelectedBus.route_number ? `Route ${activeSelectedBus.route_number}` : '—')}
                </span>
              </div>
              <div className="flex justify-between text-slate-300">
                <span className="text-slate-500">Current Occupancy:</span>
                <span className="text-slate-200">
                  {activeSelectedBus.passenger_count ?? 0} / {activeSelectedBus.capacity} passengers ({activeSelectedBus.load_factor ? `${Math.round(activeSelectedBus.load_factor * 100)}%` : '0%'})
                </span>
              </div>
            </div>

            {/* Assignment form controls */}
            <div className="space-y-3 text-xs">
              <div>
                <label className="block text-slate-300 font-semibold mb-1">
                  Select Target Route <span className="text-rose-400">*</span>
                </label>
                <select
                  value={targetRouteId}
                  onChange={(e) => setTargetRouteId(e.target.value ? Number(e.target.value) : '')}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2.5 text-slate-200 focus:outline-none focus:border-blue-500"
                >
                  <option value="">-- Choose destination route --</option>
                  {routes
                    .filter((r) => r.route_id !== (activeSelectedBus.assigned_route_id || activeSelectedBus.route_id))
                    .map((r) => (
                      <option key={r.route_id} value={r.route_id}>
                        Route {r.route_number} ({r.number_of_buses} buses currently in service)
                      </option>
                    ))}
                </select>
              </div>

              <div>
                <label className="block text-slate-300 font-semibold mb-1">Dispatcher Identity</label>
                <input
                  type="text"
                  value={dispatcherId}
                  onChange={(e) => setDispatcherId(e.target.value)}
                  placeholder="e.g. DISPATCHER-1"
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2.5 text-slate-200 focus:outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="block text-slate-300 font-semibold mb-1">
                  Operational Justification / Reason
                </label>
                <textarea
                  value={reassignReason}
                  onChange={(e) => setReassignReason(e.target.value)}
                  rows={2}
                  placeholder="e.g. Dynamic corridor demand rebalance or manual return to home route"
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2.5 text-slate-200 focus:outline-none focus:border-blue-500 resize-none"
                />
              </div>
            </div>

            {/* Movement safety notice */}
            <div className="bg-blue-950/30 border border-blue-800/60 rounded-xl p-3 text-[11px] text-blue-200 flex items-start gap-2.5">
              <span className="text-blue-400 text-sm mt-0.5">ℹ</span>
              <div>
                <span className="font-bold text-blue-300 block mb-0.5">Safety &amp; Continuous Deadheading Protocol:</span>
                <span>
                  Reassignment moves Bus {activeSelectedBus.bus_number} gradually along Coimbatore roadway geometry without coordinate teleportation. Passenger load is safely preserved. The active route automatically switches upon arrival at the target route entry stop.
                </span>
              </div>
            </div>

            {/* Modal Actions */}
            <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-800">
              <button
                type="button"
                onClick={() => setIsReassignModalOpen(false)}
                disabled={isSubmittingReassign}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg font-semibold text-xs transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleExecuteReassign}
                disabled={!targetRouteId || isSubmittingReassign}
                className="px-4 py-2 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 disabled:opacity-50 text-white rounded-lg font-bold text-xs flex items-center gap-1.5 shadow-md shadow-blue-950 transition-all"
              >
                {isSubmittingReassign ? (
                  <>
                    <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                    <span>Executing Transfer...</span>
                  </>
                ) : (
                  <>
                    <span>Confirm Reassignment</span>
                    <span>→</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
};
