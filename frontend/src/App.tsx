import { useState, useEffect } from 'react';
import { useTransitData } from './hooks/useTransitData';
import { Navbar, DashboardTab } from './components/Navbar';
import { ErrorBanner } from './components/ErrorBanner';
import { OverviewMetrics } from './components/OverviewMetrics';
import { TransitMap } from './components/TransitMap';
import { MonitoringPanel } from './components/MonitoringPanel';
import { RecommendationsPanel } from './components/RecommendationsPanel';
import { TrafficSimulationPanel } from './components/TrafficSimulationPanel';
import { NotificationsPanel } from './components/NotificationsPanel';
import { ErrorBoundary } from './components/ErrorBoundary';
import { fetchNotificationSummary } from './services/api';

export default function App() {
  const [activeTab, setActiveTab] = useState<DashboardTab>('overview');
  const [focusedBusId, setFocusedBusId] = useState<number | null>(null);
  const [alertCounts, setAlertCounts] = useState<{ active: number; critical: number }>({
    active: 0,
    critical: 0,
  });

  const {
    intelligenceOverview,
    optimizationOverview,
    liveBuses,
    liveRoutes,
    routeIntelligence,
    busIntelligence,
    recommendations,
    routesDetailed,
    connectionStatus,
    lastUpdated,
    isInitialLoading,
    isRefreshing,
    error,
    isAutoRefresh,
    toggleAutoRefresh,
    refreshNow,
  } = useTransitData();

  // Switch to map tab and focus on bus marker
  const handleSelectBusOnMap = (busId: number) => {
    setFocusedBusId(busId);
    setActiveTab('map');
  };

  // Sync notification summary count for Navbar badge on refresh
  useEffect(() => {
    fetchNotificationSummary()
      .then((sum) => {
        setAlertCounts({
          active: sum.active_alerts,
          critical: sum.critical_alerts,
        });
      })
      .catch(() => {
        // Non-blocking if API unavailable
      });
  }, [lastUpdated]);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col selection:bg-blue-600 selection:text-white">
      {/* Top Navigation Bar */}
      <Navbar
        status={connectionStatus}
        lastChecked={lastUpdated}
        isAutoRefresh={isAutoRefresh}
        isRefreshing={isRefreshing}
        activeTab={activeTab}
        alertCounts={alertCounts}
        onSelectTab={setActiveTab}
        onToggleAutoRefresh={toggleAutoRefresh}
        onRefreshNow={refreshNow}
      />

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Connection / API Error Banner */}
        <ErrorBanner
          status={connectionStatus}
          errorMessage={error}
          onRetry={refreshNow}
          isRetrying={isRefreshing}
        />

        {/* Tab 1: Overview & Map (Default Executive Dashboard) */}
        {activeTab === 'overview' && (
          <ErrorBoundary fallbackTitle="Overview Dashboard Error">
            <div className="space-y-6">
              <OverviewMetrics
                intelligence={intelligenceOverview}
                optimization={optimizationOverview}
                routes={routeIntelligence.length > 0 ? routeIntelligence : liveRoutes}
                buses={liveBuses}
                isLoading={isInitialLoading}
              />

              <TransitMap
                buses={liveBuses}
                routes={liveRoutes.length > 0 ? liveRoutes : routeIntelligence}
                detailedRoutes={routesDetailed}
                isLoading={isInitialLoading}
                selectedBusId={focusedBusId}
                onSelectBus={setFocusedBusId}
                onReassignmentExecuted={refreshNow}
              />

              <div className="grid grid-cols-1 gap-6">
                <RecommendationsPanel
                  recommendations={recommendations}
                  disclaimer={optimizationOverview?.disclaimer}
                  diagnosticReasons={optimizationOverview?.diagnostic_reasons}
                  routeIntelligence={routeIntelligence}
                  error={error}
                  isLoading={isInitialLoading}
                  onReviewRecorded={refreshNow}
                />
                <MonitoringPanel
                  routes={routeIntelligence}
                  buses={busIntelligence}
                  isLoading={isInitialLoading}
                  onSelectBusOnMap={handleSelectBusOnMap}
                />
              </div>
            </div>
          </ErrorBoundary>
        )}

        {/* Tab 2: Full Live Transit Map */}
        {activeTab === 'map' && (
          <ErrorBoundary fallbackTitle="Transit Map Error">
            <div className="space-y-6">
              <TransitMap
                buses={liveBuses}
                routes={liveRoutes.length > 0 ? liveRoutes : routeIntelligence}
                detailedRoutes={routesDetailed}
                isLoading={isInitialLoading}
                selectedBusId={focusedBusId}
                onSelectBus={setFocusedBusId}
                onReassignmentExecuted={refreshNow}
              />
            </div>
          </ErrorBoundary>
        )}

        {/* Tab 3: Detailed Route & Bus Monitoring */}
        {activeTab === 'monitoring' && (
          <ErrorBoundary fallbackTitle="Monitoring Panel Error">
            <div className="space-y-6">
              <MonitoringPanel
                routes={routeIntelligence}
                buses={busIntelligence}
                isLoading={isInitialLoading}
                onSelectBusOnMap={handleSelectBusOnMap}
              />
            </div>
          </ErrorBoundary>
        )}

        {/* Tab 4: Reallocation Advisory Panel */}
        {activeTab === 'recommendations' && (
          <ErrorBoundary fallbackTitle="Reallocation Advisory Error">
            <div className="space-y-6">
              <RecommendationsPanel
                recommendations={recommendations}
                disclaimer={optimizationOverview?.disclaimer}
                diagnosticReasons={optimizationOverview?.diagnostic_reasons}
                routeIntelligence={routeIntelligence}
                error={error}
                isLoading={isInitialLoading}
                onReviewRecorded={refreshNow}
              />
            </div>
          </ErrorBoundary>
        )}

        {/* Tab 5: Traffic Simulation & Dynamic Demand Control */}
        {activeTab === 'simulation' && (
          <ErrorBoundary fallbackTitle="Traffic Simulation Error">
            <div className="space-y-6">
              <TrafficSimulationPanel
                routes={routeIntelligence.length > 0 ? routeIntelligence : liveRoutes}
                buses={busIntelligence.length > 0 ? busIntelligence : liveBuses}
                detailedRoutes={routesDetailed}
                onRefreshRequired={refreshNow}
              />
            </div>
          </ErrorBoundary>
        )}

        {/* Tab 6: Notifications & Alert Management (Stage 9) */}
        {activeTab === 'notifications' && (
          <ErrorBoundary fallbackTitle="Notifications Panel Error">
            <div className="space-y-6">
              <NotificationsPanel onAlertCountsChange={setAlertCounts} />
            </div>
          </ErrorBoundary>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-900 bg-slate-950/80 py-4 text-center text-xs text-slate-500">
        <div className="max-w-7xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-2">
          <span>
            SmartBus (TRANSIGHT) • Hybrid Intelligent Fleet Optimization &amp; Resilience System
          </span>
          <span className="text-slate-600">
            Google OR-Tools CP-SAT Solver • Weather-Aware Transit Operations • Breakdown Mitigation
          </span>
        </div>
      </footer>
    </div>
  );
}

