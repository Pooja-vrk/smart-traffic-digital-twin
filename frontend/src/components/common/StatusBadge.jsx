import React from 'react';

/**
 * StatusBadge — coloured pill with an optional dot.
 * variant: 'green' | 'red' | 'amber' | 'blue' | 'cyan' | 'purple' | 'gray'
 * dot: boolean (default true)
 */
const StatusBadge = ({ children, variant = 'gray', dot = true, className = '' }) => (
  <span className={`status-badge ${variant} ${className}`}>
    {dot && <span className="badge-dot" />}
    {children}
  </span>
);

export default StatusBadge;
