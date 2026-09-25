import React from 'react';

const AIStatusCard = ({ simulationStatus, trafficData }) => {
  const controller = simulationStatus?.controller || 'fixed';
  const isDQN = controller === 'dqn';
  const aiDecision = trafficData?.ai;

  return (
    <div className="card ai-status-card">
      <h3 className="ai-status-card-title">AI Controller Status</h3>
      
      <div className="ai-status-card-content">
        <div className="ai-controller-info">
          <div className="ai-controller-label">Controller</div>
          <div className={`ai-controller-value ${isDQN ? 'ai-active' : ''}`}>
            {isDQN ? 'DQN (AI)' : controller === 'adaptive' ? 'Adaptive' : 'Fixed-Time'}
          </div>
        </div>

        {isDQN && aiDecision && (
          <div className="ai-decision-info">
            <div className="ai-decision-label">Latest Decision</div>
            <div className="ai-decision-value">{aiDecision.action}</div>
            {aiDecision.reason && (
              <div className="ai-decision-reason">{aiDecision.reason}</div>
            )}
            <div className="ai-decision-details">
              <div className="ai-decision-detail">
                <span className="detail-label">Action ID:</span>
                <span className="detail-value">{aiDecision.action_id}</span>
              </div>
              <div className="ai-decision-detail">
                <span className="detail-label">Requested Phase:</span>
                <span className="detail-value">{aiDecision.requested_phase}</span>
              </div>
              <div className="ai-decision-detail">
                <span className="detail-label">Approved:</span>
                <span className={`detail-value ${aiDecision.approved ? 'approved' : 'rejected'}`}>
                  {aiDecision.approved ? 'Yes' : 'No'}
                </span>
              </div>
            </div>
          </div>
        )}

        {!isDQN && (
          <div className="ai-non-dqn-info">
            <div className="ai-non-dqn-message">
              {controller === 'adaptive' 
                ? 'Adaptive controller using queue-based logic' 
                : 'Fixed-time controller with predetermined intervals'}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default AIStatusCard;
