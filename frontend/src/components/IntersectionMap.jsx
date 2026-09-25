import React from 'react';
import TrafficLight from './TrafficLight';
import { getSignalColor } from '../utils/formatters';

const IntersectionMap = ({ trafficData, simulationStatus }) => {
  const queues = trafficData?.queues || { north: 0, south: 0, east: 0, west: 0, total: 0 };
  const signal = trafficData?.signal || { phase_index: 0, phase_name: 'NS_GREEN', state: 'green', elapsed_seconds: 0 };
  const controller = simulationStatus?.controller || 'fixed';

  const getQueueColor = (count) => {
    if (count === 0) return '#22c55e';
    if (count <= 3) return '#84cc16';
    if (count <= 6) return '#eab308';
    if (count <= 10) return '#f97316';
    return '#ef4444';
  };

  const getNSGreen = () => signal.phase_index === 0;
  const getEWGreen = () => signal.phase_index === 2;

  return (
    <div className="card intersection-map">
      <div className="intersection-map-header">
        <h3 className="intersection-map-title">Digital Twin Intersection</h3>
        <div className="intersection-map-subtitle">4-Way Urban Junction • INT-001</div>
      </div>

      <div className="intersection-map-visualization">
        <div className="intersection-container">
          {/* North Approach */}
          <div className="approach north">
            <div className="approach-road">
              <div className="approach-queue" style={{ 
                backgroundColor: getQueueColor(queues.north),
                width: `${Math.min(queues.north * 10, 100)}%`
              }}>
                <span className="queue-count">{queues.north}</span>
              </div>
            </div>
            <div className="approach-label">NORTH</div>
            <TrafficLight 
              state={getNSGreen() ? 'green' : 'red'} 
              phaseName={getNSGreen() ? 'GREEN' : 'RED'}
              elapsedSeconds={getNSGreen() ? signal.elapsed_seconds : null}
            />
          </div>

          {/* East Approach */}
          <div className="approach east">
            <div className="approach-road">
              <div className="approach-queue" style={{ 
                backgroundColor: getQueueColor(queues.east),
                width: `${Math.min(queues.east * 10, 100)}%`
              }}>
                <span className="queue-count">{queues.east}</span>
              </div>
            </div>
            <div className="approach-label">EAST</div>
            <TrafficLight 
              state={getEWGreen() ? 'green' : 'red'} 
              phaseName={getEWGreen() ? 'GREEN' : 'RED'}
              elapsedSeconds={getEWGreen() ? signal.elapsed_seconds : null}
            />
          </div>

          {/* Central Intersection */}
          <div className="intersection-center">
            <div className="intersection-crossroads">
              <div className="crossroad-ns"></div>
              <div className="crossroad-ew"></div>
            </div>
            <div className="intersection-info">
              <div className="controller-badge">{controller.toUpperCase()}</div>
              <div className="total-queue">Total Queue: {queues.total}</div>
            </div>
          </div>

          {/* South Approach */}
          <div className="approach south">
            <div className="approach-road">
              <div className="approach-queue" style={{ 
                backgroundColor: getQueueColor(queues.south),
                width: `${Math.min(queues.south * 10, 100)}%`
              }}>
                <span className="queue-count">{queues.south}</span>
              </div>
            </div>
            <div className="approach-label">SOUTH</div>
            <TrafficLight 
              state={getNSGreen() ? 'green' : 'red'} 
              phaseName={getNSGreen() ? 'GREEN' : 'RED'}
              elapsedSeconds={getNSGreen() ? signal.elapsed_seconds : null}
            />
          </div>

          {/* West Approach */}
          <div className="approach west">
            <div className="approach-road">
              <div className="approach-queue" style={{ 
                backgroundColor: getQueueColor(queues.west),
                width: `${Math.min(queues.west * 10, 100)}%`
              }}>
                <span className="queue-count">{queues.west}</span>
              </div>
            </div>
            <div className="approach-label">WEST</div>
            <TrafficLight 
              state={getEWGreen() ? 'green' : 'red'} 
              phaseName={getEWGreen() ? 'GREEN' : 'RED'}
              elapsedSeconds={getEWGreen() ? signal.elapsed_seconds : null}
            />
          </div>
        </div>
      </div>

      <div className="intersection-map-legend">
        <div className="legend-item">
          <div className="legend-color" style={{ backgroundColor: '#22c55e' }}></div>
          <span className="legend-label">0-3 vehicles</span>
        </div>
        <div className="legend-item">
          <div className="legend-color" style={{ backgroundColor: '#84cc16' }}></div>
          <span className="legend-label">4-6 vehicles</span>
        </div>
        <div className="legend-item">
          <div className="legend-color" style={{ backgroundColor: '#eab308' }}></div>
          <span className="legend-label">7-10 vehicles</span>
        </div>
        <div className="legend-item">
          <div className="legend-color" style={{ backgroundColor: '#f97316' }}></div>
          <span className="legend-label">11+ vehicles</span>
        </div>
      </div>
    </div>
  );
};

export default IntersectionMap;
