import React, { useState, useEffect } from 'react';
import {
  Siren, AlertTriangle, CheckCircle2, ShieldAlert,
  ArrowRight, Clock, MapPin, Gauge, Radio, Shield, AlertCircle
} from 'lucide-react';
import Card from '../common/Card';
import StatusBadge from '../common/StatusBadge';
import { triggerEmergencyVehicle, getEmergencyStatus } from '../../services/api';

const VEHICLE_TYPES = [
  { id: 'ambulance',   label: 'Ambulance',   icon: '🚑', color: '#ef4444' },
  { id: 'fire_engine', label: 'Fire Truck',  icon: '🚒', color: '#f97316' },
  { id: 'police',      label: 'Police',      icon: '🚓', color: '#3b82f6' },
];

const APPROACHES = [
  { id: 'north', label: 'North (N2C)' },
  { id: 'south', label: 'South (S2C)' },
  { id: 'east',  label: 'East (E2C)' },
  { id: 'west',  label: 'West (W2C)' },
];

const LIFECYCLE_STAGES = [
  { id: 'DETECTED',           label: 'Detected',           color: '#38bdf8' },
  { id: 'PRIORITY_REQUESTED',  label: 'Priority Requested', color: '#f59e0b' },
  { id: 'PRIORITY_ACTIVE',     label: 'Priority Active',    color: '#ef4444' },
  { id: 'VEHICLE_PASSED',      label: 'Passed Stopline',    color: '#8b5cf6' },
  { id: 'RESTORING_NORMAL',    label: 'Restoring Normal',   color: '#10b981' },
];

const EmergencyControlPanel = ({ simulationStatus, trafficData, isConnected }) => {
  const [vehicleType, setVehicleType] = useState('ambulance');
  const [approach, setApproach]       = useState('east');
  const [spawnStep, setSpawnStep]     = useState('');
  const [isActivating, setIsActivating] = useState(false);
  const [feedback, setFeedback]       = useState(null); // { type: 'success' | 'error', message: string }
  const [scheduledEmergency, setScheduledEmergency] = useState(null);

  const isRunning = simulationStatus?.running || false;
  const currentStep = simulationStatus?.current_step ?? 0;
  const totalSteps = simulationStatus?.total_steps ?? 3600;

  // Extract emergency telemetry from WebSocket snapshot
  const emergency = trafficData?.emergency || null;
  const activeLifecycleState = emergency?.lifecycle_state || 'IDLE';
  const isPriorityActive = !!emergency?.active;
  const isEmergencyInCorridor = isPriorityActive || (activeLifecycleState !== 'IDLE' && activeLifecycleState !== 'None' && activeLifecycleState !== '');

  // Poll status or sync scheduled state
  useEffect(() => {
    if (feedback?.type === 'success') {
      const timer = setTimeout(() => setFeedback(null), 8000);
      return () => clearTimeout(timer);
    }
  }, [feedback]);

  // When simulation stops or changes, clear transient states
  useEffect(() => {
    if (!isRunning) {
      setScheduledEmergency(null);
      setIsActivating(false);
    }
  }, [isRunning]);

  // Determine if a new activation is disallowed
  const isBlocked = !isRunning || isActivating || isEmergencyInCorridor || !!scheduledEmergency;

  const handleQuickStep = (offset) => {
    if (offset === 0) {
      setSpawnStep('');
    } else {
      setSpawnStep(String(currentStep + offset));
    }
  };

  const handleActivate = async () => {
    if (isBlocked) return;
    setIsActivating(true);
    setFeedback(null);

    const stepVal = spawnStep.trim() === '' ? null : parseInt(spawnStep, 10);

    if (stepVal !== null) {
      if (isNaN(stepVal) || stepVal < 0) {
        setFeedback({ type: 'error', message: 'Spawn step must be a positive integer.' });
        setIsActivating(false);
        return;
      }
      if (stepVal > totalSteps) {
        setFeedback({ type: 'error', message: `Spawn step (${stepVal}) cannot exceed simulation total steps (${totalSteps}).` });
        setIsActivating(false);
        return;
      }
    }

    try {
      const payload = {
        vehicle_type: vehicleType,
        approach,
        spawn_step: stepVal,
      };

      const res = await triggerEmergencyVehicle(payload);
      setFeedback({
        type: 'success',
        message: res.message || `Emergency ${vehicleType} dispatch scheduled successfully.`,
      });
      setScheduledEmergency({
        vehicle_id: res.vehicle_id,
        vehicle_type: res.vehicle_type,
        approach: res.approach,
        spawn_step: res.spawn_step,
      });
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || 'Failed to dispatch emergency vehicle';
      setFeedback({ type: 'error', message: msg });
    } finally {
      setIsActivating(false);
    }
  };

  // Badge determining current status of corridor
  let panelBadge = <StatusBadge variant="gray">STANDBY</StatusBadge>;
  if (!isConnected) {
    panelBadge = <StatusBadge variant="red">DISCONNECTED</StatusBadge>;
  } else if (!isRunning) {
    panelBadge = <StatusBadge variant="gray">SIMULATION IDLE</StatusBadge>;
  } else if (isPriorityActive) {
    panelBadge = <StatusBadge variant="red" dot>CORRIDOR ACTIVE</StatusBadge>;
  } else if (isEmergencyInCorridor) {
    panelBadge = <StatusBadge variant="amber" dot>{activeLifecycleState}</StatusBadge>;
  } else if (scheduledEmergency) {
    panelBadge = <StatusBadge variant="cyan">SCHEDULED (STEP {scheduledEmergency.spawn_step})</StatusBadge>;
  }

  return (
    <Card
      title="Emergency Vehicle Control"
      titleIcon={<Siren size={15} color={isPriorityActive ? 'var(--red)' : 'var(--text-secondary)'} />}
      badge={panelBadge}
      noPadding
    >
      <div style={{ padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 12 }}>

        {/* WebSocket Disconnected Warning */}
        {!isConnected && (
          <div style={{
            background: 'rgba(239,68,68,0.1)',
            border: '1px solid rgba(239,68,68,0.3)',
            borderRadius: 6,
            padding: '8px 10px',
            fontSize: 11,
            color: '#fca5a5',
            display: 'flex',
            alignItems: 'center',
            gap: 6
          }}>
            <AlertTriangle size={13} />
            Telemetry WebSocket is disconnected. Reconnecting...
          </div>
        )}

        {/* Feedback Alert */}
        {feedback && (
          <div style={{
            background: feedback.type === 'error' ? 'rgba(239,68,68,0.12)' : 'rgba(34,197,94,0.12)',
            border: `1px solid ${feedback.type === 'error' ? 'rgba(239,68,68,0.4)' : 'rgba(34,197,94,0.4)'}`,
            borderRadius: 6,
            padding: '8px 10px',
            fontSize: 11,
            color: feedback.type === 'error' ? '#fca5a5' : '#86efac',
            display: 'flex',
            alignItems: 'flex-start',
            gap: 6,
          }}>
            {feedback.type === 'error' ? <AlertCircle size={14} style={{ marginTop: 1, flexShrink: 0 }} /> : <CheckCircle2 size={14} style={{ marginTop: 1, flexShrink: 0 }} />}
            <span>{feedback.message}</span>
          </div>
        )}

        {/* ── Vehicle Type Selection ─────────────────────── */}
        <div>
          <label style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', display: 'block', marginBottom: 6 }}>
            Emergency Vehicle Type
          </label>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6 }}>
            {VEHICLE_TYPES.map((t) => {
              const selected = vehicleType === t.id;
              return (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setVehicleType(t.id)}
                  disabled={!isRunning || isActivating || isEmergencyInCorridor}
                  style={{
                    background: selected ? 'var(--surface-3)' : 'var(--surface-2)',
                    border: `1px solid ${selected ? t.color : 'var(--border)'}`,
                    borderRadius: 6,
                    padding: '8px 6px',
                    color: selected ? '#ffffff' : 'var(--text-secondary)',
                    cursor: isBlocked ? 'not-allowed' : 'pointer',
                    fontSize: 11,
                    fontWeight: selected ? 600 : 500,
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    gap: 3,
                    opacity: isBlocked ? 0.6 : 1,
                    transition: 'all 0.15s ease',
                  }}
                >
                  <span style={{ fontSize: 16 }}>{t.icon}</span>
                  <span>{t.label}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* ── Inflow Approach Selection ───────────────────── */}
        <div>
          <label style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', display: 'block', marginBottom: 6 }}>
            Inflow Approach Corridor
          </label>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 6 }}>
            {APPROACHES.map((app) => {
              const selected = approach === app.id;
              return (
                <button
                  key={app.id}
                  type="button"
                  onClick={() => setApproach(app.id)}
                  disabled={!isRunning || isActivating || isEmergencyInCorridor}
                  style={{
                    background: selected ? 'var(--surface-3)' : 'var(--surface-2)',
                    border: `1px solid ${selected ? 'var(--blue)' : 'var(--border)'}`,
                    borderRadius: 6,
                    padding: '6px 4px',
                    color: selected ? 'var(--cyan)' : 'var(--text-secondary)',
                    cursor: isBlocked ? 'not-allowed' : 'pointer',
                    fontSize: 11,
                    fontWeight: selected ? 600 : 500,
                    textAlign: 'center',
                    opacity: isBlocked ? 0.6 : 1,
                    transition: 'all 0.15s ease',
                  }}
                >
                  {app.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* ── Spawn Step Configuration ───────────────────── */}
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
            <label style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              Spawn Step (Current: {currentStep}s)
            </label>
            <div style={{ display: 'flex', gap: 4 }}>
              <button
                type="button"
                onClick={() => handleQuickStep(0)}
                disabled={!isRunning || isEmergencyInCorridor}
                style={{
                  background: spawnStep === '' ? 'var(--surface-3)' : 'transparent',
                  border: '1px solid var(--border)',
                  borderRadius: 4,
                  padding: '2px 6px',
                  fontSize: 10,
                  color: spawnStep === '' ? 'var(--cyan)' : 'var(--text-muted)',
                  cursor: 'pointer',
                }}
              >
                Immediate
              </button>
              <button
                type="button"
                onClick={() => handleQuickStep(5)}
                disabled={!isRunning || isEmergencyInCorridor}
                style={{
                  background: 'transparent',
                  border: '1px solid var(--border)',
                  borderRadius: 4,
                  padding: '2px 6px',
                  fontSize: 10,
                  color: 'var(--text-muted)',
                  cursor: 'pointer',
                }}
              >
                +5s
              </button>
              <button
                type="button"
                onClick={() => handleQuickStep(15)}
                disabled={!isRunning || isEmergencyInCorridor}
                style={{
                  background: 'transparent',
                  border: '1px solid var(--border)',
                  borderRadius: 4,
                  padding: '2px 6px',
                  fontSize: 10,
                  color: 'var(--text-muted)',
                  cursor: 'pointer',
                }}
              >
                +15s
              </button>
            </div>
          </div>
          <input
            type="number"
            min={0}
            max={totalSteps}
            value={spawnStep}
            onChange={(e) => setSpawnStep(e.target.value)}
            placeholder={`Immediate / Next Step (defaults to step ${currentStep + 1})`}
            disabled={!isRunning || isActivating || isEmergencyInCorridor}
            style={{
              width: '100%',
              background: 'var(--surface-2)',
              border: '1px solid var(--border)',
              borderRadius: 6,
              padding: '7px 10px',
              fontSize: 11,
              color: 'var(--text-primary)',
              outline: 'none',
              boxSizing: 'border-box',
            }}
          />
        </div>

        {/* ── Action Button ──────────────────────────────── */}
        <button
          type="button"
          onClick={handleActivate}
          disabled={isBlocked}
          style={{
            background: isBlocked
              ? 'var(--surface-2)'
              : 'linear-gradient(135deg, #dc2626 0%, #b91c1c 100%)',
            border: isBlocked ? '1px solid var(--border)' : '1px solid #ef4444',
            borderRadius: 6,
            padding: '10px 14px',
            color: isBlocked ? 'var(--text-muted)' : '#ffffff',
            fontSize: 12,
            fontWeight: 700,
            letterSpacing: '0.04em',
            cursor: isBlocked ? 'not-allowed' : 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 8,
            boxShadow: isBlocked ? 'none' : '0 2px 10px rgba(220, 38, 38, 0.4)',
            transition: 'all 0.2s ease',
          }}
        >
          <Siren size={15} />
          {isActivating ? (
            'DISPATCHING VEHICLE...'
          ) : isPriorityActive ? (
            'GREEN CORRIDOR IN PROGRESS'
          ) : isEmergencyInCorridor ? (
            'EMERGENCY IN CORRIDOR'
          ) : !isRunning ? (
            'START SIMULATION FIRST'
          ) : (
            'ACTIVATE EMERGENCY VEHICLE'
          )}
        </button>

        {/* ── 7-Stage Lifecycle Stepper ──────────────────── */}
        <div style={{
          background: 'var(--surface-2)',
          border: '1px solid var(--border)',
          borderRadius: 6,
          padding: '10px 12px',
        }}>
          <div style={{ fontSize: 10.5, color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8, display: 'flex', justifyContent: 'space-between' }}>
            <span>Corridor Lifecycle Stage</span>
            <span style={{
              color: isEmergencyInCorridor ? 'var(--cyan)' : 'var(--text-muted)',
              fontWeight: 700,
            }}>
              {activeLifecycleState}
            </span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 4 }}>
            {LIFECYCLE_STAGES.map((st, idx) => {
              const isCurrent = activeLifecycleState === st.id;
              return (
                <div
                  key={st.id}
                  style={{
                    background: isCurrent ? `${st.color}22` : 'var(--surface-1)',
                    border: `1px solid ${isCurrent ? st.color : 'var(--border)'}`,
                    borderRadius: 4,
                    padding: '6px 4px',
                    textAlign: 'center',
                    transition: 'all 0.2s ease',
                  }}
                >
                  <div style={{
                    fontSize: 9,
                    color: isCurrent ? st.color : 'var(--text-muted)',
                    fontWeight: isCurrent ? 700 : 500,
                    lineHeight: 1.2,
                  }}>
                    {st.label}
                  </div>
                  {isCurrent && (
                    <div style={{
                      width: 4,
                      height: 4,
                      borderRadius: '50%',
                      background: st.color,
                      margin: '4px auto 0',
                      boxShadow: `0 0 6px ${st.color}`,
                    }} />
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* ── Real-Time TraCI Telemetry Grid ─────────────── */}
        <div style={{
          background: 'var(--surface-2)',
          border: '1px solid var(--border)',
          borderRadius: 6,
          padding: '10px 12px',
        }}>
          <div style={{ fontSize: 10.5, color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8 }}>
            Corridor Telemetry & Signal Preemption
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 8 }}>
            <div style={{ background: 'var(--surface-1)', padding: '6px 8px', borderRadius: 4, border: '1px solid var(--border)' }}>
              <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>Target Vehicle</div>
              <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-primary)' }}>
                {emergency?.vehicle_id || (scheduledEmergency ? scheduledEmergency.vehicle_id : '--')}
                {emergency?.vehicle_type ? ` (${emergency.vehicle_type})` : ''}
              </div>
            </div>

            <div style={{ background: 'var(--surface-1)', padding: '6px 8px', borderRadius: 4, border: '1px solid var(--border)' }}>
              <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>Corridor Approach</div>
              <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--cyan)' }}>
                {emergency?.approach ? emergency.approach.toUpperCase() : (scheduledEmergency ? scheduledEmergency.approach.toUpperCase() : '--')}
              </div>
            </div>

            <div style={{ background: 'var(--surface-1)', padding: '6px 8px', borderRadius: 4, border: '1px solid var(--border)' }}>
              <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>Stopline Distance</div>
              <div style={{ fontSize: 12, fontWeight: 700, color: emergency?.distance_to_stopline != null ? 'var(--amber)' : 'var(--text-secondary)' }}>
                {emergency?.distance_to_stopline != null
                  ? `${emergency.distance_to_stopline.toFixed(1)} m`
                  : activeLifecycleState === 'VEHICLE_PASSED' || activeLifecycleState === 'RESTORING_NORMAL'
                    ? 'PASSED (CLEARED)'
                    : '--'}
              </div>
            </div>

            <div style={{ background: 'var(--surface-1)', padding: '6px 8px', borderRadius: 4, border: '1px solid var(--border)' }}>
              <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>Estimated Arrival (ETA)</div>
              <div style={{ fontSize: 12, fontWeight: 700, color: emergency?.eta_seconds != null ? 'var(--purple)' : 'var(--text-secondary)' }}>
                {emergency?.eta_seconds != null
                  ? `${emergency.eta_seconds.toFixed(1)} s`
                  : activeLifecycleState === 'VEHICLE_PASSED' || activeLifecycleState === 'RESTORING_NORMAL'
                    ? 'CLEARED'
                    : '--'}
              </div>
            </div>
          </div>

          {/* Safety & Preemption Info */}
          <div style={{ marginTop: 8, paddingTop: 6, borderTop: '1px solid var(--border)', fontSize: 11, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ color: 'var(--text-muted)' }}>Preemption Status:</span>
            <span style={{
              color: isPriorityActive ? 'var(--red)' : 'var(--text-secondary)',
              fontWeight: 600,
            }}>
              {isPriorityActive ? '● SIGNAL PREEMPTION ENGAGED' : 'Normal Controller Active'}
            </span>
          </div>

          {emergency?.reason && (
            <div style={{ marginTop: 4, fontSize: 10.5, color: 'var(--text-muted)', fontStyle: 'italic' }}>
              Enforcement: {emergency.reason}
            </div>
          )}
        </div>

      </div>
    </Card>
  );
};

export default EmergencyControlPanel;
