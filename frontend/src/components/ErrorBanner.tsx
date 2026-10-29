import React from 'react';
import { ConnectionState } from '../types';

interface ErrorBannerProps {
  status: ConnectionState;
  errorMessage: string | null;
  onRetry: () => void;
  isRetrying?: boolean;
}

export const ErrorBanner: React.FC<ErrorBannerProps> = ({
  status,
  errorMessage,
  onRetry,
  isRetrying = false,
}) => {
  if (status === 'Connected' && !errorMessage) {
    return null;
  }

  const isDegraded = status === 'Degraded';

  return (
    <div
      className={`mx-auto max-w-7xl mb-6 p-4 rounded-xl border flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 transition-all duration-200 ${
        isDegraded
          ? 'bg-amber-950/40 border-amber-800/60 text-amber-200'
          : 'bg-rose-950/40 border-rose-800/60 text-rose-200'
      }`}
    >
      <div className="flex items-start gap-3">
        <div
          className={`p-2 rounded-lg ${
            isDegraded ? 'bg-amber-500/20 text-amber-400' : 'bg-rose-500/20 text-rose-400'
          }`}
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
            />
          </svg>
        </div>
        <div>
          <h4 className="text-sm font-semibold tracking-wide">
            {isDegraded ? 'Telemetry Partially Degraded' : 'Transit Backend Disconnected'}
          </h4>
          <p className="text-xs text-slate-300 mt-0.5 max-w-2xl">
            {errorMessage ||
              (isDegraded
                ? 'Some transit API endpoints did not return data. Retaining latest available snapshot.'
                : 'Could not connect to FastAPI server at http://localhost:8000. Verify the backend service is running.')}
          </p>
        </div>
      </div>

      <button
        onClick={onRetry}
        disabled={isRetrying}
        className={`px-3 py-1.5 text-xs font-semibold rounded-lg flex items-center gap-1.5 transition-colors whitespace-nowrap ${
          isDegraded
            ? 'bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/30'
            : 'bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 border border-rose-500/30'
        }`}
      >
        <svg
          className={`w-3.5 h-3.5 ${isRetrying ? 'animate-spin' : ''}`}
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
        {isRetrying ? 'Re-connecting...' : 'Retry Connection'}
      </button>
    </div>
  );
};
