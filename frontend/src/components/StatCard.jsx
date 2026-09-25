import React from 'react';

const StatCard = ({ title, value, unit, trend, color, loading }) => {
  if (loading) {
    return (
      <div className="card stat-card">
        <div className="stat-card-header">
          <h3 className="stat-card-title">{title}</h3>
        </div>
        <div className="stat-card-body">
          <div className="loading">Loading...</div>
        </div>
      </div>
    );
  }

  const displayValue = value !== null && value !== undefined ? value : 'N/A';

  return (
    <div className="card stat-card">
      <div className="stat-card-header">
        <h3 className="stat-card-title">{title}</h3>
        {trend != null && typeof trend === 'number' && !isNaN(trend) && (
          <span className={`stat-card-trend ${trend > 0 ? 'positive' : trend < 0 ? 'negative' : 'neutral'}`}>
            {trend > 0 ? '↑' : trend < 0 ? '↓' : '→'} {Math.abs(trend).toFixed(1)}%
          </span>
        )}
      </div>
      <div className="stat-card-body">
        <div className="stat-card-value" style={{ color: color || 'var(--text-primary)' }}>
          {displayValue}
        </div>
        {unit && <div className="stat-card-unit">{unit}</div>}
      </div>
    </div>
  );
};

export default StatCard;
