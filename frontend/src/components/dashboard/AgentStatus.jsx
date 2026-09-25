import React from 'react';
import { Eye, Brain, Cpu, Zap, CheckCircle } from 'lucide-react';
import Card from '../common/Card';
import StatusBadge from '../common/StatusBadge';

/* The five pipeline steps every agentic cycle goes through */
const STEPS = [
  { key: 'observe',   label: 'Observe',   icon: Eye       },
  { key: 'reason',    label: 'Reason',    icon: Brain     },
  { key: 'decide',    label: 'Decide',    icon: Cpu       },
  { key: 'act',       label: 'Act',       icon: Zap       },
  { key: 'evaluate',  label: 'Evaluate',  icon: CheckCircle },
];

/**
 * Props:
 *   simulationStatus – from useTrafficWebSocket
 *   trafficData      – from useTrafficWebSocket
 */
const AgentStatus = ({ simulationStatus, trafficData }) => {
  const controller = simulationStatus?.controller || 'fixed';
  const isDQN      = controller === 'dqn';
  const isRunning  = simulationStatus?.running || false;
  const ai         = trafficData?.ai;
  const queues     = trafficData?.queues;

  /* Determine which pipeline step is "active" when DQN is running */
  const activeStep = isRunning && isDQN
    ? (ai?.action ? 'act' : 'observe')
    : null;

  const decisionStatus = ai?.approved === true
    ? 'Executed'
    : ai?.approved === false
      ? 'Safety Restricted'
      : '--';

  const decisionVariant = ai?.approved === true
    ? 'green'
    : ai?.approved === false
      ? 'red'
      : 'gray';

  const ctrlBadgeVariant = isDQN ? 'cyan' : controller === 'adaptive' ? 'green' : 'amber';
  const ctrlLabel = isDQN ? 'DQN (AI)' : controller === 'adaptive' ? 'Adaptive' : 'Fixed-Time';

  return (
    <Card
      title="AI Agent Status"
      titleIcon={<Brain size={14} />}
      badge={<StatusBadge variant={ctrlBadgeVariant}>{ctrlLabel}</StatusBadge>}
      noPadding
    >
      <div className="agent-body">
        {/* Pipeline visualisation */}
        <div className="agent-pipeline">
          {STEPS.map((step, i) => {
            const Icon = step.icon;
            const isActive = step.key === activeStep;
            return (
              <React.Fragment key={step.key}>
                <div className={`agent-step${isActive ? ' active' : ''}`}>
                  <div className="agent-step-icon">
                    <Icon size={13} />
                  </div>
                  <div className="agent-step-label">{step.label}</div>
                </div>
                {i < STEPS.length - 1 && (
                  <div className="agent-arrow">›</div>
                )}
              </React.Fragment>
            );
          })}
        </div>

        {/* DQN data grid */}
        {isDQN ? (
          <div className="agent-data-grid">
            <div className="agent-data-item">
              <div className="agent-data-key">Selected Action</div>
              <div className={`agent-data-val${ai?.action ? ' dqn' : ''}`}>
                {ai?.action || '--'}
              </div>
            </div>

            <div className="agent-data-item">
              <div className="agent-data-key">Decision</div>
              <div className={`agent-data-val ${decisionVariant === 'green' ? 'approved' : decisionVariant === 'red' ? 'denied' : ''}`}>
                {decisionStatus}
              </div>
            </div>

            <div className="agent-data-item">
              <div className="agent-data-key">Current State</div>
              <div className="agent-data-val" style={{ fontSize: 11 }}>
                {queues
                  ? `N:${queues.north ?? 0} S:${queues.south ?? 0} E:${queues.east ?? 0} W:${queues.west ?? 0}`
                  : '--'}
              </div>
            </div>

            <div className="agent-data-item">
              <div className="agent-data-key">Requested Phase</div>
              <div className="agent-data-val" style={{ fontSize: 11 }}>
                {ai?.requested_phase != null ? String(ai.requested_phase) : '--'}
              </div>
            </div>

            {/* Q-values — only shown if backend exposes them */}
            {Array.isArray(ai?.q_values) && ai.q_values.length > 0 && (
              <div className="agent-data-item" style={{ gridColumn: '1 / -1' }}>
                <div className="agent-data-key">Q-Values</div>
                <div className="agent-data-val" style={{ fontSize: 11, fontFamily: 'monospace' }}>
                  [{ai.q_values.map(v => (typeof v === 'number' ? v.toFixed(2) : v)).join(', ')}]
                </div>
              </div>
            )}

            {/* Reward — only shown if available */}
            {typeof ai?.reward === 'number' && (
              <div className="agent-data-item" style={{ gridColumn: '1 / -1' }}>
                <div className="agent-data-key">Reward</div>
                <div className="agent-data-val" style={{ color: ai.reward >= 0 ? 'var(--green)' : 'var(--red)' }}>
                  {ai.reward.toFixed(3)}
                </div>
              </div>
            )}

            {/* Reason */}
            {ai?.reason && (
              <div className="agent-data-item" style={{ gridColumn: '1 / -1' }}>
                <div className="agent-data-key">Reason</div>
                <div style={{ fontSize: 11, color: 'var(--text-secondary)', fontStyle: 'italic', marginTop: 2 }}>
                  {ai.reason}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="agent-non-dqn">
            {controller === 'adaptive'
              ? 'Adaptive controller is active — using queue-length heuristic logic.'
              : 'Fixed-Time controller is active — using predetermined phase intervals.'}
            <div style={{ marginTop: 6, fontSize: 11, color: 'var(--text-muted)' }}>
              Switch to DQN (AI) to enable agentic decision-making.
            </div>
          </div>
        )}
      </div>
    </Card>
  );
};

export default AgentStatus;
