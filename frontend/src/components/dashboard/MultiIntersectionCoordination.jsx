import React, { useState } from 'react';
import {
  Share2, Activity, Zap, Shield, ArrowRight, ArrowLeft,
  ArrowUp, ArrowDown, RefreshCw, CheckCircle2, AlertTriangle,
  GitBranch, Compass, Sliders, Radio, Gauge, Info
} from 'lucide-react';
import Card from '../common/Card';
import StatusBadge from '../common/StatusBadge';
import { setCoordinationMode } from '../../services/api';

const COORDINATION_MODES = [
  { id: 'ARTERY_EW', label: 'E-W Arterial Green Wave', desc: 'Offsets prioritized for East-West heavy commuter flow' },
  { id: 'ARTERY_NS', label: 'N-S Transit Priority',    desc: 'Offsets synchronized for North-South transit spine' },
  { id: 'BALANCED_ADAPTIVE', label: 'Balanced Adaptive', desc: 'Real-time multi-metric demand split optimization' },
  { id: 'ISOLATED', label: 'Isolated Control',         desc: 'Signals operate independently without coordinated progression' },
];

const MultiIntersectionCoordination = ({ trafficData, simulationStatus }) => {
  const [isSwitching, setIsSwitching] = useState(false);
  const [feedback, setFeedback] = useState(null);

  const coordination = trafficData?.coordination || null;
  const metrics = coordination?.metrics || {};
  const neighbors = coordination?.neighbors || {};
  const currentMode = coordination?.mode || 'ARTERY_EW';
  const isEmergencyPreempted = coordination?.emergency_active || false;
  const preemptedApproach = coordination?.emergency_approach || null;
  const isIsolated = currentMode === 'ISOLATED' || metrics.is_coordinated === false;

  const spillbackMitigation = metrics?.spillback_mitigation || coordination?.spillback_mitigation || null;
  const isSpillbackActive = Boolean(spillbackMitigation?.active);

  const isRunning = simulationStatus?.running || false;

  const handleModeChange = async (modeKey) => {
    if (isSwitching || modeKey === currentMode) return;
    setIsSwitching(true);
    setFeedback(null);
    try {
      const res = await setCoordinationMode(modeKey);
      setFeedback({ type: 'success', message: res.message || `Switched to ${modeKey}` });
      setTimeout(() => setFeedback(null), 4000);
    } catch (err) {
      setFeedback({
        type: 'error',
        message: err.response?.data?.detail || err.message || 'Failed to switch coordination mode',
      });
      setTimeout(() => setFeedback(null), 5000);
    } finally {
      setIsSwitching(false);
    }
  };

  const getStatusBadge = (progressionStatus) => {
    switch (progressionStatus) {
      case 'PROGRESSION_ACTIVE':
        return <StatusBadge variant="green">Green Wave</StatusBadge>;
      case 'METERING_HOLD':
        return <StatusBadge variant="amber">Metering Hold</StatusBadge>;
      case 'ADVANCE_PREEMPTION':
        return <StatusBadge variant="purple">Advance Preempt</StatusBadge>;
      case 'TRANSITION_CLEARANCE':
        return <StatusBadge variant="amber">Clearance Transition</StatusBadge>;
      case 'SPILLBACK_MITIGATION':
        return <StatusBadge variant="red">Spillback Alert</StatusBadge>;
      case 'ISOLATED':
        return <StatusBadge variant="gray">Isolated</StatusBadge>;
      default:
        return <StatusBadge variant="blue">{progressionStatus || 'Synchronized'}</StatusBadge>;
    }
  };

  const north = neighbors.north || { intersection_id: 'INT-N', name: 'North Gateway', signal_state: 'green', progression_status: isIsolated ? 'ISOLATED' : 'SYNCHRONIZED', current_offset_seconds: isIsolated ? 0 : 20.8, queue_length: 0, coordination_intent: 'Simulated Arterial Intent' };
  const south = neighbors.south || { intersection_id: 'INT-S', name: 'South Gateway', signal_state: 'green', progression_status: isIsolated ? 'ISOLATED' : 'SYNCHRONIZED', current_offset_seconds: isIsolated ? 0 : 20.8, queue_length: 0, coordination_intent: 'Simulated Arterial Intent' };
  const east  = neighbors.east  || { intersection_id: 'INT-E', name: 'East Arterial', signal_state: 'red', progression_status: isIsolated ? 'ISOLATED' : 'SYNCHRONIZED', current_offset_seconds: isIsolated ? 0 : 20.8, queue_length: 0, coordination_intent: 'Simulated Arterial Intent' };
  const west  = neighbors.west  || { intersection_id: 'INT-W', name: 'West Arterial', signal_state: 'red', progression_status: isIsolated ? 'ISOLATED' : 'SYNCHRONIZED', current_offset_seconds: isIsolated ? 0 : 20.8, queue_length: 0, coordination_intent: 'Simulated Arterial Intent' };

  const centerPhase = trafficData?.signal?.state || 'green';
  const centerPhaseName = trafficData?.signal?.phase_name || 'NORTH_SOUTH_GREEN';

  // Heuristic estimates
  const ewScore = isIsolated ? 0.0 : (metrics.arterial_ew_sync_score ?? 88.5);
  const nsScore = isIsolated ? 0.0 : (metrics.arterial_ns_sync_score ?? 82.0);
  const overallQuality = isIsolated ? 0.0 : (metrics.overall_quality_score ?? 85.5);
  const platoonEfficiency = isIsolated ? 0.0 : (metrics.platoon_arrival_efficiency ?? 81.2);
  const spillbackRisk = metrics.spillback_risk ?? 'LOW';

  // Directly observed TraCI measurements
  const observedSpeedMps = metrics.observed_mean_speed_mps ?? (trafficData?.network?.mean_speed ?? null);
  const observedSpeedKmh = observedSpeedMps != null ? (observedSpeedMps * 3.6).toFixed(1) : '--';
  const observedMaxQueue = metrics.observed_max_queue ?? (trafficData?.network?.max_queue ?? 0);
  const observedTotalQueue = metrics.observed_total_queue ?? (trafficData?.network?.total_queue ?? 0);

  return (
    <Card
      title="Multi-Intersection Network Coordination"
      titleIcon={<Share2 size={15} style={{ color: 'var(--cyan)' }} />}
      badge={
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          {isEmergencyPreempted && (
            <StatusBadge variant="purple">Corridor Preemption</StatusBadge>
          )}
          <StatusBadge variant={isRunning ? 'green' : 'gray'}>
            {isRunning ? 'Network Active' : 'Standby'}
          </StatusBadge>
        </div>
      }
      noPadding
    >
      <div style={{ padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 14 }}>

        {/* ── 1. Emergency Preemption Alert Banner ─────────────────────── */}
        {isEmergencyPreempted && (
          <div style={{
            background: 'linear-gradient(90deg, rgba(168, 85, 247, 0.15), rgba(56, 189, 248, 0.15))',
            border: '1px solid rgba(168, 85, 247, 0.4)',
            borderRadius: 'var(--radius-sm)',
            padding: '10px 14px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 10,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{
                width: 28, height: 28, borderRadius: '50%',
                background: 'rgba(168, 85, 247, 0.25)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: '#c084fc',
              }}>
                <Zap size={16} />
              </div>
              <div>
                <div style={{ fontSize: 12.5, fontWeight: 700, color: '#f3e8ff' }}>
                  Coordinated Green Wave Corridor Active
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
                  Approach: <strong style={{ color: 'var(--cyan)', textTransform: 'uppercase' }}>{preemptedApproach}</strong> ➔ Upstream Metering Hold & Downstream Advance Preemption Engaged
                </div>
              </div>
            </div>
            <span style={{
              fontSize: 10.5, fontWeight: 700, padding: '3px 8px', borderRadius: 4,
              background: '#a855f7', color: '#fff', letterSpacing: '0.04em',
            }}>
              ZERO-STOP ROUTE
            </span>
          </div>
        )}

        {/* ── 2. Spillback Mitigation Decision Banner ───────────────────── */}
        {isSpillbackActive && spillbackMitigation && (
          <div style={{
            background: 'linear-gradient(90deg, rgba(239, 68, 68, 0.15), rgba(245, 158, 11, 0.15))',
            border: '1px solid rgba(239, 68, 68, 0.45)',
            borderRadius: 'var(--radius-sm)',
            padding: '10px 14px',
            display: 'flex',
            flexDirection: 'column',
            gap: 6,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <AlertTriangle size={16} style={{ color: '#ef4444' }} />
                <span style={{ fontSize: 12.5, fontWeight: 700, color: '#fee2e2' }}>
                  Spillback Mitigation Triggered — {spillbackMitigation.action}
                </span>
              </div>
              <span style={{
                fontSize: 10.5, fontWeight: 700, padding: '2px 7px', borderRadius: 4,
                background: '#ef4444', color: '#fff', letterSpacing: '0.04em',
              }}>
                LINK CAPACITY CRITICAL
              </span>
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', display: 'flex', flexWrap: 'wrap', gap: 14 }}>
              <span>Approach: <strong style={{ color: '#fff' }}>{spillbackMitigation.approach}</strong></span>
              <span>Observed Queue: <strong style={{ color: '#f87171' }}>{spillbackMitigation.queue_length} veh</strong> (Threshold: {spillbackMitigation.threshold})</span>
              <span>Metering Inflow: <strong style={{ color: '#f59e0b' }}>{Math.round(spillbackMitigation.metering_rate_factor * 100)}% ({Math.round((1 - spillbackMitigation.metering_rate_factor) * -100)}% throttle)</strong></span>
              <span>Green Flush Extension: <strong style={{ color: 'var(--green)' }}>+{spillbackMitigation.green_extension_seconds}s</strong></span>
            </div>
            {spillbackMitigation.explanation && (
              <div style={{ fontSize: 10.5, color: '#fca5a5', fontStyle: 'italic', marginTop: 2 }}>
                {spillbackMitigation.explanation}
              </div>
            )}
          </div>
        )}

        {/* ── 3. Isolated Control Mode Notice ──────────────────────────── */}
        {isIsolated && (
          <div style={{
            background: 'rgba(100, 116, 139, 0.12)',
            border: '1px solid rgba(148, 163, 184, 0.25)',
            borderRadius: 'var(--radius-sm)',
            padding: '8px 12px',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            fontSize: 11,
            color: 'var(--text-secondary)',
          }}>
            <Info size={14} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
            <span>
              <strong>Isolated Mode (Uncoordinated):</strong> Signals operate independently on local queue demand without corridor progression offsets. Heuristic synchronization scores are set to 0.0% (coordination inactive).
            </span>
          </div>
        )}

        {/* ── 4. Network Topology & Gateway Signals (Simulated Intent vs SUMO TLS) ── */}
        <div style={{
          background: 'var(--surface-2)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-md)',
          padding: '14px',
          position: 'relative',
        }}>
          <div style={{
            fontSize: 11, fontWeight: 600, color: 'var(--text-muted)',
            textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 12,
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          }}>
            <span>Simulated Gateway Coordination Intent (Physical SUMO TLS: INT-001 Center)</span>
            <span style={{ color: 'var(--text-muted)', fontSize: 10.5 }}>
              Link Travel Time: ~20.8s @ 50 km/h
            </span>
          </div>

          {/* 5-Node Cross Diagram */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: '1fr 140px 1fr',
            gridTemplateRows: 'auto auto auto',
            gap: 12,
            alignItems: 'center',
            justifyItems: 'center',
          }}>

            {/* Top: North Gateway */}
            <div style={{ gridColumn: '2 / 3', gridRow: '1 / 2', width: '100%' }}>
              <div style={{
                background: 'var(--surface-3)',
                border: `1px solid ${north.signal_state === 'green' ? 'rgba(34,197,94,0.5)' : 'var(--border)'}`,
                borderRadius: 'var(--radius-sm)',
                padding: '8px 10px',
                textAlign: 'center',
                boxShadow: north.signal_state === 'green' ? '0 0 10px rgba(34,197,94,0.15)' : 'none',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, marginBottom: 2 }}>
                  <span style={{
                    width: 8, height: 8, borderRadius: '50%',
                    backgroundColor: north.signal_state === 'green' ? '#22c55e' : north.signal_state === 'yellow' ? '#eab308' : '#ef4444',
                    boxShadow: `0 0 6px ${north.signal_state === 'green' ? '#22c55e' : '#ef4444'}`,
                  }} />
                  <span style={{ fontSize: 11.5, fontWeight: 700, color: 'var(--text-primary)' }}>INT-N (North Gateway)</span>
                </div>
                <div style={{ fontSize: 9.5, color: 'var(--cyan)', marginBottom: 3 }}>
                  {north.coordination_intent || 'Simulated Arterial Intent'}
                </div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', display: 'flex', justifyContent: 'space-between' }}>
                  <span>Offset: {isIsolated ? '0.0s' : `${north.current_offset_seconds}s`}</span>
                  <span>Q: {north.queue_length} veh</span>
                </div>
                <div style={{ marginTop: 4 }}>
                  {getStatusBadge(north.progression_status)}
                </div>
              </div>
            </div>

            {/* Left: West Arterial */}
            <div style={{ gridColumn: '1 / 2', gridRow: '2 / 3', width: '100%' }}>
              <div style={{
                background: 'var(--surface-3)',
                border: `1px solid ${west.signal_state === 'green' ? 'rgba(34,197,94,0.5)' : 'var(--border)'}`,
                borderRadius: 'var(--radius-sm)',
                padding: '8px 10px',
                textAlign: 'center',
                boxShadow: west.signal_state === 'green' ? '0 0 10px rgba(34,197,94,0.15)' : 'none',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, marginBottom: 2 }}>
                  <span style={{
                    width: 8, height: 8, borderRadius: '50%',
                    backgroundColor: west.signal_state === 'green' ? '#22c55e' : west.signal_state === 'yellow' ? '#eab308' : '#ef4444',
                    boxShadow: `0 0 6px ${west.signal_state === 'green' ? '#22c55e' : '#ef4444'}`,
                  }} />
                  <span style={{ fontSize: 11.5, fontWeight: 700, color: 'var(--text-primary)' }}>INT-W (West Arterial)</span>
                </div>
                <div style={{ fontSize: 9.5, color: 'var(--cyan)', marginBottom: 3 }}>
                  {west.coordination_intent || 'Simulated Arterial Intent'}
                </div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', display: 'flex', justifyContent: 'space-between' }}>
                  <span>Offset: {isIsolated ? '0.0s' : `${west.current_offset_seconds}s`}</span>
                  <span>Q: {west.queue_length} veh</span>
                </div>
                <div style={{ marginTop: 4 }}>
                  {getStatusBadge(west.progression_status)}
                </div>
              </div>
            </div>

            {/* Center: Primary Junction INT-001 (Physical SUMO TLS) */}
            <div style={{ gridColumn: '2 / 3', gridRow: '2 / 3', width: '100%' }}>
              <div style={{
                background: 'linear-gradient(135deg, rgba(56, 189, 248, 0.12), rgba(30, 58, 138, 0.25))',
                border: '1.5px solid var(--cyan)',
                borderRadius: 'var(--radius-sm)',
                padding: '10px 10px',
                textAlign: 'center',
                boxShadow: '0 0 14px rgba(56, 189, 248, 0.2)',
              }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--cyan)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  PHYSICAL SUMO TLS
                </div>
                <div style={{ fontSize: 13, fontWeight: 800, color: '#fff', margin: '2px 0' }}>
                  INT-001 (center)
                </div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5 }}>
                  <span style={{
                    width: 8, height: 8, borderRadius: '50%',
                    backgroundColor: centerPhase === 'green' ? '#22c55e' : centerPhase === 'yellow' ? '#eab308' : '#ef4444',
                    boxShadow: `0 0 6px ${centerPhase === 'green' ? '#22c55e' : '#ef4444'}`,
                  }} />
                  <span style={{ fontSize: 10.5, fontWeight: 600, color: 'var(--text-secondary)' }}>
                    {centerPhaseName}
                  </span>
                </div>
              </div>
            </div>

            {/* Right: East Arterial */}
            <div style={{ gridColumn: '3 / 4', gridRow: '2 / 3', width: '100%' }}>
              <div style={{
                background: 'var(--surface-3)',
                border: `1px solid ${east.signal_state === 'green' ? 'rgba(34,197,94,0.5)' : 'var(--border)'}`,
                borderRadius: 'var(--radius-sm)',
                padding: '8px 10px',
                textAlign: 'center',
                boxShadow: east.signal_state === 'green' ? '0 0 10px rgba(34,197,94,0.15)' : 'none',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, marginBottom: 2 }}>
                  <span style={{
                    width: 8, height: 8, borderRadius: '50%',
                    backgroundColor: east.signal_state === 'green' ? '#22c55e' : east.signal_state === 'yellow' ? '#eab308' : '#ef4444',
                    boxShadow: `0 0 6px ${east.signal_state === 'green' ? '#22c55e' : '#ef4444'}`,
                  }} />
                  <span style={{ fontSize: 11.5, fontWeight: 700, color: 'var(--text-primary)' }}>INT-E (East Arterial)</span>
                </div>
                <div style={{ fontSize: 9.5, color: 'var(--cyan)', marginBottom: 3 }}>
                  {east.coordination_intent || 'Simulated Arterial Intent'}
                </div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', display: 'flex', justifyContent: 'space-between' }}>
                  <span>Offset: {isIsolated ? '0.0s' : `${east.current_offset_seconds}s`}</span>
                  <span>Q: {east.queue_length} veh</span>
                </div>
                <div style={{ marginTop: 4 }}>
                  {getStatusBadge(east.progression_status)}
                </div>
              </div>
            </div>

            {/* Bottom: South Gateway */}
            <div style={{ gridColumn: '2 / 3', gridRow: '3 / 4', width: '100%' }}>
              <div style={{
                background: 'var(--surface-3)',
                border: `1px solid ${south.signal_state === 'green' ? 'rgba(34,197,94,0.5)' : 'var(--border)'}`,
                borderRadius: 'var(--radius-sm)',
                padding: '8px 10px',
                textAlign: 'center',
                boxShadow: south.signal_state === 'green' ? '0 0 10px rgba(34,197,94,0.15)' : 'none',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, marginBottom: 2 }}>
                  <span style={{
                    width: 8, height: 8, borderRadius: '50%',
                    backgroundColor: south.signal_state === 'green' ? '#22c55e' : south.signal_state === 'yellow' ? '#eab308' : '#ef4444',
                    boxShadow: `0 0 6px ${south.signal_state === 'green' ? '#22c55e' : '#ef4444'}`,
                  }} />
                  <span style={{ fontSize: 11.5, fontWeight: 700, color: 'var(--text-primary)' }}>INT-S (South Gateway)</span>
                </div>
                <div style={{ fontSize: 9.5, color: 'var(--cyan)', marginBottom: 3 }}>
                  {south.coordination_intent || 'Simulated Arterial Intent'}
                </div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', display: 'flex', justifyContent: 'space-between' }}>
                  <span>Offset: {isIsolated ? '0.0s' : `${south.current_offset_seconds}s`}</span>
                  <span>Q: {south.queue_length} veh</span>
                </div>
                <div style={{ marginTop: 4 }}>
                  {getStatusBadge(south.progression_status)}
                </div>
              </div>
            </div>

          </div>
        </div>

        {/* ── 5. Direct TraCI Measurements (Ground Truth) ────────────────── */}
        <div>
          <div style={{
            fontSize: 10.5, fontWeight: 700, color: 'var(--text-secondary)',
            textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6,
            display: 'flex', alignItems: 'center', gap: 6,
          }}>
            <Gauge size={13} style={{ color: 'var(--cyan)' }} />
            <span>Direct TraCI Measurements (Observed Ground Truth)</span>
          </div>

          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            gap: 8,
          }}>
            <div style={{
              background: 'var(--surface-2)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-sm)',
              padding: '8px 12px',
            }}>
              <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>
                Observed Mean Speed
              </div>
              <div style={{ fontSize: 16, fontWeight: 800, color: 'var(--text-primary)', marginTop: 2 }}>
                {observedSpeedKmh} km/h
              </div>
              <div style={{ fontSize: 9.5, color: 'var(--text-muted)', marginTop: 1 }}>
                {observedSpeedMps != null ? `${observedSpeedMps.toFixed(1)} m/s live` : 'Awaiting vehicles'}
              </div>
            </div>

            <div style={{
              background: 'var(--surface-2)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-sm)',
              padding: '8px 12px',
            }}>
              <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>
                Observed Max Queue
              </div>
              <div style={{ fontSize: 16, fontWeight: 800, color: 'var(--amber)', marginTop: 2 }}>
                {observedMaxQueue} veh
              </div>
              <div style={{ fontSize: 9.5, color: 'var(--text-muted)', marginTop: 1 }}>
                Peak lane queue
              </div>
            </div>

            <div style={{
              background: 'var(--surface-2)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-sm)',
              padding: '8px 12px',
            }}>
              <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>
                Observed Total Queue
              </div>
              <div style={{ fontSize: 16, fontWeight: 800, color: 'var(--text-primary)', marginTop: 2 }}>
                {observedTotalQueue} veh
              </div>
              <div style={{ fontSize: 9.5, color: 'var(--text-muted)', marginTop: 1 }}>
                All inbound approaches
              </div>
            </div>
          </div>
        </div>

        {/* ── 6. Heuristic Coordination Estimates (Progression Quality) ── */}
        <div>
          <div style={{
            fontSize: 10.5, fontWeight: 700, color: 'var(--text-secondary)',
            textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6,
            display: 'flex', alignItems: 'center', gap: 6,
          }}>
            <Activity size={13} style={{ color: 'var(--blue)' }} />
            <span>Heuristic Model Estimates (Coordination Progression Quality)</span>
          </div>

          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(4, 1fr)',
            gap: 8,
          }}>
            <div style={{
              background: 'var(--surface-2)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-sm)',
              padding: '10px 12px',
            }}>
              <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>
                E-W Arterial Sync
              </div>
              <div style={{ fontSize: 18, fontWeight: 800, color: isIsolated ? 'var(--text-muted)' : 'var(--cyan)', marginTop: 4 }}>
                {isIsolated ? '0.0%' : `${ewScore}%`}
              </div>
              <div style={{ fontSize: 10, color: 'var(--text-secondary)', marginTop: 2 }}>
                {isIsolated ? 'Isolated (uncoordinated)' : 'Progression estimate'}
              </div>
            </div>

            <div style={{
              background: 'var(--surface-2)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-sm)',
              padding: '10px 12px',
            }}>
              <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>
                N-S Transit Sync
              </div>
              <div style={{ fontSize: 18, fontWeight: 800, color: isIsolated ? 'var(--text-muted)' : 'var(--blue)', marginTop: 4 }}>
                {isIsolated ? '0.0%' : `${nsScore}%`}
              </div>
              <div style={{ fontSize: 10, color: 'var(--text-secondary)', marginTop: 2 }}>
                {isIsolated ? 'Isolated (uncoordinated)' : 'Transit spine estimate'}
              </div>
            </div>

            <div style={{
              background: 'var(--surface-2)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-sm)',
              padding: '10px 12px',
            }}>
              <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>
                Platoon Arrival
              </div>
              <div style={{ fontSize: 18, fontWeight: 800, color: isIsolated ? 'var(--text-muted)' : 'var(--green)', marginTop: 4 }}>
                {isIsolated ? '0.0%' : `${platoonEfficiency}%`}
              </div>
              <div style={{ fontSize: 10, color: 'var(--text-secondary)', marginTop: 2 }}>
                {isIsolated ? 'Independent arrivals' : 'Arrival on green est.'}
              </div>
            </div>

            <div style={{
              background: 'var(--surface-2)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-sm)',
              padding: '10px 12px',
            }}>
              <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>
                Spillback Risk
              </div>
              <div style={{
                fontSize: 15, fontWeight: 800, marginTop: 6,
                color: spillbackRisk === 'HIGH' ? 'var(--red)' : spillbackRisk === 'MODERATE' ? 'var(--amber)' : 'var(--green)',
              }}>
                {spillbackRisk}
              </div>
              <div style={{ fontSize: 10, color: 'var(--text-secondary)', marginTop: 4 }}>
                Link storage factor
              </div>
            </div>
          </div>
        </div>

        {/* ── 7. Policy Mode Switcher ─────────────────────────────────── */}
        <div>
          <div style={{
            fontSize: 11, fontWeight: 600, color: 'var(--text-muted)',
            textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8,
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          }}>
            <span>Coordination Strategy Mode</span>
            {isSwitching && (
              <span style={{ color: 'var(--cyan)', fontSize: 11, display: 'flex', alignItems: 'center', gap: 4 }}>
                <RefreshCw size={12} className="spin" /> Updating...
              </span>
            )}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 8 }}>
            {COORDINATION_MODES.map((m) => {
              const isActive = currentMode === m.id;
              return (
                <button
                  key={m.id}
                  onClick={() => handleModeChange(m.id)}
                  disabled={isSwitching}
                  style={{
                    background: isActive ? 'rgba(56, 189, 248, 0.15)' : 'var(--surface-2)',
                    border: `1px solid ${isActive ? 'var(--cyan)' : 'var(--border)'}`,
                    borderRadius: 'var(--radius-sm)',
                    padding: '8px 10px',
                    textAlign: 'left',
                    cursor: isSwitching ? 'not-allowed' : 'pointer',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: 11.5, fontWeight: 700, color: isActive ? 'var(--cyan)' : 'var(--text-primary)' }}>
                      {m.label}
                    </span>
                    {isActive && <CheckCircle2 size={13} style={{ color: 'var(--cyan)' }} />}
                  </div>
                  <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
                    {m.desc}
                  </div>
                </button>
              );
            })}
          </div>

          {feedback && (
            <div style={{
              marginTop: 8,
              padding: '6px 10px',
              borderRadius: 'var(--radius-sm)',
              fontSize: 11,
              background: feedback.type === 'success' ? 'rgba(34, 197, 94, 0.12)' : 'rgba(239, 68, 68, 0.12)',
              border: `1px solid ${feedback.type === 'success' ? 'rgba(34, 197, 94, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`,
              color: feedback.type === 'success' ? 'var(--green)' : 'var(--red)',
            }}>
              {feedback.message}
            </div>
          )}
        </div>

      </div>
    </Card>
  );
};

export default MultiIntersectionCoordination;
