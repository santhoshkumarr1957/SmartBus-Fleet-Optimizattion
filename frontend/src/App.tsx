import { useState, useEffect } from 'react';
import { useTransitData } from './hooks/useTransitData';
import { Sidebar } from './components/Sidebar';
import { Header } from './components/Header';
import { DashboardTab } from './components/Navbar';
import { ErrorBanner } from './components/ErrorBanner';
import { OverviewDashboard } from './components/OverviewDashboard';
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
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [globalSearch, setGlobalSearch] = useState('');
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

  // Switch to map tab and focus on selected bus
  const handleSelectBusOnMap = (busId: number) => {
    setFocusedBusId(busId);
    setActiveTab('map');
  };

  // Sync notification summary count periodically (10s) to avoid connection churn
  useEffect(() => {
    const syncAlertCounts = () => {
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
    };

    syncAlertCounts();
    const interval = setInterval(syncAlertCounts, 10000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="min-h-screen bg-[#F4F7FB] text-[#172033] flex flex-col font-sans">
      {/* 1. Left Sidebar Navigation matching reference image */}
      <Sidebar
        activeTab={activeTab}
        onSelectTab={setActiveTab}
        alertCounts={alertCounts}
        isMobileOpen={isMobileMenuOpen}
        onCloseMobile={() => setIsMobileMenuOpen(false)}
      />

      {/* 2. Main Workspace Layout Area (Offset for lg+ sidebar) */}
      <div className="lg:pl-64 flex-1 flex flex-col min-w-0">
        {/* Top Header Bar matching reference image */}
        <Header
          status={connectionStatus}
          lastChecked={lastUpdated}
          isAutoRefresh={isAutoRefresh}
          isRefreshing={isRefreshing}
          onToggleAutoRefresh={toggleAutoRefresh}
          onRefreshNow={refreshNow}
          onOpenMobileMenu={() => setIsMobileMenuOpen(true)}
          searchQuery={globalSearch}
          onSearchChange={setGlobalSearch}
        />

        {/* Page Content Container */}
        <main className="flex-1 w-full max-w-7xl mx-auto p-4 sm:p-6 lg:p-8">
          {/* Connection Error / Telemetry Status Banner */}
          <ErrorBanner
            status={connectionStatus}
            errorMessage={error}
            onRetry={refreshNow}
            isRetrying={isRefreshing}
          />

          {/* Tab 1: Overview & Map Dashboard */}
          {activeTab === 'overview' && (
            <ErrorBoundary fallbackTitle="Overview Dashboard Error">
              <OverviewDashboard
                intelligence={intelligenceOverview}
                optimization={optimizationOverview}
                routes={routeIntelligence.length > 0 ? routeIntelligence : liveRoutes}
                buses={liveBuses}
                detailedRoutes={routesDetailed}
                isLoading={isInitialLoading}
                selectedBusId={focusedBusId}
                onSelectBus={setFocusedBusId}
                onReassignmentExecuted={refreshNow}
                onNavigateToTab={setActiveTab}
              />
            </ErrorBoundary>
          )}

          {/* Tab 2: Full Live Transit Map */}
          {activeTab === 'map' && (
            <ErrorBoundary fallbackTitle="Transit Map Error">
              <TransitMap
                buses={liveBuses}
                routes={liveRoutes.length > 0 ? liveRoutes : routeIntelligence}
                detailedRoutes={routesDetailed}
                isLoading={isInitialLoading}
                selectedBusId={focusedBusId}
                onSelectBus={setFocusedBusId}
                onReassignmentExecuted={refreshNow}
                compactView={false}
              />
            </ErrorBoundary>
          )}

          {/* Tab 3: Route & Bus Load Intelligence */}
          {activeTab === 'monitoring' && (
            <ErrorBoundary fallbackTitle="Monitoring Panel Error">
              <MonitoringPanel
                routes={routeIntelligence}
                buses={busIntelligence}
                isLoading={isInitialLoading}
                onSelectBusOnMap={handleSelectBusOnMap}
              />
            </ErrorBoundary>
          )}

          {/* Tab 4: Fleet Optimization & Resilience (Google OR-Tools CP-SAT) */}
          {activeTab === 'recommendations' && (
            <ErrorBoundary fallbackTitle="Fleet Optimization Error">
              <RecommendationsPanel
                recommendations={recommendations}
                disclaimer={optimizationOverview?.disclaimer}
                diagnosticReasons={optimizationOverview?.diagnostic_reasons}
                routeIntelligence={routeIntelligence}
                error={error}
                isLoading={isInitialLoading}
                onReviewRecorded={refreshNow}
              />
            </ErrorBoundary>
          )}

          {/* Tab 5: Traffic Simulation Control Room */}
          {activeTab === 'simulation' && (
            <ErrorBoundary fallbackTitle="Traffic Simulation Error">
              <TrafficSimulationPanel
                routes={routeIntelligence.length > 0 ? routeIntelligence : liveRoutes}
                buses={busIntelligence.length > 0 ? busIntelligence : liveBuses}
                detailedRoutes={routesDetailed}
                onRefreshRequired={refreshNow}
              />
            </ErrorBoundary>
          )}

          {/* Tab 6: Operational Alerts & Notifications */}
          {activeTab === 'notifications' && (
            <ErrorBoundary fallbackTitle="Alerts & Notifications Error">
              <NotificationsPanel onAlertCountsChange={setAlertCounts} />
            </ErrorBoundary>
          )}
        </main>

        {/* Light-theme Footer matching design system */}
        <footer className="border-t border-[#E2E8F0] bg-white py-4 text-xs text-slate-500">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-2 text-center sm:text-left">
            <span className="font-medium text-slate-600">
              SmartBus (TRANSIGHT) • Hybrid Intelligent Fleet Optimization &amp; Resilience System
            </span>
            <span className="text-slate-400">
              Google OR-Tools CP-SAT Solver • Weather-Aware Transit Operations • Breakdown Mitigation
            </span>
          </div>
        </footer>
      </div>
    </div>
  );
}
