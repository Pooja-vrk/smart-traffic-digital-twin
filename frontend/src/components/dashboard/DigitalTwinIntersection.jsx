import React from 'react';
import { MapPin } from 'lucide-react';
import Card from '../common/Card';
import StatusBadge from '../common/StatusBadge';

/* ── helpers ─────────────────────────────────────────────────── */
const getSignalVariant = (state) => {
  if (state === 'green')  return 'green';
  if (state === 'yellow') return 'amber';
  return 'red';
};

const getSignalLabel = (state) => (state ? state.toUpperCase() : 'RED');

/* determine per-direction signal state from phase index */
const directionSignal = (dir, phaseIndex) => {
  const NS = phaseIndex === 0; // NS_GREEN
  const EW = phaseIndex === 2; // EW_GREEN
  if (dir === 'north' || dir === 'south') return NS ? 'green' : 'red';
  if (dir === 'east'  || dir === 'west')  return EW ? 'green' : 'red';
  return 'red';
};

/* yellow phase: NS_YELLOW=1, EW_YELLOW=3 */
const withYellow = (dir, phaseIndex) => {
  if ((dir === 'north' || dir === 'south') && phaseIndex === 1) return 'yellow';
  if ((dir === 'east'  || dir === 'west')  && phaseIndex === 3) return 'yellow';
  return directionSignal(dir, phaseIndex);
};

/* ── SVG intersection ────────────────────────────────────────── */
const IntersectionSVG = ({ nsGreen, ewGreen, phaseIndex, queues }) => {
  const nsCol = phaseIndex === 0 ? '#22c55e' : phaseIndex === 1 ? '#eab308' : '#ef4444';
  const ewCol = phaseIndex === 2 ? '#22c55e' : phaseIndex === 3 ? '#eab308' : '#ef4444';

  /* queue bar width: each vehicle ≈ 6 px, max 54 */
  const qW = (n) => Math.min((n || 0) * 6, 54);

  return (
    <svg
      viewBox="0 0 260 260"
      width="100%"
      height="100%"
      style={{ display: 'block' }}
      aria-label="Traffic intersection diagram"
    >
      {/* ── Road asphalt ─────────────────────────────── */}
      {/* NS road */}
      <rect x="103" y="0"   width="54" height="260" fill="#1a2d42" />
      {/* EW road */}
      <rect x="0"   y="103" width="260" height="54" fill="#1a2d42" />

      {/* ── Asphalt darker junction box ──────────────── */}
      <rect x="103" y="103" width="54" height="54" fill="#152437" />

      {/* ── Centre cross lines ──────────────────────── */}
      {/* junction border */}
      <rect x="103" y="103" width="54" height="54" fill="none" stroke="#243a54" strokeWidth="1" />

      {/* ── Lane markings — dashed centre lines ──────── */}
      {/* NS centre dashes */}
      {[12, 36, 56, 80, 164, 188, 208, 232].map(y => (
        <line key={`ns${y}`} x1="130" y1={y} x2="130" y2={y + 14}
              stroke="#3a5570" strokeWidth="1.5" strokeDasharray="8,6" />
      ))}
      {/* EW centre dashes */}
      {[12, 36, 56, 80, 164, 188, 208, 232].map(x => (
        <line key={`ew${x}`} x1={x} y1="130" x2={x + 14} y2="130"
              stroke="#3a5570" strokeWidth="1.5" strokeDasharray="8,6" />
      ))}

      {/* ── Stop lines ───────────────────────────────── */}
      <line x1="103" y1="102" x2="157" y2="102" stroke="#f4f8fc" strokeWidth="1.5" opacity="0.5" />
      <line x1="103" y1="158" x2="157" y2="158" stroke="#f4f8fc" strokeWidth="1.5" opacity="0.5" />
      <line x1="102" y1="103" x2="102" y2="157" stroke="#f4f8fc" strokeWidth="1.5" opacity="0.5" />
      <line x1="158" y1="103" x2="158" y2="157" stroke="#f4f8fc" strokeWidth="1.5" opacity="0.5" />

      {/* ── Pedestrian zebra crossings ────────────────── */}
      {/* North crossing */}
      {[103,111,119,127,135,143,151].map(x => (
        <rect key={`pn${x}`} x={x} y="88" width="6" height="12"
              fill="#f4f8fc" opacity="0.12" rx="1" />
      ))}
      {/* South crossing */}
      {[103,111,119,127,135,143,151].map(x => (
        <rect key={`ps${x}`} x={x} y="160" width="6" height="12"
              fill="#f4f8fc" opacity="0.12" rx="1" />
      ))}
      {/* West crossing */}
      {[103,111,119,127,135,143,151].map(y => (
        <rect key={`pw${y}`} x="88" y={y} width="12" height="6"
              fill="#f4f8fc" opacity="0.12" rx="1" />
      ))}
      {/* East crossing */}
      {[103,111,119,127,135,143,151].map(y => (
        <rect key={`pe${y}`} x="160" y={y} width="12" height="6"
              fill="#f4f8fc" opacity="0.12" rx="1" />
      ))}

      {/* ── Lane arrows (directional) ─────────────────── */}
      {/* North → going south (downward) */}
      <polygon points="124,70 128,82 120,82" fill="#f4f8fc" opacity="0.25" />
      {/* South → going north (upward) */}
      <polygon points="136,190 132,178 140,178" fill="#f4f8fc" opacity="0.25" />
      {/* West → going east (rightward) */}
      <polygon points="70,124 82,120 82,128" fill="#f4f8fc" opacity="0.25" />
      {/* East → going west (leftward) */}
      <polygon points="190,136 178,140 178,132" fill="#f4f8fc" opacity="0.25" />

      {/* ── Queue visualisation bars ──────────────────── */}
      {/* North queue (approaches from top) */}
      <rect x="107" y={Math.max(0, 98 - qW(queues?.north))}
            width="20" height={qW(queues?.north)}
            fill={nsCol} opacity="0.45" rx="2" />
      {/* South queue (approaches from bottom) */}
      <rect x="133" y="162"
            width="20" height={qW(queues?.south)}
            fill={nsCol} opacity="0.45" rx="2" />
      {/* West queue */}
      <rect x={Math.max(0, 98 - qW(queues?.west))} y="107"
            width={qW(queues?.west)} height="20"
            fill={ewCol} opacity="0.45" rx="2" />
      {/* East queue */}
      <rect x="162" y="133"
            width={qW(queues?.east)} height="20"
            fill={ewCol} opacity="0.45" rx="2" />

      {/* ── Traffic lights (small 3-bulb) ─────────────── */}
      {/* North light */}
      <TrafficLightSVG x={154} y={62} state={withYellow('north', phaseIndex)} />
      {/* South light */}
      <TrafficLightSVG x={100} y={186} state={withYellow('south', phaseIndex)} />
      {/* East light */}
      <TrafficLightSVG x={186} y={100} state={withYellow('east', phaseIndex)} vertical={false} />
      {/* West light */}
      <TrafficLightSVG x={62} y={154} state={withYellow('west', phaseIndex)} vertical={false} />

      {/* ── Junction centre label ─────────────────────── */}
      <circle cx="130" cy="130" r="16" fill="rgba(6,20,38,0.8)"
              stroke="rgba(122,165,210,0.2)" strokeWidth="1" />
      <text x="130" y="133" textAnchor="middle" fill="#93a9c2"
            fontSize="7" fontFamily="Inter, sans-serif" fontWeight="600">
        INT-001
      </text>
    </svg>
  );
};

/* Mini SVG traffic light element */
const TrafficLightSVG = ({ x, y, state, vertical = true }) => {
  const w = vertical ? 10 : 26;
  const h = vertical ? 26 : 10;
  const rOn  = '#ef4444';
  const yOn  = '#eab308';
  const gOn  = '#22c55e';
  const off  = '#1e293b';

  const [r, yy, g] =
    state === 'green'  ? [off, off, gOn] :
    state === 'yellow' ? [off, yOn, off] :
                         [rOn, off, off];

  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx="3"
            fill="rgba(10,27,48,0.9)" stroke="rgba(122,165,210,0.25)" strokeWidth="0.8" />
      {vertical ? (
        <>
          <circle cx={x + 5} cy={y + 5}  r="3" fill={r}  />
          <circle cx={x + 5} cy={y + 13} r="3" fill={yy} />
          <circle cx={x + 5} cy={y + 21} r="3" fill={g}  />
        </>
      ) : (
        <>
          <circle cx={x + 5}  cy={y + 5} r="3" fill={r}  />
          <circle cx={x + 13} cy={y + 5} r="3" fill={yy} />
          <circle cx={x + 21} cy={y + 5} r="3" fill={g}  />
        </>
      )}
    </g>
  );
};

/* ── Main component ──────────────────────────────────────────── */
const DigitalTwinIntersection = ({ trafficData, simulationStatus }) => {
  const queues  = trafficData?.queues  || {};
  const signal  = trafficData?.signal  || {};
  const speed   = trafficData?.speed   || {};
  const waiting = trafficData?.waiting || {};

  const phaseIndex = signal.phase_index ?? 0;
  const nsGreen    = phaseIndex === 0;
  const ewGreen    = phaseIndex === 2;

  const simTime   = simulationStatus?.simulation_time;
  const totalSteps = simulationStatus?.total_steps;
  const isRunning  = simulationStatus?.running;

  const timeLabel = simTime != null
    ? `${simTime.toFixed(0)}s${totalSteps ? ' / ' + totalSteps + 's' : ''}`
    : '--';

  const liveBadge = (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      {isRunning && (
        <div className="dt-live-badge">
          <span className="dt-live-dot" />
          Real-time
        </div>
      )}
      <span className="dt-time-label">
        {timeLabel}
      </span>
    </div>
  );

  /* directional overlay data */
  const dirs = [
    { key: 'north', label: 'N', queue: queues.north, speed: speed?.north_mps },
    { key: 'south', label: 'S', queue: queues.south, speed: speed?.south_mps },
    { key: 'east',  label: 'E', queue: queues.east,  speed: speed?.east_mps  },
    { key: 'west',  label: 'W', queue: queues.west,  speed: speed?.west_mps  },
  ];

  const avgSpeed = typeof speed?.average_mps === 'number'
    ? speed.average_mps.toFixed(1) + ' m/s'
    : '--';

  return (
    <Card
      title="Live Digital Twin — 4-Way Urban Intersection"
      titleIcon={<MapPin size={14} />}
      badge={liveBadge}
      noPadding
    >
      {/* SVG canvas */}
      <div style={{ padding: '10px 14px 0' }}>
        <div style={{ position: 'relative', maxWidth: 340, margin: '0 auto' }}>
          <IntersectionSVG
            nsGreen={nsGreen}
            ewGreen={ewGreen}
            phaseIndex={phaseIndex}
            queues={queues}
          />

          {/* Directional overlays */}
          <div className="dir-overlay dir-overlay-north">
            <div className="dir-overlay-title">NORTH</div>
            <div className="dir-overlay-row">
              <span>Queue</span>
              <span>{queues.north ?? '--'}</span>
            </div>
            <div className="dir-overlay-row">
              <span>Signal</span>
              <span style={{ color: phaseIndex === 0 ? 'var(--signal-green)' : phaseIndex === 1 ? 'var(--signal-yellow)' : 'var(--signal-red)' }}>
                {getSignalLabel(withYellow('north', phaseIndex))}
              </span>
            </div>
          </div>

          <div className="dir-overlay dir-overlay-south">
            <div className="dir-overlay-title">SOUTH</div>
            <div className="dir-overlay-row">
              <span>Queue</span>
              <span>{queues.south ?? '--'}</span>
            </div>
            <div className="dir-overlay-row">
              <span>Signal</span>
              <span style={{ color: phaseIndex === 0 ? 'var(--signal-green)' : phaseIndex === 1 ? 'var(--signal-yellow)' : 'var(--signal-red)' }}>
                {getSignalLabel(withYellow('south', phaseIndex))}
              </span>
            </div>
          </div>

          <div className="dir-overlay dir-overlay-east">
            <div className="dir-overlay-title">EAST</div>
            <div className="dir-overlay-row">
              <span>Queue</span>
              <span>{queues.east ?? '--'}</span>
            </div>
            <div className="dir-overlay-row">
              <span>Signal</span>
              <span style={{ color: phaseIndex === 2 ? 'var(--signal-green)' : phaseIndex === 3 ? 'var(--signal-yellow)' : 'var(--signal-red)' }}>
                {getSignalLabel(withYellow('east', phaseIndex))}
              </span>
            </div>
          </div>

          <div className="dir-overlay dir-overlay-west">
            <div className="dir-overlay-title">WEST</div>
            <div className="dir-overlay-row">
              <span>Queue</span>
              <span>{queues.west ?? '--'}</span>
            </div>
            <div className="dir-overlay-row">
              <span>Signal</span>
              <span style={{ color: phaseIndex === 2 ? 'var(--signal-green)' : phaseIndex === 3 ? 'var(--signal-yellow)' : 'var(--signal-red)' }}>
                {getSignalLabel(withYellow('west', phaseIndex))}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom strip: phase + speed + total queue */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        padding: '8px 16px 10px',
        borderTop: '1px solid var(--border)',
        marginTop: 8,
        flexWrap: 'wrap',
        gap: 6,
      }}>
        <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
          Phase: <strong style={{ color: 'var(--text-secondary)' }}>{signal.phase_name || '--'}</strong>
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
          Avg Speed: <strong style={{ color: 'var(--amber)' }}>{avgSpeed}</strong>
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
          Total Queue: <strong style={{ color: 'var(--text-primary)' }}>{queues.total ?? '--'}</strong>
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
          Elapsed: <strong style={{ color: 'var(--cyan)' }}>
            {typeof signal.elapsed_seconds === 'number'
              ? signal.elapsed_seconds.toFixed(1) + 's'
              : '--'}
          </strong>
        </div>
      </div>
    </Card>
  );
};

export default DigitalTwinIntersection;
