import React from 'react';

const ConnectionStatus = ({ backend, websocket, mongodb }) => {
  return (
    <div className="card connection-status">
      <h3 className="connection-status-title">System Status</h3>
      <div className="connection-status-grid">
        <div className="connection-status-item">
          <span className="connection-status-label">Backend:</span>
          <span className={`status-badge ${backend ? 'online' : 'offline'}`}>
            {backend ? '● ONLINE' : '● OFFLINE'}
          </span>
        </div>
        <div className="connection-status-item">
          <span className="connection-status-label">WebSocket:</span>
          <span className={`status-badge ${websocket ? 'connected' : 'disconnected'}`}>
            {websocket ? '● CONNECTED' : '● DISCONNECTED'}
          </span>
        </div>
        {mongodb !== undefined && (
          <div className="connection-status-item">
            <span className="connection-status-label">MongoDB:</span>
            <span className={`status-badge ${mongodb ? 'online' : 'offline'}`}>
              {mongodb ? '● AVAILABLE' : '● UNAVAILABLE'}
            </span>
          </div>
        )}
      </div>
    </div>
  );
};

export default ConnectionStatus;
