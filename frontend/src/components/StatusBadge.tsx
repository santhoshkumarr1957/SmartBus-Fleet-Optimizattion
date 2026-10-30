import React from 'react';
import { LoadStatus, PriorityTier, FeasibilityStatus, ReviewDecision } from '../types';

interface StatusBadgeProps {
  status: LoadStatus | PriorityTier | FeasibilityStatus | ReviewDecision | string;
  type?: 'load' | 'priority' | 'feasibility' | 'review' | 'execution' | 'generic';
  size?: 'sm' | 'md';
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({
  status,
  type = 'load',
  size = 'md',
}) => {
  const normalized = (status || '').toUpperCase().trim();
  const sizeClasses = size === 'sm' ? 'px-2 py-0.5 text-[11px]' : 'px-2.5 py-1 text-xs font-semibold';

  // Execution status styles
  if (type === 'execution') {
    switch (normalized) {
      case 'EXECUTED':
        return (
          <span
            className={`inline-flex items-center gap-1.5 rounded-full bg-purple-50 text-purple-700 border border-purple-200 font-medium ${sizeClasses}`}
            title="Reassignment executed into live dispatch and simulator"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-purple-600"></span>
            ⚡ Executed
          </span>
        );
      case 'IN_PROGRESS':
        return (
          <span
            className={`inline-flex items-center gap-1.5 rounded-full bg-sky-50 text-sky-700 border border-sky-200 font-medium ${sizeClasses}`}
            title="Reassignment in progress"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-sky-500 animate-pulse"></span>
            Transferring
          </span>
        );
      case 'FAILED':
        return (
          <span
            className={`inline-flex items-center gap-1.5 rounded-full bg-rose-50 text-rose-700 border border-rose-200 font-medium ${sizeClasses}`}
            title="Reassignment execution failed"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-rose-600"></span>
            ✕ Failed
          </span>
        );
      default:
        return (
          <span
            className={`inline-flex items-center gap-1.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200 font-medium ${sizeClasses}`}
          >
            Not Executed
          </span>
        );
    }
  }

  // Dispatcher Review decision styles
  if (type === 'review') {
    switch (normalized) {
      case 'APPROVED':
        return (
          <span
            className={`inline-flex items-center gap-1.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 font-medium ${sizeClasses}`}
            title="Approved for operational consideration"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
            ✓ Approved
          </span>
        );
      case 'REJECTED':
        return (
          <span
            className={`inline-flex items-center gap-1.5 rounded-full bg-rose-50 text-rose-700 border border-rose-200 font-medium ${sizeClasses}`}
            title="Recommendation rejected by transit dispatcher"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-rose-500"></span>
            ✕ Rejected
          </span>
        );
      case 'DEFERRED':
        return (
          <span
            className={`inline-flex items-center gap-1.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200 font-medium ${sizeClasses}`}
            title="Recommendation deferred for subsequent cycle re-evaluation"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-amber-500"></span>
            ⏳ Deferred
          </span>
        );
      default:
        return (
          <span
            className={`inline-flex items-center gap-1.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200 font-medium ${sizeClasses}`}
            title="Awaiting dispatcher review decision"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-amber-500"></span>
            Pending
          </span>
        );
    }
  }

  // Load status styles
  if (type === 'load') {
    switch (normalized) {
      case 'CRITICAL':
        return (
          <span
            className={`inline-flex items-center gap-1.5 rounded-full bg-rose-50 text-rose-700 border border-rose-200 font-semibold tracking-wide ${sizeClasses}`}
            title="Load factor >= 1.00 (Over capacity)"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-rose-600 animate-pulse"></span>
            CRITICAL
          </span>
        );
      case 'HIGH':
        return (
          <span
            className={`inline-flex items-center gap-1.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200 font-semibold tracking-wide ${sizeClasses}`}
            title="Load factor 0.80 - 1.00 (Near capacity)"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-amber-500"></span>
            HIGH
          </span>
        );
      case 'NORMAL':
        return (
          <span
            className={`inline-flex items-center gap-1.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200 font-semibold tracking-wide ${sizeClasses}`}
            title="Load factor 0.50 - 0.80 (Healthy load)"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-blue-500"></span>
            NORMAL
          </span>
        );
      case 'LOW':
        return (
          <span
            className={`inline-flex items-center gap-1.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 font-semibold tracking-wide ${sizeClasses}`}
            title="Load factor < 0.50 (Surplus capacity)"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
            LOW
          </span>
        );
      default:
        return (
          <span
            className={`inline-flex items-center gap-1.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200 font-medium ${sizeClasses}`}
          >
            {normalized || 'UNKNOWN'}
          </span>
        );
    }
  }

  // Priority styles
  if (type === 'priority') {
    switch (normalized) {
      case 'HIGH':
        return (
          <span
            className={`inline-flex items-center gap-1.5 rounded-full bg-rose-50 text-rose-700 border border-rose-200 font-medium ${sizeClasses}`}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-rose-500"></span>
            High Priority
          </span>
        );
      case 'MEDIUM':
        return (
          <span
            className={`inline-flex items-center gap-1.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200 font-medium ${sizeClasses}`}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-amber-500"></span>
            Medium Priority
          </span>
        );
      case 'LOW':
        return (
          <span
            className={`inline-flex items-center gap-1.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200 font-medium ${sizeClasses}`}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-blue-500"></span>
            Low Priority
          </span>
        );
      default:
        return (
          <span
            className={`inline-flex items-center gap-1.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200 font-medium ${sizeClasses}`}
          >
            {normalized || 'NORMAL'}
          </span>
        );
    }
  }

  // Feasibility styles
  if (type === 'feasibility') {
    switch (normalized) {
      case 'FEASIBLE':
        return (
          <span
            className={`inline-flex items-center gap-1 rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200 font-medium ${sizeClasses}`}
          >
            ✓ Feasible
          </span>
        );
      case 'CONDITIONALLY_FEASIBLE':
        return (
          <span
            className={`inline-flex items-center gap-1 rounded-md bg-amber-50 text-amber-700 border border-amber-200 font-medium ${sizeClasses}`}
          >
            ⚠ Conditionally Feasible
          </span>
        );
      case 'LIMITED_DATA':
        return (
          <span
            className={`inline-flex items-center gap-1 rounded-md bg-slate-100 text-slate-600 border border-slate-200 font-medium ${sizeClasses}`}
          >
            ℹ Limited Data
          </span>
        );
      case 'INFEASIBLE':
        return (
          <span
            className={`inline-flex items-center gap-1 rounded-md bg-rose-50 text-rose-700 border border-rose-200 font-medium ${sizeClasses}`}
          >
            ✕ Infeasible
          </span>
        );
      default:
        return (
          <span
            className={`inline-flex items-center gap-1 rounded-md bg-slate-100 text-slate-600 border border-slate-200 font-medium ${sizeClasses}`}
          >
            {normalized}
          </span>
        );
    }
  }

  // Generic
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full bg-slate-100 text-slate-700 border border-slate-200 font-medium ${sizeClasses}`}
    >
      {normalized}
    </span>
  );
};
