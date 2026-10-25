import React, { useState, useEffect, useMemo } from 'react';
import {
  FlaskConical, Play, Square, RefreshCw, BarChart3,
  Layers, Sliders, Shield, AlertTriangle, CheckCircle2,
  Car, Clock, Gauge, Leaf, Zap, ChevronRight, History,
  ArrowRightLeft, ArrowUp, ArrowDown, ArrowLeft, ArrowRight,
  TrendingDown, TrendingUp, Sparkles, Siren
} from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend
} from 'recharts';

import { useTrafficWebSocket } from '../hooks/useTrafficWebSocket';
import {
  getScenarioPresets, runScenario, stopScenario,
  getScenarioStatus, getLatestScenarioResult,
  getScenarioResult, getScenarioHistory, getHealth,
  getPredictionStatus
} from '../services/api';
import {
  formatNumber, formatSpeed, formatDecimal, formatSeconds
} from '../utils/formatters';

import Card from '../components/common/Card';
import StatusBadge from '../components/common/StatusBadge';
import DigitalTwinIntersection from '../components/dashboard/DigitalTwinIntersection';
import AgentStatus from '../components/dashboard/AgentStatus';
import AIDecisionHistory from '../components/dashboard/AIDecisionHistory';
import OfflineReplayModal from '../components/dashboard/OfflineReplayModal';


const DENSITY_OPTIONS = [
  { id: 'low',       label: 'Low (0.5×)',       multiplier: 0.5 },
  { id: 'medium',    label: 'Medium (1.0×)',    multiplier: 1.0 },
  { id: 'high',      label: 'High (1.5×)',      multiplier: 1.5 },
  { id: 'very_high', label: 'Peak (2.0×)',      multiplier: 2.0 },
  { id: 'custom',    label: 'Custom Multiplier', multiplier: 1.0 },
];

const CONTROLLER_OPTIONS = [
  { id: 'dqn',      label: 'DQN (Reinforcement Learning)', badge: 'AI Agent' },
  { id: 'adaptive', label: 'Rule-Based Adaptive',         badge: 'Dynamic'  },
  { id: 'fixed',    label: 'Fixed-Time Baseline',          badge: 'Static'   },
];

const MetricTile = ({ label, value, color = 'var(--text-primary)', sub = null }) => (
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
    {sub && (
      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
        {sub}
      </div>
    )}
  </div>
);

const ScenarioLab = ({ onNavigate }) => {
  const { isConnected, trafficData, aiDecisions } = useTrafficWebSocket();

  // Presets & Form state
  const [presets, setPresets] = useState([]);
  const [selectedPresetId, setSelectedPresetId] = useState('balanced');
  const [scenarioName, setScenarioName] = useState('Balanced / Normal Traffic');
  const [density, setDensity] = useState('medium');
  const [customMultiplier, setCustomMultiplier] = useState(1.0);
  const [directionBias, setDirectionBias] = useState({ north: 25, south: 25, east: 25, west: 25 });
  const [controller, setController] = useState('dqn');
  const [duration, setDuration] = useState(300);
  const [seed, setSeed] = useState(42);
  const [compareAll, setCompareAll] = useState(false);

  const [emergencyVehicle, setEmergencyVehicle] = useState(false);
  const [emergencyApproach, setEmergencyApproach] = useState('east');
  const [emergencyStep, setEmergencyStep] = useState(15);
  const [emergencyVehicleType, setEmergencyVehicleType] = useState('ambulance');

  // Runtime & Results state
  const [scenarioStatus, setScenarioStatus] = useState(null);
  const [result, setResult] = useState(null);
  const [history, setHistory] = useState([]);
  const [showHistory, setShowHistory] = useState(false);
  const [loading, setLoading] = useState(false);
  const [errorBanner, setErrorBanner] = useState(null);
  const [predictionStatus, setPredictionStatus] = useState(null);
  const [replaySimulationId, setReplaySimulationId] = useState(null);

  // Direction sum validation
  const directionSum = useMemo(() => {
    return Math.round((Number(directionBias.north || 0) + Number(directionBias.south || 0) + Number(directionBias.east || 0) + Number(directionBias.west || 0)) * 10) / 10;
  }, [directionBias]);

  const isDirectionSumValid = Math.abs(directionSum - 100.0) <= 0.2;

  // Load Presets, History & Prediction Model Status on mount
  useEffect(() => {
    const fetchInitial = async () => {
      try {
        const pList = await getScenarioPresets();
        setPresets(pList || []);
      } catch (err) {
        console.warn('Failed to load scenario presets:', err);
      }
      try {
        const hist = await getScenarioHistory({ limit: 20 });
        setHistory(hist || []);
      } catch (err) {
        console.warn('Failed to load scenario history:', err);
      }
      try {
        const ps = await getPredictionStatus();
        setPredictionStatus(ps);
      } catch (err) {
        console.warn('Failed to load prediction status:', err);
      }
    };
    fetchInitial();
  }, []);

  // Poll Scenario Status while active
  useEffect(() => {
    let intervalId = null;
    const pollStatus = async () => {
      try {
        const st = await getScenarioStatus();
        setScenarioStatus(st);
        if (st.status === 'completed' && !result) {
          const res = await getLatestScenarioResult();
          setResult(res);
          const hist = await getScenarioHistory({ limit: 20 });
          setHistory(hist || []);
        }
      } catch {
        // silent polling catch
      }
    };

    pollStatus();
    intervalId = setInterval(pollStatus, 1000);
    return () => clearInterval(intervalId);
  }, [result]);

  // Apply Preset
  const handleSelectPreset = (p) => {
    setSelectedPresetId(p.id);
    setScenarioName(p.name);
    setDensity(p.density);
    setCustomMultiplier(p.multiplier);
    setDirectionBias({
      north: p.direction_bias.north,
      south: p.direction_bias.south,
      east: p.direction_bias.east,
      west: p.direction_bias.west,
    });
    setDuration(p.recommended_duration || 300);
    if (p.emergency_vehicle !== undefined) {
      setEmergencyVehicle(Boolean(p.emergency_vehicle));
      if (p.emergency_approach) setEmergencyApproach(p.emergency_approach);
      if (p.emergency_step) setEmergencyStep(p.emergency_step);
      if (p.emergency_vehicle_type) setEmergencyVehicleType(p.emergency_vehicle_type);
    } else {
      setEmergencyVehicle(false);
    }
    setErrorBanner(null);
  };

  // Adjust direction sliders
  const handleDirectionChange = (dir, val) => {
    setSelectedPresetId('custom');
    const num = Math.max(0, Math.min(100, Number(val)));
    setDirectionBias(prev => ({ ...prev, [dir]: num }));
  };

  // Run Scenario
  const handleRun = async (overrideCompare = null, forceEmergency = false) => {
    if (!isDirectionSumValid) {
      setErrorBanner('Directional distribution percentages must sum to 100%. Current sum: ' + directionSum + '%');
      return;
    }
    setErrorBanner(null);
    setLoading(true);
    setResult(null);

    const isComp = overrideCompare !== null ? overrideCompare : compareAll;
    const isEv = forceEmergency ? true : emergencyVehicle;

    const payload = {
      name: scenarioName || 'Custom Scenario',
      density,
      multiplier: density === 'custom' ? Number(customMultiplier) : undefined,
      direction_bias: {
        north: Number(directionBias.north),
        south: Number(directionBias.south),
        east: Number(directionBias.east),
        west: Number(directionBias.west),
      },
      controller,
      duration: Number(duration),
      seed: Number(seed),
      compare_all_controllers: isComp,
      emergency_vehicle: isEv,
      emergency_vehicle_type: emergencyVehicleType || 'ambulance',
      emergency_approach: emergencyApproach,
      emergency_step: Number(emergencyStep),
    };

    try {
      const resp = await runScenario(payload);
      setScenarioStatus(resp);
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || 'Failed to start scenario';
      setErrorBanner(msg);
    } finally {
      setLoading(false);
    }
  };

  // Stop Scenario
  const handleStop = async () => {
    try {
      const resp = await stopScenario();
      setScenarioStatus(resp);
    } catch (err) {
      console.error('Failed to stop scenario:', err);
    }
  };

  // Status mapping for badge
  const isRunning = scenarioStatus?.running || false;
  const statusLabel = scenarioStatus?.status ? scenarioStatus.status.toUpperCase() : 'CONFIGURING';
  const statusVariant = isRunning
    ? 'blue'
    : (scenarioStatus?.status === 'completed'
      ? 'green'
      : (scenarioStatus?.status === 'failed' ? 'red' : 'neutral'));

  // Live traffic metrics from digital twin
  const v = trafficData?.vehicles || {};
  const q = trafficData?.queues   || {};
  const s = trafficData?.speed    || {};
  const w = trafficData?.waiting  || {};
  const pred = trafficData?.prediction || null;

  // Build Recharts comparison dataset if comparison results exist
  const comparisonChartData = useMemo(() => {
    if (!result?.comparison) return [];
    const comp = result.comparison;
    const entries = Object.keys(comp).map(key => {
      const c = comp[key];
      const m = c.metrics || {};
      return {
        controller: c.label || key.toUpperCase(),
        throughput: m.total_vehicles_served ?? m.throughput ?? 0,
        average_queue: m.average_queue ?? 0,
        peak_queue: m.max_queue ?? m.peak_queue ?? 0,
        average_waiting_time: m.average_waiting_time ?? m.average_wait ?? 0,
        average_speed: m.average_speed ?? 0,
        co2_kg: m.total_co2_emission_kg ?? 0,
      };
    });
    return entries;
  }, [result]);

  return (
    <div className="scenario-lab-page" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* ── Top Header & Presets ────────────────────────── */}
      <div style={{
        background: 'var(--surface-1)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        padding: '16px 20px',
        display: 'flex',
        flexDirection: 'column',
        gap: 12
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{ background: 'rgba(56, 189, 248, 0.15)', padding: 6, borderRadius: 6, color: 'var(--cyan)' }}>
                <FlaskConical size={18} />
              </div>
              <h1 style={{ fontSize: 18, fontWeight: 700, margin: 0, color: 'var(--text-primary)' }}>
                Scenario / What-If Lab
              </h1>
              <StatusBadge variant={statusVariant}>
                {statusLabel}
              </StatusBadge>
            </div>
            <p style={{ margin: '4px 0 0', fontSize: 12, color: 'var(--text-secondary)' }}>
              Configure micro-simulation traffic demand and evaluate controller performance through the real SUMO Digital Twin.
            </p>
          </div>

          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={() => setShowHistory(h => !h)}
              className="btn btn-secondary"
              style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 6 }}
            >
              <History size={14} />
              <span>History ({history.length})</span>
            </button>
          </div>
        </div>

        {/* Preset Selector Badges */}
        <div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 600, marginBottom: 6 }}>
            Scenario Presets
          </div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {presets.map(p => (
              <button
                key={p.id}
                onClick={() => handleSelectPreset(p)}
                disabled={isRunning}
                style={{
                  background: selectedPresetId === p.id ? 'var(--blue)' : 'var(--surface-2)',
                  color: selectedPresetId === p.id ? '#fff' : 'var(--text-secondary)',
                  border: `1px solid ${selectedPresetId === p.id ? 'var(--blue)' : 'var(--border)'}`,
                  borderRadius: 6,
                  padding: '6px 12px',
                  fontSize: 11.5,
                  fontWeight: selectedPresetId === p.id ? 600 : 500,
                  cursor: isRunning ? 'not-allowed' : 'pointer',
                  transition: 'all 0.15s ease',
                }}
              >
                {p.name}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Error / Notification Banner */}
      {errorBanner && (
        <div style={{
          background: 'rgba(239, 68, 68, 0.12)',
          border: '1px solid rgba(239, 68, 68, 0.3)',
          borderRadius: 6,
          padding: '10px 14px',
          color: '#f87171',
          fontSize: 12.5,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
        }}>
          <AlertTriangle size={16} />
          <span>{errorBanner}</span>
        </div>
      )}

      {/* ── Main 2-Column Grid ──────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: '380px 1fr', gap: 16 }}>

        {/* LEFT PANEL: Scenario Configuration */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <Card title="Traffic Scenario Parameters" titleIcon={<Sliders size={15} />}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14, padding: '4px 0' }}>

              {/* Scenario Label */}
              <div>
                <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                  Scenario Title
                </label>
                <input
                  type="text"
                  value={scenarioName}
                  onChange={e => setScenarioName(e.target.value)}
                  disabled={isRunning}
                  style={{
                    width: '100%',
                    marginTop: 4,
                    background: 'var(--surface-2)',
                    border: '1px solid var(--border)',
                    borderRadius: 4,
                    padding: '6px 10px',
                    color: 'var(--text-primary)',
                    fontSize: 12.5,
                  }}
                />
              </div>

              {/* Traffic Density */}
              <div>
                <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                  Traffic Density
                </label>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 6, marginTop: 4 }}>
                  {DENSITY_OPTIONS.slice(0, 4).map(d => (
                    <button
                      key={d.id}
                      onClick={() => setDensity(d.id)}
                      disabled={isRunning}
                      style={{
                        background: density === d.id ? 'rgba(56, 189, 248, 0.15)' : 'var(--surface-2)',
                        color: density === d.id ? 'var(--cyan)' : 'var(--text-secondary)',
                        border: `1px solid ${density === d.id ? 'var(--cyan)' : 'var(--border)'}`,
                        borderRadius: 4,
                        padding: '6px 8px',
                        fontSize: 11.5,
                        fontWeight: 600,
                        cursor: isRunning ? 'not-allowed' : 'pointer',
                      }}
                    >
                      {d.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Directional Distribution Sliders */}
              <div style={{
                background: 'var(--surface-2)',
                border: `1px solid ${isDirectionSumValid ? 'var(--border)' : 'rgba(239, 68, 68, 0.5)'}`,
                borderRadius: 6,
                padding: '10px 12px',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                  <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                    Directional Inflow Bias
                  </span>
                  <span style={{
                    fontSize: 11,
                    fontWeight: 700,
                    color: isDirectionSumValid ? 'var(--green)' : 'var(--red)',
                    fontVariantNumeric: 'tabular-nums',
                  }}>
                    Total: {directionSum}% {isDirectionSumValid ? '✓' : '(Must be 100%)'}
                  </span>
                </div>

                {/* 4 Inflow Approaches */}
                {[
                  { key: 'north', label: 'North (N2C)', icon: ArrowDown, color: 'var(--cyan)' },
                  { key: 'south', label: 'South (S2C)', icon: ArrowUp,   color: 'var(--blue)' },
                  { key: 'east',  label: 'East (E2C)',  icon: ArrowLeft, color: 'var(--amber)' },
                  { key: 'west',  label: 'West (W2C)',  icon: ArrowRight, color: 'var(--purple)' },
                ].map(({ key, label, icon: Icon, color }) => (
                  <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4, width: 95, fontSize: 11, color: 'var(--text-secondary)' }}>
                      <Icon size={12} style={{ color }} />
                      <span>{key.toUpperCase()}</span>
                    </div>
                    <input
                      type="range"
                      min="0"
                      max="100"
                      step="5"
                      value={directionBias[key]}
                      onChange={e => handleDirectionChange(key, e.target.value)}
                      disabled={isRunning}
                      style={{ flex: 1, accentColor: color, cursor: isRunning ? 'not-allowed' : 'pointer' }}
                    />
                    <span style={{ fontSize: 11.5, fontWeight: 700, width: 34, textAlign: 'right', color: 'var(--text-primary)', fontVariantNumeric: 'tabular-nums' }}>
                      {directionBias[key]}%
                    </span>
                  </div>
                ))}
              </div>

              {/* Controller Selection */}
              <div>
                <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                  Target Controller
                </label>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 4 }}>
                  {CONTROLLER_OPTIONS.map(c => (
                    <button
                      key={c.id}
                      onClick={() => { setController(c.id); setCompareAll(false); }}
                      disabled={isRunning || compareAll}
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        background: (!compareAll && controller === c.id) ? 'rgba(59, 130, 246, 0.15)' : 'var(--surface-2)',
                        border: `1px solid ${(!compareAll && controller === c.id) ? 'var(--blue)' : 'var(--border)'}`,
                        borderRadius: 4,
                        padding: '6px 10px',
                        fontSize: 11.5,
                        color: (!compareAll && controller === c.id) ? 'var(--blue-bright)' : 'var(--text-secondary)',
                        cursor: (isRunning || compareAll) ? 'not-allowed' : 'pointer',
                        textAlign: 'left',
                      }}
                    >
                      <span style={{ fontWeight: (!compareAll && controller === c.id) ? 600 : 400 }}>{c.label}</span>
                      <span style={{ fontSize: 9.5, padding: '1px 5px', borderRadius: 3, background: 'var(--surface-3)', color: 'var(--text-muted)' }}>
                        {c.badge}
                      </span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Duration & Seed */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                <div>
                  <label style={{ fontSize: 10.5, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                    Duration (s)
                  </label>
                  <input
                    type="number"
                    min="30"
                    max="3600"
                    step="30"
                    value={duration}
                    onChange={e => setDuration(Number(e.target.value))}
                    disabled={isRunning}
                    style={{
                      width: '100%',
                      marginTop: 4,
                      background: 'var(--surface-2)',
                      border: '1px solid var(--border)',
                      borderRadius: 4,
                      padding: '6px 8px',
                      color: 'var(--text-primary)',
                      fontSize: 12,
                    }}
                  />
                </div>
                <div>
                  <label style={{ fontSize: 10.5, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                    Random Seed
                  </label>
                  <input
                    type="number"
                    value={seed}
                    onChange={e => setSeed(Number(e.target.value))}
                    disabled={isRunning}
                    style={{
                      width: '100%',
                      marginTop: 4,
                      background: 'var(--surface-2)',
                      border: '1px solid var(--border)',
                      borderRadius: 4,
                      padding: '6px 8px',
                      color: 'var(--text-primary)',
                      fontSize: 12,
                    }}
                  />
                </div>
              </div>

              {/* Multi-Controller Comparison Checkbox */}
              <div style={{
                background: compareAll ? 'rgba(168, 85, 247, 0.12)' : 'var(--surface-2)',
                border: `1px solid ${compareAll ? 'rgba(168, 85, 247, 0.4)' : 'var(--border)'}`,
                borderRadius: 6,
                padding: '8px 10px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}>
                <div>
                  <div style={{ fontSize: 11.5, fontWeight: 600, color: compareAll ? 'var(--purple)' : 'var(--text-primary)' }}>
                    Multi-Controller Benchmark
                  </div>
                  <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                    Runs Fixed-Time vs Adaptive vs DQN on identical traffic demand
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={compareAll}
                  onChange={e => setCompareAll(e.target.checked)}
                  disabled={isRunning}
                  style={{ accentColor: 'var(--purple)', cursor: isRunning ? 'not-allowed' : 'pointer' }}
                />
              </div>

              {/* Emergency Vehicle Preemption Control */}
              <div style={{
                background: emergencyVehicle ? 'rgba(239, 68, 68, 0.12)' : 'var(--surface-2)',
                border: `1px solid ${emergencyVehicle ? 'rgba(239, 68, 68, 0.4)' : 'var(--border)'}`,
                borderRadius: 6,
                padding: '8px 10px',
                display: 'flex',
                flexDirection: 'column',
                gap: 8,
              }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div>
                    <div style={{ fontSize: 11.5, fontWeight: 600, color: emergencyVehicle ? '#f87171' : 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: 5 }}>
                      <span>🚨</span> Emergency Vehicle Preemption
                    </div>
                    <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                      Spawns high-priority emergency vehicle (EV_01) to test signal priority
                    </div>
                  </div>
                  <input
                    type="checkbox"
                    checked={emergencyVehicle}
                    onChange={e => setEmergencyVehicle(e.target.checked)}
                    disabled={isRunning}
                    style={{ accentColor: '#ef4444', cursor: isRunning ? 'not-allowed' : 'pointer' }}
                  />
                </div>

                {emergencyVehicle && (
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, paddingTop: 6, borderTop: '1px solid rgba(239, 68, 68, 0.2)' }}>
                    <div>
                      <label style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                        Vehicle Type
                      </label>
                      <select
                        value={emergencyVehicleType}
                        onChange={e => setEmergencyVehicleType(e.target.value)}
                        disabled={isRunning}
                        style={{
                          width: '100%',
                          marginTop: 3,
                          background: 'var(--surface-1)',
                          border: '1px solid var(--border)',
                          borderRadius: 4,
                          padding: '5px 6px',
                          color: 'var(--text-primary)',
                          fontSize: 11,
                        }}
                      >
                        <option value="ambulance">🚑 Ambulance</option>
                        <option value="fire_engine">🚒 Fire Engine</option>
                        <option value="emergency_vehicle">🚓 Police / General EV</option>
                      </select>
                    </div>
                    <div>
                      <label style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                        Inflow Approach
                      </label>
                      <select
                        value={emergencyApproach}
                        onChange={e => setEmergencyApproach(e.target.value)}
                        disabled={isRunning}
                        style={{
                          width: '100%',
                          marginTop: 3,
                          background: 'var(--surface-1)',
                          border: '1px solid var(--border)',
                          borderRadius: 4,
                          padding: '5px 6px',
                          color: 'var(--text-primary)',
                          fontSize: 11,
                        }}
                      >
                        <option value="east">East Approach (E2C)</option>
                        <option value="west">West Approach (W2C)</option>
                        <option value="north">North Approach (N2C)</option>
                        <option value="south">South Approach (S2C)</option>
                      </select>
                    </div>
                    <div style={{ gridColumn: 'span 2' }}>
                      <label style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                        Spawn Step (s)
                      </label>
                      <input
                        type="number"
                        min="1"
                        max="300"
                        value={emergencyStep}
                        onChange={e => setEmergencyStep(Number(e.target.value))}
                        disabled={isRunning}
                        style={{
                          width: '100%',
                          marginTop: 3,
                          background: 'var(--surface-1)',
                          border: '1px solid var(--border)',
                          borderRadius: 4,
                          padding: '5px 6px',
                          color: 'var(--text-primary)',
                          fontSize: 11,
                        }}
                      />
                    </div>
                  </div>
                )}
              </div>

              {/* Action Buttons */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 4 }}>
                {!isRunning ? (
                  <>
                    <button
                      onClick={() => handleRun(false)}
                      disabled={loading || !isDirectionSumValid}
                      className="btn btn-primary"
                      style={{ width: '100%', justifyContent: 'center', fontSize: 12.5, fontWeight: 700, padding: '10px 0' }}
                    >
                      <Play size={14} style={{ fill: 'currentColor', marginRight: 4 }} />
                      RUN SCENARIO ({controller.toUpperCase()})
                    </button>
                    <button
                      onClick={() => {
                        setEmergencyVehicle(true);
                        handleRun(false, true);
                      }}
                      disabled={loading || !isDirectionSumValid}
                      className="btn"
                      style={{
                        width: '100%',
                        justifyContent: 'center',
                        fontSize: 12,
                        fontWeight: 700,
                        padding: '8px 0',
                        background: 'rgba(239, 68, 68, 0.15)',
                        border: '1px solid rgba(239, 68, 68, 0.5)',
                        color: '#f87171',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 6,
                      }}
                    >
                      <Siren size={14} style={{ color: '#f87171' }} />
                      RUN EMERGENCY SCENARIO ({emergencyVehicleType.toUpperCase()})
                    </button>
                    <button
                      onClick={() => handleRun(true)}
                      disabled={loading || !isDirectionSumValid}
                      className="btn btn-secondary"
                      style={{
                        width: '100%',
                        justifyContent: 'center',
                        fontSize: 12,
                        fontWeight: 600,
                        border: '1px solid rgba(168, 85, 247, 0.4)',
                        color: 'var(--purple)',
                      }}
                    >
                      <Layers size={14} style={{ marginRight: 4 }} />
                      COMPARE ALL 3 CONTROLLERS
                    </button>
                  </>
                ) : (
                  <button
                    onClick={handleStop}
                    className="btn btn-danger"
                    style={{ width: '100%', justifyContent: 'center', fontSize: 12.5, fontWeight: 700, padding: '10px 0' }}
                  >
                    <Square size={14} style={{ fill: 'currentColor', marginRight: 4 }} />
                    STOP SCENARIO
                  </button>
                )}
              </div>

            </div>
          </Card>

          {/* Real AI / Agent Loop Status Card */}
          <AgentStatus
            simulationStatus={{
              running: isRunning,
              controller: scenarioStatus?.controller || controller,
              status: scenarioStatus?.status || 'idle',
            }}
            trafficData={trafficData}
          />
        </div>

        {/* RIGHT PANEL: Live Digital Twin & Scenario Results */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

          {/* Real-time Progress Bar */}
          {isRunning && (
            <Card noPadding>
              <div style={{ padding: '10px 14px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6, fontSize: 12 }}>
                  <span style={{ color: 'var(--text-secondary)', fontWeight: 600 }}>
                    {scenarioStatus?.is_comparison ? (
                      <span>Benchmark Progress: <strong style={{ color: 'var(--purple)' }}>{scenarioStatus.current_stage}</strong></span>
                    ) : (
                      <span>Scenario Simulation Progress: <strong style={{ color: 'var(--cyan)' }}>{scenarioStatus?.controller?.toUpperCase()}</strong></span>
                    )}
                  </span>
                  <span style={{ color: 'var(--cyan)', fontVariantNumeric: 'tabular-nums' }}>
                    {scenarioStatus?.current_step ?? 0} / {scenarioStatus?.total_steps ?? duration}s
                    {' '}({scenarioStatus?.progress_pct ?? 0}%)
                  </span>
                </div>
                <div style={{ height: 6, background: 'var(--surface-2)', borderRadius: 3, overflow: 'hidden' }}>
                  <div style={{
                    height: '100%',
                    width: `${Math.min(100, Math.max(0, scenarioStatus?.progress_pct || 0))}%`,
                    background: scenarioStatus?.is_comparison
                      ? 'linear-gradient(90deg, var(--blue), var(--purple))'
                      : 'linear-gradient(90deg, var(--blue), var(--cyan))',
                    borderRadius: 3,
                    transition: 'width 0.3s ease',
                  }} />
                </div>
              </div>
            </Card>
          )}

          {/* Real SUMO Digital Twin Intersection Canvas */}
          <DigitalTwinIntersection
            trafficData={trafficData}
            simulationStatus={{
              running: isRunning,
              status: scenarioStatus?.status || 'idle',
              controller: scenarioStatus?.controller || controller,
            }}
          />

          {/* Live Metric Tiles */}
          {isRunning && (
            <Card title="Instantaneous Telemetry" noPadding>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 8, padding: '0 14px 14px' }}>
                <MetricTile label="Active Vehicles" value={formatNumber(v.total)} color="var(--blue)" />
                <MetricTile label="Completed Trips" value={formatNumber(v.completed)} color="var(--cyan)" />
                <MetricTile label="Total Queue" value={q.total ?? '--'} color="var(--amber)" />
                <MetricTile label="Mean Speed" value={formatSpeed(s.average_mps)} color="var(--green)" />
                <MetricTile label="Avg Waiting" value={formatSeconds(w.average_seconds, 1)} color="var(--purple)" />
              </div>
            </Card>
          )}

          {/* Emergency Vehicle Preemption Standby / Countdown Card */}
          {isRunning && (emergencyVehicle || scenarioStatus?.emergency_vehicle) && !trafficData?.emergency?.active && (
            <Card
              title="Emergency Vehicle Green Corridor Preemption"
              titleIcon={<Siren size={15} style={{ color: '#f87171' }} />}
              badge={<StatusBadge variant="amber">STANDBY / DISPATCH</StatusBadge>}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '6px 4px', fontSize: 12 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--amber)' }} />
                  <span style={{ color: 'var(--text-secondary)' }}>
                    Awaiting Emergency Vehicle (<strong style={{ color: '#f87171' }}>{emergencyVehicleType.toUpperCase()}</strong>) entry on <strong>{emergencyApproach.toUpperCase()}</strong> approach.
                  </span>
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                  Scheduled at step <strong>T+{emergencyStep}s</strong> (Current: {scenarioStatus?.current_step || 0}s)
                </div>
              </div>
            </Card>
          )}

          {/* Live Emergency Vehicle Green Corridor Card */}
          {trafficData?.emergency?.active && (
            <Card
              title="Emergency Vehicle Green Corridor Preemption"
              titleIcon={<span style={{ fontSize: 16 }}>🚨</span>}
              badge={
                <StatusBadge variant={trafficData.emergency.priority_active ? 'green' : (['VEHICLE_PASSED', 'RESTORING_NORMAL'].includes(trafficData.emergency.state) ? 'purple' : 'amber')}>
                  {trafficData.emergency.priority_active ? '● PRIORITY ACTIVE' : (['VEHICLE_PASSED', 'RESTORING_NORMAL'].includes(trafficData.emergency.state) ? 'PRIORITY RELEASED' : 'PRIORITY REQUESTED')}
                </StatusBadge>
              }
            >
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 8 }}>
                  <MetricTile
                    label="Emergency Vehicle"
                    value={trafficData.emergency.vehicle_id || 'EV_01'}
                    color="var(--red)"
                    sub={`${String(trafficData.emergency.approach || '').toUpperCase()} | Lane: ${trafficData.emergency.lane_id || trafficData.emergency.edge_id || '--'}`}
                  />
                  <MetricTile
                    label="Distance to Stopline"
                    value={
                      trafficData.emergency.distance_to_stopline != null
                        ? `${Math.round(trafficData.emergency.distance_to_stopline)}m`
                        : (['VEHICLE_PASSED', 'RESTORING_NORMAL'].includes(trafficData.emergency.state) ? 'PASSED' : '--')
                    }
                    color="var(--amber)"
                    sub={`Edge: ${trafficData.emergency.edge_id || 'Inflow'}`}
                  />
                  <MetricTile
                    label="Estimated Arrival (ETA)"
                    value={
                      trafficData.emergency.eta_seconds != null
                        ? `${trafficData.emergency.eta_seconds}s`
                        : (['VEHICLE_PASSED', 'RESTORING_NORMAL'].includes(trafficData.emergency.state) ? 'CLEARED' : (trafficData.emergency.speed < 1.0 ? 'QUEUED' : '--'))
                    }
                    color="var(--cyan)"
                    sub={`Speed: ${trafficData.emergency.speed != null ? `${trafficData.emergency.speed} m/s` : '--'}`}
                  />
                  <MetricTile
                    label="Corridor State"
                    value={trafficData.emergency.lifecycle_state || trafficData.emergency.state || 'IDLE'}
                    color={trafficData.emergency.priority_active ? 'var(--green)' : 'var(--amber)'}
                    sub={`Signal: ${trafficData.emergency.priority_active ? 'PRIORITY GREEN' : (['VEHICLE_PASSED', 'RESTORING_NORMAL'].includes(trafficData.emergency.state) ? 'PRIORITY RELEASED' : 'CLEARING CONFLICT')}`}
                  />
                  <MetricTile
                    label="Priority Duration"
                    value={`${Number(trafficData.emergency.priority_duration || 0).toFixed(1)}s`}
                    color="var(--purple)"
                    sub={`Safety: ${trafficData.emergency.safety_status || 'NORMAL'}`}
                  />
                </div>
                {trafficData.emergency.reason && (
                  <div style={{
                    background: 'var(--surface-2)',
                    border: '1px solid rgba(239, 68, 68, 0.3)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '8px 12px',
                    fontSize: 11,
                    color: '#fca5a5',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                  }}>
                    <Shield size={14} style={{ color: '#f87171', flexShrink: 0 }} />
                    <span><strong>Signal Safety Enforcement:</strong> {trafficData.emergency.reason}</span>
                  </div>
                )}
              </div>
            </Card>
          )}

          {/* Predictive Traffic Intelligence (+30s Horizon Forecast) */}
          {(isRunning || pred != null) && (
            <Card
              title="Predictive Traffic Intelligence"
              titleIcon={<Sparkles size={15} style={{ color: 'var(--cyan)' }} />}
              badge={
                pred?.model_available ? (
                  <StatusBadge variant="green">ML Forecast Active (+30s)</StatusBadge>
                ) : (
                  <StatusBadge variant="gray">Forecast Standby</StatusBadge>
                )
              }
            >
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {/* Forecast Score vs Current Score & Interval */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8 }}>
                  <div style={{
                    background: 'var(--surface-2)',
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '10px 12px',
                  }}>
                    <div style={{ fontSize: 10.5, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 600, marginBottom: 4 }}>
                      Current Congestion
                    </div>
                    <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--text-primary)', fontVariantNumeric: 'tabular-nums' }}>
                      {pred ? `${Number(pred.current_score || 0).toFixed(1)}` : '--'}
                      <span style={{ fontSize: 11, fontWeight: 500, color: 'var(--text-muted)', marginLeft: 4 }}>/ 100</span>
                    </div>
                    <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
                      Instantaneous index
                    </div>
                  </div>

                  <div style={{
                    background: 'rgba(6, 182, 212, 0.08)',
                    border: '1px solid rgba(6, 182, 212, 0.3)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '10px 12px',
                  }}>
                    <div style={{ fontSize: 10.5, color: 'var(--cyan)', textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 600, marginBottom: 4, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <span>+30s ML Forecast</span>
                      {pred?.trend === 'INCREASING' && <span style={{ color: 'var(--amber)', fontSize: 10, fontWeight: 700 }}>↗ Rising</span>}
                      {pred?.trend === 'DECREASING' && <span style={{ color: 'var(--green)', fontSize: 10, fontWeight: 700 }}>↘ Falling</span>}
                      {pred?.trend === 'STABLE' && <span style={{ color: 'var(--cyan)', fontSize: 10, fontWeight: 700 }}>→ Stable</span>}
                    </div>
                    <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--cyan)', fontVariantNumeric: 'tabular-nums' }}>
                      {pred ? `${Number(pred.predicted_score || 0).toFixed(1)}` : '--'}
                      <span style={{ fontSize: 11, fontWeight: 500, color: 'var(--text-muted)', marginLeft: 4 }}>/ 100</span>
                    </div>
                    <div style={{ fontSize: 10, color: 'var(--cyan)', marginTop: 2, fontWeight: 600 }}>
                      {pred?.congestion_level || 'UNKNOWN'}
                    </div>
                  </div>

                  <div style={{
                    background: 'var(--surface-2)',
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '10px 12px',
                  }}>
                    <div style={{ fontSize: 10.5, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 600, marginBottom: 4 }}>
                      80% Ensemble Interval
                    </div>
                    <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--purple)', fontVariantNumeric: 'tabular-nums', marginTop: 3 }}>
                      {pred && pred.confidence_lower != null && pred.confidence_upper != null
                        ? `[${Number(pred.confidence_lower).toFixed(1)} – ${Number(pred.confidence_upper).toFixed(1)}]`
                        : '--'}
                    </div>
                    <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4 }}>
                      {pred?.std_dev != null ? `σ = ±${Number(pred.std_dev).toFixed(2)} (200 trees)` : 'Empirical CI'}
                    </div>
                  </div>

                  <div style={{
                    background: 'var(--surface-2)',
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '10px 12px',
                  }}>
                    <div style={{ fontSize: 10.5, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 600, marginBottom: 4 }}>
                      Live Verification
                    </div>
                    <div style={{ fontSize: 20, fontWeight: 700, color: pred?.live_mae != null ? 'var(--green)' : 'var(--text-muted)', fontVariantNumeric: 'tabular-nums' }}>
                      {pred?.live_mae != null ? `${Number(pred.live_mae).toFixed(2)}` : '--'}
                      {pred?.live_mae != null && <span style={{ fontSize: 10.5, fontWeight: 500, color: 'var(--text-muted)', marginLeft: 4 }}>MAE</span>}
                    </div>
                    <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
                      {pred?.evaluated_samples > 0
                        ? `${pred.evaluated_samples} verified samples`
                        : 'Awaiting T+30s window...'}
                    </div>
                  </div>
                </div>

                {/* Live Time-Aligned Accuracy Metrics Row */}
                {pred?.evaluated_samples > 0 && (
                  <div style={{
                    background: 'var(--surface-2)',
                    border: '1px solid rgba(16, 185, 129, 0.25)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '8px 12px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    flexWrap: 'wrap',
                    gap: 8,
                    fontSize: 11.5,
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <CheckCircle2 size={13} style={{ color: 'var(--green)' }} />
                      <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Time-Aligned Verification:</span>
                      <span style={{ color: 'var(--text-secondary)' }}>Model MAE:</span>
                      <strong style={{ color: 'var(--green)', fontVariantNumeric: 'tabular-nums' }}>{Number(pred.live_mae).toFixed(3)}</strong>
                      <span style={{ color: 'var(--text-muted)' }}>vs</span>
                      <span style={{ color: 'var(--text-secondary)' }}>Baseline MAE:</span>
                      <strong style={{ color: 'var(--amber)', fontVariantNumeric: 'tabular-nums' }}>{pred.baseline_mae != null ? Number(pred.baseline_mae).toFixed(3) : '--'}</strong>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      {pred.live_rmse != null && (
                        <span>RMSE: <strong style={{ color: 'var(--cyan)', fontVariantNumeric: 'tabular-nums' }}>{Number(pred.live_rmse).toFixed(3)}</strong></span>
                      )}
                      {pred.mae_improvement_pct != null && (
                        <span style={{
                          background: 'rgba(16, 185, 129, 0.15)',
                          color: 'var(--green)',
                          padding: '2px 8px',
                          borderRadius: 4,
                          fontWeight: 700,
                          fontSize: 11,
                        }}>
                          +{Number(pred.mae_improvement_pct).toFixed(1)}% Error Reduction
                        </span>
                      )}
                    </div>
                  </div>
                )}

                {/* Top Model Features Bar */}
                {predictionStatus?.feature_importances && Object.keys(predictionStatus.feature_importances).length > 0 && (
                  <div style={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 6,
                    paddingTop: 4,
                    borderTop: '1px solid var(--border)',
                  }}>
                    <div style={{ fontSize: 10.5, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                      Top Feature Drivers (RandomForestRegressor, 200 Trees)
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                      {Object.entries(predictionStatus.feature_importances).slice(0, 5).map(([feat, imp]) => (
                        <div key={feat} style={{
                          background: 'var(--surface-1)',
                          border: '1px solid var(--border)',
                          borderRadius: 4,
                          padding: '3px 8px',
                          fontSize: 10.5,
                          display: 'flex',
                          alignItems: 'center',
                          gap: 6,
                        }}>
                          <span style={{ color: 'var(--text-secondary)' }}>{feat.replace(/_/g, ' ')}</span>
                          <strong style={{ color: 'var(--cyan)' }}>{(Number(imp) * 100).toFixed(1)}%</strong>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </Card>
          )}

          {/* ── SCENARIO RESULT SECTION ────────────────────── */}
          {result && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <Card
                title="Scenario Evaluation Result"
                titleIcon={<BarChart3 size={15} />}
                badge={<StatusBadge variant="green">Completed</StatusBadge>}
              >
                <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

                  {/* Metadata Banner */}
                  <div style={{
                    background: 'var(--surface-2)',
                    borderRadius: 6,
                    padding: '8px 12px',
                    display: 'flex',
                    flexWrap: 'wrap',
                    gap: 12,
                    fontSize: 11.5,
                    color: 'var(--text-secondary)'
                  }}>
                    <span>Scenario: <strong style={{ color: 'var(--text-primary)' }}>{result.scenario_name}</strong></span>
                    <span>Controller: <strong style={{ color: 'var(--cyan)' }}>{result.controller?.toUpperCase()}</strong></span>
                    <span>Duration: <strong style={{ color: 'var(--text-primary)' }}>{result.duration}s</strong></span>
                    <span>Seed: <strong style={{ color: 'var(--text-primary)' }}>{result.seed}</strong></span>
                    <span>Density: <strong style={{ color: 'var(--text-primary)' }}>{result.configuration?.density} ({result.configuration?.multiplier}×)</strong></span>
                  </div>

                  {/* Primary Metrics Grid */}
                  {result.metrics && (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8 }}>
                      <MetricTile
                        label="Throughput (Served)"
                        value={formatNumber(result.metrics.total_vehicles_served)}
                        color="var(--green)"
                        sub="Completed trips"
                      />
                      <MetricTile
                        label="Average Queue"
                        value={formatDecimal(result.metrics.average_queue, 2)}
                        color="var(--amber)"
                        sub={`Peak: ${result.metrics.max_queue || 0} veh`}
                      />
                      <MetricTile
                        label="Average Waiting"
                        value={formatSeconds(result.metrics.average_waiting_time, 1)}
                        color="var(--purple)"
                        sub={`Delay: ${formatSeconds(result.metrics.average_delay, 1)}`}
                      />
                      <MetricTile
                        label="Average Speed"
                        value={formatSpeed(result.metrics.average_speed)}
                        color="var(--cyan)"
                        sub={`CO₂: ${formatDecimal(result.metrics.total_co2_emission_kg, 2)} kg`}
                      />
                    </div>
                  )}

                  {/* Verified 30s Forecast Accuracy in Scenario Results */}
                  {result.prediction_metrics && result.prediction_metrics.evaluated_samples > 0 && (
                    <div style={{
                      background: 'rgba(6, 182, 212, 0.06)',
                      border: '1px solid rgba(6, 182, 212, 0.25)',
                      borderRadius: 6,
                      padding: '10px 14px',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 8,
                    }}>
                      <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--cyan)', display: 'flex', alignItems: 'center', gap: 6 }}>
                        <Sparkles size={14} />
                        <span>30-Second Congestion Forecast Performance (Time-Aligned Empirical Verification)</span>
                      </div>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8 }}>
                        <MetricTile
                          label="Model Verified MAE"
                          value={result.prediction_metrics.live_mae != null ? Number(result.prediction_metrics.live_mae).toFixed(3) : '--'}
                          color="var(--green)"
                          sub="Mean Absolute Error"
                        />
                        <MetricTile
                          label="Baseline MAE"
                          value={result.prediction_metrics.baseline_mae != null ? Number(result.prediction_metrics.baseline_mae).toFixed(3) : '--'}
                          color="var(--amber)"
                          sub="Persistence Baseline"
                        />
                        <MetricTile
                          label="Model Verified RMSE"
                          value={result.prediction_metrics.live_rmse != null ? Number(result.prediction_metrics.live_rmse).toFixed(3) : '--'}
                          color="var(--cyan)"
                          sub="Root Mean Sq Error"
                        />
                        <MetricTile
                          label="Accuracy Gain"
                          value={result.prediction_metrics.mae_improvement_pct != null ? `+${Number(result.prediction_metrics.mae_improvement_pct).toFixed(1)}%` : '--'}
                          color="var(--purple)"
                          sub={`${result.prediction_metrics.evaluated_samples} samples verified`}
                        />
                      </div>
                    </div>
                  )}

                  {/* Emergency Vehicle Corridor Performance Card */}
                  {result.emergency_metrics && (
                    <div style={{
                      background: 'rgba(239, 68, 68, 0.06)',
                      border: '1px solid rgba(239, 68, 68, 0.25)',
                      borderRadius: 6,
                      padding: '12px 14px',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 10,
                    }}>
                      <div style={{ fontSize: 12, fontWeight: 700, color: '#f87171', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <span>🚨</span>
                          <span>Emergency Vehicle Green Corridor Evaluation ({result.emergency_metrics.vehicle_id || 'EV_01'})</span>
                        </div>
                        {result.emergency_metrics.baseline_comparison?.time_saved_pct > 0 && (
                          <span style={{
                            background: 'rgba(16, 185, 129, 0.15)',
                            color: 'var(--green)',
                            padding: '2px 8px',
                            borderRadius: 4,
                            fontWeight: 700,
                            fontSize: 11,
                          }}>
                            +{result.emergency_metrics.baseline_comparison.time_saved_pct}% Faster Clearance
                          </span>
                        )}
                      </div>

                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8 }}>
                        <MetricTile
                          label="Actual Travel Time"
                          value={`${Number(result.emergency_metrics.travel_time || 0).toFixed(1)}s`}
                          color="var(--green)"
                          sub={`Free-Flow: ${Number(result.emergency_metrics.free_flow_time || 13.03).toFixed(1)}s`}
                        />
                        <MetricTile
                          label="Intersection Delay"
                          value={`${Number(result.emergency_metrics.intersection_delay || 0).toFixed(1)}s`}
                          color={result.emergency_metrics.intersection_delay <= 2.0 ? 'var(--green)' : 'var(--amber)'}
                          sub={`Stopped: ${Number(result.emergency_metrics.stopped_waiting_time || 0).toFixed(1)}s`}
                        />
                        <MetricTile
                          label="Time to Priority Active"
                          value={`${Number(result.emergency_metrics.time_to_priority_active || 0).toFixed(1)}s`}
                          color="var(--cyan)"
                          sub="Safety Clearance Delay"
                        />
                        <MetricTile
                          label="Priority Green Duration"
                          value={`${Number(result.emergency_metrics.priority_duration || 0).toFixed(1)}s`}
                          color="var(--purple)"
                          sub={`Approach: ${String(result.emergency_metrics.approach || '').toUpperCase()}`}
                        />
                      </div>

                      {result.emergency_metrics.teleport_occurred && (
                        <div style={{
                          background: 'rgba(239, 68, 68, 0.12)',
                          border: '1px solid rgba(239, 68, 68, 0.3)',
                          borderRadius: 6,
                          padding: '8px 12px',
                          fontSize: 11.5,
                          color: '#f87171',
                          display: 'flex',
                          alignItems: 'center',
                          gap: 8,
                        }}>
                          <AlertTriangle size={15} style={{ flexShrink: 0 }} />
                          <span><strong>SUMO Teleport Recovery:</strong> Vehicle was teleported by SUMO. Priority was released and normal signal control was restored safely without gridlock.</span>
                        </div>
                      )}

                      {/* Grounded Empirical Baseline Comparison Row */}
                      {result.emergency_metrics.baseline_comparison && (
                        <div style={{
                          background: 'var(--surface-2)',
                          border: '1px solid rgba(16, 185, 129, 0.25)',
                          borderRadius: 'var(--radius-sm)',
                          padding: '10px 12px',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          flexWrap: 'wrap',
                          gap: 10,
                          fontSize: 11.5,
                        }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <CheckCircle2 size={14} style={{ color: 'var(--green)' }} />
                            <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Empirical Baseline Comparison:</span>
                            <span style={{ color: 'var(--text-secondary)' }}>Priority Travel Time:</span>
                            <strong style={{ color: 'var(--green)', fontVariantNumeric: 'tabular-nums' }}>
                              {result.emergency_metrics.baseline_comparison.priority_travel_time}s
                            </strong>
                            <span style={{ color: 'var(--text-muted)' }}>vs Normal Control:</span>
                            <strong style={{ color: 'var(--amber)', fontVariantNumeric: 'tabular-nums' }}>
                              {result.emergency_metrics.baseline_comparison.baseline_travel_time}s
                            </strong>
                            <span style={{ color: 'var(--green)', fontWeight: 700 }}>
                              (Saved {result.emergency_metrics.baseline_comparison.time_saved_seconds}s)
                            </span>
                          </div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                            <span>Cross Traffic Delay Impact: <strong style={{ color: 'var(--cyan)', fontVariantNumeric: 'tabular-nums' }}>{result.emergency_metrics.baseline_comparison.ordinary_traffic_delay_impact_sec >= 0 ? `+${result.emergency_metrics.baseline_comparison.ordinary_traffic_delay_impact_sec}s` : `${result.emergency_metrics.baseline_comparison.ordinary_traffic_delay_impact_sec}s`}</strong></span>
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Multi-Controller Benchmark Comparison Table & Charts */}
                  {result.comparison && comparisonChartData.length > 0 && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 4 }}>
                      <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--purple)', display: 'flex', alignItems: 'center', gap: 6 }}>
                        <Layers size={14} />
                        <span>Controlled Benchmark Comparison (Identical Demand & Seed {result.seed})</span>
                      </div>

                      {/* Side-by-side Table */}
                      <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11.5, textAlign: 'left' }}>
                          <thead>
                            <tr style={{ borderBottom: '1px solid var(--border)', color: 'var(--text-muted)' }}>
                              <th style={{ padding: '8px 6px' }}>Metric</th>
                              <th style={{ padding: '8px 6px' }}>Fixed-Time</th>
                              <th style={{ padding: '8px 6px' }}>Rule-Based Adaptive</th>
                              <th style={{ padding: '8px 6px', color: 'var(--cyan)' }}>DQN (Reinforcement Learning)</th>
                            </tr>
                          </thead>
                          <tbody>
                            {[
                              { label: 'Throughput (veh)', key: 'total_vehicles_served', format: v => (v != null ? formatNumber(v) : '--') },
                              { label: 'Average Queue (veh)', key: 'average_queue', format: v => (v != null ? formatDecimal(v, 2) : '--') },
                              { label: 'Peak Queue (veh)', key: 'max_queue', format: v => (v != null ? formatNumber(v) : '--') },
                              { label: 'Average Waiting Time (s)', key: 'average_waiting_time', format: v => (v != null ? formatSeconds(v, 1) : '--') },
                              { label: 'Average Delay / Veh (s)', key: 'average_delay', format: v => (v != null ? formatSeconds(v, 1) : '--') },
                              { label: 'Average Speed (m/s)', key: 'average_speed', format: v => (v != null ? formatSpeed(v) : '--') },
                              { label: 'Estimated CO₂ (kg)', key: 'total_co2_emission_kg', format: v => (v != null ? `${formatDecimal(v, 3)} kg` : '--') },
                              { label: 'Signal Phase Changes', key: 'phase_changes', format: v => (v != null ? formatNumber(v) : '--') },
                              { label: 'Safety Interventions', key: 'safety_interventions', format: v => (v != null ? formatNumber(v) : '--') },
                            ].map(({ label, key, format }) => (
                              <tr key={key} style={{ borderBottom: '1px solid rgba(122, 165, 210, 0.08)' }}>
                                <td style={{ padding: '6px', color: 'var(--text-secondary)', fontWeight: 500 }}>{label}</td>
                                <td style={{ padding: '6px', fontVariantNumeric: 'tabular-nums' }}>
                                  {format(result.comparison.fixed?.metrics?.[key])}
                                </td>
                                <td style={{ padding: '6px', fontVariantNumeric: 'tabular-nums' }}>
                                  {format(result.comparison.adaptive?.metrics?.[key])}
                                </td>
                                <td style={{ padding: '6px', fontWeight: 700, color: 'var(--cyan)', fontVariantNumeric: 'tabular-nums' }}>
                                  {format(result.comparison.dqn?.metrics?.[key])}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>

                      {/* Emergency Vehicle Priority & Cross-Traffic Comparison when EV was active */}
                      {(result.comparison.fixed?.emergency_metrics || result.comparison.adaptive?.emergency_metrics || result.comparison.dqn?.emergency_metrics) && (
                        <div style={{ marginTop: 12, padding: '10px 12px', background: 'rgba(168, 85, 247, 0.08)', border: '1px solid var(--purple)', borderRadius: 6 }}>
                          <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--purple)', display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                            <Siren size={13} />
                            <span>Emergency Priority & Cross-Traffic Impact Comparison</span>
                          </div>
                          <table style={{ width: '100%', fontSize: 11, borderCollapse: 'collapse' }}>
                            <thead>
                              <tr style={{ color: 'var(--text-muted)', borderBottom: '1px solid var(--border)' }}>
                                <th style={{ textAlign: 'left', padding: '4px' }}>Metric</th>
                                <th style={{ textAlign: 'center', padding: '4px' }}>Fixed-Time</th>
                                <th style={{ textAlign: 'center', padding: '4px' }}>Adaptive</th>
                                <th style={{ textAlign: 'center', padding: '4px', color: 'var(--cyan)' }}>DQN AI Agent</th>
                              </tr>
                            </thead>
                            <tbody>
                              <tr style={{ borderBottom: '1px solid rgba(122, 165, 210, 0.08)' }}>
                                <td style={{ padding: '4px', color: 'var(--text-secondary)' }}>EV Travel Time (s)</td>
                                <td style={{ textAlign: 'center', padding: '4px' }}>{result.comparison.fixed?.emergency_metrics?.travel_time_seconds ? `${result.comparison.fixed.emergency_metrics.travel_time_seconds}s` : '--'}</td>
                                <td style={{ textAlign: 'center', padding: '4px' }}>{result.comparison.adaptive?.emergency_metrics?.travel_time_seconds ? `${result.comparison.adaptive.emergency_metrics.travel_time_seconds}s` : '--'}</td>
                                <td style={{ textAlign: 'center', padding: '4px', fontWeight: 700, color: 'var(--cyan)' }}>{result.comparison.dqn?.emergency_metrics?.travel_time_seconds ? `${result.comparison.dqn.emergency_metrics.travel_time_seconds}s` : '--'}</td>
                              </tr>
                              <tr style={{ borderBottom: '1px solid rgba(122, 165, 210, 0.08)' }}>
                                <td style={{ padding: '4px', color: 'var(--text-secondary)' }}>EV Delay (s)</td>
                                <td style={{ textAlign: 'center', padding: '4px' }}>{result.comparison.fixed?.emergency_metrics?.delay_seconds != null ? `${result.comparison.fixed.emergency_metrics.delay_seconds}s` : '--'}</td>
                                <td style={{ textAlign: 'center', padding: '4px' }}>{result.comparison.adaptive?.emergency_metrics?.delay_seconds != null ? `${result.comparison.adaptive.emergency_metrics.delay_seconds}s` : '--'}</td>
                                <td style={{ textAlign: 'center', padding: '4px', fontWeight: 700, color: 'var(--cyan)' }}>{result.comparison.dqn?.emergency_metrics?.delay_seconds != null ? `${result.comparison.dqn.emergency_metrics.delay_seconds}s` : '--'}</td>
                              </tr>
                              <tr>
                                <td style={{ padding: '4px', color: 'var(--text-secondary)' }}>Cross-Traffic Peak Queue (veh)</td>
                                <td style={{ textAlign: 'center', padding: '4px' }}>{result.comparison.fixed?.emergency_metrics?.cross_traffic_peak_queue != null ? `${result.comparison.fixed.emergency_metrics.cross_traffic_peak_queue}` : '--'}</td>
                                <td style={{ textAlign: 'center', padding: '4px' }}>{result.comparison.adaptive?.emergency_metrics?.cross_traffic_peak_queue != null ? `${result.comparison.adaptive.emergency_metrics.cross_traffic_peak_queue}` : '--'}</td>
                                <td style={{ textAlign: 'center', padding: '4px', fontWeight: 700, color: 'var(--cyan)' }}>{result.comparison.dqn?.emergency_metrics?.cross_traffic_peak_queue != null ? `${result.comparison.dqn.emergency_metrics.cross_traffic_peak_queue}` : '--'}</td>
                              </tr>
                            </tbody>
                          </table>
                        </div>
                      )}

                      {/* Comparison Recharts */}
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginTop: 10 }}>
                        <div style={{ background: 'var(--surface-2)', padding: '10px 12px', borderRadius: 6, border: '1px solid var(--border)' }}>
                          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 6 }}>
                            Throughput by Controller (Higher is Better)
                          </div>
                          <ResponsiveContainer width="100%" height={140}>
                            <BarChart data={comparisonChartData}>
                              <CartesianGrid strokeDasharray="3 3" stroke="rgba(122,165,210,0.1)" />
                              <XAxis dataKey="controller" tick={{ fontSize: 9, fill: 'var(--text-muted)' }} />
                              <YAxis tick={{ fontSize: 9, fill: 'var(--text-muted)' }} />
                              <Tooltip contentStyle={{ background: 'var(--surface-2)', border: '1px solid var(--border)', fontSize: 11 }} />
                              <Bar dataKey="throughput" fill="var(--cyan)" radius={[4, 4, 0, 0]} />
                            </BarChart>
                          </ResponsiveContainer>
                        </div>

                        <div style={{ background: 'var(--surface-2)', padding: '10px 12px', borderRadius: 6, border: '1px solid var(--border)' }}>
                          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 6 }}>
                            Average Queue Length (Lower is Better)
                          </div>
                          <ResponsiveContainer width="100%" height={140}>
                            <BarChart data={comparisonChartData}>
                              <CartesianGrid strokeDasharray="3 3" stroke="rgba(122,165,210,0.1)" />
                              <XAxis dataKey="controller" tick={{ fontSize: 9, fill: 'var(--text-muted)' }} />
                              <YAxis tick={{ fontSize: 9, fill: 'var(--text-muted)' }} />
                              <Tooltip contentStyle={{ background: 'var(--surface-2)', border: '1px solid var(--border)', fontSize: 11 }} />
                              <Bar dataKey="average_queue" fill="var(--amber)" radius={[4, 4, 0, 0]} />
                            </BarChart>
                          </ResponsiveContainer>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Actions: Re-run & Offline Replay buttons */}
                  <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 10 }}>
                    <button
                      onClick={() => setReplaySimulationId(result.scenario_id)}
                      className="btn btn-secondary"
                      style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 6, borderColor: 'var(--cyan)', color: 'var(--cyan)' }}
                    >
                      <Play size={13} />
                      <span>Offline Replay Run</span>
                    </button>
                    <button
                      onClick={() => handleRun(result.comparison != null)}
                      className="btn btn-secondary"
                      style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 6 }}
                    >
                      <RefreshCw size={13} />
                      <span>Run Again (Seed {result.seed})</span>
                    </button>
                  </div>

                </div>
              </Card>
            </div>
          )}

          {/* Historical Scenarios Drawer / Modal Table */}
          {showHistory && (
            <Card title="Scenario Execution History" titleIcon={<History size={15} />}>
              {history.length === 0 ? (
                <div style={{ padding: '16px', textAlign: 'center', color: 'var(--text-muted)', fontSize: 12 }}>
                  No historical scenario records available.
                </div>
              ) : (
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11.5 }}>
                    <thead>
                      <tr style={{ borderBottom: '1px solid var(--border)', color: 'var(--text-muted)' }}>
                        <th style={{ padding: '6px 8px', textAlign: 'left' }}>Scenario Name</th>
                        <th style={{ padding: '6px 8px', textAlign: 'left' }}>Controller</th>
                        <th style={{ padding: '6px 8px', textAlign: 'center' }}>Density</th>
                        <th style={{ padding: '6px 8px', textAlign: 'center' }}>Seed</th>
                        <th style={{ padding: '6px 8px', textAlign: 'right' }}>Throughput</th>
                        <th style={{ padding: '6px 8px', textAlign: 'right' }}>Avg Queue</th>
                        <th style={{ padding: '6px 8px', textAlign: 'center' }}>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {history.map(item => (
                        <tr key={item.scenario_id} style={{ borderBottom: '1px solid rgba(122, 165, 210, 0.08)' }}>
                          <td style={{ padding: '6px 8px', fontWeight: 600 }}>{item.scenario_name}</td>
                          <td style={{ padding: '6px 8px' }}>
                            <span style={{ color: item.is_comparison ? 'var(--purple)' : 'var(--cyan)' }}>
                              {item.controller}
                            </span>
                          </td>
                          <td style={{ padding: '6px 8px', textAlign: 'center' }}>{item.density}</td>
                          <td style={{ padding: '6px 8px', textAlign: 'center' }}>{item.seed}</td>
                          <td style={{ padding: '6px 8px', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                            {formatNumber(item.metrics?.total_vehicles_served || 0)}
                          </td>
                          <td style={{ padding: '6px 8px', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                            {formatDecimal(item.metrics?.average_queue || 0, 2)}
                          </td>
                          <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
                              <button
                                onClick={async () => {
                                  const fullRes = await getScenarioResult(item.scenario_id);
                                  setResult(fullRes);
                                }}
                                className="btn btn-secondary"
                                style={{ fontSize: 10.5, padding: '2px 8px' }}
                              >
                                View
                              </button>
                              <button
                                onClick={() => setReplaySimulationId(item.scenario_id)}
                                className="btn btn-secondary"
                                style={{ fontSize: 10.5, padding: '2px 8px', borderColor: 'var(--cyan)', color: 'var(--cyan)' }}
                              >
                                Replay
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          )}

          {/* AI Decision History */}
          <AIDecisionHistory decisions={aiDecisions} isRunning={isRunning} />

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

export default ScenarioLab;
