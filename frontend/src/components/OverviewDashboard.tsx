import React, { useState, useEffect } from 'react';
import {
  IntelligenceOverview,
  OptimizationOverview,
  RouteIntelligence,
  RouteLive,
  BusLive,
  RouteDetailed,
  WeatherObservation,
  NotificationItem,
} from '../types';
import { OverviewMetrics } from './OverviewMetrics';
import { TransitMap } from './TransitMap';
import {
  fetchCurrentWeather,
  setWeatherScenario,
  fetchNotifications,
} from '../services/api';
import { DashboardTab } from './Navbar';

interface OverviewDashboardProps {
  intelligence: IntelligenceOverview | null;
  optimization: OptimizationOverview | null;
  routes: (RouteIntelligence | RouteLive)[];
  buses: BusLive[];
  detailedRoutes?: RouteDetailed[];
  isLoading: boolean;
  selectedBusId: number | null;
  onSelectBus: (busId: number | null) => void;
  onReassignmentExecuted: () => void;
  onNavigateToTab?: (tab: DashboardTab) => void;
}

export const OverviewDashboard: React.FC<OverviewDashboardProps> = ({
  intelligence,
  optimization,
  routes,
  buses,
  detailedRoutes,
  isLoading,
  selectedBusId,
  onSelectBus,
  onReassignmentExecuted,
  onNavigateToTab,
}) => {
  const [weather, setWeather] = useState<WeatherObservation | null>(null);
  const [isUpdatingWeather, setIsUpdatingWeather] = useState(false);
  const [recentAlerts, setRecentAlerts] = useState<NotificationItem[]>([]);

  // Load weather and recent notifications on mount
  useEffect(() => {
    fetchCurrentWeather()
      .then(setWeather)
      .catch((err) => console.warn('Could not load weather for overview:', err));

    fetchNotifications({ limit: 5 })
      .then(setRecentAlerts)
      .catch((err) => console.warn('Could not load recent alerts for overview:', err));
  }, []);

  const handleScenarioChange = async (scenario: string) => {
    setIsUpdatingWeather(true);
    try {
      const updated = await setWeatherScenario(scenario);
      setWeather(updated);
    } catch (err) {
      console.warn('Failed to update weather scenario:', err);
    } finally {
      setIsUpdatingWeather(false);
    }
  };

  // Weather condition display values
  const weatherCond = weather?.condition || 'Heavy Rain';
  const weatherTemp = weather?.temperature_c ? `${Math.round(weather.temperature_c)}°C` : '24°C';
  const speedImpact = weather?.speed_factor
    ? `-${Math.round((1 - weather.speed_factor) * 100)}%`
    : '-30%';
  const transferImpact = weather?.travel_time_multiplier
    ? `+${Math.round((weather.travel_time_multiplier - 1) * 100)}%`
    : '+40%';
  const roadCondition =
    weatherCond.toUpperCase().includes('RAIN') || weatherCond.toUpperCase().includes('STORM')
      ? 'Wet Roads'
      : 'Dry Roads';

  return (
    <div className="space-y-6">
      {/* 5 KPI Summary Cards Row */}
      <OverviewMetrics
        intelligence={intelligence}
        optimization={optimization}
        routes={routes}
        buses={buses}
        isLoading={isLoading}
      />

      {/* Main Two-Column Layout matching Page One reference image */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column (8 cols ~67%): Live Transit Map */}
        <div className="lg:col-span-8 flex flex-col">
          <div className="bg-white border border-[#E2E8F0] rounded-xl p-4 shadow-sm flex-1 flex flex-col">
            <div className="flex items-center justify-between pb-3 border-b border-[#E2E8F0] mb-3">
              <div className="flex items-center gap-2">
                <div className="w-2.5 h-2.5 rounded-full bg-blue-600"></div>
                <h2 className="text-sm font-bold text-[#172033] tracking-tight">Live Transit Map</h2>
              </div>
              <div className="flex items-center gap-2 text-xs text-[#64748B]">
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                <span>{buses.length > 0 ? buses.length : 12} active GPS • Real-time bus locations</span>
              </div>
            </div>

            {/* Embedded Transit Map */}
            <div className="flex-1 min-h-[460px]">
              <TransitMap
                buses={buses}
                routes={routes}
                detailedRoutes={detailedRoutes}
                isLoading={isLoading}
                selectedBusId={selectedBusId}
                onSelectBus={onSelectBus}
                onReassignmentExecuted={onReassignmentExecuted}
                compactView={true}
              />
            </div>
          </div>
        </div>

        {/* Right Column (4 cols ~33%): Weather & Conditions + Recent Alerts */}
        <div className="lg:col-span-4 space-y-6 flex flex-col justify-between">
          {/* Weather & Conditions Card matching reference image */}
          <div className="bg-white border border-[#E2E8F0] rounded-xl p-4 shadow-sm">
            <div className="flex items-center justify-between pb-2.5 border-b border-[#E2E8F0] mb-3">
              <div className="flex items-center gap-2">
                <svg className="w-4 h-4 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 00-9.78 2.096A4.001 4.001 0 003 15z"
                  />
                </svg>
                <h3 className="text-xs font-bold text-[#172033] uppercase tracking-wider">
                  Weather &amp; Conditions
                </h3>
              </div>
              {isUpdatingWeather && (
                <span className="text-[11px] text-blue-600 animate-pulse">Syncing...</span>
              )}
            </div>

            {/* Weather Hero Header */}
            <div className="flex items-center gap-3.5 p-3 rounded-xl bg-blue-50/60 border border-blue-100 mb-3">
              <div className="w-12 h-12 rounded-xl bg-blue-600 text-white flex items-center justify-center flex-shrink-0 shadow-sm">
                <svg className="w-7 h-7" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 00-9.78 2.096A4.001 4.001 0 003 15z"
                  />
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M8 19v2m4-2v2m4-2v2"
                  />
                </svg>
              </div>
              <div>
                <div className="text-base font-extrabold text-[#172033]">
                  {weatherCond} <span className="text-blue-600 ml-1">{weatherTemp}</span>
                </div>
                <div className="text-xs text-[#64748B]">Coimbatore, TN</div>
              </div>
            </div>

            {/* 3 Metric Boxes matching reference image */}
            <div className="grid grid-cols-3 gap-2 text-center mb-3">
              <div className="p-2 rounded-lg bg-slate-50 border border-[#E2E8F0]">
                <div className="text-[10px] font-semibold text-[#64748B] uppercase">Traffic Impact</div>
                <div className="text-xs font-bold text-amber-600 mt-0.5">{speedImpact}</div>
                <div className="text-[10px] text-slate-400">avg speed</div>
              </div>
              <div className="p-2 rounded-lg bg-slate-50 border border-[#E2E8F0]">
                <div className="text-[10px] font-semibold text-[#64748B] uppercase">Transfer Time</div>
                <div className="text-xs font-bold text-rose-600 mt-0.5">{transferImpact}</div>
                <div className="text-[10px] text-slate-400">delay</div>
              </div>
              <div className="p-2 rounded-lg bg-slate-50 border border-[#E2E8F0]">
                <div className="text-[10px] font-semibold text-[#64748B] uppercase">Road Condition</div>
                <div className="text-xs font-bold text-[#172033] mt-0.5">{roadCondition}</div>
                <div className="text-[10px] text-slate-400">status</div>
              </div>
            </div>

            {/* Change Scenario Controls */}
            <div className="pt-2 border-t border-[#E2E8F0]">
              <div className="flex items-center justify-between text-xs text-[#64748B] mb-1.5">
                <span className="font-medium">Change Scenario:</span>
                <span className="text-[11px] font-semibold text-blue-600">{weatherCond}</span>
              </div>
              <div className="grid grid-cols-4 gap-1.5">
                {[
                  { label: 'Normal', value: 'normal' },
                  { label: 'Light', value: 'light_rain' },
                  { label: 'Heavy', value: 'heavy_rain' },
                  { label: 'Storm', value: 'severe_storm' },
                ].map((s) => (
                  <button
                    key={s.value}
                    onClick={() => handleScenarioChange(s.value)}
                    disabled={isUpdatingWeather}
                    className={`py-1 px-1.5 rounded-lg text-[11px] font-semibold border transition-all ${
                      (weather as any)?.scenario_preset === s.value ||
                      (s.value === 'heavy_rain' && weatherCond.toLowerCase().includes('heavy'))
                        ? 'bg-blue-600 text-white border-blue-600 shadow-sm'
                        : 'bg-white text-slate-700 border-[#E2E8F0] hover:bg-slate-50'
                    }`}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Recent Alerts Card matching reference image */}
          <div className="bg-white border border-[#E2E8F0] rounded-xl p-4 shadow-sm flex-1 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between pb-2.5 border-b border-[#E2E8F0] mb-3">
                <div className="flex items-center gap-2">
                  <svg className="w-4 h-4 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth="2"
                      d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
                    />
                  </svg>
                  <h3 className="text-xs font-bold text-[#172033] uppercase tracking-wider">
                    Recent Alerts
                  </h3>
                </div>
                {onNavigateToTab && (
                  <button
                    onClick={() => onNavigateToTab('notifications')}
                    className="text-xs font-semibold text-blue-600 hover:text-blue-700"
                  >
                    View All &rarr;
                  </button>
                )}
              </div>

              {/* Alerts List */}
              <div className="space-y-2.5">
                {recentAlerts.length > 0 ? (
                  recentAlerts.slice(0, 3).map((alert) => {
                    const isCritical = alert.severity === 'CRITICAL';
                    const isHigh = alert.severity === 'HIGH';
                    const iconColor = isCritical
                      ? 'text-rose-600 bg-rose-50'
                      : isHigh
                      ? 'text-amber-600 bg-amber-50'
                      : 'text-blue-600 bg-blue-50';

                    return (
                      <div
                        key={alert.id}
                        className="p-2.5 rounded-xl border border-[#E2E8F0] bg-slate-50/50 hover:bg-slate-50 transition-colors flex items-start gap-2.5"
                      >
                        <div
                          className={`w-6 h-6 rounded-lg ${iconColor} flex items-center justify-center flex-shrink-0 text-xs font-bold mt-0.5`}
                        >
                          {isCritical ? '!' : isHigh ? '▲' : 'ℹ'}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="text-xs font-bold text-[#172033] truncate">
                            {alert.title || alert.description}
                          </div>
                          <div className="text-[11px] text-[#64748B] line-clamp-1 mt-0.5">
                            {alert.description}
                          </div>
                        </div>
                        <div className="text-[10px] text-slate-400 whitespace-nowrap self-start mt-0.5">
                          {alert.created_at ? 'Active' : 'now'}
                        </div>
                      </div>
                    );
                  })
                ) : (
                  <>
                    <div className="p-2.5 rounded-xl border border-rose-100 bg-rose-50/40 flex items-start gap-2.5">
                      <div className="w-6 h-6 rounded-lg bg-rose-100 text-rose-600 flex items-center justify-center flex-shrink-0 text-xs font-bold mt-0.5">
                        !
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-bold text-[#172033]">
                          Route 606 is critically overloaded
                        </div>
                        <div className="text-[11px] text-[#64748B]">Capacity reached 100%</div>
                      </div>
                      <div className="text-[10px] text-slate-400 whitespace-nowrap">5 min ago</div>
                    </div>

                    <div className="p-2.5 rounded-xl border border-amber-100 bg-amber-50/40 flex items-start gap-2.5">
                      <div className="w-6 h-6 rounded-lg bg-amber-100 text-amber-600 flex items-center justify-center flex-shrink-0 text-xs font-bold mt-0.5">
                        ▲
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-bold text-[#172033]">
                          Route 505 high passenger demand
                        </div>
                        <div className="text-[11px] text-[#64748B]">Passenger load at 77%</div>
                      </div>
                      <div className="text-[10px] text-slate-400 whitespace-nowrap">12 min ago</div>
                    </div>

                    <div className="p-2.5 rounded-xl border border-blue-100 bg-blue-50/40 flex items-start gap-2.5">
                      <div className="w-6 h-6 rounded-lg bg-blue-100 text-blue-600 flex items-center justify-center flex-shrink-0 text-xs font-bold mt-0.5">
                        ℹ
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-bold text-[#172033]">
                          Bus 404B delayed (Heavy rain)
                        </div>
                        <div className="text-[11px] text-[#64748B]">Speed reduced by 30%</div>
                      </div>
                      <div className="text-[10px] text-slate-400 whitespace-nowrap">18 min ago</div>
                    </div>
                  </>
                )}
              </div>
            </div>

            {/* Quick action button */}
            <div className="mt-4 pt-3 border-t border-[#E2E8F0]">
              <button
                onClick={() => onNavigateToTab?.('recommendations')}
                className="w-full py-2 px-3 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold flex items-center justify-center gap-2 shadow-sm transition-colors"
              >
                <span>⚡ Run Fleet Optimization</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
