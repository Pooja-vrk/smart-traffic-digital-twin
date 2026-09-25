import React from 'react';
import {
  LayoutDashboard,
  PlayCircle,
  BarChart3,
  FileText,
  Settings,
  TrafficCone,
  X,
} from 'lucide-react';

const NAV_ITEMS = [
  { id: 'dashboard',  label: 'Dashboard',   icon: LayoutDashboard },
  { id: 'simulation', label: 'Simulation',   icon: PlayCircle      },
  { id: 'analytics',  label: 'Analytics',    icon: BarChart3       },
  { id: 'reports',    label: 'Reports',      icon: FileText        },
  { id: 'settings',   label: 'Settings',     icon: Settings        },
];

const Sidebar = ({ currentPage, onPageChange, isOpen, onClose }) => {
  return (
    <>
      {/* Mobile overlay */}
      {isOpen && <div className="sidebar-overlay" onClick={onClose} />}

      <aside className={`sidebar${isOpen ? ' open' : ''}`} aria-label="Main navigation">
        {/* Mobile close */}
        <button className="sidebar-mobile-close" onClick={onClose} aria-label="Close menu">
          <X size={16} />
        </button>

        {/* Logo */}
        <div className="sidebar-logo">
          <div className="sidebar-logo-icon">
            <TrafficCone size={18} />
          </div>
          <div className="sidebar-logo-text">
            <span className="sidebar-logo-title">Smart Traffic</span>
            <span className="sidebar-logo-sub">Digital Twin</span>
          </div>
        </div>

        {/* Navigation */}
        <nav className="sidebar-nav" role="navigation">
          <div className="sidebar-nav-label">Navigation</div>
          {NAV_ITEMS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              className={`sidebar-link${currentPage === id ? ' active' : ''}`}
              onClick={() => { onPageChange(id); onClose(); }}
              aria-current={currentPage === id ? 'page' : undefined}
            >
              <Icon size={16} className="sidebar-link-icon" />
              <span>{label}</span>
            </button>
          ))}
        </nav>

        {/* Footer tagline */}
        <div className="sidebar-footer">
          <div className="sidebar-footer-tagline">
            <strong>Smarter Traffic</strong>
            Greener Cities · Better Tomorrow
          </div>
        </div>
      </aside>
    </>
  );
};

export default Sidebar;
