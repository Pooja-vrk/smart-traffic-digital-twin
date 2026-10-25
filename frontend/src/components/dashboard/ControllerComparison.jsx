import React, { useState, useEffect } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import { BarChart3, ArrowRight, RefreshCw, BarChart2 } from 'lucide-react';
import Card from '../common/Card';
import { getControllerComparison } from '../../services/api';

/* Colours per controller */
const CTRL_COLORS = {
  fixed:    '#F3A928',
  adaptive: '#16D39A',
  dqn:      '#15B8D6',
};

const CTRL_LABELS = {
  fixed:    'Fixed-Time',
  adaptive: 'Adaptive',
  dqn:      'DQN (AI)',
};

/**
 * Builds chart-ready array from the analytics/controller-comparison API response.
 */
const buildChartData = (data) => {
  if (!data?.controllers || Object.keys(data.controllers).length === 0) return [];
  const metrics = [
    { keys: ['throughput', 'total_vehicles_served'], label: 'Throughput', unit: 'veh' },
    { keys: ['average_queue', 'avg_queue'],          label: 'Avg Queue',  unit: 'veh' },
    { keys: ['average_wait', 'average_waiting_time', 'avg_wait'], label: 'Avg Wait', unit: 's' },
    { keys: ['average_speed', 'avg_speed'],          label: 'Avg Speed',  unit: 'm/s' },
  ];

  return metrics.map(({ keys, label, unit }) => {
    const row = { metric: label, unit };
    Object.entries(data.controllers).forEach(([id, vals]) => {
      let val = null;
      for (const k of keys) {
        if (typeof vals?.[k] === 'number') {
          val = vals[k];
          break;
        }
      }
      row[id] = val != null ? parseFloat(val.toFixed(2)) : null;
    });
    return row;
  });
};

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  const unit = payload[0]?.payload?.unit || '';

  return (
    <div
      style={{
        background: 'var(--surface-2)',
        border: '1px solid var(--border-bright)',
        borderRadius: 8,
        padding: '8px 12px',
        fontSize: 12,
        boxShadow: 'var(--shadow-md)',
      }}
    >
      <div style={{ color: 'var(--text-muted)', marginBottom: 4, fontWeight: 600 }}>{label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} style={{ color: p.fill, display: 'flex', justifyContent: 'space-between', gap: 12 }}>
          <span>{CTRL_LABELS[p.dataKey] || p.dataKey}:</span>
          <strong>{p.value != null ? `${p.value} ${unit}` : '--'}</strong>
        </div>
      ))}
    </div>
  );
};

const ControllerComparison = ({ onNavigateAnalytics, refreshTrigger }) => {
  const [data,    setData]    = useState(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(null);

  const loadData = () => {
    setLoading(true);
    setError(null);
    getControllerComparison()
      .then((d) => {
        setData(d);
        setLoading(false);
      })
      .catch(() => {
        setError('No historical comparison data in database');
        setLoading(false);
      });
  };

  useEffect(() => {
    loadData();
  }, [refreshTrigger]);

  const chartData = buildChartData(data);
  const availableControllers = data?.controllers ? Object.keys(data.controllers) : [];

  const viewLink = (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <button
        onClick={loadData}
        style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', display: 'flex', alignItems: 'center' }}
        title="Refresh comparison metrics"
      >
        <RefreshCw size={11} />
      </button>
      <button className="comparison-view-link" onClick={onNavigateAnalytics}>
        View Details <ArrowRight size={12} />
      </button>
    </div>
  );

  return (
    <Card
      title="Controller Comparison"
      titleIcon={<BarChart3 size={14} />}
      badge={viewLink}
      noPadding
    >
      <div className="comparison-body">
        {loading && (
          <div style={{ color: 'var(--text-muted)', fontSize: 12, padding: '24px 0', textAlign: 'center' }}>
            Loading comparison benchmarks…
          </div>
        )}

        {error && !loading && (
          <div style={{ color: 'var(--text-muted)', fontSize: 11.5, padding: '20px 12px', textAlign: 'center' }}>
            <BarChart2 size={22} style={{ opacity: 0.3, margin: '0 auto 6px', display: 'block' }} />
            Run simulations with Fixed-Time, Adaptive, and DQN controllers to populate comparative benchmarks.
          </div>
        )}

        {!loading && !error && availableControllers.length === 0 && (
          <div style={{ color: 'var(--text-muted)', fontSize: 11.5, padding: '20px 12px', textAlign: 'center' }}>
            <BarChart2 size={22} style={{ opacity: 0.3, margin: '0 auto 6px', display: 'block' }} />
            No completed simulation runs recorded yet. Run all controllers to generate comparison data.
          </div>
        )}

        {!loading && !error && availableControllers.length > 0 && chartData.length > 0 && (
          <div>
            <ResponsiveContainer width="100%" height={175}>
              <BarChart data={chartData} margin={{ top: 6, right: 4, left: -18, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(122,165,210,0.1)" vertical={false} />
                <XAxis
                  dataKey="metric"
                  stroke="var(--text-muted)"
                  tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
                  tickLine={false}
                />
                <YAxis
                  stroke="var(--text-muted)"
                  tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
                  tickLine={false}
                  axisLine={false}
                />
                <Tooltip content={<CustomTooltip />} />
                <Legend
                  wrapperStyle={{ fontSize: 10, color: 'var(--text-muted)', paddingTop: 4 }}
                  formatter={(val) => CTRL_LABELS[val] || val}
                />
                {availableControllers.map((id) => (
                  <Bar
                    key={id}
                    dataKey={id}
                    fill={CTRL_COLORS[id] || '#2F6BFF'}
                    radius={[2, 2, 0, 0]}
                    maxBarSize={18}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>

            {/* Compact Mini Summary */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: `repeat(${availableControllers.length}, 1fr)`,
                gap: 6,
                marginTop: 8,
                paddingTop: 8,
                borderTop: '1px solid var(--border)',
                fontSize: 10.5,
              }}
            >
              {availableControllers.map((cId) => {
                const cData = data.controllers[cId];
                const color = CTRL_COLORS[cId] || 'var(--text-primary)';
                return (
                  <div key={cId} style={{ background: 'var(--surface-2)', padding: '6px 8px', borderRadius: 4 }}>
                    <div style={{ fontWeight: 700, color }}>{CTRL_LABELS[cId] || cId}</div>
                    <div style={{ color: 'var(--text-muted)', marginTop: 2 }}>
                      TP: <strong style={{ color: 'var(--text-primary)' }}>{cData?.throughput ?? '--'}</strong> | Q:{' '}
                      <strong style={{ color: 'var(--text-primary)' }}>{cData?.average_queue ?? '--'}</strong>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </Card>
  );
};

export default ControllerComparison;
