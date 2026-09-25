import React from 'react';

/**
 * Premium KPI card.
 * Props:
 *   label       – metric name
 *   value       – display value (string | number)
 *   unit        – unit label shown below the value
 *   icon        – Lucide icon component
 *   accentColor – hex colour for the top accent bar & icon bg
 *   waiting     – secondary "waiting" status text (shown when no live data)
 *   sub         – small subtitle text (optional)
 */
const KPICard = ({
  label,
  value,
  unit,
  icon: Icon,
  accentColor = 'var(--blue)',
  waiting,
  sub,
}) => {
  const isEmpty = value === null || value === undefined || value === '--';

  return (
    <div className="kpi-card">
      {/* Top accent stripe */}
      <div className="kpi-card-accent" style={{ background: accentColor }} />

      <div className="kpi-card-top">
        <span className="kpi-card-label">{label}</span>
        {Icon && (
          <div
            className="kpi-card-icon"
            style={{
              background: `${accentColor}1A`,
              border: `1px solid ${accentColor}33`,
            }}
          >
            <Icon size={14} style={{ color: accentColor }} />
          </div>
        )}
      </div>

      <div className="kpi-card-value" style={{ color: isEmpty ? 'var(--text-muted)' : accentColor }}>
        {isEmpty ? '--' : value}
      </div>

      {unit && <div className="kpi-card-unit">{unit}</div>}

      {sub && (
        <div className="kpi-card-waiting" style={{ color: 'var(--text-muted)' }}>
          {sub}
        </div>
      )}

      {isEmpty && waiting && (
        <div className="kpi-card-waiting">{waiting}</div>
      )}
    </div>
  );
};

export default KPICard;
