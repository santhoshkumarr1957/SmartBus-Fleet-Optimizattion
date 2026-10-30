import React, { useEffect, useRef, useState, useMemo, useCallback } from 'react';
import L from 'leaflet';
import { BusLive, RouteLive, RouteIntelligence, RouteDetailed, LoadStatus } from '../types';
import { fetchRoutesDetailed, fetchLiveBuses, manualReassignBus } from '../services/api';

interface TransitMapProps {
  buses: BusLive[];
  routes: (RouteLive | RouteIntelligence)[];
  detailedRoutes?: RouteDetailed[];
  isLoading?: boolean;
  selectedBusId?: number | null;
  onSelectBus?: (busId: number | null) => void;
  onReassignmentExecuted?: () => void;
  compactView?: boolean;
}

// Corridor route colors for Coimbatore network
const ROUTE_COLORS: Record<string, string> = {
  '101': '#2563eb', // Avinashi Rd corridor (Blue)
  '202': '#10b981', // Saibaba Colony (Emerald)
  '303': '#f59e0b', // Trichy Rd (Amber)
  '404': '#8b5cf6', // Singanallur Express (Purple)
  '505': '#ec4899', // Ukkadam Direct (Pink)
  '606': '#06b6d4', // Peelamedu Shuttle (Cyan)
};

const ROUTE_NAMES: Record<string, string> = {
  '101': '101 - Avinashi Road Express',
  '202': '202 - Saibaba Colony Loop',
  '303': '303 - Trichy Road - Singanallur',
  '404': '404 - Singanallur Express',
  '505': '505 - Ukkadam Direct',
  '606': '606 - Peelamedu Shuttle',
};

// Helper to determine load status and color from bus data
function getBusLoadStatus(bus: BusLive): { status: LoadStatus; color: string; bgClass: string } {
  const lf =
    bus.load_factor ??
    (bus.capacity > 0 && bus.passenger_count !== null ? bus.passenger_count / bus.capacity : null);

  if (lf === null) {
    return { status: 'NORMAL', color: '#2563EB', bgClass: 'bg-blue-600' };
  }
  if (lf >= 1.0) {
    return { status: 'CRITICAL', color: '#EF4444', bgClass: 'bg-rose-500' };
  }
  if (lf >= 0.8) {
    return { status: 'HIGH', color: '#F59E0B', bgClass: 'bg-amber-500' };
  }
  if (lf >= 0.5) {
    return { status: 'NORMAL', color: '#2563EB', bgClass: 'bg-blue-600' };
  }
  return { status: 'LOW', color: '#10B981', bgClass: 'bg-emerald-500' };
}

// Create custom SVG marker icon for Leaflet matching the reference image
function createBusDivIcon(bus: BusLive, isSelected: boolean) {
  const { color } = getBusLoadStatus(bus);
  const size = isSelected ? 40 : 32;
  const pulseRing = isSelected
    ? `<div class="absolute -inset-1.5 rounded-full border-2 border-blue-600 animate-ping opacity-75"></div>`
    : '';

  const html = `
    <div class="relative flex items-center justify-center cursor-pointer transition-transform hover:scale-110" style="width: ${size}px; height: ${size}px;">
      ${pulseRing}
      <div class="w-full h-full rounded-full shadow-md flex items-center justify-center text-white font-bold border-2 border-white" style="background-color: ${color};">
        <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
          <path d="M4 16c0 .88.39 1.67 1 2.22V20c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-1h8v1c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-1.78c.61-.55 1-1.34 1-2.22V6c0-3.5-3.58-4-8-4s-8 .5-8 4v10zm3.5 1c-.83 0-1.5-.67-1.5-1.5S6.67 14 7.5 14s1.5.67 1.5 1.5S8.33 17 7.5 17zm9 0c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5zm1.5-6H6V6h12v5z"/>
        </svg>
      </div>
      <div class="absolute -bottom-4 bg-white text-[10px] font-bold px-1.5 py-0.2 rounded shadow-sm border border-slate-200 text-[#172033] whitespace-nowrap">
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
  selectedBusId: externalSelectedBusId,
  onSelectBus,
  onReassignmentExecuted,
  compactView = false,
}) => {
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);
  const markersLayerRef = useRef<L.LayerGroup | null>(null);
  const routesLayerRef = useRef<L.LayerGroup | null>(null);
  const markersByBusIdRef = useRef<Map<number, L.Marker>>(new Map());
  const initialFitDoneRef = useRef<boolean>(false);
  const onSelectBusRef = useRef(onSelectBus);
  onSelectBusRef.current = onSelectBus;

  // Change route preview map refs
  const modalMapContainerRef = useRef<HTMLDivElement | null>(null);
  const modalMapInstanceRef = useRef<L.Map | null>(null);

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

  // Periodic polling for fresh bus telemetry
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
        console.warn('[TransitMap] Failed to poll live bus telemetry:', err);
      } finally {
        isPolling = false;
      }
    };

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

  // Load detailed routes if not provided
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

  // Filter buses with valid GPS
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

  // Lead selected bus for detail card
  const activeSelectedBus = useMemo(() => {
    if (selectedBusId) {
      const found = busList.find((b) => b.bus_id === selectedBusId);
      if (found) return found;
    }
    return busList[0] || null;
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
        message: `Bus ${activeSelectedBus.bus_number} successfully reassigned to Route ${res.target_route_number}.`,
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

  // Contained Leaflet preview map inside Change Route modal
  useEffect(() => {
    if (!isReassignModalOpen || !modalMapContainerRef.current || !activeSelectedBus) {
      if (modalMapInstanceRef.current) {
        modalMapInstanceRef.current.remove();
        modalMapInstanceRef.current = null;
      }
      return;
    }

    const container = modalMapContainerRef.current;
    if ((container as any)._leaflet_id) {
      (container as any)._leaflet_id = null;
    }

    const busLat = activeSelectedBus.latitude || 11.0168;
    const busLon = activeSelectedBus.longitude || 76.9558;

    const modalMap = L.map(container, {
      center: [busLat, busLon],
      zoom: 13,
      zoomControl: true,
      attributionControl: false,
    });
    modalMapInstanceRef.current = modalMap;

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
    }).addTo(modalMap);

    // Plot bus marker
    const busIcon = L.divIcon({
      className: 'modal-bus-marker',
      html: `
        <div style="background-color: #2563EB; color: white; padding: 3px 8px; border-radius: 9999px; font-weight: bold; font-size: 11px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.25); border: 2px solid white; display: flex; align-items: center; gap: 4px; white-space: nowrap;">
          <span>🚌</span>
          <span>Bus ${activeSelectedBus.bus_number}</span>
        </div>
      `,
      iconSize: [84, 26],
      iconAnchor: [42, 13],
    });

    const busMarker = L.marker([busLat, busLon], { icon: busIcon }).addTo(modalMap);
    busMarker.bindPopup(
      `<strong>Bus ${activeSelectedBus.bus_number}</strong><br/>Route ${activeSelectedBus.assigned_route_number || activeSelectedBus.route_number || '—'}`
    );

    // If target route is selected, plot target corridor path and fit bounds
    if (targetRouteId && detailedRoutes.length > 0) {
      const selectedRoute = detailedRoutes.find((r) => r.id === targetRouteId);
      if (selectedRoute && selectedRoute.stops && selectedRoute.stops.length > 0) {
        const coords: [number, number][] = selectedRoute.stops.map((s) => [s.latitude, s.longitude]);
        const rColor = ROUTE_COLORS[selectedRoute.route_number] || '#2563EB';
        L.polyline(coords, {
          color: rColor,
          weight: 4,
          opacity: 0.85,
        }).addTo(modalMap);

        const bounds = L.latLngBounds([[busLat, busLon], ...coords]);
        modalMap.fitBounds(bounds, { padding: [30, 30] });
      }
    } else {
      modalMap.setView([busLat, busLon], 14);
    }

    // Invalidate size once modal layout transition completes
    const timer = setTimeout(() => {
      modalMap.invalidateSize();
    }, 150);

    return () => {
      clearTimeout(timer);
      if (modalMapInstanceRef.current) {
        modalMapInstanceRef.current.remove();
        modalMapInstanceRef.current = null;
      }
    };
  }, [isReassignModalOpen, activeSelectedBus, targetRouteId, detailedRoutes]);

  // Initialize Map centered on Coimbatore
  useEffect(() => {
    if (!mapContainerRef.current || mapInstanceRef.current) return;

    if ((mapContainerRef.current as any)._leaflet_id) {
      (mapContainerRef.current as any)._leaflet_id = null;
    }

    const initialLat = 11.007;
    const initialLon = 76.975;

    let map: L.Map | null = null;
    try {
      map = L.map(mapContainerRef.current, {
        center: [initialLat, initialLon],
        zoom: 13,
        zoomControl: true,
        attributionControl: false,
      });

      // Free OpenStreetMap light tiles
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; OpenStreetMap contributors',
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
    }, 200);

    return () => {
      clearTimeout(resizeTimer1);
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

  // Render route paths and stop markers
  useEffect(() => {
    const map = mapInstanceRef.current;
    const routesLayer = routesLayerRef.current;
    if (!map || !routesLayer || !mapReady) return;

    routesLayer.clearLayers();

    detailedRoutes.forEach((route) => {
      if (filterRoute !== 'ALL' && filterRoute !== route.route_number) {
        return;
      }

      const color = ROUTE_COLORS[route.route_number] || '#2563eb';
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

      if (validStops.length < 2) return;

      const latlngs: [number, number][] = validStops.map((s) => [s.latitude, s.longitude]);

      const polyline = L.polyline(latlngs, {
        color,
        weight: 4,
        opacity: 0.85,
        lineJoin: 'round',
      }).addTo(routesLayer);

      polyline.bindTooltip(
        `<strong>Route ${route.route_number}</strong>: ${route.name}`,
        { sticky: true }
      );

      validStops.forEach((stop, idx) => {
        const isTerminus = idx === 0 || idx === validStops.length - 1;
        const circleMarker = L.circleMarker([stop.latitude, stop.longitude], {
          radius: isTerminus ? 5 : 3.5,
          color: '#ffffff',
          weight: 2,
          fillColor: color,
          fillOpacity: 0.9,
        }).addTo(routesLayer);

        circleMarker.bindTooltip(
          `Stop ${stop.sequence_order}: ${stop.name} (Route ${route.route_number})`,
          { direction: 'top', offset: [0, -4] }
        );
      });
    });
  }, [detailedRoutes, mapReady, filterRoute]);

  // Update bus markers with animated telemetry
  useEffect(() => {
    const map = mapInstanceRef.current;
    const markersLayer = markersLayerRef.current;
    if (!map || !markersLayer || !mapReady) return;

    const markersMap = markersByBusIdRef.current;
    const currentBusIds = new Set(validGpsBuses.map((b) => b.bus_id));

    markersMap.forEach((marker, busId) => {
      if (!currentBusIds.has(busId)) {
        markersLayer.removeLayer(marker);
        markersMap.delete(busId);
      }
    });

    validGpsBuses.forEach((bus) => {
      const isSelected = selectedBusId === bus.bus_id;
      const icon = createBusDivIcon(bus, isSelected);
      const lat = bus.latitude!;
      const lon = bus.longitude!;

      if (markersMap.has(bus.bus_id)) {
        const marker = markersMap.get(bus.bus_id)!;
        marker.setLatLng([lat, lon]);
        marker.setIcon(icon);
      } else {
        const marker = L.marker([lat, lon], { icon }).addTo(markersLayer);
        marker.on('click', () => {
          handleSelectBus(bus.bus_id);
        });
        marker.bindTooltip(
          `<div class="font-sans text-xs">
            <strong>Bus ${bus.bus_number}</strong> • Route ${bus.route_number}<br/>
            Speed: ${Math.round(bus.speed || 0)} km/h • Load: ${Math.round(
            (bus.load_factor ?? 0) * 100
          )}%
          </div>`,
          { direction: 'top', offset: [0, -18] }
        );
        markersMap.set(bus.bus_id, marker);
      }
    });

    if (!initialFitDoneRef.current && validGpsBuses.length > 0) {
      initialFitDoneRef.current = true;
      const bounds = L.latLngBounds(validGpsBuses.map((b) => [b.latitude!, b.longitude!]));
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 });
    }
  }, [validGpsBuses, selectedBusId, mapReady, handleSelectBus]);

  const fitAllBuses = useCallback(() => {
    const map = mapInstanceRef.current;
    if (!map || validGpsBuses.length === 0) return;
    const bounds = L.latLngBounds(validGpsBuses.map((b) => [b.latitude!, b.longitude!]));
    map.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 });
  }, [validGpsBuses]);

  const assignedRouteName = activeSelectedBus
    ? ROUTE_NAMES[activeSelectedBus.route_number || ''] || `Route ${activeSelectedBus.route_number}`
    : 'Route 101 - Avinashi Road Express';

  const busLoadFactorPct = activeSelectedBus
    ? Math.round(
        (activeSelectedBus.load_factor ??
          (activeSelectedBus.capacity > 0 && activeSelectedBus.passenger_count !== null
            ? activeSelectedBus.passenger_count / activeSelectedBus.capacity
            : 0.62)) * 100
      )
    : 62;

  // Render Compact View (for Overview tab)
  if (compactView) {
    return (
      <div className="relative w-full h-full min-h-[460px] rounded-xl overflow-hidden border border-[#E2E8F0]">
        <div ref={mapContainerRef} className="w-full h-full" />

        <div className="absolute bottom-3 left-3 z-20 bg-white/95 backdrop-blur-sm border border-[#E2E8F0] rounded-xl p-2.5 shadow-sm text-xs">
          <div className="flex items-center gap-3 text-[11px] font-semibold">
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500"></span>
              <span className="text-slate-700">Low Load</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-blue-600"></span>
              <span className="text-slate-700">Normal Load</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-amber-500"></span>
              <span className="text-slate-700">High Load</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-rose-500"></span>
              <span className="text-slate-700">Critical Load</span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Full Page 2 Live Transit Map View
  return (
    <section className="space-y-4">
      {/* Header matching reference image */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-[#172033] tracking-tight">Live Transit Map</h1>
          <p className="text-xs text-[#64748B]">
            Real-time geospatial fleet positioning with live load factor telemetry
          </p>
        </div>

        {/* Top Right Controls */}
        <div className="flex items-center gap-2 self-start sm:self-auto">
          <select
            value={filterRoute}
            onChange={(e) => setFilterRoute(e.target.value)}
            className="bg-white text-[#172033] text-xs font-semibold rounded-lg px-3 py-2 border border-[#E2E8F0] shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
          >
            <option value="ALL">All Routes ({routes.length > 0 ? routes.length : 6})</option>
            {routes.map((r) => (
              <option key={r.route_id} value={r.route_number}>
                Route {r.route_number} ({r.number_of_buses} buses)
              </option>
            ))}
          </select>

          <button
            onClick={fitAllBuses}
            className="px-3.5 py-2 bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold rounded-lg shadow-sm flex items-center gap-1.5 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"
              />
            </svg>
            <span>Fit Fleet</span>
          </button>
        </div>
      </div>

      {reassignFeedback && (
        <div
          className={`p-3 rounded-xl border text-xs flex items-center justify-between shadow-sm ${
            reassignFeedback.type === 'success'
              ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
              : 'bg-rose-50 border-rose-200 text-rose-800'
          }`}
        >
          <span>{reassignFeedback.message}</span>
          <button onClick={() => setReassignFeedback(null)} className="text-xs opacity-60 hover:opacity-100">
            ✕
          </button>
        </div>
      )}

      {/* Main 2-Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-8 bg-white border border-[#E2E8F0] rounded-xl overflow-hidden shadow-sm flex flex-col min-h-[580px]">
          <div className="flex-1 relative w-full h-full min-h-[520px]">
            <div ref={mapContainerRef} className="w-full h-full" />
          </div>

          <div className="p-3 border-t border-[#E2E8F0] bg-white flex items-center justify-between gap-2 overflow-x-auto">
            {['101', '202', '303', '404', '505', '606'].map((rNum) => {
              const color = ROUTE_COLORS[rNum];
              const isFiltered = filterRoute === rNum;
              return (
                <button
                  key={rNum}
                  onClick={() => setFilterRoute(filterRoute === rNum ? 'ALL' : rNum)}
                  className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-semibold border transition-all whitespace-nowrap ${
                    isFiltered
                      ? 'bg-blue-50 text-blue-700 border-blue-300 shadow-sm'
                      : 'bg-slate-50 text-slate-700 border-[#E2E8F0] hover:bg-slate-100'
                  }`}
                >
                  <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: color }}></span>
                  <span>Route {rNum}</span>
                </button>
              );
            })}
          </div>
        </div>

        <div className="lg:col-span-4 flex flex-col space-y-4">
          <div className="bg-white border border-[#E2E8F0] rounded-xl p-4 shadow-sm flex-1 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between pb-3 border-b border-[#E2E8F0]">
                <h3 className="text-sm font-bold text-[#172033] tracking-tight">Selected Vehicle</h3>
                {activeSelectedBus && (
                  <button
                    onClick={() => handleSelectBus(null)}
                    className="text-xs text-slate-400 hover:text-slate-600"
                    title="Clear selection"
                  >
                    ✕
                  </button>
                )}
              </div>

              {activeSelectedBus ? (
                <div className="mt-4 space-y-3.5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className="w-8 h-8 rounded-lg bg-blue-600 text-white flex items-center justify-center font-bold text-xs">
                        🚌
                      </div>
                      <span className="text-base font-extrabold text-[#172033]">
                        Bus {activeSelectedBus.bus_number}
                      </span>
                    </div>
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
                      In Service
                    </span>
                  </div>

                  <div className="w-full h-36 rounded-xl overflow-hidden border border-[#E2E8F0] bg-slate-100 shadow-inner">
                    <img
                      src="/bus-model.jpg"
                      alt={`Bus ${activeSelectedBus.bus_number}`}
                      className="w-full h-full object-cover"
                    />
                  </div>

                  <div className="space-y-2 text-xs pt-1">
                    <div className="flex justify-between items-center py-1 border-b border-slate-100">
                      <span className="text-[#64748B] font-medium">Route</span>
                      <span className="font-bold text-[#172033]">{assignedRouteName}</span>
                    </div>

                    <div className="flex justify-between items-center py-1 border-b border-slate-100">
                      <span className="text-[#64748B] font-medium">Current Stop</span>
                      <span className="font-semibold text-[#172033]">Rathinapuri</span>
                    </div>

                    <div className="flex justify-between items-center py-1 border-b border-slate-100">
                      <span className="text-[#64748B] font-medium">Speed</span>
                      <span className="font-semibold text-[#172033]">
                        {Math.round(activeSelectedBus.speed || 28)} km/h
                      </span>
                    </div>

                    <div className="flex justify-between items-center py-1 border-b border-slate-100">
                      <span className="text-[#64748B] font-medium">Passenger Load</span>
                      <span className="font-semibold text-[#172033]">
                        {activeSelectedBus.passenger_count || 111} / {activeSelectedBus.capacity || 180}
                      </span>
                    </div>

                    <div className="py-1 border-b border-slate-100">
                      <div className="flex justify-between items-center mb-1">
                        <span className="text-[#64748B] font-medium">Load Factor</span>
                        <span className="font-bold text-blue-600">{busLoadFactorPct}%</span>
                      </div>
                      <div className="w-full bg-slate-100 rounded-full h-2 overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all duration-300 ${
                            busLoadFactorPct >= 100
                              ? 'bg-rose-500'
                              : busLoadFactorPct >= 80
                              ? 'bg-amber-500'
                              : 'bg-blue-600'
                          }`}
                          style={{ width: `${Math.min(100, busLoadFactorPct)}%` }}
                        />
                      </div>
                    </div>

                    <div className="flex justify-between items-center py-1 border-b border-slate-100">
                      <span className="text-[#64748B] font-medium">Next Stop</span>
                      <span className="font-semibold text-[#172033]">PN Palayam (2 min)</span>
                    </div>

                    <div className="flex justify-between items-center py-1">
                      <span className="text-[#64748B] font-medium">Status</span>
                      <span className="font-bold text-emerald-600">On Time</span>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="py-12 text-center text-xs text-[#64748B]">
                  Click any bus marker on the map to inspect live load and kinematic telemetry.
                </div>
              )}
            </div>

            {activeSelectedBus && (
              <div className="mt-4 pt-3 border-t border-[#E2E8F0]">
                <button
                  onClick={() => {
                    setTargetRouteId('');
                    setReassignReason('');
                    setReassignFeedback(null);
                    setIsReassignModalOpen(true);
                  }}
                  disabled={activeSelectedBus.is_transferring}
                  className="w-full py-2 px-3 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-semibold text-xs shadow-sm transition-colors flex items-center justify-center gap-2"
                >
                  <span>🔄</span>
                  <span>Change Route</span>
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Manual Route Assignment Modal Dialog */}
      {isReassignModalOpen && activeSelectedBus && (
        <div
          className="fixed inset-0 z-[9999] flex items-center justify-center p-3 sm:p-4 bg-slate-900/60 backdrop-blur-sm overflow-y-auto animate-fade-in"
          onClick={(e) => {
            if (e.target === e.currentTarget) setIsReassignModalOpen(false);
          }}
        >
          <div className="max-w-xl w-full bg-white border border-[#E2E8F0] rounded-2xl shadow-2xl overflow-hidden flex flex-col my-auto max-h-[92vh]">
            {/* Modal Header */}
            <div className="flex items-center justify-between px-5 py-3.5 border-b border-[#E2E8F0] bg-white sticky top-0 z-10">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center text-sm font-bold border border-blue-100">
                  🔄
                </div>
                <div>
                  <h3 className="text-sm font-bold text-[#172033]">
                    Manual Route Assignment — Bus {activeSelectedBus.bus_number}
                  </h3>
                  <p className="text-[11px] text-[#64748B]">
                    Reassign vehicle corridor with continuous deadheading
                  </p>
                </div>
              </div>
              <button
                onClick={() => setIsReassignModalOpen(false)}
                className="text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-lg p-1.5 transition-colors"
                title="Close modal"
              >
                ✕
              </button>
            </div>

            {/* Modal Scrollable Body */}
            <div className="p-5 space-y-4 overflow-y-auto flex-1">
              {/* Vehicle Context Cards */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                <div className="p-2.5 rounded-lg bg-slate-50 border border-[#E2E8F0]">
                  <span className="text-[10px] uppercase font-semibold text-[#64748B] block">Home Route</span>
                  <span className="font-bold text-[#172033]">
                    {activeSelectedBus.home_route_number ? `Route ${activeSelectedBus.home_route_number}` : '—'}
                  </span>
                </div>
                <div className="p-2.5 rounded-lg bg-slate-50 border border-[#E2E8F0]">
                  <span className="text-[10px] uppercase font-semibold text-[#64748B] block">Current Assigned</span>
                  <span className="font-bold text-blue-600">
                    Route {activeSelectedBus.assigned_route_number || activeSelectedBus.route_number || '—'}
                  </span>
                </div>
                <div className="p-2.5 rounded-lg bg-slate-50 border border-[#E2E8F0]">
                  <span className="text-[10px] uppercase font-semibold text-[#64748B] block">Active Service</span>
                  <span className="font-bold text-emerald-600">
                    Route {activeSelectedBus.active_route_number || activeSelectedBus.route_number || '—'}
                  </span>
                </div>
                <div className="p-2.5 rounded-lg bg-slate-50 border border-[#E2E8F0]">
                  <span className="text-[10px] uppercase font-semibold text-[#64748B] block">Passengers</span>
                  <span className="font-bold text-[#172033]">
                    {activeSelectedBus.passenger_count ?? 0} / {activeSelectedBus.capacity}
                  </span>
                </div>
              </div>

              {/* Contained Modal Map Container */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold text-[#172033]">Corridor Geographic Preview</span>
                  <span className="text-[11px] text-[#64748B]">
                    {targetRouteId ? 'Target corridor highlighted' : 'Bus current position'}
                  </span>
                </div>
                <div
                  ref={modalMapContainerRef}
                  className="w-full h-44 sm:h-52 rounded-xl overflow-hidden border border-[#E2E8F0] relative shadow-inner bg-slate-100"
                  style={{ zIndex: 1 }}
                />
              </div>

              {/* Assignment Form Controls */}
              <div className="space-y-3 text-xs">
                <div>
                  <label className="block text-[#172033] font-semibold mb-1">
                    Select Target Route <span className="text-rose-500">*</span>
                  </label>
                  <select
                    value={targetRouteId}
                    onChange={(e) => setTargetRouteId(e.target.value ? Number(e.target.value) : '')}
                    className="w-full bg-slate-50 border border-[#E2E8F0] rounded-lg p-2.5 text-[#172033] focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 font-medium"
                  >
                    <option value="">-- Choose destination corridor --</option>
                    {routes
                      .filter((r) => r.route_id !== (activeSelectedBus.assigned_route_id || activeSelectedBus.route_id))
                      .map((r) => (
                        <option key={r.route_id} value={r.route_id}>
                          Route {r.route_number} ({r.number_of_buses} buses currently in service)
                        </option>
                      ))}
                  </select>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-[#172033] font-semibold mb-1">Dispatcher Identity</label>
                    <input
                      type="text"
                      value={dispatcherId}
                      onChange={(e) => setDispatcherId(e.target.value)}
                      placeholder="e.g. DISPATCHER-1"
                      className="w-full bg-slate-50 border border-[#E2E8F0] rounded-lg p-2 text-[#172033] focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
                    />
                  </div>

                  <div>
                    <label className="block text-[#172033] font-semibold mb-1">
                      Reason / Justification
                    </label>
                    <input
                      type="text"
                      value={reassignReason}
                      onChange={(e) => setReassignReason(e.target.value)}
                      placeholder="e.g. Demand rebalance"
                      className="w-full bg-slate-50 border border-[#E2E8F0] rounded-lg p-2 text-[#172033] focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
                    />
                  </div>
                </div>

                {/* Safety Protocol Note */}
                <div className="p-2.5 rounded-lg bg-blue-50 border border-blue-200 text-[11px] text-blue-900 flex items-start gap-2">
                  <span className="text-blue-600 font-bold mt-0.5">ℹ</span>
                  <div className="leading-tight">
                    <strong>Safety &amp; Kinematic Deadheading Protocol:</strong> Reassignment transfers Bus {activeSelectedBus.bus_number} gradually along roadway geometry without teleportation. Passenger load is preserved and reassignment is committed to authoritative backend telemetry.
                  </div>
                </div>
              </div>
            </div>

            {/* Modal Actions */}
            <div className="flex items-center justify-end gap-2.5 px-5 py-3 border-t border-[#E2E8F0] bg-slate-50 sticky bottom-0 z-10">
              <button
                type="button"
                onClick={() => setIsReassignModalOpen(false)}
                disabled={isSubmittingReassign}
                className="px-4 py-2 bg-white hover:bg-slate-100 border border-[#E2E8F0] text-slate-700 rounded-lg font-semibold text-xs transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleExecuteReassign}
                disabled={!targetRouteId || isSubmittingReassign}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg font-bold text-xs flex items-center gap-1.5 shadow-sm transition-all"
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
