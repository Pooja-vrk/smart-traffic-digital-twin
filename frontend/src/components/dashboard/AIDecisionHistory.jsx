import React, { useState, useMemo } from 'react';
import {
  History, ShieldCheck, ShieldAlert, Cpu, Eye, X,
  ChevronLeft, ChevronRight, Filter, AlertTriangle,
  Siren, Sparkles, Activity, Clock, Gauge, ArrowRight
} from 'lucide-react';
import Card from '../common/Card';
import StatusBadge from '../common/StatusBadge';

const formatActionName = (action) => {
  if (!action) return '--';
  return action.replace('REQUEST_', 'REQ ').replace('_', ' ');
};

const AIDecisionHistory = ({
  decisions = [],
  isRunning = false,
  simulationId = null,
}) => {
  const [filterType, setFilterType] = useState('all'); // 'all', 'override', 'emergency'
  const [controllerFilter, setControllerFilter] = useState('all');
  const [selectedDecisionIndex, setSelectedDecisionIndex] = useState(null);

  // Apply filtering
  const filteredDecisions = useMemo(() => {
    return decisions.filter((d) => {
      // Safety override filter
      if (filterType === 'override') {
        const isOverride = d.is_safety_override === true || d.approved === false;
        if (!isOverride) return false;
      }
      // Emergency priority filter
      if (filterType === 'emergency') {
        const isEmergency =
          (d.emergency && d.emergency.active) ||
          d.action === 'REQUEST_EMERGENCY_PRIORITY' ||
          d.requested_action === 'REQUEST_EMERGENCY_PRIORITY';
        if (!isEmergency) return false;
      }
      // Controller filter
      if (controllerFilter !== 'all') {
        const c = String(d.controller || '').toLowerCase();
        if (!c.includes(controllerFilter.toLowerCase())) return false;
      }
      return true;
    });
  }, [decisions, filterType, controllerFilter]);

  const selectedDecision =
    selectedDecisionIndex !== null && filteredDecisions[selectedDecisionIndex]
      ? filteredDecisions[selectedDecisionIndex]
      : null;

  const handlePrevDecision = () => {
    if (selectedDecisionIndex > 0) {
      setSelectedDecisionIndex(selectedDecisionIndex - 1);
    }
  };

  const handleNextDecision = () => {
    if (selectedDecisionIndex < filteredDecisions.length - 1) {
      setSelectedDecisionIndex(selectedDecisionIndex + 1);
    }
  };

  return (
    <>
      <Card
        title="Explainable Agentic AI Decision Stream"
        titleIcon={<History size={14} />}
        badge={
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            {decisions.some(d => d.is_safety_override) && (
              <span
                style={{
                  fontSize: 10,
                  padding: '2px 6px',
                  borderRadius: 4,
                  background: 'rgba(239, 68, 68, 0.15)',
                  color: 'var(--red)',
                  fontWeight: 600,
                }}
              >
                Overrides Logged
              </span>
            )}
            <StatusBadge variant={isRunning ? 'cyan' : 'gray'}>
              {isRunning ? `${decisions.length} Decisions` : 'History Log'}
            </StatusBadge>
          </div>
        }
        noPadding
      >
        {/* Filter bar */}
        <div
          style={{
            padding: '8px 12px',
            background: 'var(--surface-2)',
            borderBottom: '1px solid var(--border)',
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 8,
            fontSize: 11,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <Filter size={11} style={{ color: 'var(--text-muted)' }} />
            <button
              onClick={() => setFilterType('all')}
              style={{
                background: filterType === 'all' ? 'var(--cyan)' : 'transparent',
                color: filterType === 'all' ? '#000' : 'var(--text-secondary)',
                border: '1px solid var(--border)',
                borderRadius: 4,
                padding: '2px 8px',
                fontWeight: 600,
                cursor: 'pointer',
                fontSize: 10.5,
              }}
            >
              All ({decisions.length})
            </button>
            <button
              onClick={() => setFilterType('override')}
              style={{
                background: filterType === 'override' ? 'var(--red)' : 'transparent',
                color: filterType === 'override' ? '#fff' : 'var(--text-secondary)',
                border: '1px solid var(--border)',
                borderRadius: 4,
                padding: '2px 8px',
                fontWeight: 600,
                cursor: 'pointer',
                fontSize: 10.5,
              }}
            >
              Safety Overrides
            </button>
            <button
              onClick={() => setFilterType('emergency')}
              style={{
                background: filterType === 'emergency' ? 'var(--purple)' : 'transparent',
                color: filterType === 'emergency' ? '#fff' : 'var(--text-secondary)',
                border: '1px solid var(--border)',
                borderRadius: 4,
                padding: '2px 8px',
                fontWeight: 600,
                cursor: 'pointer',
                fontSize: 10.5,
              }}
            >
              Emergency Priority
            </button>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ color: 'var(--text-muted)', fontSize: 10.5 }}>Controller:</span>
            <select
              value={controllerFilter}
              onChange={(e) => setControllerFilter(e.target.value)}
              style={{
                background: 'var(--surface-1)',
                color: 'var(--text-primary)',
                border: '1px solid var(--border)',
                borderRadius: 4,
                padding: '2px 6px',
                fontSize: 10.5,
              }}
            >
              <option value="all">All Controllers</option>
              <option value="dqn">DQN Agent</option>
              <option value="adaptive">Adaptive</option>
              <option value="fixed">Fixed-Time</option>
            </select>
          </div>
        </div>

        {/* Decisions Table */}
        <div style={{ maxHeight: 220, overflowY: 'auto' }}>
          {filteredDecisions.length === 0 ? (
            <div
              style={{
                padding: '24px 16px',
                textAlign: 'center',
                color: 'var(--text-muted)',
                fontSize: 12,
              }}
            >
              <Cpu size={24} style={{ opacity: 0.3, margin: '0 auto 8px', display: 'block' }} />
              {decisions.length === 0
                ? isRunning
                  ? 'Awaiting first decision from active controller…'
                  : 'Start a simulation to stream real-time decision telemetry.'
                : 'No decisions match the selected filter criteria.'}
            </div>
          ) : (
            <table className="traffic-table" style={{ fontSize: 11.5 }}>
              <thead>
                <tr>
                  <th style={{ width: '15%' }}>Sim Time</th>
                  <th style={{ width: '30%' }}>Proposed Action</th>
                  <th style={{ width: '25%' }}>Safety Validation</th>
                  <th style={{ width: '20%' }}>Outcome / Reward</th>
                  <th style={{ width: '10%', textAlign: 'center' }}>Inspect</th>
                </tr>
              </thead>
              <tbody>
                {filteredDecisions.map((d, index) => {
                  const isApproved = d.approved === true || d.validated_action === 'APPROVED';
                  const isOverride = d.is_safety_override === true;
                  const isLatest = index === 0 && isRunning;
                  const actionName = d.requested_action || d.action || 'KEEP';
                  const maxQ =
                    Array.isArray(d.q_values) && d.q_values.length > 0
                      ? Math.max(...d.q_values).toFixed(2)
                      : null;

                  return (
                    <tr
                      key={d.decision_id || d.id || `${d.simulation_time}-${index}`}
                      onClick={() => setSelectedDecisionIndex(index)}
                      style={{
                        background:
                          selectedDecisionIndex === index
                            ? 'rgba(21, 184, 214, 0.16)'
                            : isLatest
                            ? 'rgba(21, 184, 214, 0.08)'
                            : undefined,
                        cursor: 'pointer',
                        transition: 'background 0.2s',
                      }}
                    >
                      <td style={{ fontWeight: 600, color: 'var(--text-secondary)' }}>
                        {typeof d.simulation_time === 'number'
                          ? `${d.simulation_time.toFixed(1)}s`
                          : `${d.decision_time || d.step || 0}s`}
                      </td>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                          <span
                            style={{
                              fontWeight: 700,
                              color:
                                actionName.includes('NORTH_SOUTH') || d.action_id === 1
                                  ? 'var(--green)'
                                  : actionName.includes('EAST_WEST') || d.action_id === 2
                                  ? 'var(--cyan)'
                                  : actionName.includes('EMERGENCY')
                                  ? 'var(--purple)'
                                  : 'var(--text-primary)',
                            }}
                          >
                            {formatActionName(actionName)}
                          </span>
                          {maxQ && (
                            <span style={{ fontSize: 9.5, color: 'var(--text-muted)' }}>
                              (Q:{maxQ})
                            </span>
                          )}
                        </div>
                      </td>
                      <td>
                        {isOverride ? (
                          <span
                            style={{
                              color: 'var(--red)',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: 3,
                              fontWeight: 600,
                              fontSize: 10,
                              background: 'rgba(239, 68, 68, 0.12)',
                              padding: '1px 5px',
                              borderRadius: 3,
                            }}
                          >
                            <ShieldAlert size={10} /> OVERRIDE
                          </span>
                        ) : isApproved ? (
                          <span
                            style={{
                              color: 'var(--green)',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: 3,
                              fontWeight: 600,
                              fontSize: 10,
                            }}
                          >
                            <ShieldCheck size={11} /> APPROVED
                          </span>
                        ) : (
                          <span
                            style={{
                              color: 'var(--amber)',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: 3,
                              fontWeight: 600,
                              fontSize: 10,
                            }}
                          >
                            <ShieldAlert size={11} /> RESTRICTED
                          </span>
                        )}
                      </td>
                      <td style={{ fontFamily: 'monospace', fontSize: 11 }}>
                        {typeof d.reward === 'number' ? (
                          <span style={{ color: d.reward >= 0 ? 'var(--green)' : 'var(--amber)' }}>
                            {d.reward.toFixed(3)}
                          </span>
                        ) : d.post_action_metrics?.queue_delta != null ? (
                          <span
                            style={{
                              color:
                                d.post_action_metrics.queue_delta <= 0
                                  ? 'var(--green)'
                                  : 'var(--amber)',
                            }}
                          >
                            ΔQ: {d.post_action_metrics.queue_delta > 0 ? '+' : ''}
                            {d.post_action_metrics.queue_delta}
                          </span>
                        ) : (
                          <span style={{ color: 'var(--text-muted)' }}>--</span>
                        )}
                      </td>
                      <td style={{ textAlign: 'center' }}>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedDecisionIndex(index);
                          }}
                          style={{
                            background: 'transparent',
                            border: 'none',
                            color: 'var(--cyan)',
                            cursor: 'pointer',
                            padding: 2,
                          }}
                          title="Inspect complete 7-stage explanation"
                        >
                          <Eye size={12} />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </Card>

      {/* ── EXPLAINABLE AI DECISION INSPECTION MODAL ──────────────────────── */}
      {selectedDecision && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.75)',
            backdropFilter: 'blur(4px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 9999,
            padding: 16,
          }}
          onClick={() => setSelectedDecisionIndex(null)}
        >
          <div
            style={{
              background: 'var(--surface-1)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)',
              width: '100%',
              maxWidth: 720,
              maxHeight: '90vh',
              overflowY: 'auto',
              boxShadow: '0 20px 40px rgba(0, 0, 0, 0.5)',
              display: 'flex',
              flexDirection: 'column',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div
              style={{
                padding: '14px 18px',
                borderBottom: '1px solid var(--border)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                background: 'var(--surface-2)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Sparkles size={16} style={{ color: 'var(--cyan)' }} />
                <div>
                  <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--text-primary)' }}>
                    7-Stage Decision Explanation
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                    Step {selectedDecision.step || 0} • Sim Time:{' '}
                    {typeof selectedDecision.simulation_time === 'number'
                      ? `${selectedDecision.simulation_time.toFixed(1)}s`
                      : `${selectedDecision.decision_time || 0}s`}{' '}
                    • Controller: {selectedDecision.controller || 'DQN'}
                  </div>
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <button
                  disabled={selectedDecisionIndex <= 0}
                  onClick={handlePrevDecision}
                  style={{
                    background: 'var(--surface-1)',
                    border: '1px solid var(--border)',
                    borderRadius: 4,
                    color: selectedDecisionIndex <= 0 ? 'var(--text-muted)' : 'var(--text-primary)',
                    padding: '4px 8px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 4,
                    fontSize: 11,
                    cursor: selectedDecisionIndex <= 0 ? 'not-allowed' : 'pointer',
                  }}
                >
                  <ChevronLeft size={13} /> Prev
                </button>
                <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                  {selectedDecisionIndex + 1} / {filteredDecisions.length}
                </span>
                <button
                  disabled={selectedDecisionIndex >= filteredDecisions.length - 1}
                  onClick={handleNextDecision}
                  style={{
                    background: 'var(--surface-1)',
                    border: '1px solid var(--border)',
                    borderRadius: 4,
                    color:
                      selectedDecisionIndex >= filteredDecisions.length - 1
                        ? 'var(--text-muted)'
                        : 'var(--text-primary)',
                    padding: '4px 8px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 4,
                    fontSize: 11,
                    cursor:
                      selectedDecisionIndex >= filteredDecisions.length - 1
                        ? 'not-allowed'
                        : 'pointer',
                  }}
                >
                  Next <ChevronRight size={13} />
                </button>
                <button
                  onClick={() => setSelectedDecisionIndex(null)}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    color: 'var(--text-muted)',
                    cursor: 'pointer',
                    padding: 4,
                    marginLeft: 8,
                  }}
                >
                  <X size={18} />
                </button>
              </div>
            </div>

            {/* Modal Body: 7-Stage Walkthrough */}
            <div style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 14 }}>
              {/* Safety Override Alert Banner if applicable */}
              {selectedDecision.is_safety_override && (
                <div
                  style={{
                    background: 'rgba(239, 68, 68, 0.12)',
                    border: '1px solid var(--red)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '10px 14px',
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: 10,
                  }}
                >
                  <ShieldAlert size={18} style={{ color: 'var(--red)', flexShrink: 0, marginTop: 2 }} />
                  <div>
                    <div style={{ fontWeight: 700, color: 'var(--red)', fontSize: 12 }}>
                      Safety Manager Override Enforced
                    </div>
                    <div style={{ fontSize: 11.5, color: 'var(--text-secondary)', marginTop: 2 }}>
                      {selectedDecision.safety_reason ||
                        'The active signal safety state machine modified or deferred the controller proposed action to protect conflict clearances.'}
                    </div>
                  </div>
                </div>
              )}

              {/* Action Comparison: Proposed vs Executed */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: '1fr 1fr',
                  gap: 12,
                  background: 'var(--surface-2)',
                  padding: 12,
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid var(--border)',
                }}
              >
                <div>
                  <div style={{ fontSize: 10, textTransform: 'uppercase', color: 'var(--text-muted)', fontWeight: 600 }}>
                    Proposed Action (Policy)
                  </div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--cyan)', marginTop: 4 }}>
                    {selectedDecision.requested_action || selectedDecision.action || 'KEEP'}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 2 }}>
                    Target Phase: Phase {selectedDecision.requested_phase ?? '--'}
                  </div>
                </div>

                <div>
                  <div style={{ fontSize: 10, textTransform: 'uppercase', color: 'var(--text-muted)', fontWeight: 600 }}>
                    Executed Phase (Safety Enforced)
                  </div>
                  <div
                    style={{
                      fontSize: 14,
                      fontWeight: 700,
                      color: selectedDecision.is_safety_override ? 'var(--amber)' : 'var(--green)',
                      marginTop: 4,
                    }}
                  >
                    Phase {selectedDecision.validated_phase ?? selectedDecision.current_phase ?? '--'} ({selectedDecision.validated_action || 'APPROVED'})
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 2 }}>
                    Status: {selectedDecision.safety_status || 'SAFE'}
                  </div>
                </div>
              </div>

              {/* Stage 1: Observe */}
              <div style={{ borderLeft: '3px solid var(--blue)', paddingLeft: 12 }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--blue)', textTransform: 'uppercase' }}>
                  Stage 1: Observation Telemetry
                </div>
                <div style={{ fontSize: 11.5, color: 'var(--text-secondary)', marginTop: 4 }}>
                  {selectedDecision.observation?.queue_length_by_approach ? (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8, marginTop: 6 }}>
                      {['north', 'south', 'east', 'west'].map((dir) => (
                        <div key={dir} style={{ background: 'var(--surface-2)', padding: '6px 8px', borderRadius: 4 }}>
                          <span style={{ textTransform: 'capitalize', color: 'var(--text-muted)', fontSize: 10 }}>{dir}: </span>
                          <span style={{ fontWeight: 600 }}>{selectedDecision.observation.queue_length_by_approach[dir] || 0} veh</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div>Observed queues: {selectedDecision.observation?.total_queue || 0} total vehicles</div>
                  )}
                </div>
              </div>

              {/* Stage 2: Analyze */}
              <div style={{ borderLeft: '3px solid var(--cyan)', paddingLeft: 12 }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--cyan)', textTransform: 'uppercase' }}>
                  Stage 2: Pressure & Corridor Analysis
                </div>
                <div style={{ fontSize: 11.5, color: 'var(--text-secondary)', marginTop: 4 }}>
                  {selectedDecision.detected_conditions ? (
                    <div>
                      NS Pressure: <strong>{selectedDecision.detected_conditions.ns_pressure ?? 0}</strong> • EW Pressure:{' '}
                      <strong>{selectedDecision.detected_conditions.ew_pressure ?? 0}</strong> • Imbalance:{' '}
                      <strong>{selectedDecision.detected_conditions.pressure_imbalance ?? 0}</strong> • Dominant:{' '}
                      <strong>{selectedDecision.detected_conditions.dominant_corridor || 'BALANCED'}</strong> • Congestion:{' '}
                      <span style={{ color: 'var(--cyan)', fontWeight: 600 }}>
                        {selectedDecision.detected_conditions.congestion_level || 'NORMAL'}
                      </span>
                    </div>
                  ) : (
                    <div>Queue pressure and directional balance evaluated across approaches.</div>
                  )}
                </div>
              </div>

              {/* Stage 3: Select Action */}
              <div style={{ borderLeft: '3px solid var(--green)', paddingLeft: 12 }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--green)', textTransform: 'uppercase' }}>
                  Stage 3: Policy Selection & Rationale
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-primary)', marginTop: 4, lineHeight: 1.4 }}>
                  {selectedDecision.decision_reason || selectedDecision.reason || 'Controller evaluated current state.'}
                </div>
                {Array.isArray(selectedDecision.q_values) && selectedDecision.q_values.length > 0 && (
                  <div style={{ marginTop: 6, fontSize: 11, color: 'var(--text-secondary)' }}>
                    <span style={{ color: 'var(--text-muted)' }}>Q-values (Expected Cumulative Returns): </span>
                    <span style={{ fontFamily: 'monospace' }}>
                      [KEEP: {selectedDecision.q_values[0]?.toFixed(2) ?? '--'}, REQ_NS:{' '}
                      {selectedDecision.q_values[1]?.toFixed(2) ?? '--'}, REQ_EW:{' '}
                      {selectedDecision.q_values[2]?.toFixed(2) ?? '--'}]
                    </span>
                    <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
                      * Note: Values represent estimated cumulative discounted reward across future steps, not state probabilities.
                    </div>
                  </div>
                )}
              </div>

              {/* Stage 4: Safety Validation */}
              <div style={{ borderLeft: '3px solid var(--amber)', paddingLeft: 12 }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--amber)', textTransform: 'uppercase' }}>
                  Stage 4: Safety State Machine Validation
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-primary)', marginTop: 4 }}>
                  {selectedDecision.safety_reason || 'Safety manager validated phase timing constraints.'}
                </div>
              </div>

              {/* Stage 6: Evaluate / Outcome */}
              {selectedDecision.post_action_metrics && (
                <div style={{ borderLeft: '3px solid var(--purple)', paddingLeft: 12 }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--purple)', textTransform: 'uppercase' }}>
                    Stage 6: Outcome Performance Deltas
                  </div>
                  <div style={{ display: 'flex', gap: 14, marginTop: 6, fontSize: 11 }}>
                    <div style={{ background: 'var(--surface-2)', padding: '6px 10px', borderRadius: 4 }}>
                      Queue Delta:{' '}
                      <strong
                        style={{
                          color:
                            selectedDecision.post_action_metrics.queue_delta <= 0
                              ? 'var(--green)'
                              : 'var(--red)',
                        }}
                      >
                        {selectedDecision.post_action_metrics.queue_delta > 0 ? '+' : ''}
                        {selectedDecision.post_action_metrics.queue_delta} veh
                      </strong>
                    </div>
                    <div style={{ background: 'var(--surface-2)', padding: '6px 10px', borderRadius: 4 }}>
                      Wait Delta:{' '}
                      <strong
                        style={{
                          color:
                            selectedDecision.post_action_metrics.waiting_time_delta <= 0
                              ? 'var(--green)'
                              : 'var(--red)',
                        }}
                      >
                        {selectedDecision.post_action_metrics.waiting_time_delta > 0 ? '+' : ''}
                        {selectedDecision.post_action_metrics.waiting_time_delta}s
                      </strong>
                    </div>
                    {selectedDecision.post_action_metrics.current_avg_speed != null && (
                      <div style={{ background: 'var(--surface-2)', padding: '6px 10px', borderRadius: 4 }}>
                        Avg Speed: <strong>{selectedDecision.post_action_metrics.current_avg_speed} m/s</strong>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Optional: Real-time Predictive Intelligence */}
              {selectedDecision.prediction && selectedDecision.prediction.model_available && (
                <div style={{ borderLeft: '3px solid var(--cyan)', paddingLeft: 12 }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--cyan)', textTransform: 'uppercase' }}>
                    Prediction Horizon Telemetry (30s Horizon)
                  </div>
                  <div style={{ fontSize: 11.5, color: 'var(--text-secondary)', marginTop: 4 }}>
                    Forecast Congestion Score:{' '}
                    <strong>{selectedDecision.prediction.predicted_score?.toFixed(1) ?? '--'}</strong> / 100 • 80% CI:{' '}
                    <strong>
                      [{selectedDecision.prediction.confidence_lower?.toFixed(1) ?? '--'},{' '}
                      {selectedDecision.prediction.confidence_upper?.toFixed(1) ?? '--'}]
                    </strong>{' '}
                    • Trend: <strong>{selectedDecision.prediction.trend || 'STABLE'}</strong>
                  </div>
                </div>
              )}

              {/* Optional: Emergency Priority Context */}
              {selectedDecision.emergency && selectedDecision.emergency.active && (
                <div style={{ borderLeft: '3px solid var(--purple)', paddingLeft: 12 }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--purple)', textTransform: 'uppercase' }}>
                    Emergency Green Corridor Status
                  </div>
                  <div style={{ fontSize: 11.5, color: 'var(--text-secondary)', marginTop: 4 }}>
                    Vehicle: <strong>{selectedDecision.emergency.vehicle_id}</strong> • Approach:{' '}
                    <strong>{selectedDecision.emergency.approach}</strong> • Distance to Stopline:{' '}
                    <strong>{selectedDecision.emergency.distance?.toFixed(1) ?? '--'}m</strong> • Priority Active:{' '}
                    <strong style={{ color: 'var(--green)' }}>
                      {selectedDecision.emergency.priority_active ? 'YES' : 'PENDING'}
                    </strong>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default AIDecisionHistory;
