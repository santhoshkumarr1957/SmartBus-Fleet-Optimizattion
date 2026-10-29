import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  NotificationItem,
  NotificationSummary,
  AlertSeverity,
  AlertStatus,
  AlertSource,
} from '../types';
import {
  fetchNotifications,
  fetchNotificationSummary,
  acknowledgeNotification,
  resolveNotification,
  refreshNotifications,
} from '../services/api';

interface NotificationsPanelProps {
  onAlertCountsChange?: (counts: { active: number; critical: number }) => void;
}

export const NotificationsPanel: React.FC<NotificationsPanelProps> = ({
  onAlertCountsChange,
}) => {
  // State
  const [alerts, setAlerts] = useState<NotificationItem[]>([]);
  const [summary, setSummary] = useState<NotificationSummary | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [successBanner, setSuccessBanner] = useState<string | null>(null);

  // Filters
  const [severityFilter, setSeverityFilter] = useState<string>('ALL');
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [sourceFilter, setSourceFilter] = useState<string>('ALL');
  const [includeSimulation, setIncludeSimulation] = useState<boolean>(true);

  // Modal State for Acknowledge / Resolve
  const [activeModal, setActiveModal] = useState<{
    alert: NotificationItem;
    action: 'ACKNOWLEDGE' | 'RESOLVE';
  } | null>(null);
  const [dispatcherId, setDispatcherId] = useState<string>('DISPATCHER-1');
  const [actionNotes, setActionNotes] = useState<string>('');
  const [isSubmittingAction, setIsSubmittingAction] = useState<boolean>(false);

  // Load alerts and summary from backend
  const loadData = useCallback(async (quiet: boolean = false) => {
    if (!quiet) setIsLoading(true);
    setError(null);
    try {
      const [alertsData, summaryData] = await Promise.all([
        fetchNotifications({ limit: 100 }),
        fetchNotificationSummary(),
      ]);
      setAlerts(alertsData);
      setSummary(summaryData);
      if (onAlertCountsChange) {
        onAlertCountsChange({
          active: summaryData.active_alerts,
          critical: summaryData.critical_alerts,
        });
      }
    } catch (err: any) {
      setError(err?.message || 'Failed to load notifications from transit backend');
    } finally {
      if (!quiet) setIsLoading(false);
    }
  }, [onAlertCountsChange]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Handle Manual Refresh & Telemetry Evaluation
  const handleRefresh = async () => {
    setIsRefreshing(true);
    setError(null);
    try {
      const refreshRes = await refreshNotifications({ includeSimulation });
      setSuccessBanner(
        `Alert evaluation completed: ${refreshRes.new_alerts_created} new alerts detected, ${refreshRes.existing_alerts_updated} existing alerts verified.`
      );
      // Reload alerts list
      await loadData(true);
      setTimeout(() => setSuccessBanner(null), 6000);
    } catch (err: any) {
      setError(err?.message || 'Failed to refresh and evaluate alerts');
    } finally {
      setIsRefreshing(false);
    }
  };

  // Submit Acknowledge or Resolve
  const handleConfirmAction = async () => {
    if (!activeModal) return;
    setIsSubmittingAction(true);
    setError(null);
    try {
      if (activeModal.action === 'ACKNOWLEDGE') {
        const updated = await acknowledgeNotification(activeModal.alert.id, {
          dispatcher_id: dispatcherId.trim() || 'DISPATCHER-1',
          notes: actionNotes.trim() || undefined,
        });
        setAlerts((prev) =>
          prev.map((a) => (a.id === updated.id ? updated : a))
        );
        setSuccessBanner(`Alert #${updated.id} acknowledged by ${updated.acknowledged_by}`);
      } else {
        const updated = await resolveNotification(activeModal.alert.id, {
          dispatcher_id: dispatcherId.trim() || 'DISPATCHER-1',
          notes: actionNotes.trim() || undefined,
        });
        setAlerts((prev) =>
          prev.map((a) => (a.id === updated.id ? updated : a))
        );
        setSuccessBanner(`Alert #${updated.id} resolved by ${updated.resolved_by}`);
      }

      // Refresh summary counts
      const updatedSummary = await fetchNotificationSummary();
      setSummary(updatedSummary);
      if (onAlertCountsChange) {
        onAlertCountsChange({
          active: updatedSummary.active_alerts,
          critical: updatedSummary.critical_alerts,
        });
      }

      setActiveModal(null);
      setActionNotes('');
      setTimeout(() => setSuccessBanner(null), 5000);
    } catch (err: any) {
      setError(err?.message || `Failed to ${activeModal.action.toLowerCase()} alert`);
    } finally {
      setIsSubmittingAction(false);
    }
  };

  // Filter alerts locally
  const filteredAlerts = useMemo(() => {
    return alerts.filter((alert) => {
      if (severityFilter !== 'ALL' && alert.severity !== severityFilter) {
        return false;
      }
      if (statusFilter !== 'ALL' && alert.status !== statusFilter) {
        return false;
      }
      if (sourceFilter !== 'ALL' && alert.source !== sourceFilter) {
        return false;
      }
      return true;
    });
  }, [alerts, severityFilter, statusFilter, sourceFilter]);

  // Helpers for badge styling
  const getSeverityBadge = (severity: AlertSeverity) => {
    switch (severity) {
      case 'CRITICAL':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-500/20 text-rose-300 border border-rose-500/40 animate-pulse">
            <span className="w-1.5 h-1.5 rounded-full bg-rose-400"></span>
            CRITICAL
          </span>
        );
      case 'HIGH':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-500/20 text-amber-300 border border-amber-500/40">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400"></span>
            HIGH
          </span>
        );
      case 'WARNING':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-yellow-500/20 text-yellow-300 border border-yellow-500/40">
            <span className="w-1.5 h-1.5 rounded-full bg-yellow-400"></span>
            WARNING
          </span>
        );
      case 'INFO':
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-sky-500/20 text-sky-300 border border-sky-500/40">
            <span className="w-1.5 h-1.5 rounded-full bg-sky-400"></span>
            INFO
          </span>
        );
    }
  };

  const getStatusBadge = (status: AlertStatus) => {
    switch (status) {
      case 'ACTIVE':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-rose-500/15 text-rose-300 border border-rose-500/30">
            ACTIVE
          </span>
        );
      case 'ACKNOWLEDGED':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-amber-500/15 text-amber-300 border border-amber-500/30">
            ACKNOWLEDGED
          </span>
        );
      case 'RESOLVED':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
            RESOLVED
          </span>
        );
    }
  };

  const getSourceBadge = (source: AlertSource) => {
    if (source === 'SIMULATION') {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-purple-500/20 text-purple-300 border border-purple-500/30">
          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
          </svg>
          SIMULATED
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
        LIVE TELEMETRY
      </span>
    );
  };

  const formatTimestamp = (isoStr: string) => {
    try {
      const dt = new Date(isoStr);
      return dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) +
        ' ' +
        dt.toLocaleDateString([], { month: 'short', day: 'numeric' });
    } catch {
      return isoStr;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header and Summary Counters */}
      <div className="bg-slate-900/80 backdrop-blur border border-slate-800 rounded-xl p-5 shadow-lg">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 pb-4 border-b border-slate-800/80">
          <div>
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-rose-500/15 border border-rose-500/30 flex items-center justify-center text-rose-400">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
                </svg>
              </div>
              <h2 className="text-lg font-bold text-white tracking-tight">
                Transit Notifications & Alert Management
              </h2>
              <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-rose-500/20 text-rose-300 border border-rose-500/30 uppercase">
                Stage 9
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Rule-based operational transit event detection, dispatcher review, and resolution workflows.
            </p>
          </div>

          {/* Action Bar: Include Simulation toggle + Refresh Button */}
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer bg-slate-800/60 px-3 py-1.5 rounded-lg border border-slate-700/60 hover:bg-slate-800 transition">
              <input
                type="checkbox"
                checked={includeSimulation}
                onChange={(e) => setIncludeSimulation(e.target.checked)}
                className="rounded border-slate-700 text-blue-600 focus:ring-blue-500 h-3.5 w-3.5 bg-slate-900"
              />
              <span>Include Simulation Scenarios</span>
            </label>

            <button
              onClick={handleRefresh}
              disabled={isRefreshing}
              className="px-3.5 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800 text-white text-xs font-semibold flex items-center gap-2 transition shadow-sm border border-blue-400/30"
            >
              <svg
                className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin' : ''}`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                />
              </svg>
              <span>{isRefreshing ? 'Evaluating Telemetry...' : 'Refresh & Evaluate'}</span>
            </button>
          </div>
        </div>

        {/* Aggregate KPI Metric Cards */}
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3 mt-4">
          <div className="bg-slate-950/60 border border-slate-800 rounded-lg p-3">
            <div className="text-[11px] font-medium text-slate-400">Active Alerts</div>
            <div className="text-xl font-bold text-white mt-1 flex items-center gap-1.5">
              <span>{summary?.active_alerts ?? 0}</span>
              {(summary?.active_alerts ?? 0) > 0 && (
                <span className="w-2 h-2 rounded-full bg-rose-400 animate-pulse"></span>
              )}
            </div>
          </div>

          <div className="bg-slate-950/60 border border-rose-950/60 rounded-lg p-3">
            <div className="text-[11px] font-medium text-rose-400">Critical</div>
            <div className="text-xl font-bold text-rose-300 mt-1">
              {summary?.critical_alerts ?? 0}
            </div>
          </div>

          <div className="bg-slate-950/60 border border-amber-950/60 rounded-lg p-3">
            <div className="text-[11px] font-medium text-amber-400">High / Warning</div>
            <div className="text-xl font-bold text-amber-300 mt-1">
              {(summary?.high_alerts ?? 0) + (summary?.warning_alerts ?? 0)}
            </div>
          </div>

          <div className="bg-slate-950/60 border border-slate-800 rounded-lg p-3">
            <div className="text-[11px] font-medium text-slate-400">Acknowledged</div>
            <div className="text-xl font-bold text-slate-200 mt-1">
              {summary?.acknowledged_alerts ?? 0}
            </div>
          </div>

          <div className="bg-slate-950/60 border border-slate-800 rounded-lg p-3">
            <div className="text-[11px] font-medium text-emerald-400">Resolved</div>
            <div className="text-xl font-bold text-emerald-300 mt-1">
              {summary?.resolved_alerts ?? 0}
            </div>
          </div>

          <div className="bg-slate-950/60 border border-slate-800 rounded-lg p-3">
            <div className="text-[11px] font-medium text-purple-400">Simulated</div>
            <div className="text-xl font-bold text-purple-300 mt-1">
              {summary?.simulation_alerts ?? 0}
            </div>
          </div>
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
          <button
            onClick={() => setSuccessBanner(null)}
            className="text-emerald-400 hover:text-emerald-200"
          >
            ✕
          </button>
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
          <button
            onClick={() => setError(null)}
            className="text-rose-400 hover:text-rose-200"
          >
            ✕
          </button>
        </div>
      )}

      {/* Filter Toolbar */}
      <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4 flex flex-wrap items-center justify-between gap-4">
        {/* Severity Filters */}
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-xs text-slate-400 mr-1 font-medium">Severity:</span>
          {['ALL', 'CRITICAL', 'HIGH', 'WARNING', 'INFO'].map((sev) => (
            <button
              key={sev}
              onClick={() => setSeverityFilter(sev)}
              className={`px-2.5 py-1 rounded-md text-xs font-semibold transition ${
                severityFilter === sev
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'bg-slate-800/60 text-slate-400 hover:text-slate-200 hover:bg-slate-800'
              }`}
            >
              {sev}
            </button>
          ))}
        </div>

        {/* Status Filters */}
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-xs text-slate-400 mr-1 font-medium">Status:</span>
          {['ALL', 'ACTIVE', 'ACKNOWLEDGED', 'RESOLVED'].map((st) => (
            <button
              key={st}
              onClick={() => setStatusFilter(st)}
              className={`px-2.5 py-1 rounded-md text-xs font-semibold transition ${
                statusFilter === st
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'bg-slate-800/60 text-slate-400 hover:text-slate-200 hover:bg-slate-800'
              }`}
            >
              {st}
            </button>
          ))}
        </div>

        {/* Source Filters */}
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-slate-400 mr-1 font-medium">Source:</span>
          {['ALL', 'LIVE', 'SIMULATION'].map((src) => (
            <button
              key={src}
              onClick={() => setSourceFilter(src)}
              className={`px-2.5 py-1 rounded-md text-xs font-semibold transition ${
                sourceFilter === src
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'bg-slate-800/60 text-slate-400 hover:text-slate-200 hover:bg-slate-800'
              }`}
            >
              {src}
            </button>
          ))}
        </div>
      </div>

      {/* Alert Feed List */}
      {isLoading ? (
        <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-12 text-center">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-blue-500 mb-3"></div>
          <p className="text-sm text-slate-400">Loading transit alerts from database...</p>
        </div>
      ) : filteredAlerts.length === 0 ? (
        <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-12 text-center">
          <div className="w-12 h-12 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 mx-auto flex items-center justify-center mb-3">
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <h3 className="text-base font-semibold text-white">No Transit Alerts Matching Filters</h3>
          <p className="text-xs text-slate-400 mt-1 max-w-md mx-auto">
            All active routes and buses are operating within expected parameters. You can click &quot;Refresh &amp; Evaluate&quot; to perform a fresh telemetry scan.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {filteredAlerts.map((alert) => (
            <div
              key={alert.id}
              className={`bg-slate-900/90 border rounded-xl p-4 transition shadow-md hover:border-slate-700 ${
                alert.severity === 'CRITICAL'
                  ? 'border-rose-900/80 bg-rose-950/10'
                  : alert.severity === 'HIGH'
                  ? 'border-amber-900/60 bg-amber-950/10'
                  : alert.severity === 'WARNING'
                  ? 'border-yellow-900/60'
                  : 'border-slate-800'
              }`}
            >
              <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                {/* Alert Main Info */}
                <div className="space-y-1.5 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    {getSeverityBadge(alert.severity)}
                    {getStatusBadge(alert.status)}
                    {getSourceBadge(alert.source)}

                    {alert.route_number && (
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono font-medium bg-blue-500/15 text-blue-300 border border-blue-500/30">
                        Route {alert.route_number}
                      </span>
                    )}

                    {alert.bus_number && (
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono font-medium bg-indigo-500/15 text-indigo-300 border border-indigo-500/30">
                        Bus {alert.bus_number}
                      </span>
                    )}

                    <span className="text-[11px] text-slate-500 ml-auto sm:ml-0">
                      {formatTimestamp(alert.created_at)}
                    </span>
                  </div>

                  <h3 className="text-sm font-bold text-white tracking-tight pt-0.5">
                    {alert.title}
                  </h3>

                  <p className="text-xs text-slate-300 leading-relaxed">
                    {alert.description}
                  </p>

                  {/* Audit Trail Note */}
                  {(alert.acknowledged_by || alert.resolved_by || alert.notes) && (
                    <div className="pt-2 text-[11px] text-slate-400 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-slate-800/80 mt-2">
                      {alert.acknowledged_by && (
                        <span>
                          <strong className="text-slate-300">Acknowledged:</strong>{' '}
                          {alert.acknowledged_by} at{' '}
                          {alert.acknowledged_at ? formatTimestamp(alert.acknowledged_at) : ''}
                        </span>
                      )}
                      {alert.resolved_by && (
                        <span>
                          <strong className="text-emerald-400">Resolved:</strong>{' '}
                          {alert.resolved_by} at{' '}
                          {alert.resolved_at ? formatTimestamp(alert.resolved_at) : ''}
                        </span>
                      )}
                      {alert.notes && (
                        <span className="italic text-slate-400">
                          &quot;{alert.notes}&quot;
                        </span>
                      )}
                    </div>
                  )}
                </div>

                {/* Workflow Actions */}
                <div className="flex items-center gap-2 shrink-0 self-end sm:self-center">
                  {alert.status === 'ACTIVE' && (
                    <>
                      <button
                        onClick={() =>
                          setActiveModal({ alert, action: 'ACKNOWLEDGE' })
                        }
                        className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-amber-500/15 hover:bg-amber-500/25 text-amber-300 border border-amber-500/30 transition"
                      >
                        Acknowledge
                      </button>
                      <button
                        onClick={() =>
                          setActiveModal({ alert, action: 'RESOLVE' })
                        }
                        className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white transition shadow-sm"
                      >
                        Resolve
                      </button>
                    </>
                  )}

                  {alert.status === 'ACKNOWLEDGED' && (
                    <button
                      onClick={() =>
                        setActiveModal({ alert, action: 'RESOLVE' })
                      }
                      className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white transition shadow-sm"
                    >
                      Resolve
                    </button>
                  )}

                  {alert.status === 'RESOLVED' && (
                    <span className="inline-flex items-center gap-1 text-xs text-emerald-400 font-semibold px-2.5 py-1 rounded bg-emerald-500/10 border border-emerald-500/20">
                      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
                      </svg>
                      Completed
                    </span>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Action Modal (Acknowledge / Resolve) */}
      {activeModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-fadeIn">
          <div className="bg-slate-900 border border-slate-700 rounded-xl max-w-md w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                {activeModal.action === 'ACKNOWLEDGE' ? (
                  <>
                    <span className="w-2.5 h-2.5 rounded-full bg-amber-400"></span>
                    Acknowledge Transit Alert #{activeModal.alert.id}
                  </>
                ) : (
                  <>
                    <span className="w-2.5 h-2.5 rounded-full bg-emerald-400"></span>
                    Resolve Transit Alert #{activeModal.alert.id}
                  </>
                )}
              </h3>
              <button
                onClick={() => setActiveModal(null)}
                className="text-slate-400 hover:text-slate-200"
              >
                ✕
              </button>
            </div>

            <div className="space-y-2">
              <div className="text-xs text-slate-300 font-medium">
                {activeModal.alert.title}
              </div>
              <div className="text-xs text-slate-400 bg-slate-950/60 p-2.5 rounded border border-slate-800">
                {activeModal.alert.description}
              </div>
            </div>

            <div className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  Dispatcher Identifier
                </label>
                <input
                  type="text"
                  value={dispatcherId}
                  onChange={(e) => setDispatcherId(e.target.value)}
                  placeholder="e.g. DISPATCHER-1"
                  className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-xs text-white focus:outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  Operational Notes (Optional)
                </label>
                <textarea
                  value={actionNotes}
                  onChange={(e) => setActionNotes(e.target.value)}
                  placeholder={
                    activeModal.action === 'ACKNOWLEDGE'
                      ? 'Note initial response or investigation taken...'
                      : 'Note how the issue was resolved or mitigated...'
                  }
                  rows={3}
                  className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-xs text-white focus:outline-none focus:border-blue-500 resize-none"
                />
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-800">
              <button
                type="button"
                onClick={() => setActiveModal(null)}
                disabled={isSubmittingAction}
                className="px-3.5 py-1.5 rounded-lg text-xs font-semibold text-slate-300 hover:bg-slate-800 transition"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleConfirmAction}
                disabled={isSubmittingAction}
                className={`px-4 py-1.5 rounded-lg text-xs font-semibold text-white transition shadow-sm flex items-center gap-1.5 ${
                  activeModal.action === 'ACKNOWLEDGE'
                    ? 'bg-amber-600 hover:bg-amber-500 disabled:bg-amber-800'
                    : 'bg-emerald-600 hover:bg-emerald-500 disabled:bg-emerald-800'
                }`}
              >
                {isSubmittingAction && (
                  <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
                )}
                <span>
                  Confirm{' '}
                  {activeModal.action === 'ACKNOWLEDGE' ? 'Acknowledge' : 'Resolve'}
                </span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
