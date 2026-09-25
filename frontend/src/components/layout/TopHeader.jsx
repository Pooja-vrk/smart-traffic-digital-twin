import React, { useState, useEffect } from 'react';
import { UserCircle2, Menu } from 'lucide-react';

const PAGE_TITLES = {
  dashboard:  'Command Center',
  simulation: 'Simulation Lab',
  analytics:  'Analytics',
  reports:    'Reports',
  settings:   'Settings',
};

const TopHeader = ({ currentPage, isBackendOnline, onMenuToggle }) => {
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const statusClass = isBackendOnline === true
    ? ''
    : isBackendOnline === false
      ? 'offline'
      : 'connecting';

  const statusLabel = isBackendOnline === true
    ? 'System Online'
    : isBackendOnline === false
      ? 'System Offline'
      : 'Connecting…';

  const dateStr = now.toLocaleDateString(undefined, {
    weekday: 'short', month: 'short', day: 'numeric',
  });

  const timeStr = now.toLocaleTimeString(undefined, {
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  });

  return (
    <header className="top-header">
      <div className="top-header-left">
        {/* Mobile hamburger */}
        <button
          className="mobile-menu-btn"
          onClick={onMenuToggle}
          aria-label="Open menu"
        >
          <Menu size={16} />
        </button>
        <span className="top-header-page-title">
          {PAGE_TITLES[currentPage] || 'Smart Traffic Digital Twin'}
        </span>
      </div>

      <div className="top-header-right">
        <div className={`header-system-status${statusClass ? ' ' + statusClass : ''}`}>
          <span className="header-dot" />
          {statusLabel}
        </div>
        <span className="header-datetime">{dateStr} · {timeStr}</span>
        <div className="header-user-btn" aria-label="User profile">
          <UserCircle2 size={17} />
        </div>
      </div>
    </header>
  );
};

export default TopHeader;
