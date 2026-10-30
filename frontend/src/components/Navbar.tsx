import React from 'react';
import { ConnectionState } from '../types';
import { Sidebar } from './Sidebar';
import { Header } from './Header';

export type DashboardTab =
  | 'overview'
  | 'map'
  | 'monitoring'
  | 'recommendations'
  | 'simulation'
  | 'notifications';

export { Sidebar, Header };

interface NavbarProps {
  status: ConnectionState;
  lastChecked: string | null;
  isAutoRefresh: boolean;
  isRefreshing: boolean;
  activeTab: DashboardTab;
  alertCounts?: { active: number; critical: number };
  onSelectTab: (tab: DashboardTab) => void;
  onToggleAutoRefresh: () => void;
  onRefreshNow: () => void;
  onOpenMobileMenu?: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  status,
  lastChecked,
  isAutoRefresh,
  isRefreshing,
  activeTab: _activeTab,
  alertCounts: _alertCounts,
  onSelectTab: _onSelectTab,
  onToggleAutoRefresh,
  onRefreshNow,
  onOpenMobileMenu,
}) => {
  return (
    <Header
      status={status}
      lastChecked={lastChecked}
      isAutoRefresh={isAutoRefresh}
      isRefreshing={isRefreshing}
      onToggleAutoRefresh={onToggleAutoRefresh}
      onRefreshNow={onRefreshNow}
      onOpenMobileMenu={onOpenMobileMenu}
    />
  );
};
