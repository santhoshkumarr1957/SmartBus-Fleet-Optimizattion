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
    <section className="space-y-4">
      {/* Header matching reference image */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-[#172033] tracking-tight">
            Route &amp; Bus Load Intelligence
          </h1>
          <p className="text-xs text-[#64748B]">
            Real-time classification based on passenger loading, capacities, and seat availability
          </p>
        </div>

        {/* View Switcher: Routes (6) vs Buses (12) matching reference image */}
        <div className="flex items-center gap-1.5 bg-slate-100 p-1 rounded-xl border border-[#E2E8F0] self-start sm:self-auto">
          <button
            onClick={() => setActiveTab('routes')}
            className={`px-3.5 py-1.5 text-xs font-semibold rounded-lg transition-all ${
              activeTab === 'routes'
                ? 'bg-blue-600 text-white shadow-sm'
                : 'text-[#64748B] hover:text-[#172033]'
            }`}
          >
            Routes ({routes.length > 0 ? routes.length : 6})
          </button>
          <button
            onClick={() => setActiveTab('buses')}
            className={`px-3.5 py-1.5 text-xs font-semibold rounded-lg transition-all ${
              activeTab === 'buses'
                ? 'bg-blue-600 text-white shadow-sm'
                : 'text-[#64748B] hover:text-[#172033]'
            }`}
          >
            Buses ({buses.length > 0 ? buses.length : 12})
          </button>
        </div>
      </div>

      {/* Filter and Search Bar matching reference image */}
      <div className="bg-white border border-[#E2E8F0] rounded-xl p-3 shadow-sm flex flex-col sm:flex-row items-center justify-between gap-3">
        {/* Search input on the left */}
        <div className="relative w-full sm:w-80">
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
              />
            </svg>
          </div>
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search route number, name..."
            className="w-full pl-9 pr-3 py-1.5 text-xs bg-slate-50 border border-[#E2E8F0] rounded-lg text-[#172033] placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
          />
          {searchTerm && (
            <button
              onClick={() => setSearchTerm('')}
              className="absolute right-2.5 top-2 text-slate-400 hover:text-slate-600 text-xs"
            >
              ✕
            </button>
          )}
        </div>

        {/* Classification Filter Pills matching reference image */}
        <div className="flex items-center gap-1.5 overflow-x-auto w-full sm:w-auto self-start sm:self-auto">
          <span className="text-xs font-semibold text-[#64748B] mr-1 hidden md:inline">
            Classification:
          </span>
          {(['ALL', 'CRITICAL', 'HIGH', 'NORMAL', 'LOW'] as const).map((status) => {
            const isSelected = filterStatus === status;
            return (
              <button
                key={status}
                onClick={() => setFilterStatus(status)}
                className={`px-3 py-1 text-xs font-semibold rounded-lg transition-all whitespace-nowrap ${
                  isSelected
                    ? 'bg-blue-600 text-white shadow-sm'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                {status}
              </button>
            );
          })}
        </div>
      </div>

      {/* Tab 1: Route Intelligence Table matching reference image */}
      {activeTab === 'routes' && (
        <div className="bg-white border border-[#E2E8F0] rounded-xl overflow-hidden shadow-sm">
          {filteredRoutes.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 text-slate-500 font-semibold text-[11px] border-b border-[#E2E8F0] tracking-wider">
                  <tr>
                    <th className="py-3 px-4 font-semibold">Route</th>
                    <th className="py-3 px-4 font-semibold">Status</th>
                    <th className="py-3 px-4 font-semibold">Load Factor</th>
                    <th className="py-3 px-4 font-semibold">Passengers / Capacity</th>
                    <th className="py-3 px-4 font-semibold">Available Seats</th>
                    <th className="py-3 px-4 font-semibold">Active Fleet</th>
                    <th className="py-3 px-4 font-semibold">Operational Assessment</th>
                    <th className="py-3 px-4 font-semibold text-center">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#E2E8F0]">
                  {filteredRoutes.map((route) => {
                    const lfPct = Math.round((route.load_factor ?? 0) * 100);
                    const progressBarColor =
                      lfPct >= 100
                        ? 'bg-rose-500'
                        : lfPct >= 80
                        ? 'bg-amber-500'
                        : lfPct >= 50
                        ? 'bg-blue-600'
                        : 'bg-emerald-500';

                    return (
                      <tr key={route.route_id} className="hover:bg-slate-50/80 transition-colors">
                        <td className="py-3.5 px-4 font-bold text-blue-600 whitespace-nowrap">
                          Route {route.route_number}
                        </td>
                        <td className="py-3.5 px-4 whitespace-nowrap">
                          <StatusBadge status={route.status} type="load" size="sm" />
                        </td>
                        <td className="py-3.5 px-4 whitespace-nowrap">
                          <div className="flex items-center gap-2">
                            <span className="font-bold text-[#172033] w-9">{lfPct}%</span>
                            <div className="w-20 bg-slate-100 rounded-full h-1.5 overflow-hidden">
                              <div
                                className={`h-full rounded-full ${progressBarColor}`}
                                style={{ width: `${Math.min(100, lfPct)}%` }}
                              />
                            </div>
                          </div>
                        </td>
                        <td className="py-3.5 px-4 text-[#172033] font-medium whitespace-nowrap">
                          {route.total_passengers} / {route.total_capacity}
                        </td>
                        <td className="py-3.5 px-4 font-bold text-emerald-600 whitespace-nowrap">
                          {route.available_seats}
                        </td>
                        <td className="py-3.5 px-4 text-[#172033] font-medium whitespace-nowrap">
                          {route.number_of_buses}
                        </td>
                        <td
                          className={`py-3.5 px-4 max-w-xs truncate font-medium ${
                            route.status === 'CRITICAL'
                              ? 'text-rose-600 font-semibold'
                              : 'text-slate-600'
                          }`}
                          title={route.assessment}
                        >
                          {route.assessment}
                        </td>
                        <td className="py-3.5 px-4 whitespace-nowrap text-center">
                          <button
                            onClick={() => {
                              // View details / focus
                            }}
                            className="px-3 py-1 rounded-lg text-xs font-semibold text-blue-600 hover:text-blue-700 bg-blue-50 hover:bg-blue-100 border border-blue-200 transition-colors"
                          >
                            View
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="py-12 text-center text-slate-500 text-xs">
              {isLoading ? 'Loading route intelligence records...' : 'No transit routes match criteria.'}
            </div>
          )}
        </div>
      )}

      {/* Tab 2: Bus Intelligence Table matching reference image */}
      {activeTab === 'buses' && (
        <div className="bg-white border border-[#E2E8F0] rounded-xl overflow-hidden shadow-sm">
          {filteredBuses.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 text-slate-500 font-semibold text-[11px] border-b border-[#E2E8F0] tracking-wider">
                  <tr>
                    <th className="py-3 px-4 font-semibold">Bus ID</th>
                    <th className="py-3 px-4 font-semibold">Assigned Route</th>
                    <th className="py-3 px-4 font-semibold">Status</th>
                    <th className="py-3 px-4 font-semibold">Passenger Load</th>
                    <th className="py-3 px-4 font-semibold">Load Factor</th>
                    <th className="py-3 px-4 font-semibold">Available Seats</th>
                    <th className="py-3 px-4 font-semibold text-center">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#E2E8F0]">
                  {filteredBuses.map((bus) => {
                    const lfPct = Math.round((bus.load_factor ?? 0) * 100);
                    return (
                      <tr key={bus.bus_id} className="hover:bg-slate-50/80 transition-colors">
                        <td className="py-3.5 px-4 font-bold text-[#172033] whitespace-nowrap">
                          Bus {bus.bus_number}
                        </td>
                        <td className="py-3.5 px-4 whitespace-nowrap font-semibold text-blue-600">
                          Route {bus.assigned_route_number || bus.route_number || '—'}
                        </td>
                        <td className="py-3.5 px-4 whitespace-nowrap">
                          <StatusBadge status={bus.status} type="load" size="sm" />
                        </td>
                        <td className="py-3.5 px-4 font-medium text-[#172033] whitespace-nowrap">
                          {bus.passenger_count ?? '—'} / {bus.capacity}
                        </td>
                        <td className="py-3.5 px-4 whitespace-nowrap">
                          <div className="flex items-center gap-2">
                            <span className="font-bold text-[#172033] w-9">{lfPct}%</span>
                            <div className="w-16 bg-slate-100 rounded-full h-1.5 overflow-hidden">
                              <div
                                className={`h-full rounded-full ${
                                  lfPct >= 100
                                    ? 'bg-rose-500'
                                    : lfPct >= 80
                                    ? 'bg-amber-500'
                                    : 'bg-blue-600'
                                }`}
                                style={{ width: `${Math.min(100, lfPct)}%` }}
                              />
                            </div>
                          </div>
                        </td>
                        <td className="py-3.5 px-4 font-semibold text-emerald-600 whitespace-nowrap">
                          {bus.available_seats ?? (bus.capacity - bus.passenger_count)} seats
                        </td>
                        <td className="py-3.5 px-4 whitespace-nowrap text-center">
                          <button
                            onClick={() => onSelectBusOnMap?.(bus.bus_id)}
                            className="px-3 py-1 rounded-lg text-xs font-semibold text-blue-600 hover:text-blue-700 bg-blue-50 hover:bg-blue-100 border border-blue-200 transition-colors"
                          >
                            View on Map
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="py-12 text-center text-slate-500 text-xs">
              No buses match the selected criteria.
            </div>
          )}
        </div>
      )}
    </section>
  );
};
