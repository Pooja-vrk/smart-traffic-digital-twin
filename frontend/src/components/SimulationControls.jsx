import React, { useState } from 'react';
import { startSimulation, stopSimulation } from '../services/api';
import { CONTROLLERS, SIMULATION_DEFAULTS } from '../utils/constants';

const SimulationControls = ({ simulationStatus, onStart, onStop }) => {
  const [selectedController, setSelectedController] = useState('dqn');
  const [steps, setSteps] = useState(SIMULATION_DEFAULTS.steps);
  const [seed, setSeed] = useState(SIMULATION_DEFAULTS.seed);
  const [isStarting, setIsStarting] = useState(false);
  const [isStopping, setIsStopping] = useState(false);

  const isRunning = simulationStatus?.running || false;
  const canStart = !isRunning && !isStarting;
  const canStop = isRunning && !isStopping;

  const handleStart = async () => {
    setIsStarting(true);
    try {
      await startSimulation({
        controller: selectedController,
        steps: parseInt(steps),
        seed: parseInt(seed),
        gui: false,
      });
      if (onStart) onStart();
    } catch (error) {
      console.error('Failed to start simulation:', error);
      alert('Failed to start simulation: ' + (error.response?.data?.detail || error.message));
    } finally {
      setIsStarting(false);
    }
  };

  const handleStop = async () => {
    setIsStopping(true);
    try {
      await stopSimulation();
      if (onStop) onStop();
    } catch (error) {
      console.error('Failed to stop simulation:', error);
      alert('Failed to stop simulation: ' + (error.response?.data?.detail || error.message));
    } finally {
      setIsStopping(false);
    }
  };

  return (
    <div className="card simulation-controls">
      <h3 className="simulation-controls-title">Simulation Controls</h3>
      
      <div className="simulation-controls-form">
        <div className="form-group">
          <label className="form-label">Controller</label>
          <select
            className="form-select"
            value={selectedController}
            onChange={(e) => setSelectedController(e.target.value)}
            disabled={isRunning}
          >
            {CONTROLLERS.map((controller) => (
              <option key={controller.id} value={controller.id}>
                {controller.name}
              </option>
            ))}
          </select>
        </div>

        <div className="form-group">
          <label className="form-label">Duration (seconds)</label>
          <input
            type="number"
            className="form-input"
            value={steps}
            onChange={(e) => setSteps(e.target.value)}
            min="1"
            max="3600"
            disabled={isRunning}
          />
        </div>

        <div className="form-group">
          <label className="form-label">Random Seed</label>
          <input
            type="number"
            className="form-input"
            value={seed}
            onChange={(e) => setSeed(e.target.value)}
            disabled={isRunning}
          />
        </div>

        <div className="simulation-controls-buttons">
          <button
            className={`btn btn-success ${!canStart ? 'disabled' : ''}`}
            onClick={handleStart}
            disabled={!canStart}
          >
            {isStarting ? 'Starting...' : 'Start Simulation'}
          </button>
          <button
            className={`btn btn-danger ${!canStop ? 'disabled' : ''}`}
            onClick={handleStop}
            disabled={!canStop}
          >
            {isStopping ? 'Stopping...' : 'Stop Simulation'}
          </button>
        </div>
      </div>

      {simulationStatus && (
        <div className="simulation-status-info">
          <div className="status-item">
            <span className="status-label">Status:</span>
            <span className={`status-value status-${simulationStatus.status}`}>
              {simulationStatus.status.toUpperCase()}
            </span>
          </div>
          {simulationStatus.simulation_id && (
            <div className="status-item">
              <span className="status-label">ID:</span>
              <span className="status-value">{simulationStatus.simulation_id.slice(0, 8)}...</span>
            </div>
          )}
          {simulationStatus.current_step !== null && (
            <div className="status-item">
              <span className="status-label">Step:</span>
              <span className="status-value">{simulationStatus.current_step} / {simulationStatus.total_steps}</span>
            </div>
          )}
          {simulationStatus.simulation_time !== null && simulationStatus.simulation_time !== undefined && (
            <div className="status-item">
              <span className="status-label">Time:</span>
              <span className="status-value">{typeof simulationStatus.simulation_time === 'number' ? `${simulationStatus.simulation_time.toFixed(1)}s` : '--'}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default SimulationControls;
