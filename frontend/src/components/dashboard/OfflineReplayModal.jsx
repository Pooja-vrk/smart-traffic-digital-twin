import React, { useState, useEffect, useRef } from 'react';
import {
  Play, Pause, SkipBack, SkipForward, RotateCcw,
  X, ShieldCheck, ShieldAlert, Clock, Gauge, Car,
  Sliders, Activity, Sparkles, AlertCircle
} from 'lucide-react';
import { getSimulationReplay } from '../../services/api';
import DigitalTwinIntersection from './DigitalTwinIntersection';
import StatusBadge from '../common/StatusBadge';

const OfflineReplayModal = ({ simulationId, onClose }) => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [bundle, setBundle] = useState(null);
  const [currentFrameIndex, setCurrentFrameIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1); // 0.5x, 1x, 2x, 5x

  const playTimerRef = useRef(null);

  // Fetch replay bundle on mount
  useEffect(() => {
    let isMounted = true;
    const fetchReplay = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await getSimulationReplay(simulationId);
        if (isMounted) {
          if (!data || !data.frames || data.frames.length === 0) {
            setError('No replay frames found for this simulation session.');
          } else {
            setBundle(data);
            setCurrentFrameIndex(0);
          }
        }
      } catch (err) {
        if (isMounted) {
          setError(
            err.response?.data?.detail ||
              'Failed to load offline replay telemetry bundle. Ensure the simulation has completed and recorded data.'
          );
        }
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    if (simulationId) {
      fetchReplay();
    }

    return () => {
      isMounted = false;
      if (playTimerRef.current) clearInterval(playTimerRef.current);
    };
  }, [simulationId]);

  // Playback timer loop
  useEffect(() => {
    if (isPlaying && bundle?.frames?.length) {
      const intervalMs = Math.max(50, Math.round(1000 / playbackSpeed));
      playTimerRef.current = setInterval(() => {
        setCurrentFrameIndex((prev) => {
          if (prev >= bundle.frames.length - 1) {
            setIsPlaying(false);
            return prev;
          }
          return prev + 1;
        });
      }, intervalMs);
    } else {
      if (playTimerRef.current) clearInterval(playTimerRef.current);
    }

    return () => {
      if (playTimerRef.current) clearInterval(playTimerRef.current);
    };
  }, [isPlaying, playbackSpeed, bundle]);

  const currentFrame = bundle?.frames?.[currentFrameIndex] || null;
  const snapshot = currentFrame?.snapshot || null;
  const decision = currentFrame?.decision || null;

  const handleSeek = (e) => {
    const val = parseInt(e.target.value, 10);
    setCurrentFrameIndex(val);
  };

  const handlePrev = () => {
    setCurrentFrameIndex((prev) => Math.max(0, prev - 1));
  };

  const handleNext = () => {
    if (bundle?.frames) {
      setCurrentFrameIndex((prev) => Math.min(bundle.frames.length - 1, prev + 1));
    }
  };

  const handleRestart = () => {
    setCurrentFrameIndex(0);
    setIsPlaying(false);
  };

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.85)',
        backdropFilter: 'blur(6px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 9999,
        padding: 16,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: 'var(--surface-1)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-md)',
          width: '100%',
          maxWidth: 960,
          maxHeight: '94vh',
          display: 'flex',
          flexDirection: 'column',
          boxShadow: '0 24px 48px rgba(0, 0, 0, 0.7)',
          overflow: 'hidden',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header Banner */}
        <div
          style={{
            padding: '12px 18px',
            background: 'var(--surface-2)',
            borderBottom: '1px solid var(--border)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span
              style={{
                background: 'rgba(21, 184, 214, 0.15)',
                color: 'var(--cyan)',
                border: '1px solid var(--cyan)',
                padding: '2px 8px',
                borderRadius: 4,
                fontSize: 10.5,
                fontWeight: 700,
                letterSpacing: '0.04em',
                textTransform: 'uppercase',
              }}
            >
              Offline Replay Mode
            </span>
            <div>
              <div style={{ fontWeight: 700, fontSize: 13.5, color: 'var(--text-primary)' }}>
                Deterministic Telemetry Playback • Run: {simulationId}
              </div>
              <div style={{ fontSize: 10.5, color: 'var(--text-muted)' }}>
                Zero SUMO execution • Instant historical inspection
              </div>
            </div>
          </div>

          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--text-muted)',
              cursor: 'pointer',
              padding: 4,
            }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Content Area */}
        {loading ? (
          <div style={{ padding: 48, textAlign: 'center', color: 'var(--text-muted)' }}>
            <Activity className="animate-spin" size={32} style={{ margin: '0 auto 12px' }} />
            <div>Loading synchronized telemetry frames...</div>
          </div>
        ) : error ? (
          <div style={{ padding: 48, textAlign: 'center', color: 'var(--red)' }}>
            <AlertCircle size={32} style={{ margin: '0 auto 12px' }} />
            <div>{error}</div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', flex: 1, overflowY: 'auto' }}>
            {/* Visualizer & Decision Split */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '1.2fr 0.8fr',
                gap: 16,
                padding: 16,
                background: 'var(--surface-1)',
              }}
            >
              {/* Intersection 2D Canvas */}
              <div>
                <DigitalTwinIntersection
                  trafficData={snapshot}
                  simulationStatus={{ running: false, status: 'offline_replay' }}
                />
              </div>

              {/* Synchronized Decision Inspection Card */}
              <div
                style={{
                  background: 'var(--surface-2)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-sm)',
                  padding: 14,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 10,
                  fontSize: 11.5,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid var(--border)', paddingBottom: 8 }}>
                  <span style={{ fontWeight: 700, color: 'var(--text-primary)' }}>
                    Frame Decision Telemetry
                  </span>
                  <span style={{ color: 'var(--cyan)', fontWeight: 600 }}>
                    Step {currentFrame?.step ?? 0} ({currentFrame?.simulation_time?.toFixed(1) ?? '0.0'}s)
                  </span>
                </div>

                {decision ? (
                  <>
                    <div>
                      <span style={{ color: 'var(--text-muted)', fontSize: 10, textTransform: 'uppercase' }}>
                        Proposed vs Executed Action
                      </span>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 4 }}>
                        <span style={{ fontWeight: 700, color: 'var(--cyan)' }}>
                          {decision.requested_action || decision.action || 'KEEP'}
                        </span>
                        <span style={{ color: 'var(--text-muted)' }}>➔</span>
                        <span
                          style={{
                            fontWeight: 700,
                            color: decision.is_safety_override ? 'var(--amber)' : 'var(--green)',
                          }}
                        >
                          Phase {decision.validated_phase ?? decision.current_phase ?? 0} ({decision.validated_action || 'APPROVED'})
                        </span>
                      </div>
                    </div>

                    {decision.is_safety_override && (
                      <div
                        style={{
                          background: 'rgba(239, 68, 68, 0.12)',
                          border: '1px solid var(--red)',
                          borderRadius: 4,
                          padding: '6px 8px',
                          color: 'var(--red)',
                          fontSize: 11,
                        }}
                      >
                        <strong>Safety Override: </strong>
                        {decision.safety_reason || 'Safety manager enforced clearance constraints.'}
                      </div>
                    )}

                    <div>
                      <span style={{ color: 'var(--text-muted)', fontSize: 10, textTransform: 'uppercase' }}>
                        Controller Rationale
                      </span>
                      <div style={{ color: 'var(--text-secondary)', marginTop: 2, lineHeight: 1.35 }}>
                        {decision.decision_reason || decision.reason || 'Normal schedule/policy execution.'}
                      </div>
                    </div>

                    {Array.isArray(decision.q_values) && decision.q_values.length > 0 && (
                      <div>
                        <span style={{ color: 'var(--text-muted)', fontSize: 10, textTransform: 'uppercase' }}>
                          Raw Expected Returns (Q-values)
                        </span>
                        <div style={{ fontFamily: 'monospace', fontSize: 11, marginTop: 2 }}>
                          [KEEP: {decision.q_values[0]?.toFixed(2) ?? '--'}, NS: {decision.q_values[1]?.toFixed(2) ?? '--'}, EW: {decision.q_values[2]?.toFixed(2) ?? '--'}]
                        </div>
                      </div>
                    )}

                    {decision.post_action_metrics && (
                      <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
                        <span style={{ background: 'var(--surface-1)', padding: '3px 6px', borderRadius: 4 }}>
                          ΔQ: {decision.post_action_metrics.queue_delta > 0 ? '+' : ''}{decision.post_action_metrics.queue_delta}
                        </span>
                        <span style={{ background: 'var(--surface-1)', padding: '3px 6px', borderRadius: 4 }}>
                          ΔWait: {decision.post_action_metrics.waiting_time_delta}s
                        </span>
                      </div>
                    )}
                  </>
                ) : (
                  <div style={{ color: 'var(--text-muted)', fontStyle: 'italic', padding: '16px 0', textAlign: 'center' }}>
                    No discrete decision record at this frame step.
                  </div>
                )}
              </div>
            </div>

            {/* Playback & Scrubber Controls */}
            <div
              style={{
                padding: '12px 20px',
                background: 'var(--surface-2)',
                borderTop: '1px solid var(--border)',
                display: 'flex',
                flexDirection: 'column',
                gap: 8,
              }}
            >
              {/* Slider Scrubber */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <span style={{ fontSize: 11, color: 'var(--text-secondary)', minWidth: 44 }}>
                  {currentFrame?.simulation_time?.toFixed(1) ?? '0.0'}s
                </span>
                <input
                  type="range"
                  min={0}
                  max={Math.max(0, (bundle?.frames?.length || 1) - 1)}
                  value={currentFrameIndex}
                  onChange={handleSeek}
                  style={{
                    flex: 1,
                    accentColor: 'var(--cyan)',
                    cursor: 'pointer',
                  }}
                />
                <span style={{ fontSize: 11, color: 'var(--text-muted)', minWidth: 44, textAlign: 'right' }}>
                  {bundle?.duration_seconds?.toFixed(1) ?? '0.0'}s
                </span>
              </div>

              {/* Control Buttons */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <button
                    onClick={handleRestart}
                    style={{
                      background: 'var(--surface-1)',
                      border: '1px solid var(--border)',
                      borderRadius: 4,
                      color: 'var(--text-secondary)',
                      padding: '4px 8px',
                      cursor: 'pointer',
                    }}
                    title="Restart from beginning"
                  >
                    <RotateCcw size={13} />
                  </button>
                  <button
                    onClick={handlePrev}
                    disabled={currentFrameIndex <= 0}
                    style={{
                      background: 'var(--surface-1)',
                      border: '1px solid var(--border)',
                      borderRadius: 4,
                      color: currentFrameIndex <= 0 ? 'var(--text-muted)' : 'var(--text-primary)',
                      padding: '4px 8px',
                      cursor: currentFrameIndex <= 0 ? 'not-allowed' : 'pointer',
                    }}
                    title="Previous frame (Step back 1s)"
                  >
                    <SkipBack size={13} />
                  </button>
                  <button
                    onClick={() => setIsPlaying(!isPlaying)}
                    style={{
                      background: isPlaying ? 'var(--amber)' : 'var(--cyan)',
                      color: '#000',
                      border: 'none',
                      borderRadius: 4,
                      padding: '5px 14px',
                      fontWeight: 700,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      fontSize: 12,
                    }}
                  >
                    {isPlaying ? <Pause size={13} /> : <Play size={13} />}
                    {isPlaying ? 'Pause' : 'Play'}
                  </button>
                  <button
                    onClick={handleNext}
                    disabled={!bundle || currentFrameIndex >= bundle.frames.length - 1}
                    style={{
                      background: 'var(--surface-1)',
                      border: '1px solid var(--border)',
                      borderRadius: 4,
                      color:
                        !bundle || currentFrameIndex >= bundle.frames.length - 1
                          ? 'var(--text-muted)'
                          : 'var(--text-primary)',
                      padding: '4px 8px',
                      cursor:
                        !bundle || currentFrameIndex >= bundle.frames.length - 1
                          ? 'not-allowed'
                          : 'pointer',
                    }}
                    title="Next frame (Step forward 1s)"
                  >
                    <SkipForward size={13} />
                  </button>
                </div>

                {/* Speed Controls */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11 }}>
                  <span style={{ color: 'var(--text-muted)' }}>Speed:</span>
                  {[0.5, 1, 2, 5].map((spd) => (
                    <button
                      key={spd}
                      onClick={() => setPlaybackSpeed(spd)}
                      style={{
                        background: playbackSpeed === spd ? 'var(--cyan)' : 'var(--surface-1)',
                        color: playbackSpeed === spd ? '#000' : 'var(--text-secondary)',
                        border: '1px solid var(--border)',
                        borderRadius: 3,
                        padding: '2px 6px',
                        fontWeight: 600,
                        fontSize: 10.5,
                        cursor: 'pointer',
                      }}
                    >
                      {spd}×
                    </button>
                  ))}
                </div>

                {/* Frame Counter */}
                <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                  Frame {currentFrameIndex + 1} of {bundle?.total_frames || 0}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default OfflineReplayModal;
