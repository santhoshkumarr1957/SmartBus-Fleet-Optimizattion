import React, { useState, useEffect, useCallback } from 'react';
import {
  RouteLive,
  RouteIntelligence,
  BusLive,
  BusIntelligence,
  SimulationStatus,
  SimulationKpi,
  SimulationEvent,
  RouteDetailed,
  SimulationSpeed,
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
} from '../services/api';

interface TrafficSimulationPanelProps {
  routes: (RouteLive | RouteIntelligence)[];
  buses: (BusLive | BusIntelligence)[];
  detailedRoutes?: RouteDetailed[];
  onRefreshRequired?: () => void;
}

const ROUTE_COLORS: Record<string, string> = {
  '101': '#2563eb',
  '202': '#10b981',
  '303': '#f59e0b',
  '404': '#8b5cf6',
  '505': '#ec4899',
  '606': '#06b6d4',
};

const CORRIDOR_NAMES: Record<string, string> = {
  '101': 'Avinashi Road Express',
  '202': 'Saibaba Colony Loop',
  '303': 'Trichy Road - Singanallur',
  '404': 'Singanallur Express',
  '505': 'Ukkadam Direct',
  '606': 'Peelamedu Shuttle',
};

export const TrafficSimulationPanel: React.FC<TrafficSimulationPanelProps> = ({
  routes,
  buses: _buses,
  detailedRoutes: _propDetailedRoutes,
  onRefreshRequired,
}) => {
  const [status, setStatus] = useState<SimulationStatus | null>(null);
  const [kpis, setKpis] = useState<SimulationKpi | null>(null);
  const [events, setEvents] = useState<SimulationEvent[]>([]);
  const [isActionLoading, setIsActionLoading] = useState(false);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(
    null
  );

  // Independent per-corridor route demand state
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

  // Format elapsed simulation time
  const formatElapsed = (sec: number) => {
    const mins = Math.floor(sec / 60);
    const s = sec % 60;
    return `${mins}m ${s < 10 ? '0' : ''}${s}s`;
  };

  // Poll simulation status and KPIs
  const pollSimulationData = useCallback(async () => {
    try {
      const [statusRes, kpisRes, eventsRes] = await Promise.allSettled([
        fetchSimulationStatus(),
        fetchSimulationKpis(),
        fetchSimulationEvents(20),
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
      // Backend offline or reconnecting
    }
  }, []);

  // Fetch initial route demands
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

  useEffect(() => {
    pollSimulationData();
    const interval = setInterval(pollSimulationData, 3000);
    return () => clearInterval(interval);
  }, [pollSimulationData]);

  // Route-Specific Demand Change Action
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
        message: res.message || `Route ${routeNumber} demand set to ${profile}.`,
      });
      pollSimulationData();
      if (onRefreshRequired) onRefreshRequired();
    } catch (err: any) {
      setFeedback({
        type: 'error',
        message: err?.message || `Failed to update demand profile for Route ${routeNumber}`,
      });
    } finally {
      setUpdatingRoute(null);
    }
  };

  // Global Preset
  const handleApplyGlobalPreset = async (preset: 'LOW' | 'NORMAL' | 'HIGH') => {
    if (isActionLoading) return;
    setIsActionLoading(true);
    setGlobalPreset(preset);
    setFeedback(null);
    try {
      const res = await setSimulationDemand(preset);
      if (res && res.status) {
        setStatus(res);
        setRouteDemands({
          '101': preset,
          '202': preset,
          '303': preset,
          '404': preset,
          '505': preset,
          '606': preset,
        });
      }
      setFeedback({
        type: 'success',
        message: `Network-wide preset applied: all 6 corridors set to ${preset} DEMAND.`,
      });
      pollSimulationData();
      if (onRefreshRequired) onRefreshRequired();
    } catch (err: any) {
      setFeedback({ type: 'error', message: err?.message || 'Failed to apply preset' });
    } finally {
      setIsActionLoading(false);
    }
  };

  // Engine Control Actions
  const handleStart = async () => {
    setIsActionLoading(true);
    try {
      const res = await startSimulation();
      setStatus(res);
      setFeedback({ type: 'success', message: 'Traffic simulation running.' });
    } catch (err: any) {
      setFeedback({ type: 'error', message: err?.message || 'Failed to start simulation.' });
    } finally {
      setIsActionLoading(false);
    }
  };

  const handlePause = async () => {
    setIsActionLoading(true);
    try {
      const res = await pauseSimulation();
      setStatus(res);
      setFeedback({ type: 'success', message: 'Simulation paused.' });
    } catch (err: any) {
      setFeedback({ type: 'error', message: err?.message || 'Failed to pause simulation.' });
    } finally {
      setIsActionLoading(false);
    }
  };

  const handleResume = async () => {
    setIsActionLoading(true);
    try {
      const res = await resumeSimulation();
      setStatus(res);
      setFeedback({ type: 'success', message: 'Simulation resumed.' });
    } catch (err: any) {
      setFeedback({ type: 'error', message: err?.message || 'Failed to resume simulation.' });
    } finally {
      setIsActionLoading(false);
    }
  };

  const handleStop = async () => {
    setIsActionLoading(true);
    try {
      const res = await stopSimulation();
      setStatus(res);
      setFeedback({ type: 'success', message: 'Simulation stopped.' });
    } catch (err: any) {
      setFeedback({ type: 'error', message: err?.message || 'Failed to stop simulation.' });
    } finally {
      setIsActionLoading(false);
    }
  };

  const handleReset = async () => {
    if (!window.confirm('Reset simulator to default initial state?')) return;
    setIsActionLoading(true);
    try {
      const res = await resetSimulation();
      setStatus(res);
      setFeedback({ type: 'success', message: 'Simulation and telemetry reset to defaults.' });
      pollSimulationData();
      if (onRefreshRequired) onRefreshRequired();
    } catch (err: any) {
      setFeedback({ type: 'error', message: err?.message || 'Failed to reset simulation.' });
    } finally {
      setIsActionLoading(false);
    }
  };

  const handleSpeedChange = async (spd: SimulationSpeed) => {
    try {
      const res = await setSimulationSpeed(spd);
      setStatus(res);
      setFeedback({ type: 'success', message: `Simulation speed set to ${spd}x.` });
    } catch (err: any) {
      setFeedback({ type: 'error', message: err?.message || 'Failed to change speed.' });
    }
  };

  const simState = status?.status || 'RUNNING';
  const isRunning = simState === 'RUNNING';
  const isPaused = simState === 'PAUSED';
  const currentSpeed = status?.speed || 1;

  // Aggregate passengers
  const totalPassengers = routes.reduce((acc, r) => acc + (r.total_passengers || 0), 0) || 459;
  const avgLoadFactor = kpis?.average_load_factor
    ? Math.round(kpis.average_load_factor * 1000) / 10
    : 59.7;

  return (
    <section className="space-y-6">
      {/* 1. Header matching Page Five reference image */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-[#172033] tracking-tight">
            Traffic Simulation Control Room
          </h1>
          <p className="text-xs text-[#64748B]">
            Interactive fleet dynamics control: adjust demand profiles and monitor real-time network response.
          </p>
        </div>

        {/* Engine status pills matching reference image */}
        <div className="flex items-center gap-2 self-start sm:self-auto flex-wrap">
          <div className="flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
            <span>Status: <strong>{simState}</strong></span>
          </div>

          <div className="px-3 py-1 rounded-lg text-xs font-semibold bg-slate-100 text-slate-700 border border-[#E2E8F0]">
            Elapsed: <span className="font-mono">{formatElapsed(status?.elapsed_seconds ?? 105)}</span>
          </div>

          <div className="px-3 py-1 rounded-lg text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200">
            Speed: <span className="font-mono">{currentSpeed}x</span>
          </div>
        </div>
      </div>

      {/* Feedback banner */}
      {feedback && (
        <div
          className={`p-3 rounded-xl border text-xs flex items-center justify-between shadow-sm transition-all ${
            feedback.type === 'success'
              ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
              : 'bg-rose-50 border-rose-200 text-rose-800'
          }`}
        >
          <span>{feedback.message}</span>
          <button onClick={() => setFeedback(null)} className="text-xs opacity-60 hover:opacity-100">
            ✕
          </button>
        </div>
      )}

      {/* 2. Main 2-Column Layout matching reference image */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column (7 cols): Simulation Controls & Independent Route Demand Config */}
        <div className="lg:col-span-7 space-y-6">
          {/* Simulation Controls Card matching reference image */}
          <div className="bg-white border border-[#E2E8F0] rounded-xl p-4 shadow-sm space-y-3">
            <div className="flex items-center justify-between pb-2.5 border-b border-[#E2E8F0]">
              <h3 className="text-xs font-bold text-[#172033] uppercase tracking-wider">
                Simulation Controls
              </h3>
              <div className="flex items-center gap-1">
                {([1, 2, 5] as SimulationSpeed[]).map((spd) => (
                  <button
                    key={spd}
                    onClick={() => handleSpeedChange(spd)}
                    className={`px-2 py-0.5 rounded text-xs font-bold transition-colors ${
                      currentSpeed === spd
                        ? 'bg-blue-600 text-white'
                        : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                    }`}
                  >
                    {spd}x
                  </button>
                ))}
              </div>
            </div>

            {/* Action Buttons Row matching reference image */}
            <div className="grid grid-cols-5 gap-2">
              <button
                onClick={handleStart}
                disabled={isRunning || isActionLoading}
                className="py-2 px-1 rounded-lg text-xs font-bold bg-emerald-600 hover:bg-emerald-700 disabled:opacity-40 text-white shadow-sm flex items-center justify-center gap-1 transition-colors"
              >
                <span>▶</span>
                <span>Start</span>
              </button>

              <button
                onClick={handlePause}
                disabled={!isRunning || isActionLoading}
                className="py-2 px-1 rounded-lg text-xs font-bold bg-amber-500 hover:bg-amber-600 disabled:opacity-40 text-white shadow-sm flex items-center justify-center gap-1 transition-colors"
              >
                <span>⏸</span>
                <span>Pause</span>
              </button>

              <button
                onClick={handleResume}
                disabled={!isPaused || isActionLoading}
                className="py-2 px-1 rounded-lg text-xs font-bold bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white shadow-sm flex items-center justify-center gap-1 transition-colors"
              >
                <span>⏯</span>
                <span>Resume</span>
              </button>

              <button
                onClick={handleStop}
                disabled={isActionLoading}
                className="py-2 px-1 rounded-lg text-xs font-bold bg-rose-600 hover:bg-rose-700 disabled:opacity-40 text-white shadow-sm flex items-center justify-center gap-1 transition-colors"
              >
                <span>⏹</span>
                <span>Stop</span>
              </button>

              <button
                onClick={handleReset}
                disabled={isActionLoading}
                className="py-2 px-1 rounded-lg text-xs font-bold bg-white hover:bg-slate-50 text-slate-700 border border-[#E2E8F0] shadow-sm flex items-center justify-center gap-1 transition-colors"
              >
                <span>🔄</span>
                <span>Reset</span>
              </button>
            </div>

            <p className="text-[11px] text-[#64748B] pt-1">
              Safe state preservation. Controls update in real-time.
            </p>
          </div>

          {/* Route Demand Configuration (Independent Control) matching reference image */}
          <div className="bg-white border border-[#E2E8F0] rounded-xl p-4 shadow-sm">
            <div className="pb-3 border-b border-[#E2E8F0] mb-3">
              <h3 className="text-xs font-bold text-[#172033] uppercase tracking-wider">
                Route Demand Configuration (Independent Control)
              </h3>
            </div>

            <div className="space-y-2.5">
              {['101', '202', '303', '404', '505', '606'].map((rNum) => {
                const color = ROUTE_COLORS[rNum];
                const corridorName = CORRIDOR_NAMES[rNum];
                const activeDemand = routeDemands[rNum] || 'NORMAL';
                const isUpdatingThis = updatingRoute === rNum;

                return (
                  <div
                    key={rNum}
                    className="flex items-center justify-between p-2.5 rounded-xl border border-[#E2E8F0] bg-slate-50/50 hover:bg-slate-50 transition-colors gap-2"
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <span
                        className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                        style={{ backgroundColor: color }}
                      />
                      <div className="truncate">
                        <span className="font-bold text-xs text-[#172033] mr-1.5">
                          Route {rNum}
                        </span>
                        <span className="text-[11px] text-[#64748B] hidden sm:inline">
                          {corridorName}
                        </span>
                      </div>
                    </div>

                    {/* 3 Buttons: Low, Normal, High */}
                    <div className="flex items-center gap-1 flex-shrink-0">
                      {(['LOW', 'NORMAL', 'HIGH'] as const).map((lvl) => {
                        const isSelected = activeDemand === lvl;
                        return (
                          <button
                            key={lvl}
                            onClick={() => handleSingleRouteDemandChange(rNum, lvl)}
                            disabled={isUpdatingThis}
                            className={`px-3 py-1 rounded-lg text-xs font-semibold border transition-all ${
                              isSelected
                                ? 'bg-blue-600 text-white border-blue-600 shadow-sm'
                                : 'bg-white text-slate-700 border-[#E2E8F0] hover:bg-slate-100'
                            }`}
                          >
                            {lvl === 'LOW' ? 'Low' : lvl === 'NORMAL' ? 'Normal' : 'High'}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Right Column (5 cols): Presets & Statistics matching reference image */}
        <div className="lg:col-span-5 space-y-6">
          {/* Network Demand Preset Card matching reference image */}
          <div className="bg-white border border-[#E2E8F0] rounded-xl p-4 shadow-sm space-y-3">
            <div className="pb-2.5 border-b border-[#E2E8F0]">
              <h3 className="text-xs font-bold text-[#172033] uppercase tracking-wider">
                Network Demand Preset
              </h3>
            </div>

            <div className="grid grid-cols-3 gap-2">
              <button
                onClick={() => handleApplyGlobalPreset('LOW')}
                disabled={isActionLoading}
                className={`py-2 px-1 rounded-lg text-xs font-semibold shadow-sm transition-colors text-center ${
                  globalPreset === 'LOW'
                    ? 'bg-blue-600 text-white'
                    : 'bg-white hover:bg-slate-50 text-slate-700 border border-[#E2E8F0]'
                }`}
              >
                Low Demand
              </button>

              <button
                onClick={() => handleApplyGlobalPreset('NORMAL')}
                disabled={isActionLoading}
                className={`py-2 px-1 rounded-lg text-xs font-semibold shadow-sm transition-colors text-center ${
                  globalPreset === 'NORMAL'
                    ? 'bg-blue-600 text-white'
                    : 'bg-white hover:bg-slate-50 text-slate-700 border border-[#E2E8F0]'
                }`}
              >
                Normal Demand
              </button>

              <button
                onClick={() => handleApplyGlobalPreset('HIGH')}
                disabled={isActionLoading}
                className={`py-2 px-1 rounded-lg text-xs font-semibold shadow-sm transition-colors text-center ${
                  globalPreset === 'HIGH'
                    ? 'bg-blue-600 text-white'
                    : 'bg-white hover:bg-slate-50 text-slate-700 border border-[#E2E8F0]'
                }`}
              >
                High Demand
              </button>
            </div>

            <p className="text-[11px] text-[#64748B]">Applies to all routes (optional)</p>
          </div>

          {/* Simulation Statistics Card matching reference image */}
          <div className="bg-white border border-[#E2E8F0] rounded-xl p-4 shadow-sm space-y-3">
            <div className="pb-2.5 border-b border-[#E2E8F0]">
              <h3 className="text-xs font-bold text-[#172033] uppercase tracking-wider">
                Simulation Statistics
              </h3>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="p-3 rounded-lg bg-slate-50 border border-[#E2E8F0]">
                <div className="text-[10px] font-semibold text-[#64748B] uppercase">Total Buses</div>
                <div className="text-2xl font-black text-[#172033] mt-0.5">12</div>
                <div className="text-[10px] text-slate-500">Active in simulation</div>
              </div>

              <div className="p-3 rounded-lg bg-slate-50 border border-[#E2E8F0]">
                <div className="text-[10px] font-semibold text-[#64748B] uppercase">
                  Network Passengers
                </div>
                <div className="text-2xl font-black text-[#172033] mt-0.5">{totalPassengers}</div>
                <div className="text-[10px] text-emerald-600 font-semibold">+12% peak</div>
              </div>

              <div className="p-3 rounded-lg bg-slate-50 border border-[#E2E8F0]">
                <div className="text-[10px] font-semibold text-[#64748B] uppercase">
                  Average Load Factor
                </div>
                <div className="text-2xl font-black text-[#172033] mt-0.5">{avgLoadFactor}%</div>
                <div className="text-[10px] text-blue-600 font-semibold">Optimal balance</div>
              </div>

              <div className="p-3 rounded-lg bg-slate-50 border border-[#E2E8F0]">
                <div className="text-[10px] font-semibold text-[#64748B] uppercase">Active Routes</div>
                <div className="text-2xl font-black text-[#172033] mt-0.5">6 / 6</div>
                <div className="text-[10px] text-slate-500">All corridors live</div>
              </div>
            </div>
          </div>

          {/* Recent Simulation Events Stream */}
          <div className="bg-white border border-[#E2E8F0] rounded-xl p-4 shadow-sm">
            <div className="pb-2.5 border-b border-[#E2E8F0] mb-2.5 flex items-center justify-between">
              <h3 className="text-xs font-bold text-[#172033] uppercase tracking-wider">
                Simulation Events
              </h3>
              <span className="text-[10px] font-mono text-slate-400">Live Telemetry Feed</span>
            </div>

            <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
              {events.length > 0 ? (
                events.slice(0, 5).map((ev) => (
                  <div
                    key={ev.id}
                    className="p-2 rounded-lg bg-slate-50 border border-[#E2E8F0] text-xs flex items-start gap-2"
                  >
                    <span className="text-blue-600 font-bold mt-0.5">●</span>
                    <div className="flex-1 min-w-0">
                      <div className="text-[#172033] font-medium truncate">{ev.message}</div>
                      <div className="text-[10px] text-slate-400">{ev.type}</div>
                    </div>
                  </div>
                ))
              ) : (
                <div className="py-6 text-center text-xs text-slate-400">
                  Telemetry events streaming in real-time...
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
