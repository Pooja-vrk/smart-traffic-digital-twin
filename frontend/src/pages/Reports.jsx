import React, { useState, useEffect } from 'react';
import { FileText, RefreshCw, Download } from 'lucide-react';
import { getSimulationHistory, getSimulationDetail } from '../services/api';
import { formatNumber, formatDecimal, formatSpeed, formatSeconds } from '../utils/formatters';
import Card       from '../components/common/Card';
import StatusBadge from '../components/common/StatusBadge';
import EmptyState  from '../components/common/EmptyState';

const ctrlTag = (id) => {
  const map = { fixed: 'Fixed-Time', adaptive: 'Adaptive', dqn: 'DQN (AI)' };
  return <span className={`controller-tag ${id}`}>{map[id] || id || '--'}</span>;
};

const fmt = (v, fn) => (v != null ? fn(v) : '--');

const Reports = () => {
  const [history, setHistory]   = useState([]);
  const [loading, setLoading]   = useState(true);
  const [error,   setError]     = useState(null);
  const [selected, setSelected] = useState(null);
  const [detail,  setDetail]    = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getSimulationHistory({ limit: 50 });
      setHistory(Array.isArray(data) ? data : []);
    } catch {
      setError('Unable to load simulation history. Backend may be offline.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleSelect = async (sim) => {
    setSelected(sim);
    setDetail(null);
    setDetailLoading(true);
    try {
      const d = await getSimulationDetail(sim.simulation_id || sim._id);
      setDetail(d);
    } catch {
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

      {/* Header actions */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
        <button className="btn btn-primary" onClick={load} disabled={loading}
          style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 14px' }}>
          <RefreshCw size={13} />
          Refresh
        </button>
      </div>

      {loading && (
        <div className="loading-overlay"><div className="spinner" /> Loading reports…</div>
      )}

      {error && !loading && (
        <EmptyState icon={FileText} text={error} sub="Ensure the backend is running and MongoDB is connected." />
      )}

      {!loading && !error && history.length === 0 && (
        <EmptyState
          icon={FileText}
          text="No simulation reports yet"
          sub="Complete at least one simulation to generate a report."
        />
      )}

      {!loading && history.length > 0 && (
        <Card title="Simulation Reports" titleIcon={<FileText size={14} />} noPadding>
          <div style={{ overflowX: 'auto' }}>
            <table className="reports-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Simulation ID</th>
                  <th>Controller</th>
                  <th>Seed</th>
                  <th>Duration</th>
                  <th>Status</th>
                  <th>Throughput</th>
                  <th>Avg Queue</th>
                  <th>Avg Wait</th>
                  <th>Avg Speed</th>
                  <th>CO₂ (kg)</th>
                  <th>Completed</th>
                </tr>
              </thead>
              <tbody>
                {history.map((sim, i) => {
                  const id  = sim.simulation_id || sim._id || '';
                  const m   = sim.metrics || {};
                  const isSelected = selected && (selected.simulation_id || selected._id) === id;
                  return (
                    <tr
                      key={id}
                      onClick={() => handleSelect(sim)}
                      style={{
                        cursor: 'pointer',
                        background: isSelected ? 'rgba(47,107,255,0.07)' : undefined,
                      }}
                    >
                      <td style={{ color: 'var(--text-muted)', fontSize: 11 }}>{i + 1}</td>
                      <td style={{ fontSize: 10.5, fontFamily: 'monospace', color: 'var(--text-muted)' }}>
                        {id.slice(0, 12)}…
                      </td>
                      <td>{ctrlTag(sim.controller)}</td>
                      <td>{sim.seed  ?? '--'}</td>
                      <td>{sim.steps != null ? `${sim.steps}s` : '--'}</td>
                      <td>
                        <StatusBadge
                          variant={
                            sim.status === 'completed' ? 'green' :
                            sim.status === 'error'     ? 'red'   :
                            sim.status === 'stopped'   ? 'amber' : 'gray'
                          }
                        >
                          {sim.status || 'unknown'}
                        </StatusBadge>
                      </td>
                      <td style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                        {fmt(m.total_vehicles_served, formatNumber)}
                      </td>
                      <td>{fmt(m.average_queue,         v => formatDecimal(v, 2))}</td>
                      <td>{fmt(m.average_waiting_time,  v => formatSeconds(v, 1))}</td>
                      <td>{fmt(m.average_speed,         formatSpeed)}</td>
                      <td>{m.total_co2_emission_kg != null ? formatDecimal(m.total_co2_emission_kg, 2) : '--'}</td>
                      <td style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                        {sim.completed_at
                          ? new Date(sim.completed_at).toLocaleDateString()
                          : '--'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Detail panel */}
      {selected && (
        <Card
          title={`Report Detail — ${(selected.simulation_id || selected._id || '').slice(0, 16)}…`}
          titleIcon={<FileText size={14} />}
          badge={ctrlTag(selected.controller)}
          noPadding
        >
          <div style={{ padding: '12px 14px' }}>
            {detailLoading && (
              <div className="loading-overlay" style={{ padding: 24 }}>
                <div className="spinner" /> Loading detail…
              </div>
            )}

            {!detailLoading && !detail && (
              <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                Detailed data not available for this simulation.
              </div>
            )}

            {!detailLoading && detail && (
              <div>
                {/* Metadata row */}
                <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 12, fontSize: 12, color: 'var(--text-muted)' }}>
                  <span>ID: <strong style={{ color: 'var(--text-secondary)' }}>{detail.simulation_id}</strong></span>
                  <span>Controller: <strong style={{ color: 'var(--cyan)' }}>{detail.controller}</strong></span>
                  <span>Steps: <strong style={{ color: 'var(--text-secondary)' }}>{detail.steps}</strong></span>
                  <span>Seed: <strong style={{ color: 'var(--text-secondary)' }}>{detail.seed}</strong></span>
                  <span>Status: <StatusBadge variant={detail.status === 'completed' ? 'green' : 'gray'}>{detail.status}</StatusBadge></span>
                </div>

                {/* Metrics grid */}
                {detail.metrics && (
                  <div className="sim-results-grid" style={{ gridTemplateColumns: 'repeat(4,1fr)' }}>
                    {[
                      ['Throughput',   formatNumber(detail.metrics.total_vehicles_served), 'var(--cyan)'],
                      ['Avg Queue',    formatDecimal(detail.metrics.average_queue, 2),     'var(--amber)'],
                      ['Avg Wait',     formatSeconds(detail.metrics.average_waiting_time, 1), 'var(--purple)'],
                      ['Avg Speed',    formatSpeed(detail.metrics.average_speed),           'var(--green)'],
                      ['CO₂ (kg)',
                        detail.metrics.total_co2_emission_kg != null
                          ? formatDecimal(detail.metrics.total_co2_emission_kg, 2) : '--',
                        'var(--text-primary)'],
                    ].map(([lbl, val, col]) => (
                      <div key={lbl} className="result-stat">
                        <div className="result-stat-label">{lbl}</div>
                        <div className="result-stat-val" style={{ color: col }}>{val}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </Card>
      )}
    </div>
  );
};

export default Reports;
