import React, { useState, useEffect } from 'react';
import {
  Activity, ClipboardList, BarChart2,
  Car, ListTree, Clock, Gauge, Leaf,
} from 'lucide-react';
import { useTrafficWebSocket } from '../hooks/useTrafficWebSocket';
import { getHealth, getSimulationResult } from '../services/api';
import {
  formatNumber, formatSpeed, formatDecimal, formatSeconds,
  calculateCongestionScore,
} from '../utils/formatters';

import Card               from '../components/common/Card';
import StatusBadge        from '../components/common/StatusBadge';
import SimulationControl  from '../components/dashboard/SimulationControl';
import SystemStatus       from '../components/dashboard/SystemStatus';
import DigitalTwinIntersection from '../components/dashboard/DigitalTwinIntersection';
import AgentStatus        from '../components/dashboard/AgentStatus';
import TrafficMetricsChart from '../components/dashboard/TrafficMetricsChart';
import LiveTrafficFeed    from '../components/dashboard/LiveTrafficFeed';
import RecentEvents       from '../components/dashboard/RecentEvents';
import AIDecisionHistory    from '../components/dashboard/AIDecisionHistory';

import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer,
} from 'recharts';

const MAX_HISTORY = 150;

/* ── small helper components ─────────────────────────────── */
const MetricTile = ({ label, value, color = 'var(--text-primary)' }) => (
  <div style={{
    background: 'var(--surface-2)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-sm)',
    padding: '10px 12px',
  }}>
    <div style={{ fontSize: 10.5, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 600, marginBottom: 4 }}>
      {label}
    </div>
    <div style={{ fontSize: 20, fontWeight: 700, color, fontVariantNumeric: 'tabular-nums' }}>
      {value}
    </div>
  </div>
);

const MiniChart = ({ data, dataKey, color, label, unit }) => (
  <Card title={label} noPadding>
    <div style={{ padding: '4px 12px 10px' }}>
      {data.length === 0 ? (
        <div style={{ height: 100, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, color: 'var(--text-muted)' }}>
          No data yet
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={110}>
          <LineChart data={data} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(122,165,210,0.1)" />
            <XAxis dataKey="t" tick={{ fontSize: 9, fill: 'var(--text-muted)' }} tickLine={false} />
            <YAxis tick={{ fontSize: 9, fill: 'var(--text-muted)' }} tickLine={false} axisLine={false} />
            <Tooltip
              contentStyle={{ background: 'var(--surface-2)', border: '1px solid var(--border-bright)', borderRadius: 6, fontSize: 11 }}
              itemStyle={{ color }}
            />
            <Line type="monotone" dataKey={dataKey} stroke={color} strokeWidth={1.8} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  </Card>
);

/* ── Main page ─────────────────────────────────────────────── */
const Simulation = () => {
  const { isConnected, simulationStatus, trafficData, aiDecisions, startStopPoll } = useTrafficWebSocket();

  const [health,  setHealth]  = useState(null);
  const [result,  setResult]  = useState(null);
  const [history, setHistory] = useState([]);
  const [logs,    setLogs]    = useState([]);

  /* Health */
  useEffect(() => {
    const load = async () => {
      try { setHealth(await getHealth()); } catch { /* silent */ }
    };
    load();
    const id = setInterval(load, 30_000);
    return () => clearInterval(id);
  }, []);

  /* Build chart history */
  useEffect(() => {
    if (!trafficData || !simulationStatus?.running) return;
    setHistory(prev => {
      const t = trafficData.simulation_time != null
        ? Math.round(trafficData.simulation_time) : prev.length;
      const point = {
        t,
        simulation_time: trafficData.simulation_time ?? prev.length,
        queue:           trafficData.queues?.total              ?? 0,
        waiting_time:    trafficData.waiting?.average_seconds   ?? 0,
        throughput:      trafficData.vehicles?.completed        ?? 0,
        speed:           trafficData.speed?.average_mps         ?? 0,
        congestion:      calculateCongestionScore(trafficData.queues, trafficData.waiting, trafficData.speed) ?? 0,
      };
      return [...prev, point].slice(-MAX_HISTORY);
    });

    /* Append to event log */
    const ai = trafficData?.ai;
    if (ai?.action) {
      const ts = new Date().toLocaleTimeString(undefined, { hour12: false });
      setLogs(prev => [
        { id: Date.now(), ts, type: 'ai',  msg: `DQN → ${ai.action}${ai.approved === false ? ' (restricted)' : ''}` },
        ...prev,
      ].slice(0, 60));
    }
  }, [trafficData, simulationStatus?.running]);

  /* Fetch result when sim ends */
  useEffect(() => {
    if (!simulationStatus?.running && simulationStatus?.status) {
      getSimulationResult().then(setResult).catch(() => setResult(null));
    }
  }, [simulationStatus?.running, simulationStatus?.status]);

  const handleSimStart = () => {
    setHistory([]);
    setResult(null);
    setLogs([]);
  };

  /* ── derived live metrics ──────────────────────────────── */
  const v = trafficData?.vehicles || {};
  const q = trafficData?.queues   || {};
  const s = trafficData?.speed    || {};
  const w = trafficData?.waiting  || {};

  const isRunning = simulationStatus?.running || false;
  const pct = simulationStatus?.current_step != null && simulationStatus?.total_steps
    ? Math.min(100, Math.round((simulationStatus.current_step / simulationStatus.total_steps) * 100))
    : 0;

  return (
    <div>
      {/* ── 2-col layout ────────────────────────────────── */}
      <div className="sim-2col">

        {/* LEFT panel */}
        <div className="sim-left">
          <SimulationControl
            simulationStatus={simulationStatus}
            onStart={handleSimStart}
            startStopPoll={startStopPoll}
          />
          <SystemStatus
            backend={health ? health.status !== 'error' : null}
            websocket={isConnected}
            mongodb={health?.mongodb_available}
          />
          <AgentStatus
            simulationStatus={simulationStatus}
            trafficData={trafficData}
          />
          <RecentEvents />
        </div>

        {/* RIGHT panel */}
        <div className="sim-right">

          {/* Progress bar when running */}
          {isRunning && (
            <Card noPadding>
              <div style={{ padding: '10px 14px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6, fontSize: 12 }}>
                  <span style={{ color: 'var(--text-secondary)', fontWeight: 600 }}>
                    Simulation Progress
                  </span>
                  <span style={{ color: 'var(--cyan)', fontVariantNumeric: 'tabular-nums' }}>
                    {simulationStatus.current_step ?? 0} / {simulationStatus.total_steps ?? '?'} s
                    {' '}({pct}%)
                  </span>
                </div>
                <div style={{ height: 5, background: 'var(--surface-2)', borderRadius: 3, overflow: 'hidden' }}>
                  <div style={{
                    height: '100%',
                    width: `${pct}%`,
                    background: 'linear-gradient(90deg, var(--blue), var(--cyan))',
                    borderRadius: 3,
                    transition: 'width 0.4s ease',
                  }} />
                </div>
              </div>
            </Card>
          )}

          {/* Digital Twin */}
          <DigitalTwinIntersection
            trafficData={trafficData}
            simulationStatus={simulationStatus}
          />

          {/* Live metrics tiles */}
          <Card title="Live Traffic Metrics" titleIcon={<Activity size={14} />} noPadding>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 8, padding: '0 14px 14px' }}>
              <MetricTile label="Active Vehicles"  value={formatNumber(v.total)}          color="var(--blue)"   />
              <MetricTile label="Processed"         value={formatNumber(v.completed)}      color="var(--cyan)"   />
              <MetricTile label="Total Queue"       value={q.total ?? '--'}                color="var(--amber)"  />
              <MetricTile label="Avg Speed"         value={formatSpeed(s.average_mps)}     color="var(--green)"  />
              <MetricTile label="Avg Wait"          value={formatSeconds(w.average_seconds, 1)} color="var(--purple)" />
            </div>
          </Card>

          {/* Multi-series chart */}
          <TrafficMetricsChart history={history} isLive={isRunning} />

          {/* 2×2 mini charts */}
          {history.length > 0 && (
            <div className="sim-charts-grid">
              <MiniChart data={history} dataKey="queue"      color="var(--amber)"  label="Queue Length"    unit="veh" />
              <MiniChart data={history} dataKey="speed"      color="var(--green)"  label="Avg Speed"       unit="m/s" />
              <MiniChart data={history} dataKey="throughput" color="var(--cyan)"   label="Throughput"      unit="veh" />
              <MiniChart data={history} dataKey="congestion" color="var(--red)"    label="Congestion Score" unit="score" />
            </div>
          )}

          {/* Live feed table */}
          <LiveTrafficFeed trafficData={trafficData} />

          {/* Simulation result */}
          {result && (
            <Card
              title="Simulation Results"
              titleIcon={<ClipboardList size={14} />}
              badge={
                <StatusBadge variant="green">Completed</StatusBadge>
              }
              noPadding
            >
              <div style={{ padding: '12px 14px' }}>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
                  <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                    ID: <strong style={{ color: 'var(--text-secondary)' }}>{result.simulation_id?.slice(0, 12)}…</strong>
                  </span>
                  <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                    Controller: <strong style={{ color: 'var(--cyan)' }}>{result.controller}</strong>
                  </span>
                  <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                    Duration: <strong style={{ color: 'var(--text-secondary)' }}>{result.steps}s</strong>
                  </span>
                </div>
                {result.metrics && (
                  <div className="sim-results-grid">
                    <div className="result-stat">
                      <div className="result-stat-label">Vehicles Served</div>
                      <div className="result-stat-val">{formatNumber(result.metrics.total_vehicles_served)}</div>
                    </div>
                    <div className="result-stat">
                      <div className="result-stat-label">Avg Queue</div>
                      <div className="result-stat-val">{formatDecimal(result.metrics.average_queue, 2)}</div>
                    </div>
                    <div className="result-stat">
                      <div className="result-stat-label">Avg Wait</div>
                      <div className="result-stat-val">{formatSeconds(result.metrics.average_waiting_time, 1)}</div>
                    </div>
                    <div className="result-stat">
                      <div className="result-stat-label">Avg Speed</div>
                      <div className="result-stat-val">{formatSpeed(result.metrics.average_speed)}</div>
                    </div>
                    <div className="result-stat">
                      <div className="result-stat-label">CO₂ Emission</div>
                      <div className="result-stat-val">
                        {result.metrics.total_co2_emission_kg != null
                          ? `${formatDecimal(result.metrics.total_co2_emission_kg, 2)} kg`
                          : '--'}
                      </div>
                    </div>
                    <div className="result-stat" style={{ gridColumn: '3' }}>
                      <div className="result-stat-label">Throughput</div>
                      <div className="result-stat-val" style={{ color: 'var(--green)' }}>
                        {formatNumber(result.metrics.total_vehicles_served)}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </Card>
          )}

          {/* AI Decision History */}
          <AIDecisionHistory
            decisions={aiDecisions}
            isRunning={simulationStatus?.running}
          />

        </div>
      </div>
    </div>
  );
};

export default Simulation;
