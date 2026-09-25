import React, { useState, useEffect } from 'react';
import {
  BarChart3, Activity, TrendingUp, ListTree, Gauge, Leaf, RefreshCw,
} from 'lucide-react';
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import {
  getAnalyticsSummary,
  getControllerComparison,
  getCongestionDistribution,
  getTrafficTrends,
  getControllerPerformance,
  getSimulationHistory,
} from '../services/api';
import { formatNumber, formatDecimal, formatSpeed, formatSeconds } from '../utils/formatters';
import Card       from '../components/common/Card';
import StatusBadge from '../components/common/StatusBadge';
import EmptyState  from '../components/common/EmptyState';
import KPICard     from '../components/dashboard/KPICard';

/* ── helpers ─────────────────────────────────────────────────── */
const CTRL_COLORS = { fixed: '#F3A928', adaptive: '#16D39A', dqn: '#15B8D6' };
const CTRL_LABEL  = { fixed: 'Fixed-Time', adaptive: 'Adaptive', dqn: 'DQN (AI)' };
const CONG_COLORS = {
  FREE_FLOW: '#22c55e', LOW: '#84cc16', MODERATE: '#eab308',
  HIGH: '#f97316',      SEVERE: '#ef4444',
};

const ctrlTag = (id) => (
  <span className={`controller-tag ${id}`}>{CTRL_LABEL[id] || id}</span>
);

/* Best value in a row */
const isBest = (val, rows, higherIsBetter = true) => {
  if (val == null) return false;
  const vals = rows.map(r => r.val).filter(v => v != null);
  return higherIsBetter
    ? val === Math.max(...vals)
    : val === Math.min(...vals);
};

const CustomBarTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: 'var(--surface-2)', border: '1px solid var(--border-bright)', borderRadius: 8, padding: '8px 12px', fontSize: 12 }}>
      <div style={{ color: 'var(--text-muted)', marginBottom: 4 }}>{label}</div>
      {payload.map(p => (
        <div key={p.dataKey} style={{ color: p.fill }}>
          {CTRL_LABEL[p.dataKey] || p.dataKey}: <strong>{p.value ?? '--'}</strong>
        </div>
      ))}
    </div>
  );
};

/* ── Main ────────────────────────────────────────────────────── */
const Analytics = ({ onNavigate }) => {
  const [loading,    setLoading]    = useState(true);
  const [summary,    setSummary]    = useState(null);
  const [comparison, setComparison] = useState(null);
  const [congestion, setCongestion] = useState(null);
  const [trends,     setTrends]     = useState(null);
  const [performance, setPerformance] = useState(null);
  const [history,    setHistory]    = useState([]);
  const [error,      setError]      = useState(null);

  const loadAll = async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, c, cong, t, p, h] = await Promise.all([
        getAnalyticsSummary()         .catch(() => null),
        getControllerComparison()     .catch(() => null),
        getCongestionDistribution()   .catch(() => null),
        getTrafficTrends()            .catch(() => null),
        getControllerPerformance()    .catch(() => null),
        getSimulationHistory()        .catch(() => []),
      ]);
      setSummary(s);    setComparison(c); setCongestion(cong);
      setTrends(t);     setPerformance(p); setHistory(Array.isArray(h) ? h : []);
    } catch (e) {
      setError('Failed to load analytics. Backend may be unavailable.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadAll(); }, []);

  /* ── Build chart data from comparison API ──────────────────── */
  const buildCompChart = (data) => {
    if (!data?.controllers) return [];
    const metrics = [
      { key: 'throughput',       label: 'Throughput' },
      { key: 'avg_queue',        label: 'Avg Queue'  },
      { key: 'avg_waiting_time', label: 'Avg Wait'   },
      { key: 'avg_speed',        label: 'Avg Speed'  },
    ];
    return metrics.map(({ key, label }) => {
      const row = { metric: label };
      Object.entries(data.controllers).forEach(([id, v]) => {
        row[id] = typeof v?.[key] === 'number' ? parseFloat(v[key].toFixed(2)) : null;
      });
      return row;
    });
  };

  const compChart   = buildCompChart(comparison);
  const controllers = comparison?.controllers ? Object.keys(comparison.controllers) : [];

  /* Trends line chart data */
  const trendsData = trends?.trends?.map(pt => ({
    t:           Math.round(pt.simulation_time ?? 0),
    queue:       pt.queue,
    speed:       pt.speed,
    throughput:  pt.throughput,
    waiting:     pt.waiting_time,
  })) || [];

  /* Congestion distribution bars */
  const congLevels = congestion?.congestion_levels
    ? Object.entries(congestion.congestion_levels)
    : [];
  const congTotal = congLevels.reduce((a, [, v]) => a + (v || 0), 0);

  if (loading) {
    return (
      <div className="loading-overlay">
        <div className="spinner" />
        Loading analytics data…
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: 32 }}>
        <EmptyState text={error} sub="Start a simulation to generate data." />
        <div style={{ textAlign: 'center', marginTop: 12 }}>
          <button className="btn btn-primary" onClick={loadAll} style={{ display: 'inline-flex', gap: 6 }}>
            <RefreshCw size={13} /> Retry
          </button>
        </div>
      </div>
    );
  }

  const noData = !summary && !comparison && !trends;

  return (
    <div className="analytics-grid">

      {/* ── Summary KPI row ──────────────────────────────── */}
      {summary && (
        <div className="analytics-4kpi">
          <KPICard
            label="Total Simulations"
            value={summary.total_simulations != null ? String(summary.total_simulations) : null}
            unit="runs"
            icon={Activity}
            accentColor="var(--blue)"
          />
          <KPICard
            label="Vehicles Served"
            value={summary.total_vehicles_served != null ? formatNumber(summary.total_vehicles_served) : null}
            unit="total"
            icon={TrendingUp}
            accentColor="var(--cyan)"
          />
          <KPICard
            label="Best Throughput"
            value={summary.best_throughput != null ? String(summary.best_throughput) : null}
            unit="vehicles"
            icon={Gauge}
            accentColor="var(--green)"
          />
          <KPICard
            label="Lowest Avg Queue"
            value={summary.lowest_average_queue != null ? formatDecimal(summary.lowest_average_queue, 2) : null}
            unit="vehicles"
            icon={ListTree}
            accentColor="var(--amber)"
          />
        </div>
      )}

      {noData && (
        <EmptyState
          text="No analytics data available yet"
          sub="Run at least one simulation to populate this page."
        />
      )}

      {/* ── Controller comparison bar chart ──────────────── */}
      {compChart.length > 0 && (
        <Card title="Controller Performance Comparison" titleIcon={<BarChart3 size={14} />} noPadding>
          <div style={{ padding: '8px 14px 14px' }}>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={compChart} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(122,165,210,0.1)" vertical={false} />
                <XAxis dataKey="metric" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fill: 'var(--text-muted)' }} tickLine={false} axisLine={false} />
                <Tooltip content={<CustomBarTooltip />} />
                <Legend wrapperStyle={{ fontSize: 11, color: 'var(--text-muted)' }} formatter={v => CTRL_LABEL[v] || v} />
                {controllers.map(id => (
                  <Bar key={id} dataKey={id} fill={CTRL_COLORS[id] || '#2F6BFF'} radius={[3,3,0,0]} maxBarSize={22} />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      )}

      {/* ── Detailed perf table ───────────────────────────── */}
      {performance?.controllers && (
        <Card title="Detailed Controller Metrics" titleIcon={<Activity size={14} />} noPadding>
          <div style={{ overflowX: 'auto' }}>
            <table className="perf-table">
              <thead>
                <tr>
                  <th>Controller</th>
                  <th>Throughput</th>
                  <th>Avg Queue</th>
                  <th>Avg Wait</th>
                  <th>Avg Speed</th>
                  <th>Runs</th>
                  <th>CO₂ (kg)</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(performance.controllers).map(([id, m]) => (
                  <tr key={id}>
                    <td className="controller-name">{ctrlTag(id)}</td>
                    <td style={{ color: 'var(--text-primary)', fontWeight: 600 }}>
                      {m?.throughput != null ? formatNumber(m.throughput) : '--'}
                    </td>
                    <td>{m?.avg_queue != null ? formatDecimal(m.avg_queue, 2) : '--'}</td>
                    <td>{m?.avg_waiting_time != null ? formatSeconds(m.avg_waiting_time, 1) : '--'}</td>
                    <td>{m?.avg_speed != null ? formatSpeed(m.avg_speed) : '--'}</td>
                    <td>{m?.runs ?? '--'}</td>
                    <td>{m?.avg_co2_kg != null ? formatDecimal(m.avg_co2_kg, 2) : '--'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* ── 2-col: trends + congestion ────────────────────── */}
      <div className="analytics-2col">

        {/* Traffic trends */}
        {trendsData.length > 0 && (
          <Card title="Traffic Trends" titleIcon={<TrendingUp size={14} />} noPadding>
            <div style={{ padding: '4px 12px 12px' }}>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={trendsData} margin={{ top: 4, right: 4, left: -18, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(122,165,210,0.1)" />
                  <XAxis dataKey="t" tick={{ fontSize: 10, fill: 'var(--text-muted)' }} tickLine={false} />
                  <YAxis tick={{ fontSize: 10, fill: 'var(--text-muted)' }} tickLine={false} axisLine={false} />
                  <Tooltip contentStyle={{ background: 'var(--surface-2)', border: '1px solid var(--border-bright)', borderRadius: 8, fontSize: 11 }} />
                  <Legend wrapperStyle={{ fontSize: 10 }} />
                  <Line type="monotone" dataKey="queue"      name="Queue"      stroke="var(--amber)"  strokeWidth={1.6} dot={false} isAnimationActive={false} />
                  <Line type="monotone" dataKey="speed"      name="Speed"      stroke="var(--green)"  strokeWidth={1.6} dot={false} isAnimationActive={false} />
                  <Line type="monotone" dataKey="throughput" name="Throughput" stroke="var(--cyan)"   strokeWidth={1.6} dot={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Card>
        )}

        {/* Congestion distribution */}
        {congLevels.length > 0 && (
          <Card title="Congestion Distribution" titleIcon={<Gauge size={14} />} noPadding>
            <div style={{ padding: '12px 14px' }}>
              {congLevels.map(([level, count]) => {
                const pct = congTotal > 0 ? ((count / congTotal) * 100).toFixed(1) : 0;
                return (
                  <div key={level} className="cong-bar-row">
                    <span className="cong-bar-label">{level.replace('_', ' ')}</span>
                    <div className="cong-bar-track">
                      <div
                        className="cong-bar-fill"
                        style={{ width: `${pct}%`, background: CONG_COLORS[level] || 'var(--blue)' }}
                      />
                    </div>
                    <span className="cong-bar-pct">{pct}%</span>
                  </div>
                );
              })}
            </div>
          </Card>
        )}
      </div>

      {/* ── Simulation history ───────────────────────────── */}
      {history.length > 0 && (
        <Card title="Simulation History" titleIcon={<ListTree size={14} />} noPadding>
          <div style={{ overflowX: 'auto' }}>
            <table className="reports-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Controller</th>
                  <th>Steps</th>
                  <th>Seed</th>
                  <th>Status</th>
                  <th>Throughput</th>
                  <th>Avg Queue</th>
                  <th>Avg Wait</th>
                </tr>
              </thead>
              <tbody>
                {history.slice(0, 20).map((sim) => (
                  <tr key={sim.simulation_id || sim._id}>
                    <td style={{ color: 'var(--text-muted)', fontSize: 10.5, fontFamily: 'monospace' }}>
                      {(sim.simulation_id || sim._id || '').slice(0, 10)}…
                    </td>
                    <td>{ctrlTag(sim.controller)}</td>
                    <td>{sim.steps ?? '--'}</td>
                    <td>{sim.seed  ?? '--'}</td>
                    <td>
                      <StatusBadge variant={sim.status === 'completed' ? 'green' : sim.status === 'error' ? 'red' : 'gray'}>
                        {sim.status || 'unknown'}
                      </StatusBadge>
                    </td>
                    <td>{sim.metrics?.total_vehicles_served != null ? formatNumber(sim.metrics.total_vehicles_served) : '--'}</td>
                    <td>{sim.metrics?.average_queue         != null ? formatDecimal(sim.metrics.average_queue, 2)     : '--'}</td>
                    <td>{sim.metrics?.average_waiting_time  != null ? formatSeconds(sim.metrics.average_waiting_time, 1) : '--'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

    </div>
  );
};

export default Analytics;
