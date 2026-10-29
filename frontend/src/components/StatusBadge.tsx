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
  const sizeClasses = size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-xs font-semibold';

  // Execution status styles (Stage 11)
  if (type === 'execution') {
    switch (normalized) {
      case 'EXECUTED':
        return (
          <span
            className={`inline-flex items-center gap-1 rounded-md bg-purple-500/15 text-purple-300 border border-purple-500/40 ${sizeClasses}`}
            title="Reassignment executed into live dispatch and simulator"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-purple-400"></span>
            ⚡ Executed
          </span>
        );
      case 'IN_PROGRESS':
        return (
          <span
            className={`inline-flex items-center gap-1 rounded-md bg-sky-500/15 text-sky-300 border border-sky-500/40 ${sizeClasses}`}
            title="Reassignment in progress"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-sky-400 animate-pulse"></span>
            Transferring
          </span>
        );
      case 'FAILED':
        return (
          <span
            className={`inline-flex items-center gap-1 rounded-md bg-rose-500/15 text-rose-300 border border-rose-500/40 ${sizeClasses}`}
            title="Reassignment execution failed"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-rose-400"></span>
            ✕ Execution Failed
          </span>
        );
      default:
        return (
          <span
            className={`inline-flex items-center gap-1 rounded-md bg-slate-800 text-slate-400 border border-slate-700 ${sizeClasses}`}
          >
            Not Executed
          </span>
        );
    }
  }

  // Dispatcher Review decision styles (Stage 7)
  if (type === 'review') {
    switch (normalized) {
      case 'APPROVED':
        return (
          <span
            className={`inline-flex items-center gap-1 rounded-md bg-emerald-500/15 text-emerald-300 border border-emerald-500/40 ${sizeClasses}`}
            title="Approved for operational consideration (Non-automated dispatch)"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
            ✓ Approved
          </span>
        );
      case 'REJECTED':
        return (
          <span
            className={`inline-flex items-center gap-1 rounded-md bg-rose-500/15 text-rose-300 border border-rose-500/40 ${sizeClasses}`}
            title="Recommendation rejected by transit dispatcher"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-rose-400"></span>
            ✕ Rejected
          </span>
        );
      case 'DEFERRED':
        return (
          <span
            className={`inline-flex items-center gap-1 rounded-md bg-amber-500/15 text-amber-300 border border-amber-500/40 ${sizeClasses}`}
            title="Recommendation deferred for subsequent cycle re-evaluation"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400"></span>
            ⏳ Deferred
          </span>
        );
      default:
        return (
          <span
            className={`inline-flex items-center gap-1 rounded-md bg-slate-800 text-slate-400 border border-slate-700 ${sizeClasses}`}
            title="Awaiting dispatcher review decision"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-slate-500"></span>
            Pending Review
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
            className={`inline-flex items-center gap-1.5 rounded-full bg-rose-500/15 text-rose-400 border border-rose-500/30 ${sizeClasses}`}
            title="Load factor >= 1.00 (Over capacity)"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-rose-400 animate-pulse"></span>
            CRITICAL
          </span>
        );
      case 'HIGH':
        return (
          <span
            className={`inline-flex items-center gap-1.5 rounded-full bg-amber-500/15 text-amber-400 border border-amber-500/30 ${sizeClasses}`}
            title="Load factor 0.80 - 1.00 (Near capacity)"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400"></span>
            HIGH
          </span>
        );
      case 'NORMAL':
        return (
          <span
            className={`inline-flex items-center gap-1.5 rounded-full bg-blue-500/15 text-blue-400 border border-blue-500/30 ${sizeClasses}`}
            title="Load factor 0.50 - 0.80 (Healthy load)"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-blue-400"></span>
            NORMAL
          </span>
        );
      case 'LOW':
        return (
          <span
            className={`inline-flex items-center gap-1.5 rounded-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 ${sizeClasses}`}
            title="Load factor < 0.50 (Surplus capacity)"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
            LOW
          </span>
        );
      default:
        return (
          <span
            className={`inline-flex items-center gap-1.5 rounded-full bg-slate-700/40 text-slate-400 border border-slate-700 ${sizeClasses}`}
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
            className={`inline-flex items-center gap-1.5 rounded-full bg-rose-500/15 text-rose-300 border border-rose-500/40 ${sizeClasses}`}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-rose-400"></span>
            High Priority
          </span>
        );
      case 'MEDIUM':
        return (
          <span
            className={`inline-flex items-center gap-1.5 rounded-full bg-amber-500/15 text-amber-300 border border-amber-500/40 ${sizeClasses}`}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400"></span>
            Medium Priority
          </span>
        );
      case 'LOW':
        return (
          <span
            className={`inline-flex items-center gap-1.5 rounded-full bg-blue-500/15 text-blue-300 border border-blue-500/40 ${sizeClasses}`}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-blue-400"></span>
            Low Priority
          </span>
        );
      default:
        return (
          <span
            className={`inline-flex items-center gap-1.5 rounded-full bg-slate-700/40 text-slate-400 border border-slate-700 ${sizeClasses}`}
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
            className={`inline-flex items-center gap-1 rounded-md bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 ${sizeClasses}`}
          >
            ✓ Feasible
          </span>
        );
      case 'CONDITIONALLY_FEASIBLE':
        return (
          <span
            className={`inline-flex items-center gap-1 rounded-md bg-amber-500/15 text-amber-300 border border-amber-500/30 ${sizeClasses}`}
          >
            ⚠ Conditionally Feasible
          </span>
        );
      case 'LIMITED_DATA':
        return (
          <span
            className={`inline-flex items-center gap-1 rounded-md bg-slate-600/30 text-slate-300 border border-slate-600/50 ${sizeClasses}`}
          >
            ℹ Limited Data
          </span>
        );
      case 'INFEASIBLE':
        return (
          <span
            className={`inline-flex items-center gap-1 rounded-md bg-rose-500/15 text-rose-300 border border-rose-500/30 ${sizeClasses}`}
          >
            ✕ Infeasible
          </span>
        );
      default:
        return (
          <span
            className={`inline-flex items-center gap-1 rounded-md bg-slate-700/40 text-slate-300 border border-slate-700 ${sizeClasses}`}
          >
            {normalized}
          </span>
        );
    }
  }

  // Generic
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full bg-slate-800 text-slate-300 border border-slate-700 ${sizeClasses}`}
    >
      {normalized}
    </span>
  );
};
