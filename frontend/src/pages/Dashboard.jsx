import React, { useState, useEffect } from 'react';
import { Car, ListTree, Clock, Gauge, Leaf, Play } from 'lucide-react';
import { useTrafficWebSocket } from '../hooks/useTrafficWebSocket';
import { getHealth } from '../services/api';
import { calculateCongestionScore, formatDecimal } from '../utils/formatters';

// Layout / Common
import KPICard              from '../components/dashboard/KPICard';
import SimulationControl    from '../components/dashboard/SimulationControl';
import SystemStatus         from '../components/dashboard/SystemStatus';
import DigitalTwinIntersection from '../components/dashboard/DigitalTwinIntersection';
import TrafficMetricsChart  from '../components/dashboard/TrafficMetricsChart';
import ControllerComparison from '../components/dashboard/ControllerComparison';
import RecentEvents         from '../components/dashboard/RecentEvents';
import LiveTrafficFeed      from '../components/dashboard/LiveTrafficFeed';
import AgentStatus          from '../components/dashboard/AgentStatus';
import AIDecisionHistory    from '../components/dashboard/AIDecisionHistory';
import OfflineReplayModal   from '../components/dashboard/OfflineReplayModal';

const MAX_HISTORY = 120;

const Dashboard = ({ onNavigate }) => {
  const { isConnected, simulationStatus, trafficData, aiDecisions, startStopPoll } = useTrafficWebSocket();

  const [health,  setHealth]  = useState(null);
  const [history, setHistory] = useState([]);
  const [replaySimulationId, setReplaySimulationId] = useState(null);


  /* Health polling */
  useEffect(() => {
    const load = async () => {
      try { setHealth(await getHealth()); } catch { /* silent */ }
    };
    load();
    const id = setInterval(load, 30_000);
    return () => clearInterval(id);
  }, []);

  /* Build live chart history from WS telemetry */
  useEffect(() => {
    if (!trafficData || !simulationStatus?.running) return;
    setHistory(prev => {
      const point = {
        simulation_time: trafficData.simulation_time ?? prev.length,
        queue:           trafficData.queues?.total    ?? 0,
        waiting_time:    trafficData.waiting?.average_seconds ?? 0,
        throughput:      trafficData.vehicles?.completed      ?? 0,
        speed:           trafficData.speed?.average_mps       ?? 0,
      };
      return [...prev, point].slice(-MAX_HISTORY);
    });
  }, [trafficData, simulationStatus?.running]);

  /* Clear history when a new simulation starts */
  const handleSimStart = () => setHistory([]);

  /* ── Derived KPI values ─────────────────────────────── */
  const vehicles  = trafficData?.vehicles;
  const queues    = trafficData?.queues;
  const speed     = trafficData?.speed;
  const waiting   = trafficData?.waiting;

  const totalVehicles = vehicles?.total != null ? String(vehicles.total) : null;

  const avgQueue = queues?.total != null
    ? formatDecimal(queues.total / 4, 1)
    : null;

  const avgWait = waiting?.average_seconds != null
    ? formatDecimal(waiting.average_seconds, 1)
    : null;

  const avgSpeed = speed?.average_mps != null
    ? formatDecimal(speed.average_mps, 1)
    : null;

  /* CO₂ proxy – only shown when a result metric is available live.
     The backend sends total_co2_emission_kg in simulation results;
     during live running we derive a rough proxy from speed / queue. */
  const co2 = trafficData?.co2_emission_kg != null
    ? formatDecimal(trafficData.co2_emission_kg, 1)
    : null;

  const isLive = simulationStatus?.running || false;

  return (
    <div>
      {/* ── KPI row ─────────────────────────────────────── */}
      <div className="kpi-row">
        <KPICard
          label="Total Vehicles"
          value={totalVehicles}
          unit={vehicles?.completed != null ? `${vehicles.completed} processed` : 'Vehicles Active'}
          icon={Car}
          accentColor="var(--blue)"
          waiting="Waiting for simulation"
        />
        <KPICard
          label="Avg Queue Length"
          value={avgQueue}
          unit="vehicles / approach"
          icon={ListTree}
          accentColor="var(--cyan)"
          waiting="Waiting for simulation"
        />
        <KPICard
          label="Avg Waiting Time"
          value={avgWait}
          unit="seconds"
          icon={Clock}
          accentColor="var(--purple)"
          waiting="Waiting for simulation"
        />
        <KPICard
          label="Avg Speed"
          value={avgSpeed}
          unit="m / s"
          icon={Gauge}
          accentColor="var(--amber)"
          waiting="Waiting for simulation"
        />
        <KPICard
          label="CO₂ Proxy"
          value={co2}
          unit="kg (estimated)"
          icon={Leaf}
          accentColor="var(--green)"
          waiting="Available post-simulation"
        />
      </div>

      {/* ── 3-column main grid ───────────────────────────── */}
      <div className="dashboard-3col">

        {/* ── LEFT column ─────────────────────────────────── */}
        <div className="dashboard-left">
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
        </div>

        {/* ── CENTER column ───────────────────────────────── */}
        <div className="dashboard-center">
          {simulationStatus?.simulation_id && !simulationStatus?.running && (
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 6 }}>
              <button
                onClick={() => setReplaySimulationId(simulationStatus.simulation_id)}
                className="btn btn-secondary"
                style={{
                  fontSize: 11,
                  padding: '3px 10px',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 5,
                  borderColor: 'var(--cyan)',
                  color: 'var(--cyan)',
                }}
              >
                <Play size={11} /> Replay Session Offline
              </button>
            </div>
          )}
          <DigitalTwinIntersection
            trafficData={trafficData}
            simulationStatus={simulationStatus}
          />
          <AIDecisionHistory
            decisions={aiDecisions}
            isRunning={simulationStatus?.running}
            simulationId={simulationStatus?.simulation_id}
          />
          <LiveTrafficFeed trafficData={trafficData} />
        </div>

        {/* ── RIGHT column ────────────────────────────────── */}
        <div className="dashboard-right">
          <TrafficMetricsChart
            history={history}
            isLive={isLive}
          />
          <ControllerComparison
            onNavigateAnalytics={() => onNavigate && onNavigate('analytics')}
            refreshTrigger={simulationStatus?.status}
          />
          <RecentEvents />
        </div>

      </div>

      {/* Offline Replay Modal */}
      {replaySimulationId && (
        <OfflineReplayModal
          simulationId={replaySimulationId}
          onClose={() => setReplaySimulationId(null)}
        />
      )}
    </div>
  );
};

export default Dashboard;
