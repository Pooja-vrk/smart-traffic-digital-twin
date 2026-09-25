import React, { useState, useEffect } from 'react';
import { Play, Square, SlidersHorizontal } from 'lucide-react';
import Card from '../common/Card';
import { startSimulation, stopSimulation } from '../../services/api';
import { SIMULATION_DEFAULTS } from '../../utils/constants';

const CONTROLLERS = [
  { id: 'fixed',    label: 'Fixed-Time' },
  { id: 'adaptive', label: 'Adaptive'   },
  { id: 'dqn',      label: 'DQN (AI)'  },
];

/**
 * Props:
 *   simulationStatus  – from useTrafficWebSocket
 *   onStart           – callback when start succeeds (clears history etc.)
 *   onStop            – callback when stop is requested (optional)
 *   startStopPoll     – from useTrafficWebSocket; activates status polling fallback
 */
const SimulationControl = ({ simulationStatus, onStart, onStop, startStopPoll }) => {
  const [controller, setController] = useState('dqn');
  const [steps, setSteps]           = useState(SIMULATION_DEFAULTS.steps);
  const [seed, setSeed]             = useState(SIMULATION_DEFAULTS.seed);
  const [isStarting, setIsStarting] = useState(false);
  const [error, setError]           = useState(null);

  // Derive states from simulationStatus (source of truth is WS)
  const wsStatus  = simulationStatus?.status || 'idle';
  const isRunning = simulationStatus?.running || false;

  // Stop is "in flight" while status is 'stopping' (set by backend on POST /stop)
  // OR while we're locally waiting for confirmation (belt-and-suspenders)
  const isStopping = wsStatus === 'stopping';

  const canStart = !isRunning && !isStarting;
  // Stop enabled only when genuinely running AND not already in stopping transition
  const canStop  = isRunning && !isStopping;

  // When the simulation finishes (any terminal state), clear the starting flag
  useEffect(() => {
    if (!isRunning) {
      setIsStarting(false);
    }
  }, [isRunning]);

  const handleStart = async () => {
    setIsStarting(true);
    setError(null);
    try {
      await startSimulation({
        controller,
        steps: parseInt(steps, 10),
        seed:  parseInt(seed, 10),
        gui:   false,
      });
      if (onStart) onStart();
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to start simulation');
      setIsStarting(false);
    }
    // Do NOT reset isStarting in finally — the WS status_update will drive that
    // via the useEffect above once isRunning becomes true
  };

  const handleStop = async () => {
    // Guard: only fire if actually enabled (prevents double-click race)
    if (!canStop) return;
    setError(null);
    try {
      await stopSimulation();
      // The backend has set _status = "stopping" and fired stop_event.
      // The WS will deliver simulation_stopped + status_update when the worker
      // finishes. Activate a polling fallback in case the WS is slow.
      if (startStopPoll) startStopPoll();
      if (onStop) onStop();
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to stop simulation');
    }
    // NOTE: we do NOT reset isStopping here — it is driven entirely by the
    // simulationStatus.status from the WS. This prevents duplicate stop requests.
  };

  return (
    <Card
      title="Simulation Control"
      titleIcon={<SlidersHorizontal size={14} />}
      noPadding
    >
      <div className="sim-control-body">
        {/* Controller segmented buttons */}
        <div className="form-label">Controller</div>
        <div className="seg-btn-group">
          {CONTROLLERS.map(({ id, label }) => (
            <button
              key={id}
              className={`seg-btn${controller === id ? ' active' + (id === 'dqn' ? ' dqn-active' : '') : ''}`}
              onClick={() => setController(id)}
              disabled={isRunning}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Duration */}
        <div className="form-group">
          <label className="form-label">Duration (seconds)</label>
          <input
            type="number"
            className="form-input"
            value={steps}
            onChange={e => setSteps(e.target.value)}
            min="1"
            max="3600"
            disabled={isRunning}
          />
        </div>

        {/* Seed */}
        <div className="form-group">
          <label className="form-label">Random Seed</label>
          <input
            type="number"
            className="form-input"
            value={seed}
            onChange={e => setSeed(e.target.value)}
            disabled={isRunning}
          />
        </div>

        {/* Action buttons */}
        <div className="btn-row">
          <button
            className="btn btn-primary"
            onClick={handleStart}
            disabled={!canStart}
            title={isStarting ? 'Starting simulation…' : 'Start simulation'}
          >
            <Play size={13} />
            {isStarting ? 'Starting…' : 'Start'}
          </button>
          <button
            className="btn btn-danger"
            onClick={handleStop}
            disabled={!canStop}
            title={
              !isRunning  ? 'No simulation running' :
              isStopping  ? 'Stop already requested…' :
                            'Stop simulation'
            }
          >
            <Square size={13} />
            {isStopping ? 'Stopping…' : 'Stop'}
          </button>
        </div>

        {/* Error */}
        {error && (
          <div style={{ marginTop: 8, fontSize: 11.5, color: 'var(--red)' }}>
            ⚠ {error}
          </div>
        )}

        {/* Status box */}
        <div className="sim-status-box">
          <div className="sim-status-row">
            <span className="sim-status-key">Status</span>
            <span className={`sim-status-val ${wsStatus}`}>
              {wsStatus.toUpperCase()}
            </span>
          </div>
          {simulationStatus?.controller && (
            <div className="sim-status-row">
              <span className="sim-status-key">Controller</span>
              <span className="sim-status-val" style={{ color: 'var(--text-secondary)' }}>
                {simulationStatus.controller === 'dqn' ? 'DQN (AI)' : simulationStatus.controller}
              </span>
            </div>
          )}
          {simulationStatus?.current_step != null && (
            <div className="sim-status-row">
              <span className="sim-status-key">Progress</span>
              <span className="sim-status-val" style={{ color: 'var(--text-secondary)' }}>
                {simulationStatus.current_step} / {simulationStatus.total_steps} s
              </span>
            </div>
          )}
          {typeof simulationStatus?.simulation_time === 'number' && (
            <div className="sim-status-row">
              <span className="sim-status-key">Sim Time</span>
              <span className="sim-status-val" style={{ color: 'var(--cyan)' }}>
                {simulationStatus.simulation_time.toFixed(1)} s
              </span>
            </div>
          )}
        </div>
      </div>
    </Card>
  );
};

export default SimulationControl;
