import React, { useState, useEffect } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import { BarChart3, ArrowRight } from 'lucide-react';
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
 * Expected shape: { controllers: { fixed: {...}, adaptive: {...}, dqn: {...} } }
 * Each controller object may contain: throughput, avg_queue, avg_waiting_time, avg_speed
 */
const buildChartData = (data) => {
  if (!data?.controllers) return [];
  const metrics = [
    { key: 'throughput',       label: 'Throughput',  unit: 'veh' },
    { key: 'avg_queue',        label: 'Avg Queue',   unit: 'veh' },
    { key: 'avg_waiting_time', label: 'Avg Wait',    unit: 's'   },
    { key: 'avg_speed',        label: 'Avg Speed',   unit: 'm/s' },
  ];

  return metrics.map(({ key, label, unit }) => {
    const row = { metric: label };
    Object.entries(data.controllers).forEach(([id, vals]) => {
      const v = vals?.[key];
      row[id] = typeof v === 'number' ? parseFloat(v.toFixed(2)) : null;
    });
    return row;
  });
};

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: 'var(--surface-2)',
      border: '1px solid var(--border-bright)',
      borderRadius: 8,
      padding: '8px 12px',
      fontSize: 12,
    }}>
      <div style={{ color: 'var(--text-muted)', marginBottom: 4 }}>{label}</div>
      {payload.map(p => (
        <div key={p.dataKey} style={{ color: p.fill }}>
          {CTRL_LABELS[p.dataKey] || p.dataKey}:{' '}
          <strong>{p.value != null ? p.value : '--'}</strong>
        </div>
      ))}
    </div>
  );
};

const ControllerComparison = ({ onNavigateAnalytics }) => {
  const [data,    setData]    = useState(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(null);

  useEffect(() => {
    getControllerComparison()
      .then(d => { setData(d); setLoading(false); })
      .catch(() => { setError('No comparison data available'); setLoading(false); });
  }, []);

  const chartData = buildChartData(data);
  const controllers = data?.controllers ? Object.keys(data.controllers) : ['fixed', 'adaptive', 'dqn'];

  const viewLink = (
    <button className="comparison-view-link" onClick={onNavigateAnalytics}>
      View Details <ArrowRight size={12} />
    </button>
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
          <div style={{ color: 'var(--text-muted)', fontSize: 12, padding: '12px 0', textAlign: 'center' }}>
            Loading comparison…
          </div>
        )}
        {error && !loading && (
          <div style={{ color: 'var(--text-muted)', fontSize: 12, padding: '12px 0', textAlign: 'center' }}>
            {error}
          </div>
        )}
        {!loading && !error && chartData.length > 0 && (
          <ResponsiveContainer width="100%" height={190}>
            <BarChart data={chartData} margin={{ top: 4, right: 4, left: -18, bottom: 0 }}>
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
                wrapperStyle={{ fontSize: 10, color: 'var(--text-muted)' }}
                formatter={(val) => CTRL_LABELS[val] || val}
              />
              {controllers.map(id => (
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
        )}
      </div>
    </Card>
  );
};

export default ControllerComparison;
