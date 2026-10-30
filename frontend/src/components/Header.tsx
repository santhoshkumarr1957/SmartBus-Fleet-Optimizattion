import React, { useState, useEffect } from 'react';
import { ConnectionState } from '../types';

interface HeaderProps {
  status: ConnectionState;
  lastChecked: string | null;
  isAutoRefresh: boolean;
  isRefreshing: boolean;
  onToggleAutoRefresh: () => void;
  onRefreshNow: () => void;
  onOpenMobileMenu?: () => void;
  searchQuery?: string;
  onSearchChange?: (q: string) => void;
}

export const Header: React.FC<HeaderProps> = ({
  status,
  lastChecked,
  isAutoRefresh,
  isRefreshing,
  onToggleAutoRefresh,
  onRefreshNow,
  onOpenMobileMenu,
  searchQuery = '',
  onSearchChange,
}) => {
  const [currentTime, setCurrentTime] = useState<string>('');
  const [currentDate, setCurrentDate] = useState<string>('');

  useEffect(() => {
    const updateDateTime = () => {
      const now = new Date();
      // Format: "Mon, 27 Oct 2026"
      const dateStr = now.toLocaleDateString('en-US', {
        weekday: 'short',
        day: 'numeric',
        month: 'short',
        year: 'numeric',
      });
      // Format: "10:24 AM"
      const timeStr = now.toLocaleTimeString('en-US', {
        hour: 'numeric',
        minute: '2-digit',
        hour12: true,
      });
      setCurrentDate(dateStr);
      setCurrentTime(timeStr);
    };

    updateDateTime();
    const interval = setInterval(updateDateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  const getStatusBadge = () => {
    switch (status) {
      case 'Connected':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
            Online
          </span>
        );
      case 'Degraded':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
            <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse"></span>
            Partial
          </span>
        );
      case 'Disconnected':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200">
            <span className="w-2 h-2 rounded-full bg-rose-500"></span>
            Offline
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200">
            <span className="w-2 h-2 rounded-full bg-blue-500 animate-spin"></span>
            Syncing...
          </span>
        );
    }
  };

  return (
    <header className="sticky top-0 z-30 h-16 bg-white border-b border-[#E2E8F0] px-4 sm:px-6 flex items-center justify-between gap-4">
      {/* Left: Mobile hamburger + Search input */}
      <div className="flex items-center gap-3 flex-1 max-w-md">
        {onOpenMobileMenu && (
          <button
            onClick={onOpenMobileMenu}
            className="lg:hidden p-2 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-100"
            aria-label="Open navigation menu"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
        )}

        {/* Search Bar matching reference image */}
        <div className="relative w-full">
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
            value={searchQuery}
            onChange={(e) => onSearchChange?.(e.target.value)}
            placeholder="Search routes, buses, stops..."
            className="w-full pl-9 pr-3 py-1.5 text-xs bg-slate-50 border border-[#E2E8F0] rounded-lg text-[#172033] placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
          />
        </div>
      </div>

      {/* Right: Controls & Badges */}
      <div className="flex items-center gap-2 sm:gap-4">
        {/* Live Simulation status pill */}
        <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
          Live Simulation
        </div>

        {/* Quick controls: Auto-refresh & Manual Refresh */}
        <div className="flex items-center gap-1.5">
          <button
            onClick={onToggleAutoRefresh}
            className={`px-2.5 py-1 text-xs font-medium rounded-lg border flex items-center gap-1.5 transition-colors ${
              isAutoRefresh
                ? 'bg-blue-50 text-blue-700 border-blue-200 hover:bg-blue-100'
                : 'bg-slate-100 text-slate-500 border-slate-200 hover:bg-slate-200'
            }`}
            title={isAutoRefresh ? 'Auto-refresh active (5s interval)' : 'Auto-refresh paused'}
          >
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                isAutoRefresh ? 'bg-blue-600 animate-pulse' : 'bg-slate-400'
              }`}
            ></span>
            <span className="hidden md:inline">Live 5s:</span> {isAutoRefresh ? 'ON' : 'PAUSED'}
          </button>

          <button
            onClick={onRefreshNow}
            disabled={isRefreshing}
            className="p-1.5 text-xs font-medium text-slate-600 hover:text-blue-600 bg-slate-100 hover:bg-slate-200 active:bg-slate-300 border border-slate-200 rounded-lg transition-colors flex items-center gap-1 disabled:opacity-50"
            title={lastChecked ? `Last refreshed: ${lastChecked}` : 'Refresh now'}
          >
            <svg
              className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin text-blue-600' : ''}`}
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
          </button>
        </div>

        {/* Backend health status badge */}
        <div className="hidden lg:block">{getStatusBadge()}</div>

        {/* Dispatcher profile badge matching reference image */}
        <div className="flex items-center gap-2 pl-2 sm:pl-3 border-l border-[#E2E8F0]">
          <div className="w-8 h-8 rounded-full bg-blue-600 text-white font-bold text-xs flex items-center justify-center shadow-sm">
            D
          </div>
          <div className="hidden xl:block text-left leading-tight">
            <div className="text-xs font-bold text-[#172033]">Dispatcher</div>
            <div className="text-[10px] font-semibold text-blue-600 uppercase">TRANSIGHT</div>
          </div>
        </div>

        {/* Date and Time badge matching reference image */}
        <div className="hidden md:block text-right leading-tight pl-2 sm:pl-3 border-l border-[#E2E8F0]">
          <div className="text-xs font-semibold text-slate-700">{currentDate || 'Mon, 27 Oct 2026'}</div>
          <div className="text-[11px] font-mono font-medium text-slate-500">{currentTime || '10:24 AM'}</div>
        </div>
      </div>
    </header>
  );
};
