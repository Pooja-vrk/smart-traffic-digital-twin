import React from 'react';
import { TableProperties } from 'lucide-react';
import Card from '../common/Card';

const DIRS = ['north', 'south', 'east', 'west'];

/* Returns the signal state string for a given direction */
const dirSignal = (dir, phaseIndex) => {
  const NS = ['north', 'south'];
  const EW = ['east', 'west'];
  if (NS.includes(dir)) {
    if (phaseIndex === 0) return 'green';
    if (phaseIndex === 1) return 'yellow';
    return 'red';
  }
  if (EW.includes(dir)) {
    if (phaseIndex === 2) return 'green';
    if (phaseIndex === 3) return 'yellow';
    return 'red';
  }
  return 'red';
};

const SignalPill = ({ state }) => (
  <span className={`signal-pill ${state || 'red'}`}>
    <span style={{
      width: 5,
      height: 5,
      borderRadius: '50%',
      background: 'currentColor',
      display: 'inline-block',
    }} />
    {(state || 'red').toUpperCase()}
  </span>
);

const fmt = (v, decimals = 1, suffix = '') => {
  if (v == null || (typeof v === 'number' && isNaN(v))) return '--';
  if (typeof v === 'number') return v.toFixed(decimals) + suffix;
  return String(v);
};

/**
 * Props:
 *   trafficData – real-time WS traffic object
 */
const LiveTrafficFeed = ({ trafficData }) => {
  const queues  = trafficData?.queues  || {};
  const signal  = trafficData?.signal  || {};
  const speed   = trafficData?.speed   || {};
  const waiting = trafficData?.waiting || {};

  const phaseIndex = signal.phase_index ?? 0;

  /* per-direction speed – the backend may provide only average_mps;
     fall back to that if per-direction fields are absent */
  const dirSpeed = (dir) => {
    const key = `${dir}_mps`;
    if (typeof speed[key] === 'number') return speed[key];
    if (typeof speed.average_mps === 'number') return speed.average_mps;
    return null;
  };

  const dirWait = (dir) => {
    const key = `${dir}_seconds`;
    if (typeof waiting[key] === 'number') return waiting[key];
    return waiting.average_seconds ?? null;
  };

  return (
    <Card title="Live Traffic Feed" titleIcon={<TableProperties size={14} />} noPadding>
      <div style={{ overflowX: 'auto' }}>
        <table className="traffic-table">
          <thead>
            <tr>
              <th>Direction</th>
              <th>Queue</th>
              <th>Wait (s)</th>
              <th>Avg Speed</th>
              <th>Signal</th>
            </tr>
          </thead>
          <tbody>
            {DIRS.map(dir => {
              const sig = dirSignal(dir, phaseIndex);
              return (
                <tr key={dir}>
                  <td className="direction-cell">{dir.toUpperCase()}</td>
                  <td>{queues[dir] ?? '--'}</td>
                  <td>{fmt(dirWait(dir), 1, 's')}</td>
                  <td>{fmt(dirSpeed(dir), 1, ' m/s')}</td>
                  <td><SignalPill state={sig} /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
};

export default LiveTrafficFeed;
