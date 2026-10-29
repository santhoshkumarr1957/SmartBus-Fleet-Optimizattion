import React, { useState, useMemo } from 'react';
import { RouteIntelligence, BusIntelligence } from '../types';
import { StatusBadge } from './StatusBadge';

interface MonitoringPanelProps {
  routes: RouteIntelligence[];
  buses: BusIntelligence[];
  isLoading: boolean;
  onSelectBusOnMap?: (busId: number) => void;
}

export const MonitoringPanel: React.FC<MonitoringPanelProps> = ({
  routes,
  buses,
  isLoading,
  onSelectBusOnMap,
}) => {
  const [activeTab, setActiveTab] = useState<'routes' | 'buses'>('routes');
  const [filterStatus, setFilterStatus] = useState<string>('ALL');
  const [searchTerm, setSearchTerm] = useState<string>('');

  // Filter routes
  const filteredRoutes = useMemo(() => {
    return routes.filter((r) => {
      if (filterStatus !== 'ALL' && r.status !== filterStatus) {
        return false;
      }
      if (searchTerm) {
        const term = searchTerm.toLowerCase();
        const matchesNum = r.route_number.toLowerCase().includes(term);
        const matchesAssess = r.assessment.toLowerCase().includes(term);
        if (!matchesNum && !matchesAssess) return false;
      }
      return true;
    });
  }, [routes, filterStatus, searchTerm]);

  // Filter buses
  const filteredBuses = useMemo(() => {
    return buses.filter((b) => {
      if (filterStatus !== 'ALL' && b.status !== filterStatus) {
        return false;
      }
      if (searchTerm) {
        const term = searchTerm.toLowerCase();
        const matchesNum = b.bus_number.toLowerCase().includes(term);
        const matchesRoute = (b.route_number || '').toLowerCase().includes(term);
        if (!matchesNum && !matchesRoute) return false;
      }
      return true;
    });
  }, [buses, filterStatus, searchTerm]);

  return (
    <section className="mb-8">
      {/* Panel Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4">
        <div>
          <h2 className="text-lg font-bold text-white tracking-tight">
            Route & Bus Load Intelligence
          </h2>
          <p className="text-xs text-slate-400">
            Real-time classification based on passenger loading, capacities, and seat availability
          </p>
        </div>

        {/* View Switcher: Routes vs Buses */}
        <div className="flex items-center gap-2">
          <div className="bg-slate-900 border border-slate-800 p-1 rounded-lg flex items-center">
            <button
              onClick={() => setActiveTab('routes')}
              className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${
                activeTab === 'routes'
                  ? 'bg-blue-600 text-white shadow'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Routes ({routes.length})
            </button>
            <button
              onClick={() => setActiveTab('buses')}
              className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${
                activeTab === 'buses'
                  ? 'bg-blue-600 text-white shadow'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Buses ({buses.length})
            </button>
          </div>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-3 mb-4 flex flex-col sm:flex-row items-center justify-between gap-3">
        {/* Status Filter Pills */}
        <div className="flex items-center gap-1.5 overflow-x-auto w-full sm:w-auto">
          <span className="text-xs text-slate-500 mr-1 hidden md:inline">Classification:</span>
          {(['ALL', 'CRITICAL', 'HIGH', 'NORMAL', 'LOW'] as const).map((status) => (
            <button
              key={status}
              onClick={() => setFilterStatus(status)}
              className={`px-2.5 py-1 text-xs font-medium rounded-lg transition-colors whitespace-nowrap ${
                filterStatus === status
                  ? 'bg-blue-500/20 text-blue-300 border border-blue-500/40'
                  : 'bg-slate-800 text-slate-400 hover:text-slate-200 border border-transparent'
              }`}
            >
              {status}
            </button>
          ))}
        </div>

        {/* Search Input */}
        <div className="relative w-full sm:w-64">
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder={activeTab === 'routes' ? 'Search route number...' : 'Search bus or route...'}
            className="w-full bg-slate-950/80 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500"
          />
          {searchTerm && (
            <button
              onClick={() => setSearchTerm('')}
              className="absolute right-2.5 top-2 text-slate-500 hover:text-slate-300 text-xs"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* Tab 1: Route Intelligence Table */}
      {activeTab === 'routes' && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-sm">
          {filteredRoutes.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-950/60 text-slate-400 uppercase font-semibold text-[11px] border-b border-slate-800 tracking-wider">
                  <tr>
                    <th className="py-3 px-4">Route</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4">Load Factor</th>
                    <th className="py-3 px-4">Passengers / Capacity</th>
                    <th className="py-3 px-4">Available Seats</th>
                    <th className="py-3 px-4">Active Fleet</th>
                    <th className="py-3 px-4">Operational Assessment</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/80">
                  {filteredRoutes.map((route) => {
                    const lfPct = Math.round(route.load_factor * 100);
                    return (
                      <tr key={route.route_id} className="hover:bg-slate-800/40 transition-colors">
                        <td className="py-3 px-4 font-bold text-white whitespace-nowrap">
                          <span className="text-blue-400 font-mono">Route {route.route_number}</span>
                        </td>
                        <td className="py-3 px-4 whitespace-nowrap">
                          <StatusBadge status={route.status} type="load" size="sm" />
                        </td>
                        <td className="py-3 px-4 whitespace-nowrap">
                          <div className="flex items-center gap-2">
                            <span className="font-mono font-semibold text-slate-200 w-10">
                              {lfPct}%
                            </span>
                            <div className="w-20 bg-slate-800 rounded-full h-1.5 overflow-hidden">
                              <div
                                className={`h-full ${
                                  lfPct >= 100
                                    ? 'bg-rose-500'
                                    : lfPct >= 80
                                    ? 'bg-amber-500'
                                    : lfPct >= 50
                                    ? 'bg-blue-500'
                                    : 'bg-emerald-500'
                                }`}
                                style={{ width: `${Math.min(100, lfPct)}%` }}
                              ></div>
                            </div>
                          </div>
                        </td>
                        <td className="py-3 px-4 font-mono text-slate-300 whitespace-nowrap">
                          {route.total_passengers} / {route.total_capacity} pax
                        </td>
                        <td className="py-3 px-4 font-mono font-semibold text-emerald-400 whitespace-nowrap">
                          {route.available_seats} seats
                        </td>
                        <td className="py-3 px-4 text-slate-300 whitespace-nowrap">
                          {route.number_of_buses} vehicles
                        </td>
                        <td className="py-3 px-4 text-slate-400 max-w-xs truncate" title={route.assessment}>
                          {route.assessment}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="py-12 text-center text-slate-500 text-xs">
              {isLoading ? 'Loading route intelligence records...' : 'No transit routes match the selected criteria.'}
            </div>
          )}
        </div>
      )}

      {/* Tab 2: Bus Intelligence Cards/Table */}
      {activeTab === 'buses' && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-sm">
          {filteredBuses.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-950/60 text-slate-400 uppercase font-semibold text-[11px] border-b border-slate-800 tracking-wider">
                  <tr>
                    <th className="py-3 px-4">Bus ID</th>
                    <th className="py-3 px-4">Home Route</th>
                    <th className="py-3 px-4">Assigned Route</th>
                    <th className="py-3 px-4">Active Route</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4">Current Load</th>
                    <th className="py-3 px-4">Capacity</th>
                    <th className="py-3 px-4">Available</th>
                    <th className="py-3 px-4">Load Factor</th>
                    <th className="py-3 px-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/80">
                  {filteredBuses.map((bus) => {
                    const lfPct = Math.round(bus.load_factor * 100);
                    return (
                      <tr key={bus.bus_id} className="hover:bg-slate-800/40 transition-colors">
                        <td className="py-3 px-4 font-bold text-white whitespace-nowrap">
                          <span className="font-mono text-slate-200">Bus {bus.bus_number}</span>
                        </td>
                        <td className="py-3 px-4 whitespace-nowrap font-mono text-slate-400">
                          {bus.home_route_number ? `Route ${bus.home_route_number}` : '—'}
                        </td>
                        <td className="py-3 px-4 whitespace-nowrap font-mono font-medium text-blue-400">
                          {bus.assigned_route_number
                            ? `Route ${bus.assigned_route_number}`
                            : (bus.route_number ? `Route ${bus.route_number}` : '—')}
                        </td>
                        <td className="py-3 px-4 whitespace-nowrap font-mono font-medium text-emerald-400">
                          {bus.is_transferring ? (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-purple-500/20 text-purple-300 border border-purple-500/40 animate-pulse">
                              ⚡ Transferring → {bus.target_route_number}
                            </span>
                          ) : (
                            <span>
                              {bus.active_route_number
                                ? `Route ${bus.active_route_number}`
                                : (bus.route_number ? `Route ${bus.route_number}` : '—')}
                            </span>
                          )}
                        </td>
                        <td className="py-3 px-4 whitespace-nowrap">
                          <StatusBadge status={bus.status} type="load" size="sm" />
                        </td>
                        <td className="py-3 px-4 font-mono text-slate-200 whitespace-nowrap">
                          {bus.passenger_count} pax
                        </td>
                        <td className="py-3 px-4 font-mono text-slate-400 whitespace-nowrap">
                          {bus.capacity} seats
                        </td>
                        <td className="py-3 px-4 font-mono font-semibold text-emerald-400 whitespace-nowrap">
                          {bus.available_seats} seats
                        </td>
                        <td className="py-3 px-4 whitespace-nowrap">
                          <div className="flex items-center gap-2">
                            <span className="font-mono font-semibold text-slate-200 w-10">
                              {lfPct}%
                            </span>
                            <div className="w-16 bg-slate-800 rounded-full h-1.5 overflow-hidden">
                              <div
                                className={`h-full ${
                                  lfPct >= 100
                                    ? 'bg-rose-500'
                                    : lfPct >= 80
                                    ? 'bg-amber-500'
                                    : lfPct >= 50
                                    ? 'bg-blue-500'
                                    : 'bg-emerald-500'
                                }`}
                                style={{ width: `${Math.min(100, lfPct)}%` }}
                              ></div>
                            </div>
                          </div>
                        </td>
                        <td className="py-3 px-4 text-right whitespace-nowrap space-x-2">
                          {onSelectBusOnMap && (
                            <>
                              <button
                                onClick={() => onSelectBusOnMap(bus.bus_id)}
                                className="text-xs text-blue-400 hover:text-blue-300 font-medium hover:underline"
                                title="Inspect vehicle telemetry on map"
                              >
                                Locate →
                              </button>
                              <button
                                onClick={() => onSelectBusOnMap(bus.bus_id)}
                                className="text-xs text-indigo-400 hover:text-indigo-300 font-semibold hover:underline"
                                title="Open manual route reassignment dialog"
                              >
                                Change Route 🔄
                              </button>
                            </>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="py-12 text-center text-slate-500 text-xs">
              {isLoading ? 'Loading bus telemetry records...' : 'No buses match the selected filter criteria.'}
            </div>
          )}
        </div>
      )}
    </section>
  );
};
