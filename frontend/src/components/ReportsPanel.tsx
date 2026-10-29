import React, { useState, useEffect, useMemo } from 'react';
import {
  ReportsOverview,
  FleetUtilizationReport,
  RoutePerformanceReport,
  DisruptionReport,
  TrendsReport,
} from '../types';
import {
  fetchReportsOverview,
  fetchTrendsReport,
  downloadReportCsv,
} from '../services/api';

type ReportSection = 'overview' | 'fleet' | 'routes' | 'trends' | 'disruptions' | 'reallocation';

export const ReportsPanel: React.FC = () => {
  const [activeSection, setActiveSection] = useState<ReportSection>('overview');
  const [overview, setOverview] = useState<ReportsOverview | null>(null);
  const [trends, setTrends] = useState<TrendsReport | null>(null);
  const [trendRange, setTrendRange] = useState<'1h' | '24h' | '7d'>('24h');
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isExporting, setIsExporting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [successBanner, setSuccessBanner] = useState<string | null>(null);

  // Search filter inside tables
  const [searchQuery, setSearchQuery] = useState<string>('');

  // Load initial data
  const loadData = async (quiet: boolean = false) => {
    if (!quiet) setIsLoading(true);
    setError(null);
    try {
      const [ovData, trendData] = await Promise.all([
        fetchReportsOverview(),
        fetchTrendsReport(trendRange),
      ]);
      setOverview(ovData);
      setTrends(trendData);
    } catch (err: any) {
      setError(err?.message || 'Failed to load transit reports and performance analytics');
    } finally {
      if (!quiet) setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  // Handle changing trend range
  const handleRangeChange = async (range: '1h' | '24h' | '7d') => {
    setTrendRange(range);
    try {
      const data = await fetchTrendsReport(range);
      setTrends(data);
    } catch (err: any) {
      setError(err?.message || 'Failed to fetch trends for selected range');
    }
  };

  // Handle CSV export
  const handleExport = async (type: 'fleet' | 'routes' | 'disruptions' | 'reallocation' | 'trends') => {
    setIsExporting(type);
    setError(null);
    try {
      await downloadReportCsv(type, trendRange);
      setSuccessBanner(`Successfully exported ${type.toUpperCase()} report as CSV`);
      setTimeout(() => setSuccessBanner(null), 5000);
    } catch (err: any) {
      setError(err?.message || `Failed to export ${type} report CSV`);
    } finally {
      setIsExporting(null);
    }
  };

  const fleet: FleetUtilizationReport | undefined = overview?.fleet;
  const routes: RoutePerformanceReport | undefined = overview?.routes;
  const disruptions: DisruptionReport | undefined = overview ? {
    generated_at: overview.generated_at,
    live_incidents_total: overview.disruptions_summary.live_incidents_total,
    live_active_count: overview.disruptions_summary.live_active,
    live_acknowledged_count: 0,
    live_resolved_count: overview.disruptions_summary.live_incidents_total - overview.disruptions_summary.live_active,
    live_breakdowns_count: overview.disruptions_summary.live_breakdowns,
    live_route_disruptions_count: overview.disruptions_summary.live_closures,
    live_overcrowding_alerts_count: 0,
    live_events: [],
    simulation_scenarios_count: overview.disruptions_summary.simulated_scenarios,
    simulated_events: [],
    is_simulation_isolated: true,
    disclaimer: "Live operational alerts and simulated scenarios are strictly isolated. Simulated results reflect hypothetical tests and do not represent real-world incidents.",
  } : undefined;
  const reviewsSummary = overview?.reviews_summary;

  // Filtered routes
  const filteredRoutes = useMemo(() => {
    if (!routes?.routes) return [];
    if (!searchQuery.trim()) return routes.routes;
    const q = searchQuery.toLowerCase();
    return routes.routes.filter(
      (r) =>
        r.route_number.toLowerCase().includes(q) ||
        (r.name && r.name.toLowerCase().includes(q)) ||
        (r.origin && r.origin.toLowerCase().includes(q)) ||
        (r.destination && r.destination.toLowerCase().includes(q))
    );
  }, [routes, searchQuery]);

  // Filtered buses
  const filteredBuses = useMemo(() => {
    if (!fleet?.buses) return [];
    if (!searchQuery.trim()) return fleet.buses;
    const q = searchQuery.toLowerCase();
    return fleet.buses.filter(
      (b) =>
        b.bus_number.toLowerCase().includes(q) ||
        b.license_plate.toLowerCase().includes(q) ||
        (b.current_route_number && b.current_route_number.toLowerCase().includes(q)) ||
        b.status.toLowerCase().includes(q)
    );
  }, [fleet, searchQuery]);

  // Render SVG Trend Chart
  const renderTrendChart = () => {
    if (!trends || !trends.datapoints || trends.datapoints.length === 0) {
      return (
        <div className="h-64 flex items-center justify-center text-slate-500 text-xs">
          No historical passenger telemetry recorded for this time range.
        </div>
      );
    }

    const dps = trends.datapoints;
    const width = 800;
    const height = 240;
    const padding = { top: 20, right: 30, bottom: 40, left: 50 };
    const chartW = width - padding.left - padding.right;
    const chartH = height - padding.top - padding.bottom;

    const maxLf = Math.max(1.2, Math.ceil((trends.peak_observed_load_factor || 1.0) * 10) / 10);
    const minLf = 0.0;

    const getX = (index: number) => padding.left + (index / Math.max(1, dps.length - 1)) * chartW;
    const getY = (val: number) => padding.top + chartH - ((val - minLf) / (maxLf - minLf)) * chartH;

    // Line and Area SVG paths
    const points = dps.map((d, i) => `${getX(i)},${getY(d.average_load_factor)}`).join(' ');
    const areaPoints = `${getX(0)},${padding.top + chartH} ${points} ${getX(dps.length - 1)},${padding.top + chartH}`;

    // Threshold lines at 0.80 and 1.00
    const y80 = getY(0.8);
    const y100 = getY(1.0);

    return (
      <div className="relative overflow-x-auto">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="w-full h-auto min-w-[600px] select-none text-[11px]"
        >
          <defs>
            <linearGradient id="trendGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.4" />
              <stop offset="100%" stopColor="#3b82f6" stopOpacity="0.0" />
            </linearGradient>
          </defs>

          {/* Grid lines */}
          <line
            x1={padding.left}
            y1={y100}
            x2={width - padding.right}
            y2={y100}
            stroke="#ef4444"
            strokeDasharray="4 4"
            strokeOpacity="0.5"
            strokeWidth="1"
          />
          <text x={padding.left + 5} y={y100 - 4} fill="#ef4444" fontSize="10" opacity="0.8">
            100% Critical Capacity
          </text>

          <line
            x1={padding.left}
            y1={y80}
            x2={width - padding.right}
            y2={y80}
            stroke="#f59e0b"
            strokeDasharray="4 4"
            strokeOpacity="0.5"
            strokeWidth="1"
          />
          <text x={padding.left + 5} y={y80 - 4} fill="#f59e0b" fontSize="10" opacity="0.8">
            80% High Load Threshold
          </text>

          {/* Area fill */}
          <polygon points={areaPoints} fill="url(#trendGradient)" />

          {/* Trend line */}
          <polyline
            points={points}
            fill="none"
            stroke="#3b82f6"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />

          {/* Data points */}
          {dps.map((d, i) => {
            const cx = getX(i);
            const cy = getY(d.average_load_factor);
            const isCritical = d.average_load_factor >= 1.0;
            const isHigh = d.average_load_factor >= 0.8 && !isCritical;
            return (
              <g key={i} className="group cursor-pointer">
                <circle
                  cx={cx}
                  cy={cy}
                  r="4"
                  fill={isCritical ? '#ef4444' : isHigh ? '#f59e0b' : '#3b82f6'}
                  stroke="#0f172a"
                  strokeWidth="2"
                  className="transition transform group-hover:scale-150"
                />
                {/* Tooltip on hover */}
                <title>{`${d.timestamp}: ${(d.average_load_factor * 100).toFixed(1)}% Load (${d.total_passengers} pax, ${d.sample_count} samples)`}</title>
              </g>
            );
          })}

          {/* X Axis labels (sampling every few points) */}
          {dps.map((d, i) => {
            const step = dps.length > 15 ? 3 : 1;
            if (i % step !== 0 && i !== dps.length - 1) return null;
            return (
              <text
                key={i}
                x={getX(i)}
                y={height - 10}
                fill="#94a3b8"
                textAnchor="middle"
                fontSize="10"
              >
                {d.timestamp}
              </text>
            );
          })}

          {/* Y Axis labels */}
          {[0, 0.5, 0.8, 1.0].map((val) => (
            <text
              key={val}
              x={padding.left - 8}
              y={getY(val) + 3}
              fill="#64748b"
              textAnchor="end"
              fontSize="10"
            >
              {(val * 100).toFixed(0)}%
            </text>
          ))}
        </svg>
      </div>
    );
  };

  return (
    <div className="space-y-6">
      {/* Header with Title and Global CSV Export */}
      <div className="bg-slate-900/80 backdrop-blur border border-slate-800 rounded-xl p-5 shadow-lg">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 pb-4 border-b border-slate-800/80">
          <div>
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-indigo-500/15 border border-indigo-500/30 flex items-center justify-center text-indigo-400">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
              </div>
              <h2 className="text-lg font-bold text-white tracking-tight">
                Reports &amp; Performance Analytics
              </h2>
              <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 uppercase">
                Stage 10
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Deterministic, explainable transit operational intelligence, historical telemetry trends, and CSV data export.
            </p>
          </div>

          {/* CSV Export & Refresh Actions */}
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => handleExport('fleet')}
              disabled={isExporting !== null}
              className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold flex items-center gap-1.5 border border-slate-700 transition"
              title="Export Fleet Asset Utilization CSV"
            >
              <span>{isExporting === 'fleet' ? 'Exporting...' : 'Export Fleet CSV'}</span>
            </button>

            <button
              onClick={() => handleExport('routes')}
              disabled={isExporting !== null}
              className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold flex items-center gap-1.5 border border-slate-700 transition"
              title="Export Route Performance CSV"
            >
              <span>{isExporting === 'routes' ? 'Exporting...' : 'Export Routes CSV'}</span>
            </button>

            <button
              onClick={() => handleExport('trends')}
              disabled={isExporting !== null}
              className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold flex items-center gap-1.5 border border-slate-700 transition"
              title="Export Historical Trends CSV"
            >
              <span>{isExporting === 'trends' ? 'Exporting...' : 'Export Trends CSV'}</span>
            </button>

            <button
              onClick={() => loadData(false)}
              disabled={isLoading}
              className="px-3.5 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800 text-white text-xs font-semibold flex items-center gap-1.5 transition shadow-sm border border-blue-400/30 ml-1"
            >
              <svg className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              <span>Refresh</span>
            </button>
          </div>
        </div>

        {/* Sub-Navigation Tabs */}
        <div className="flex border-b border-slate-800 mt-4 -mb-1 overflow-x-auto no-scrollbar gap-1">
          {[
            { id: 'overview', label: 'Overview & KPIs' },
            { id: 'fleet', label: 'Fleet Utilization' },
            { id: 'routes', label: 'Route Performance' },
            { id: 'trends', label: 'Historical Trends' },
            { id: 'disruptions', label: 'Disruption Analysis' },
            { id: 'reallocation', label: 'Reallocation & Reviews' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveSection(tab.id as ReportSection)}
              className={`py-2 px-3 text-xs font-semibold border-b-2 whitespace-nowrap transition-colors ${
                activeSection === tab.id
                  ? 'border-indigo-500 text-indigo-400 bg-indigo-500/5'
                  : 'border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-700'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Success Banner */}
      {successBanner && (
        <div className="bg-emerald-950/50 border border-emerald-500/40 text-emerald-200 text-xs px-4 py-3 rounded-xl flex items-center justify-between shadow-md">
          <div className="flex items-center gap-2">
            <svg className="w-4 h-4 text-emerald-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
            </svg>
            <span>{successBanner}</span>
          </div>
          <button onClick={() => setSuccessBanner(null)} className="text-emerald-400 hover:text-emerald-200">✕</button>
        </div>
      )}

      {/* Error Banner */}
      {error && (
        <div className="bg-rose-950/60 border border-rose-500/40 text-rose-200 text-xs px-4 py-3 rounded-xl flex items-center justify-between shadow-md">
          <div className="flex items-center gap-2">
            <svg className="w-4 h-4 text-rose-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <span>{error}</span>
          </div>
          <button onClick={() => setError(null)} className="text-rose-400 hover:text-rose-200">✕</button>
        </div>
      )}

      {/* Main Section Content */}
      {isLoading ? (
        <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-16 text-center">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-indigo-500 mb-3"></div>
          <p className="text-sm text-slate-400">Computing deterministic performance analytics...</p>
        </div>
      ) : (
        <>
          {/* SECTION 1: OVERVIEW & EXECUTIVE KPIS */}
          {activeSection === 'overview' && (
            <div className="space-y-6">
              {/* Executive KPI Cards */}
              <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3">
                <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4">
                  <div className="text-[11px] font-medium text-slate-400">Fleet Availability</div>
                  <div className="text-2xl font-bold text-white mt-1">
                    {fleet?.fleet_availability_pct ?? 0}%
                  </div>
                  <div className="text-[10px] text-slate-500 mt-0.5">
                    {fleet?.operational_buses ?? 0} of {fleet?.total_buses ?? 0} operational
                  </div>
                </div>

                <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4">
                  <div className="text-[11px] font-medium text-slate-400">Fleet Load Factor</div>
                  <div className="text-2xl font-bold text-blue-400 mt-1">
                    {((fleet?.fleet_load_factor ?? 0) * 100).toFixed(1)}%
                  </div>
                  <div className="text-[10px] text-slate-500 mt-0.5">
                    {fleet?.total_current_passengers ?? 0} pax / {fleet?.total_passenger_capacity ?? 0} cap
                  </div>
                </div>

                <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4">
                  <div className="text-[11px] font-medium text-slate-400">Available Seats</div>
                  <div className="text-2xl font-bold text-emerald-400 mt-1">
                    {fleet?.available_seats ?? 0}
                  </div>
                  <div className="text-[10px] text-slate-500 mt-0.5">Across operational fleet</div>
                </div>

                <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4">
                  <div className="text-[11px] font-medium text-slate-400">Active Corridors</div>
                  <div className="text-2xl font-bold text-slate-200 mt-1">
                    {routes?.active_routes ?? 0} / {routes?.total_routes ?? 0}
                  </div>
                  <div className="text-[10px] text-slate-500 mt-0.5">
                    {routes?.overloaded_routes_count ?? 0} high/critical demand
                  </div>
                </div>

                <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4">
                  <div className="text-[11px] font-medium text-slate-400">Live Disruption Alerts</div>
                  <div className="text-2xl font-bold text-rose-400 mt-1">
                    {disruptions?.live_active_count ?? 0}
                  </div>
                  <div className="text-[10px] text-slate-500 mt-0.5">
                    {disruptions?.live_breakdowns_count ?? 0} breakdowns, {disruptions?.live_route_disruptions_count ?? 0} closures
                  </div>
                </div>

                <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4">
                  <div className="text-[11px] font-medium text-slate-400">Dispatcher Reviews</div>
                  <div className="text-2xl font-bold text-indigo-400 mt-1">
                    {reviewsSummary?.total_reviews ?? 0}
                  </div>
                  <div className="text-[10px] text-slate-500 mt-0.5">
                    {reviewsSummary?.approved ?? 0} approved, {reviewsSummary?.rejected ?? 0} rejected
                  </div>
                </div>
              </div>

              {/* Historical Trend Preview in Overview */}
              <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
                  <div>
                    <h3 className="text-sm font-bold text-white">Passenger Load Factor Trend (24h)</h3>
                    <p className="text-xs text-slate-400">
                      Hourly aggregate load factor progression across active telemetry samples
                    </p>
                  </div>
                  <button
                    onClick={() => setActiveSection('trends')}
                    className="text-xs text-indigo-400 hover:text-indigo-300 font-semibold flex items-center gap-1"
                  >
                    View Detailed Timeseries →
                  </button>
                </div>
                {renderTrendChart()}
              </div>

              {/* Network Balance Summary */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 space-y-3">
                  <h4 className="text-xs font-bold text-white uppercase tracking-wider text-slate-400">
                    Fleet Load Factor Distribution
                  </h4>
                  <div className="space-y-2">
                    {[
                      { label: 'Critical (≥100%)', count: fleet?.load_distribution.CRITICAL ?? 0, color: 'bg-rose-500' },
                      { label: 'High (80%-99%)', count: fleet?.load_distribution.HIGH ?? 0, color: 'bg-amber-500' },
                      { label: 'Normal (50%-79%)', count: fleet?.load_distribution.NORMAL ?? 0, color: 'bg-blue-500' },
                      { label: 'Low (<50%)', count: fleet?.load_distribution.LOW ?? 0, color: 'bg-emerald-500' },
                    ].map((item) => (
                      <div key={item.label} className="flex items-center justify-between text-xs">
                        <span className="text-slate-300 flex items-center gap-2">
                          <span className={`w-2.5 h-2.5 rounded-full ${item.color}`}></span>
                          {item.label}
                        </span>
                        <span className="font-bold text-white">{item.count} buses</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 space-y-3">
                  <h4 className="text-xs font-bold text-white uppercase tracking-wider text-slate-400">
                    Operational Scope &amp; Safety Note
                  </h4>
                  <p className="text-xs text-slate-300 leading-relaxed">
                    All analytics shown reflect the <strong className="text-white">CURRENT_OPERATIONAL_SNAPSHOT</strong> derived deterministically from active bus telemetry and passenger load tables.
                  </p>
                  <div className="text-[11px] text-slate-400 border-t border-slate-800 pt-2 italic">
                    Historical trends represent timestamped telemetry in UTC. Real operational incidents and hypothetical disruption simulations remain strictly isolated.
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* SECTION 2: FLEET UTILIZATION */}
          {activeSection === 'fleet' && (
            <div className="space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Filter buses by number, plate, or status..."
                  className="px-3.5 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-xs text-white placeholder-slate-500 w-full sm:w-72 focus:outline-none focus:border-indigo-500"
                />
                <button
                  onClick={() => handleExport('fleet')}
                  className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200 border border-slate-700 transition"
                >
                  Download Fleet CSV
                </button>
              </div>

              {/* Buses Table */}
              <div className="bg-slate-900/90 border border-slate-800 rounded-xl overflow-hidden shadow-lg">
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-950/80 text-slate-400 border-b border-slate-800 font-semibold uppercase text-[10px]">
                      <tr>
                        <th className="p-3">Bus Number</th>
                        <th className="p-3">Plate</th>
                        <th className="p-3">Status</th>
                        <th className="p-3">Route</th>
                        <th className="p-3">Capacity</th>
                        <th className="p-3">Occupancy</th>
                        <th className="p-3">Available Seats</th>
                        <th className="p-3">Load Factor</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60 text-slate-300">
                      {filteredBuses.map((b) => (
                        <tr key={b.bus_id} className="hover:bg-slate-800/40 transition">
                          <td className="p-3 font-mono font-bold text-white">{b.bus_number}</td>
                          <td className="p-3 font-mono text-slate-400">{b.license_plate}</td>
                          <td className="p-3">
                            <span
                              className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                                b.status === 'ACTIVE'
                                  ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30'
                                  : b.status === 'BROKEN_DOWN'
                                  ? 'bg-rose-500/15 text-rose-300 border border-rose-500/30'
                                  : 'bg-amber-500/15 text-amber-300 border border-amber-500/30'
                              }`}
                            >
                              {b.status}
                            </span>
                          </td>
                          <td className="p-3">
                            {b.current_route_number ? (
                              <span className="font-mono text-blue-300">Route {b.current_route_number}</span>
                            ) : (
                              <span className="text-slate-500">Unassigned</span>
                            )}
                          </td>
                          <td className="p-3">{b.capacity}</td>
                          <td className="p-3">{b.current_load} pax</td>
                          <td className="p-3">{b.available_seats}</td>
                          <td className="p-3">
                            <div className="flex items-center gap-2">
                              <div className="w-16 bg-slate-800 rounded-full h-1.5 overflow-hidden">
                                <div
                                  className={`h-full ${
                                    b.load_factor >= 1.0
                                      ? 'bg-rose-500'
                                      : b.load_factor >= 0.8
                                      ? 'bg-amber-500'
                                      : 'bg-blue-500'
                                  }`}
                                  style={{ width: `${Math.min(100, b.load_factor * 100)}%` }}
                                ></div>
                              </div>
                              <span className="font-mono text-[11px]">
                                {(b.load_factor * 100).toFixed(1)}%
                              </span>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* SECTION 3: ROUTE PERFORMANCE */}
          {activeSection === 'routes' && (
            <div className="space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Filter routes by number or terminal..."
                  className="px-3.5 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-xs text-white placeholder-slate-500 w-full sm:w-72 focus:outline-none focus:border-indigo-500"
                />
                <button
                  onClick={() => handleExport('routes')}
                  className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200 border border-slate-700 transition"
                >
                  Download Routes CSV
                </button>
              </div>

              {/* Routes Table */}
              <div className="bg-slate-900/90 border border-slate-800 rounded-xl overflow-hidden shadow-lg">
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-950/80 text-slate-400 border-b border-slate-800 font-semibold uppercase text-[10px]">
                      <tr>
                        <th className="p-3">Route</th>
                        <th className="p-3">Corridor</th>
                        <th className="p-3">Terminals</th>
                        <th className="p-3">Buses</th>
                        <th className="p-3">Capacity</th>
                        <th className="p-3">Passengers</th>
                        <th className="p-3">Available Seats</th>
                        <th className="p-3">Load Factor</th>
                        <th className="p-3">Condition Assessment</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60 text-slate-300">
                      {filteredRoutes.map((r) => (
                        <tr key={r.route_id} className="hover:bg-slate-800/40 transition">
                          <td className="p-3 font-mono font-bold text-white">{r.route_number}</td>
                          <td className="p-3 font-medium text-slate-200">{r.name || 'Corridor'}</td>
                          <td className="p-3 text-slate-400">
                            {r.origin} → {r.destination}
                          </td>
                          <td className="p-3 font-mono">{r.assigned_bus_count}</td>
                          <td className="p-3">{r.total_capacity}</td>
                          <td className="p-3">{r.total_passengers}</td>
                          <td className="p-3">{r.available_seats}</td>
                          <td className="p-3">
                            <span
                              className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                                r.status === 'CRITICAL'
                                  ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                                  : r.status === 'HIGH'
                                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                                  : r.status === 'LOW'
                                  ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                                  : 'bg-blue-500/20 text-blue-300 border border-blue-500/40'
                              }`}
                            >
                              {(r.load_factor * 100).toFixed(1)}% ({r.status})
                            </span>
                          </td>
                          <td className="p-3 text-slate-400 text-[11px]">{r.overcrowding_level}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* SECTION 4: HISTORICAL TRENDS */}
          {activeSection === 'trends' && (
            <div className="space-y-4">
              <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-lg space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div>
                    <h3 className="text-sm font-bold text-white">Passenger Load Factor Progression</h3>
                    <p className="text-xs text-slate-400">
                      {trends?.data_density_note || 'Historical telemetry trends in UTC'}
                    </p>
                  </div>

                  {/* Range Selector */}
                  <div className="flex items-center gap-1.5 bg-slate-950 p-1 rounded-lg border border-slate-800">
                    {(['1h', '24h', '7d'] as const).map((rng) => (
                      <button
                        key={rng}
                        onClick={() => handleRangeChange(rng)}
                        className={`px-3 py-1 rounded-md text-xs font-semibold transition ${
                          trendRange === rng
                            ? 'bg-indigo-600 text-white shadow-sm'
                            : 'text-slate-400 hover:text-white'
                        }`}
                      >
                        {rng.toUpperCase()}
                      </button>
                    ))}
                  </div>
                </div>

                {renderTrendChart()}

                {/* Metric Summary Bar */}
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-3 border-t border-slate-800 text-center sm:text-left">
                  <div className="bg-slate-950/60 p-3 rounded-lg border border-slate-800/60">
                    <div className="text-[10px] text-slate-400">Total Telemetry Samples</div>
                    <div className="text-lg font-bold text-white">{trends?.total_samples ?? 0} records</div>
                  </div>
                  <div className="bg-slate-950/60 p-3 rounded-lg border border-slate-800/60">
                    <div className="text-[10px] text-slate-400">Overall Average Load Factor</div>
                    <div className="text-lg font-bold text-blue-400">
                      {((trends?.overall_average_load_factor ?? 0) * 100).toFixed(1)}%
                    </div>
                  </div>
                  <div className="bg-slate-950/60 p-3 rounded-lg border border-slate-800/60">
                    <div className="text-[10px] text-slate-400">Peak Observed Load Factor</div>
                    <div className="text-lg font-bold text-rose-400">
                      {((trends?.peak_observed_load_factor ?? 0) * 100).toFixed(1)}%
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* SECTION 5: DISRUPTIONS & RESILIENCE */}
          {activeSection === 'disruptions' && (
            <div className="space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <h3 className="text-sm font-bold text-white">Operational Disruption &amp; Scenario Audit</h3>
                  <p className="text-xs text-slate-400">
                    Audit of live transit incidents alongside isolated resilience testing scenarios
                  </p>
                </div>
                <button
                  onClick={() => handleExport('disruptions')}
                  className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200 border border-slate-700 transition"
                >
                  Download Disruptions CSV
                </button>
              </div>

              {/* Strict Isolation Notice */}
              <div className="bg-amber-950/30 border border-amber-500/30 rounded-xl p-4 flex items-start gap-3 text-xs text-amber-200">
                <svg className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <div>
                  <div className="font-bold">Strict Operational &amp; Simulation Isolation</div>
                  <div className="text-amber-300/80 mt-0.5">
                    Live operational alerts and simulated scenarios are strictly isolated. Simulated results represent hypothetical what-if drills and do not modify or reflect real-world bus or corridor statuses.
                  </div>
                </div>
              </div>

              {/* Summary Cards */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl">
                  <div className="text-[11px] text-slate-400 font-medium">Live Vehicle Breakdowns</div>
                  <div className="text-2xl font-bold text-rose-400 mt-1">{disruptions?.live_breakdowns_count ?? 0}</div>
                </div>
                <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl">
                  <div className="text-[11px] text-slate-400 font-medium">Live Route Discontinuations</div>
                  <div className="text-2xl font-bold text-amber-400 mt-1">{disruptions?.live_route_disruptions_count ?? 0}</div>
                </div>
                <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl">
                  <div className="text-[11px] text-slate-400 font-medium">Active Incidents</div>
                  <div className="text-2xl font-bold text-white mt-1">{disruptions?.live_active_count ?? 0}</div>
                </div>
                <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl">
                  <div className="text-[11px] text-slate-400 font-medium">Simulated Scenarios</div>
                  <div className="text-2xl font-bold text-purple-400 mt-1">{disruptions?.simulation_scenarios_count ?? 0}</div>
                </div>
              </div>
            </div>
          )}

          {/* SECTION 6: REALLOCATION & DISPATCHER REVIEWS */}
          {activeSection === 'reallocation' && (
            <div className="space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <h3 className="text-sm font-bold text-white">Reallocation Proposals &amp; Dispatcher Reviews</h3>
                  <p className="text-xs text-slate-400">
                    Audit trail of human dispatcher decisions regarding Stage 5 rule-based reallocation proposals
                  </p>
                </div>
                <button
                  onClick={() => handleExport('reallocation')}
                  className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200 border border-slate-700 transition"
                >
                  Download Reviews CSV
                </button>
              </div>

              {/* Operational Non-Execution Statement */}
              <div className="bg-blue-950/30 border border-blue-500/30 rounded-xl p-4 flex items-start gap-3 text-xs text-blue-200">
                <svg className="w-5 h-5 text-blue-400 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <div>
                  <div className="font-bold">Supervisory Oversight Only — No Automatic Reassignment</div>
                  <div className="text-blue-300/80 mt-0.5">
                    The transit database schema records dispatcher review determinations and advisory proposals for supervisory oversight. In accordance with safety constraints, APPROVED reviews do not execute automated vehicle reassignments or track actual completed physical deadhead transfers.
                  </div>
                </div>
              </div>

              {/* Review KPI Summary */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl">
                  <div className="text-[11px] text-slate-400 font-medium">Total Reviews Logged</div>
                  <div className="text-2xl font-bold text-white mt-1">{reviewsSummary?.total_reviews ?? 0}</div>
                </div>
                <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl">
                  <div className="text-[11px] text-slate-400 font-medium">Approved Proposals</div>
                  <div className="text-2xl font-bold text-emerald-400 mt-1">{reviewsSummary?.approved ?? 0}</div>
                </div>
                <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl">
                  <div className="text-[11px] text-slate-400 font-medium">Rejected Proposals</div>
                  <div className="text-2xl font-bold text-rose-400 mt-1">{reviewsSummary?.rejected ?? 0}</div>
                </div>
                <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl">
                  <div className="text-[11px] text-slate-400 font-medium">Deferred Proposals</div>
                  <div className="text-2xl font-bold text-amber-400 mt-1">{reviewsSummary?.deferred ?? 0}</div>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
};
