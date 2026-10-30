import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  NotificationItem,
  NotificationSummary,
  AlertSeverity,
  AlertStatus,
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
  const [alerts, setAlerts] = useState<NotificationItem[]>([]);
  const [summary, setSummary] = useState<NotificationSummary | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [successBanner, setSuccessBanner] = useState<string | null>(null);

  // Filters matching reference image
  const [severityFilter, setSeverityFilter] = useState<string>('ALL');
  const [statusFilter, setStatusFilter] = useState<string>('ALL');

  // Detail / Action modal
  const [activeModal, setActiveModal] = useState<{
    alert: NotificationItem;
    action: 'VIEW' | 'ACKNOWLEDGE' | 'RESOLVE';
  } | null>(null);
  const dispatcherId = 'DISPATCHER-1';
  const [actionNotes, setActionNotes] = useState<string>('');
  const [isSubmittingAction, setIsSubmittingAction] = useState<boolean>(false);

  // Load alerts and summary from backend
  const loadData = useCallback(
    async (quiet: boolean = false) => {
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
    },
    [onAlertCountsChange]
  );

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Handle Manual Refresh / Mark all evaluation
  const handleRefresh = async () => {
    setIsRefreshing(true);
    setError(null);
    try {
      const refreshRes = await refreshNotifications({ includeSimulation: true });
      setSuccessBanner(
        `Alert evaluation completed: ${refreshRes.new_alerts_created} new alerts detected, ${refreshRes.existing_alerts_updated} existing alerts verified.`
      );
      await loadData(true);
      setTimeout(() => setSuccessBanner(null), 5000);
    } catch (err: any) {
      setError(err?.message || 'Failed to evaluate alerts');
    } finally {
      setIsRefreshing(false);
    }
  };

  // Submit Acknowledge or Resolve
  const handleConfirmAction = async () => {
    if (!activeModal || activeModal.action === 'VIEW') return;
    setIsSubmittingAction(true);
    setError(null);
    try {
      if (activeModal.action === 'ACKNOWLEDGE') {
        const updated = await acknowledgeNotification(activeModal.alert.id, {
          dispatcher_id: dispatcherId.trim() || 'DISPATCHER-1',
          notes: actionNotes.trim() || undefined,
        });
        setAlerts((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
        setSuccessBanner(`Alert #${updated.id} investigated by ${updated.acknowledged_by}`);
      } else {
        const updated = await resolveNotification(activeModal.alert.id, {
          dispatcher_id: dispatcherId.trim() || 'DISPATCHER-1',
          notes: actionNotes.trim() || undefined,
        });
        setAlerts((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
        setSuccessBanner(`Alert #${updated.id} marked as resolved.`);
      }

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
      setError(err?.message || 'Failed to process alert action');
    } finally {
      setIsSubmittingAction(false);
    }
  };

  // Filter alerts
  const filteredAlerts = useMemo(() => {
    return alerts.filter((a) => {
      if (severityFilter !== 'ALL' && a.severity !== severityFilter) return false;
      if (statusFilter !== 'ALL' && a.status !== statusFilter) return false;
      return true;
    });
  }, [alerts, severityFilter, statusFilter]);

  // Format relative time helper
  const formatTimeAgo = (isoStr: string) => {
    try {
      const diff = Math.floor((Date.now() - new Date(isoStr).getTime()) / 1000);
      if (diff < 60) return 'Just now';
      if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
      if (diff < 86400) return `${Math.floor(diff / 3600)} hour ago`;
      return `${Math.floor(diff / 86400)} day ago`;
    } catch {
      return '5 min ago';
    }
  };

  const getSeverityBadge = (severity: AlertSeverity) => {
    switch (severity) {
      case 'CRITICAL':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200">
            <span className="w-1.5 h-1.5 rounded-full bg-rose-600 animate-pulse"></span>
            Critical
          </span>
        );
      case 'HIGH':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-500"></span>
            High
          </span>
        );
      case 'WARNING':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-500"></span>
            Warning
          </span>
        );
      case 'INFO':
      default:
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200">
            <span className="w-1.5 h-1.5 rounded-full bg-blue-500"></span>
            Info
          </span>
        );
    }
  };

  const getStatusBadge = (status: AlertStatus) => {
    switch (status) {
      case 'ACTIVE':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200">
            <span className="w-1.5 h-1.5 rounded-full bg-rose-600 animate-pulse"></span>
            Active
          </span>
        );
      case 'ACKNOWLEDGED':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-sky-50 text-sky-700 border border-sky-200">
            <span className="w-1.5 h-1.5 rounded-full bg-sky-500"></span>
            Investigating
          </span>
        );
      case 'RESOLVED':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
            Resolved
          </span>
        );
    }
  };

  return (
    <section className="space-y-4">
      {/* 1. Header matching Page Six reference image */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-[#172033] tracking-tight">
            Alerts &amp; Notifications
          </h1>
          <p className="text-xs text-[#64748B]">
            Real-time operational alerts, breakdowns, and system notifications.
            {summary && (
              <span className="ml-2 font-medium text-slate-500">
                ({summary.active_alerts} active • {summary.critical_alerts} critical)
              </span>
            )}
          </p>
        </div>

        {/* Top Right Controls matching reference image: 2 Selects + Mark All Read button */}
        <div className="flex items-center gap-2 self-start sm:self-auto flex-wrap">
          {/* Severities Filter Dropdown */}
          <select
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value)}
            className="bg-white text-[#172033] text-xs font-semibold rounded-lg px-3 py-2 border border-[#E2E8F0] shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
          >
            <option value="ALL">All Severities</option>
            <option value="CRITICAL">Critical</option>
            <option value="HIGH">High</option>
            <option value="WARNING">Warning</option>
            <option value="INFO">Info</option>
          </select>

          {/* Status Filter Dropdown */}
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="bg-white text-[#172033] text-xs font-semibold rounded-lg px-3 py-2 border border-[#E2E8F0] shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
          >
            <option value="ALL">All Status</option>
            <option value="ACTIVE">Active</option>
            <option value="ACKNOWLEDGED">Investigating</option>
            <option value="RESOLVED">Resolved</option>
          </select>

          {/* Blue Mark All Read / Refresh Button matching reference image */}
          <button
            onClick={handleRefresh}
            disabled={isRefreshing}
            className="px-3.5 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-xs font-semibold rounded-lg shadow-sm flex items-center gap-1.5 transition-colors"
          >
            <svg
              className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin' : ''}`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
            </svg>
            <span>{isRefreshing ? 'Evaluating...' : 'Mark All Read'}</span>
          </button>
        </div>
      </div>

      {/* Success banner */}
      {successBanner && (
        <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-xs text-emerald-800 font-medium shadow-sm flex items-center justify-between">
          <span>{successBanner}</span>
          <button onClick={() => setSuccessBanner(null)} className="text-xs opacity-60 hover:opacity-100">
            ✕
          </button>
        </div>
      )}

      {/* Error banner */}
      {error && (
        <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-xs text-rose-800 font-medium shadow-sm flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-xs opacity-60 hover:opacity-100">
            ✕
          </button>
        </div>
      )}

      {/* 2. Alerts Table matching reference image */}
      <div className="bg-white border border-[#E2E8F0] rounded-xl overflow-hidden shadow-sm">
        {filteredAlerts.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-500 font-semibold text-[11px] border-b border-[#E2E8F0] tracking-wider">
                <tr>
                  <th className="py-3 px-4 font-semibold">Severity</th>
                  <th className="py-3 px-4 font-semibold">Type</th>
                  <th className="py-3 px-4 font-semibold">Route / Bus</th>
                  <th className="py-3 px-4 font-semibold">Description</th>
                  <th className="py-3 px-4 font-semibold">Time</th>
                  <th className="py-3 px-4 font-semibold">Status</th>
                  <th className="py-3 px-4 font-semibold text-center">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E2E8F0]">
                {filteredAlerts.map((alert) => {
                  const alertType = alert.alert_type || (alert.title.includes('Capacity') ? 'Overload' : 'Demand');
                  const routeOrBus = alert.route_number
                    ? `Route ${alert.route_number}`
                    : alert.bus_number
                    ? `Bus ${alert.bus_number}`
                    : 'Network';

                  return (
                    <tr key={alert.id} className="hover:bg-slate-50/80 transition-colors">
                      <td className="py-3.5 px-4 whitespace-nowrap">
                        {getSeverityBadge(alert.severity)}
                      </td>
                      <td className="py-3.5 px-4 whitespace-nowrap font-medium text-slate-700">
                        {alertType}
                      </td>
                      <td className="py-3.5 px-4 whitespace-nowrap font-bold text-blue-600">
                        {routeOrBus}
                      </td>
                      <td className="py-3.5 px-4 text-[#172033] font-medium max-w-md truncate" title={alert.description}>
                        {alert.description}
                      </td>
                      <td className="py-3.5 px-4 whitespace-nowrap text-slate-500">
                        {formatTimeAgo(alert.created_at)}
                      </td>
                      <td className="py-3.5 px-4 whitespace-nowrap">
                        {getStatusBadge(alert.status)}
                      </td>
                      <td className="py-3.5 px-4 whitespace-nowrap text-center">
                        <button
                          onClick={() => setActiveModal({ alert, action: 'VIEW' })}
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
            {isLoading ? 'Loading operational alerts...' : 'No notifications match selected filters.'}
          </div>
        )}
      </div>

      {/* View / Action Modal Dialog in clean light theme */}
      {activeModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm">
          <div className="max-w-lg w-full bg-white border border-[#E2E8F0] rounded-2xl p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-[#E2E8F0]">
              <div className="flex items-center gap-2">
                <span className="text-base">🔔</span>
                <h3 className="text-sm font-bold text-[#172033]">
                  Alert #{activeModal.alert.id} Details
                </h3>
              </div>
              <button
                onClick={() => setActiveModal(null)}
                className="text-slate-400 hover:text-slate-700 text-base"
              >
                ✕
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div className="flex items-center gap-2">
                {getSeverityBadge(activeModal.alert.severity)}
                {getStatusBadge(activeModal.alert.status)}
              </div>

              <div>
                <span className="text-slate-500 block text-[11px] font-semibold">Title</span>
                <span className="font-bold text-[#172033] text-sm">{activeModal.alert.title}</span>
              </div>

              <div>
                <span className="text-slate-500 block text-[11px] font-semibold">Description</span>
                <p className="text-slate-700 bg-slate-50 p-2.5 rounded-lg border border-[#E2E8F0]">
                  {activeModal.alert.description}
                </p>
              </div>

              {activeModal.action !== 'VIEW' && (
                <div>
                  <label className="text-slate-600 font-semibold block mb-1">Dispatcher Notes</label>
                  <textarea
                    value={actionNotes}
                    onChange={(e) => setActionNotes(e.target.value)}
                    rows={2}
                    placeholder="Enter resolution notes"
                    className="w-full bg-slate-50 border border-[#E2E8F0] rounded-lg p-2 text-slate-800 resize-none"
                  />
                </div>
              )}
            </div>

            <div className="flex items-center justify-between pt-3 border-t border-[#E2E8F0]">
              <div>
                {activeModal.alert.status === 'ACTIVE' && (
                  <button
                    onClick={() => {
                      setActiveModal({ alert: activeModal.alert, action: 'ACKNOWLEDGE' });
                    }}
                    className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-sky-50 text-sky-700 border border-sky-200 hover:bg-sky-100"
                  >
                    Investigate
                  </button>
                )}
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => setActiveModal(null)}
                  className="px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-slate-100 hover:bg-slate-200 text-slate-700"
                >
                  Close
                </button>
                {activeModal.alert.status !== 'RESOLVED' && (
                  <button
                    onClick={() => {
                      if (activeModal.action === 'RESOLVE') {
                        handleConfirmAction();
                      } else {
                        setActiveModal({ alert: activeModal.alert, action: 'RESOLVE' });
                      }
                    }}
                    disabled={isSubmittingAction}
                    className="px-4 py-1.5 rounded-lg text-xs font-bold bg-emerald-600 hover:bg-emerald-700 text-white shadow-sm"
                  >
                    {isSubmittingAction ? 'Processing...' : 'Resolve Alert'}
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </section>
  );
};
