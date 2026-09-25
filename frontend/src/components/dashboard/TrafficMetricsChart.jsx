import React from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import { Activity } from 'lucide-react';
import Card from '../common/Card';

const SERIES = [
  { key: 'queue',        name: 'Queue',       color: '#F3A928', unit: 'veh' },
  { key: 'waiting_time', name: 'Wait Time',   color: '#A855F7', unit: 's'   },
  { key: 'throughput',   name: 'Throughput',  color: '#16D39A', unit: 'veh' },
];

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
      <div style={{ color: 'var(--text-muted)', marginBottom: 4 }}>
        t = {label}s
      </div>
      {payload.map(p => (
        <div key={p.dataKey} style={{ color: p.color, fontVariantNumeric: 'tabular-nums' }}>
          {p.name}: <strong>{typeof p.value === 'number' ? p.value.toFixed(1) : '--'}</strong>
        </div>
      ))}
    </div>
  );
};

/**
 * Props:
 *   history   – array of { simulation_time, queue, waiting_time, throughput }
 *   isLive    – bool
 */
const TrafficMetricsChart = ({ history = [], isLive = false }) => {
  const chartData = history.map(pt => ({
    time:        typeof pt.simulation_time === 'number' ? Math.round(pt.simulation_time) : pt.simulation_time,
    queue:       pt.queue,
    waiting_time: pt.waiting_time,
    throughput:  pt.throughput,
  }));

  const badge = isLive ? (
    <div style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--green)' }}>
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--green)', display: 'inline-block' }} />
      Live
    </div>
  ) : null;

  return (
    <Card
      title="Traffic Metrics"
      titleIcon={<Activity size={14} />}
      badge={badge}
      noPadding
    >
      {/* Legend */}
      <div className="chart-legend-row">
        {SERIES.map(s => (
          <div key={s.key} className="chart-legend-item">
            <span className="chart-legend-dot" style={{ background: s.color }} />
            {s.name}
          </div>
        ))}
      </div>

      <div className="metrics-chart-body" style={{ marginTop: 4 }}>
        {chartData.length === 0 ? (
          <div style={{
            height: 180,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--text-muted)',
            fontSize: 12,
          }}>
            Waiting for simulation data…
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={chartData} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(122,165,210,0.1)" />
              <XAxis
                dataKey="time"
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
              {SERIES.map(s => (
                <Line
                  key={s.key}
                  type="monotone"
                  dataKey={s.key}
                  name={s.name}
                  stroke={s.color}
                  strokeWidth={1.8}
                  dot={false}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </Card>
  );
};

export default TrafficMetricsChart;
