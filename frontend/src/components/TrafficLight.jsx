import React from 'react';
import { getSignalColor } from '../utils/formatters';

const TrafficLight = ({ state, phaseName, elapsedSeconds }) => {
  const color = getSignalColor(state);

  return (
    <div className="traffic-light">
      <div className="traffic-light-container">
        <div className={`traffic-light-bulb ${state === 'red' ? 'active' : ''}`} style={{ backgroundColor: state === 'red' ? '#ef4444' : '#374151' }}></div>
        <div className={`traffic-light-bulb ${state === 'yellow' ? 'active' : ''}`} style={{ backgroundColor: state === 'yellow' ? '#eab308' : '#374151' }}></div>
        <div className={`traffic-light-bulb ${state === 'green' ? 'active' : ''}`} style={{ backgroundColor: state === 'green' ? '#22c55e' : '#374151' }}></div>
      </div>
      <div className="traffic-light-info">
        <div className="traffic-light-phase">{phaseName || 'UNKNOWN'}</div>
        {typeof elapsedSeconds === 'number' && !isNaN(elapsedSeconds) && (
          <div className="traffic-light-elapsed">{elapsedSeconds.toFixed(1)}s</div>
        )}
      </div>
    </div>
  );
};

export default TrafficLight;
