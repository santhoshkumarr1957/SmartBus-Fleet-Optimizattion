import React from 'react';
import {
  IntelligenceOverview,
  OptimizationOverview,
  RouteIntelligence,
  RouteLive,
  BusLive,
} from '../types';

interface OverviewMetricsProps {
  intelligence: IntelligenceOverview | null;
  optimization: OptimizationOverview | null;
  routes: (RouteIntelligence | RouteLive)[];
  buses: BusLive[];
  isLoading: boolean;
}

export const OverviewMetrics: React.FC<OverviewMetricsProps> = ({
  intelligence,
  optimization,
  routes,
  buses,
  isLoading,
}) => {
  // Aggregate system-wide passenger counts & capacity
  const totalPassengers = routes.reduce((acc, r) => acc + (r.total_passengers || 0), 0);
  const totalCapacity = routes.reduce((acc, r) => acc + (r.total_capacity || 0), 0);
  const utilizationPct =
    totalCapacity > 0 ? Math.round((totalPassengers / totalCapacity) * 1000) / 10 : 0;

  // Active buses with valid GPS coordinates
  const busesWithGps = buses.filter((b) => b.latitude !== null && b.longitude !== null).length;

  return (
    <section className="mb-8">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-lg font-bold text-white tracking-tight">System Overview</h2>
          <p className="text-xs text-slate-400">
            Real-time aggregate transit load intelligence and fleet health
          </p>
        </div>
        {isLoading && (
          <span className="text-xs text-slate-400 flex items-center gap-1.5 animate-pulse">
            <span className="w-2 h-2 rounded-full bg-blue-400"></span>
            Syncing metrics...
          </span>
        )}
      </div>

      {/* Primary KPI Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        {/* KPI 1: Total Buses */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-sm hover:border-slate-700 transition-colors">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-medium uppercase tracking-wider">Fleet Buses</span>
            <div className="w-7 h-7 rounded-lg bg-blue-500/10 text-blue-400 flex items-center justify-center">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4"
                />
              </svg>
            </div>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-extrabold text-white">
              {intelligence?.total_buses ?? buses.length ?? '—'}
            </span>
            <span className="text-xs text-slate-500">active vehicles</span>
          </div>
          <div className="mt-3 pt-2 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-400">
            <span>GPS Tracking:</span>
            <span className="font-mono text-emerald-400">
              {buses.length > 0 ? `${busesWithGps}/${buses.length} online` : 'Telemetry pending'}
            </span>
          </div>
        </div>

        {/* KPI 2: Total Routes */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-sm hover:border-slate-700 transition-colors">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-medium uppercase tracking-wider">Transit Routes</span>
            <div className="w-7 h-7 rounded-lg bg-indigo-500/10 text-indigo-400 flex items-center justify-center">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7"
                />
              </svg>
            </div>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-extrabold text-white">
              {intelligence?.total_routes ?? routes.length ?? '—'}
            </span>
            <span className="text-xs text-slate-500">monitored</span>
          </div>
          <div className="mt-3 pt-2 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-400">
            <span>Distribution:</span>
            <span className="text-slate-300">
              {intelligence
                ? `${intelligence.normal_routes} Norm / ${intelligence.low_routes} Low`
                : `${routes.length} active`}
            </span>
          </div>
        </div>

        {/* KPI 3: System Passenger Count & Utilization */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-sm hover:border-slate-700 transition-colors">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-medium uppercase tracking-wider">Load Utilization</span>
            <div className="w-7 h-7 rounded-lg bg-emerald-500/10 text-emerald-400 flex items-center justify-center">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"
                />
              </svg>
            </div>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-extrabold text-white">
              {totalCapacity > 0 ? `${utilizationPct}%` : '—'}
            </span>
            <span className="text-xs text-slate-500">
              {totalPassengers}/{totalCapacity || '—'} pax
            </span>
          </div>
          <div className="mt-3 pt-2 border-t border-slate-800/80">
            <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
              <div
                className={`h-full transition-all duration-500 ${
                  utilizationPct >= 90
                    ? 'bg-rose-500'
                    : utilizationPct >= 75
                    ? 'bg-amber-500'
                    : 'bg-emerald-500'
                }`}
                style={{ width: `${Math.min(100, utilizationPct)}%` }}
              ></div>
            </div>
          </div>
        </div>

        {/* KPI 4: Routes Requiring Attention */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-sm hover:border-slate-700 transition-colors">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-medium uppercase tracking-wider">Attention Needed</span>
            <div
              className={`w-7 h-7 rounded-lg flex items-center justify-center ${
                (intelligence?.routes_needing_attention ?? 0) > 0
                  ? 'bg-rose-500/15 text-rose-400'
                  : 'bg-emerald-500/10 text-emerald-400'
              }`}
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                />
              </svg>
            </div>
          </div>
          <div className="flex items-baseline gap-2">
            <span
              className={`text-2xl font-extrabold ${
                (intelligence?.routes_needing_attention ?? 0) > 0 ? 'text-rose-400' : 'text-emerald-400'
              }`}
            >
              {intelligence?.routes_needing_attention ?? 0}
            </span>
            <span className="text-xs text-slate-500">routes</span>
          </div>
          <div className="mt-3 pt-2 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-400">
            <span>Severity:</span>
            <span className="text-slate-300">
              {intelligence
                ? `${intelligence.critical_routes} Critical • ${intelligence.high_routes} High`
                : 'No alerts'}
            </span>
          </div>
        </div>

        {/* KPI 5: Reallocation Advisory Opportunities */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-sm hover:border-slate-700 transition-colors">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-medium uppercase tracking-wider">Advisory Recs</span>
            <div className="w-7 h-7 rounded-lg bg-amber-500/10 text-amber-400 flex items-center justify-center">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M13 10V3L4 14h7v7l9-11h-7z"
                />
              </svg>
            </div>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-extrabold text-white">
              {optimization?.total_recommendations ?? intelligence?.potential_reallocation_opportunities ?? 0}
            </span>
            <span className="text-xs text-slate-500">opportunities</span>
          </div>
          <div className="mt-3 pt-2 border-t border-slate-800/80 flex items-center justify-between text-xs">
            <span className="text-slate-400">Reviews:</span>
            <div className="flex items-center gap-1.5 font-mono text-[11px]">
              <span className="text-emerald-400" title="Approved for consideration">
                App:{optimization?.approved_count ?? 0}
              </span>
              <span className="text-slate-600">•</span>
              <span className="text-slate-400" title="Pending review">
                Pend:{optimization?.pending_count ?? (optimization?.total_recommendations ?? 0)}
              </span>
              <span className="text-slate-600">•</span>
              <span className="text-rose-400" title="Rejected">
                Rej:{optimization?.rejected_count ?? 0}
              </span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
