import React from 'react';
import {
  Brain, Cpu, Zap, CheckCircle, Eye, ShieldCheck, ShieldAlert,
  ArrowRight, Sparkles, AlertTriangle, Layers
} from 'lucide-react';
import Card from '../common/Card';
import StatusBadge from '../common/StatusBadge';

const AGENTIC_LOOP_STAGES = [
  { key: 'observe', label: 'Observe', desc: 'Queues & Phase', icon: Eye },
  { key: 'decide', label: 'Decide', desc: 'DQN Q-Network', icon: Brain },
  { key: 'safety', label: 'Safety Check', desc: 'Clearance & Min Green', icon: ShieldCheck },
  { key: 'act', label: 'Actuate', desc: 'TraCI Phase Change', icon: Zap },
  { key: 'evaluate', label: 'Evaluate', desc: 'Reward & Delay', icon: CheckCircle },
];

const ACTION_MAP = {
  0: { label: 'KEEP_CURRENT_PHASE', short: 'KEEP', desc: 'Maintain active green corridor' },
  1: { label: 'REQUEST_NORTH_SOUTH', short: 'REQ_NS', desc: 'Transition green to North-South' },
  2: { label: 'REQUEST_EAST_WEST', short: 'REQ_EW', desc: 'Transition green to East-West' },
};

/**
 * Generates a strictly grounded explanation based ONLY on real backend telemetry.
 */
const buildGroundedExplanation = (ai, queues, signal) => {
  if (!ai || !ai.action) {
    return 'Waiting for active policy inference from reinforcement learning network.';
  }

  const actionName = ai.action;
  const qVals = ai.q_values || [];
  const hasQ = Array.isArray(qVals) && qVals.length === 3;
  const maxQ = hasQ ? Math.max(...qVals) : null;
  const selectedQ = hasQ && typeof ai.action_id === 'number' ? qVals[ai.action_id] : null;

  let explanation = `DQN policy selected action ${actionName}.`;

  if (hasQ && selectedQ != null) {
    if (selectedQ === maxQ) {
      explanation += ` Selected action yielded highest estimated Q-value (${selectedQ.toFixed(3)}) across the action space.`;
    } else {
      explanation += ` Evaluated Q-value: ${selectedQ.toFixed(3)}.`;
    }
  }

  if (queues) {
    const nsTotal = (queues.north ?? 0) + (queues.south ?? 0);
    const ewTotal = (queues.east ?? 0) + (queues.west ?? 0);
    explanation += ` Observed approach demand: NS=${nsTotal} queued, EW=${ewTotal} queued.`;
  }

  if (ai.approved === false) {
    explanation += ` Safety Manager restricted execution to guarantee minimum yellow/green clearance intervals.`;
  }

  return explanation;
};

const AgentStatus = ({ simulationStatus, trafficData }) => {
  const controller = simulationStatus?.controller || 'fixed';
  const isDQN = controller === 'dqn';
  const isRunning = simulationStatus?.running || false;
  const isStopped = simulationStatus?.status === 'stopped';
  const isCompleted = simulationStatus?.status === 'completed';

  const ai = trafficData?.ai;
  const queues = trafficData?.queues;
  const signal = trafficData?.signal;
  const speed = trafficData?.speed;

  const isApproved = ai?.approved === true;
  const isDenied = ai?.approved === false;

  const qValues = Array.isArray(ai?.q_values) ? ai.q_values : [];
  const maxQAbs = qValues.length > 0 ? Math.max(...qValues.map((v) => Math.abs(v))) : 1;

  const activeLoopStep = isRunning && isDQN
    ? ai?.approved === false
      ? 'safety'
      : ai?.action
        ? 'act'
        : 'observe'
    : null;

  const groundedExplanation = buildGroundedExplanation(ai, queues, signal);

  return (
    <Card
      title="Agentic AI Command Center"
      titleIcon={<Brain size={15} />}
      badge={
        <StatusBadge variant={isDQN && isRunning ? 'cyan' : isDQN ? 'blue' : controller === 'adaptive' ? 'green' : 'amber'}>
          {isDQN ? (isRunning ? '● DQN ACTIVE' : isCompleted ? 'DQN COMPLETED' : 'DQN STANDBY') : controller === 'adaptive' ? 'ADAPTIVE' : 'FIXED-TIME'}
        </StatusBadge>
      }
      noPadding
    >
      <div style={{ padding: '12px 14px' }}>
        {/* ── Emergency Vehicle Intelligence Section ──────────────── */}
        {trafficData?.emergency?.active && (
          <div
            style={{
              marginBottom: 12,
              background: 'rgba(239, 68, 68, 0.08)',
              border: '1px solid rgba(239, 68, 68, 0.4)',
              borderRadius: 'var(--radius-sm)',
              padding: '10px 12px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, fontWeight: 700, color: '#fca5a5', textTransform: 'uppercase' }}>
                <span style={{ fontSize: 14 }}>🚨</span> Emergency Vehicle Intelligence
              </div>
              <StatusBadge variant={trafficData.emergency.priority_active ? 'green' : 'amber'}>
                {trafficData.emergency.priority_active ? 'PRIORITY ACTIVE' : 'PRIORITY REQUESTED'}
              </StatusBadge>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6, marginBottom: 8, fontSize: 11 }}>
              <div style={{ background: 'var(--surface-2)', padding: '6px 8px', borderRadius: 4 }}>
                <div style={{ fontSize: 9.5, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Vehicle ID</div>
                <div style={{ fontWeight: 700, color: 'var(--text-primary)', marginTop: 2 }}>{trafficData.emergency.vehicle_id || 'EV_01'}</div>
              </div>
              <div style={{ background: 'var(--surface-2)', padding: '6px 8px', borderRadius: 4 }}>
                <div style={{ fontSize: 9.5, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Approach</div>
                <div style={{ fontWeight: 700, color: '#fef08a', textTransform: 'uppercase', marginTop: 2 }}>{trafficData.emergency.approach || '--'}</div>
              </div>
              <div style={{ background: 'var(--surface-2)', padding: '6px 8px', borderRadius: 4 }}>
                <div style={{ fontSize: 9.5, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Distance</div>
                <div style={{ fontWeight: 700, color: 'var(--text-primary)', marginTop: 2 }}>
                  {trafficData.emergency.distance != null ? `${Math.round(trafficData.emergency.distance)}m` : '--'}
                </div>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginBottom: 8, fontSize: 11 }}>
              <div style={{ background: 'var(--surface-2)', padding: '6px 8px', borderRadius: 4 }}>
                <div style={{ fontSize: 9.5, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Safety Status</div>
                <div style={{ fontWeight: 700, color: trafficData.emergency.priority_active ? 'var(--green)' : 'var(--amber)', marginTop: 2 }}>
                  {trafficData.emergency.safety_status || 'NORMAL'}
                </div>
              </div>
              <div style={{ background: 'var(--surface-2)', padding: '6px 8px', borderRadius: 4 }}>
                <div style={{ fontSize: 9.5, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Current Action</div>
                <div style={{ fontWeight: 700, color: 'var(--cyan)', marginTop: 2, fontSize: 10.5 }}>
                  {trafficData.emergency.current_action || 'NORMAL_CONTROL'}
                </div>
              </div>
            </div>

            <div style={{ fontSize: 10.5, color: '#fca5a5', lineHeight: 1.35, background: 'rgba(0,0,0,0.25)', padding: '6px 8px', borderRadius: 4 }}>
              <strong>Reason:</strong> {trafficData.emergency.reason || 'Safety Manager governing emergency corridor transition.'}
            </div>
          </div>
        )}

        {/* ── 1. Architectural Agentic Loop ────────────────── */}
        <div
          style={{
            background: 'var(--surface-2)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-sm)',
            padding: '10px 8px',
            marginBottom: 12,
          }}
        >
          <div
            style={{
              fontSize: 9.5,
              fontWeight: 700,
              color: 'var(--text-muted)',
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              marginBottom: 8,
              textAlign: 'center',
            }}
          >
            Autonomous Agentic Cycle
          </div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            {AGENTIC_LOOP_STAGES.map((st, i) => {
              const Icon = st.icon;
              const isActive = st.key === activeLoopStep;
              return (
                <React.Fragment key={st.key}>
                  <div
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'center',
                      flex: 1,
                      textAlign: 'center',
                    }}
                  >
                    <div
                      style={{
                        width: 26,
                        height: 26,
                        borderRadius: 6,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        background: isActive ? 'rgba(21, 184, 214, 0.2)' : 'var(--surface)',
                        border: `1px solid ${isActive ? 'var(--cyan)' : 'var(--border)'}`,
                        color: isActive ? 'var(--cyan)' : 'var(--text-muted)',
                        transition: 'all 0.2s ease',
                      }}
                    >
                      <Icon size={12} />
                    </div>
                    <span
                      style={{
                        fontSize: 9,
                        fontWeight: 600,
                        color: isActive ? 'var(--cyan)' : 'var(--text-muted)',
                        marginTop: 4,
                        textTransform: 'uppercase',
                      }}
                    >
                      {st.label}
                    </span>
                  </div>
                  {i < AGENTIC_LOOP_STAGES.length - 1 && (
                    <ArrowRight size={10} style={{ color: 'var(--border-bright)', opacity: 0.6 }} />
                  )}
                </React.Fragment>
              );
            })}
          </div>
        </div>

        {isDQN ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {/* ── 2. Observed Traffic State Grid ───────────── */}
            <div>
              <div
                style={{
                  fontSize: 10,
                  fontWeight: 700,
                  color: 'var(--text-muted)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  marginBottom: 5,
                }}
              >
                Observed Environment State
              </div>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(4, 1fr)',
                  gap: 6,
                  background: 'var(--surface-2)',
                  padding: '8px 10px',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid var(--border)',
                }}
              >
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: 9.5, color: 'var(--text-muted)' }}>North Q</div>
                  <strong style={{ fontSize: 13, color: 'var(--text-primary)', fontVariantNumeric: 'tabular-nums' }}>
                    {queues?.north ?? 0}
                  </strong>
                </div>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: 9.5, color: 'var(--text-muted)' }}>South Q</div>
                  <strong style={{ fontSize: 13, color: 'var(--text-primary)', fontVariantNumeric: 'tabular-nums' }}>
                    {queues?.south ?? 0}
                  </strong>
                </div>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: 9.5, color: 'var(--text-muted)' }}>East Q</div>
                  <strong style={{ fontSize: 13, color: 'var(--text-primary)', fontVariantNumeric: 'tabular-nums' }}>
                    {queues?.east ?? 0}
                  </strong>
                </div>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: 9.5, color: 'var(--text-muted)' }}>West Q</div>
                  <strong style={{ fontSize: 13, color: 'var(--text-primary)', fontVariantNumeric: 'tabular-nums' }}>
                    {queues?.west ?? 0}
                  </strong>
                </div>
              </div>
            </div>

            {/* ── 3. Q-Value Analysis (Policy Distribution) ── */}
            <div
              style={{
                background: 'var(--surface-2)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)',
                padding: '10px 12px',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: 6,
                }}
              >
                <span
                  style={{
                    fontSize: 10,
                    fontWeight: 700,
                    color: 'var(--text-muted)',
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                  }}
                >
                  Q-Value Action Estimates
                </span>
                <span style={{ fontSize: 9.5, color: 'var(--text-muted)' }}>
                  Discrete Policy Output
                </span>
              </div>

              {qValues.length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {[0, 1, 2].map((actIdx) => {
                    const actMeta = ACTION_MAP[actIdx];
                    const isSelected = ai?.action_id === actIdx;
                    const val = qValues[actIdx];
                    const barPct =
                      maxQAbs > 0 && typeof val === 'number'
                        ? Math.min(100, Math.max(12, (Math.abs(val) / maxQAbs) * 100))
                        : 33;

                    return (
                      <div
                        key={actIdx}
                        style={{
                          background: isSelected ? 'rgba(21, 184, 214, 0.12)' : 'rgba(0,0,0,0.15)',
                          border: `1px solid ${isSelected ? 'var(--cyan)' : 'transparent'}`,
                          borderRadius: 4,
                          padding: '5px 8px',
                          transition: 'all 0.15s ease',
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span
                            style={{
                              fontSize: 11,
                              fontWeight: isSelected ? 700 : 500,
                              color: isSelected ? 'var(--cyan)' : 'var(--text-secondary)',
                            }}
                          >
                            {isSelected ? '▶ ' : '  '}
                            {actMeta.label}
                          </span>
                          <span
                            style={{
                              fontFamily: 'monospace',
                              fontWeight: 700,
                              fontSize: 11,
                              color: isSelected ? 'var(--cyan)' : 'var(--text-primary)',
                            }}
                          >
                            {typeof val === 'number' ? val.toFixed(3) : '--'}
                          </span>
                        </div>
                        <div
                          style={{
                            height: 3,
                            background: 'var(--surface)',
                            borderRadius: 2,
                            overflow: 'hidden',
                            marginTop: 3,
                          }}
                        >
                          <div
                            style={{
                              height: '100%',
                              width: `${barPct}%`,
                              background: isSelected
                                ? 'linear-gradient(90deg, var(--blue), var(--cyan))'
                                : 'rgba(122, 165, 210, 0.3)',
                              borderRadius: 2,
                            }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div style={{ fontSize: 11, color: 'var(--text-muted)', textAlign: 'center', padding: '6px 0' }}>
                  {isRunning ? 'Computing neural Q-values…' : 'Q-values available when DQN runs.'}
                </div>
              )}
            </div>

            {/* ── 4. Selected Action & Safety Manager ──────── */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              <div
                style={{
                  background: 'var(--surface-2)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-sm)',
                  padding: '8px 10px',
                }}
              >
                <div style={{ fontSize: 9.5, color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>
                  Selected Action
                </div>
                <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--cyan)', marginTop: 2 }}>
                  {ai?.action || '--'}
                </div>
              </div>

              <div
                style={{
                  background: 'var(--surface-2)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-sm)',
                  padding: '8px 10px',
                }}
              >
                <div style={{ fontSize: 9.5, color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>
                  Safety Manager
                </div>
                <div
                  style={{
                    fontSize: 11.5,
                    fontWeight: 700,
                    marginTop: 2,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 4,
                    color: isApproved ? 'var(--green)' : isDenied ? 'var(--red)' : 'var(--text-muted)',
                  }}
                >
                  {isApproved ? (
                    <>
                      <ShieldCheck size={13} /> APPROVED
                    </>
                  ) : isDenied ? (
                    <>
                      <ShieldAlert size={13} /> RESTRICTED
                    </>
                  ) : (
                    '--'
                  )}
                </div>
              </div>
            </div>

            {/* ── 5. Reward & Decision Timestamp ──────────── */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              <div
                style={{
                  background: 'var(--surface-2)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-sm)',
                  padding: '8px 10px',
                }}
              >
                <div style={{ fontSize: 9.5, color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>
                  Step Reward
                </div>
                <div
                  style={{
                    fontSize: 12,
                    fontWeight: 700,
                    color: typeof ai?.reward === 'number' ? (ai.reward >= 0 ? 'var(--green)' : 'var(--amber)') : 'var(--text-muted)',
                    marginTop: 2,
                    fontFamily: 'monospace',
                  }}
                >
                  {typeof ai?.reward === 'number' ? ai.reward.toFixed(3) : '--'}
                </div>
              </div>

              <div
                style={{
                  background: 'var(--surface-2)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-sm)',
                  padding: '8px 10px',
                }}
              >
                <div style={{ fontSize: 9.5, color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>
                  Decision Time
                </div>
                <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-primary)', marginTop: 2 }}>
                  {typeof ai?.decision_time === 'number' ? `t = ${ai.decision_time.toFixed(1)}s` : '--'}
                </div>
              </div>
            </div>

            {/* ── 6. Grounded AI Explanation (Why this action?) */}
            <div
              style={{
                background: 'rgba(21, 184, 214, 0.06)',
                border: '1px solid rgba(21, 184, 214, 0.25)',
                borderRadius: 'var(--radius-sm)',
                padding: '8px 10px',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 5,
                  fontSize: 10,
                  fontWeight: 700,
                  color: 'var(--cyan)',
                  textTransform: 'uppercase',
                  marginBottom: 3,
                }}
              >
                <Sparkles size={11} /> Grounded Rationale
              </div>
              <p style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.4, margin: 0 }}>
                {groundedExplanation}
              </p>
            </div>
          </div>
        ) : (
          <div className="agent-non-dqn">
            {controller === 'adaptive'
              ? 'Adaptive controller is active — using queue-length heuristic logic.'
              : 'Fixed-Time controller is active — using predetermined cycle phases.'}
            <div style={{ marginTop: 6, fontSize: 11, color: 'var(--text-muted)' }}>
              Switch to DQN (AI) to activate policy neural network & decision telemetry.
            </div>
          </div>
        )}
      </div>
    </Card>
  );
};

export default AgentStatus;
