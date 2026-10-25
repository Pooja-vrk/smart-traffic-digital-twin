import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  MapPin, ZoomIn, ZoomOut, Maximize2, RotateCcw,
  Car, AlertCircle, Info, Shield, Gauge, Clock, Layers
} from 'lucide-react';
import Card from '../common/Card';
import StatusBadge from '../common/StatusBadge';

/* ── Signal phase helper mappings ────────────────────────────── */
const getSignalStateForDirection = (dir, phaseIndex) => {
  // Phase 0: NS_GREEN, Phase 1: NS_YELLOW, Phase 2: EW_GREEN, Phase 3: EW_YELLOW
  if (dir === 'north' || dir === 'south') {
    if (phaseIndex === 0) return 'green';
    if (phaseIndex === 1) return 'yellow';
    return 'red';
  }
  if (dir === 'east' || dir === 'west') {
    if (phaseIndex === 2) return 'green';
    if (phaseIndex === 3) return 'yellow';
    return 'red';
  }
  return 'red';
};

const getSignalColor = (state) => {
  if (state === 'green') return '#22c55e';
  if (state === 'yellow') return '#eab308';
  return '#ef4444';
};

/* ── Realistic 3-Lamp Traffic Signal Head ─────────────────────── */
const TrafficLightHead = ({ x, y, state, angle = 0, label = '' }) => {
  const isGreen = state === 'green';
  const isYellow = state === 'yellow';
  const isRed = state === 'red';

  return (
    <g transform={`translate(${x}, ${y}) rotate(${angle})`}>
      {/* Signal Post / Housing */}
      <rect
        x="-4.5"
        y="-12"
        width="9"
        height="24"
        rx="2"
        fill="#0b131e"
        stroke="rgba(122, 165, 210, 0.4)"
        strokeWidth="0.8"
        filter="drop-shadow(0px 2px 4px rgba(0,0,0,0.7))"
      />
      {/* Sun Visors / Hoods */}
      <line x1="-3.5" y1="-8" x2="3.5" y2="-8" stroke="#1e293b" strokeWidth="1" />
      <line x1="-3.5" y1="0" x2="3.5" y2="0" stroke="#1e293b" strokeWidth="1" />
      <line x1="-3.5" y1="8" x2="3.5" y2="8" stroke="#1e293b" strokeWidth="1" />

      {/* Red Lamp */}
      <circle
        cx="0"
        cy="-7"
        r="2.6"
        fill={isRed ? '#ef4444' : '#331515'}
        stroke={isRed ? '#fca5a5' : '#1e1111'}
        strokeWidth="0.5"
        style={isRed ? { filter: 'drop-shadow(0px 0px 4px #ef4444)' } : {}}
      />
      {/* Yellow Lamp */}
      <circle
        cx="0"
        cy="0"
        r="2.6"
        fill={isYellow ? '#eab308' : '#332910'}
        stroke={isYellow ? '#fef08a' : '#1e1a0b'}
        strokeWidth="0.5"
        style={isYellow ? { filter: 'drop-shadow(0px 0px 4px #eab308)' } : {}}
      />
      {/* Green Lamp */}
      <circle
        cx="0"
        cy="7"
        r="2.6"
        fill={isGreen ? '#22c55e' : '#0e2b17'}
        stroke={isGreen ? '#86efac' : '#08170c'}
        strokeWidth="0.5"
        style={isGreen ? { filter: 'drop-shadow(0px 0px 4px #22c55e)' } : {}}
      />
    </g>
  );
};

/* ── Live Vehicle SVG Element ────────────────────────────────── */
const VehicleNode = React.memo(({ veh, onSelect, isSelected }) => {
  const isStopped = (veh.speed ?? 0) < 0.2 || (veh.waiting_time ?? 0) > 0.5;
  const isEmergency = veh.vehicle_type?.includes('emergency') || veh.vehicle_type?.includes('ambulance') || veh.vehicle_type?.includes('fire') || veh.id?.startsWith('EV') || veh.id === 'EV_01';
  const isHeavy = !isEmergency && (veh.vehicle_type?.includes('heavy') || (veh.length ?? 5) > 6.0);

  // In SUMO network: X is East-West, Y is South-North (0..600).
  // In SVG: X is East-West, Y is inverted (0 is North, 600 is South).
  const svgX = veh.x;
  const svgY = 600 - veh.y;
  const angle = veh.angle ?? 0;

  const len = Math.max(veh.length ?? 5.0, isEmergency ? 6.5 : 4.5);
  const wid = Math.max(veh.width ?? 2.0, isEmergency ? 2.4 : 2.0);

  // Styling based on state and type
  const bodyColor = isEmergency
    ? '#ef4444' // Emergency Red
    : isHeavy
      ? '#f59e0b' // Amber/Orange for trucks
      : isStopped
        ? '#f43f5e' // Rose/Red for stopped/queued
        : '#38bdf8'; // Cyan/Blue for moving cars

  const strokeColor = isEmergency
    ? '#ffffff'
    : isSelected
      ? '#ffffff'
      : isStopped
        ? '#fda4af'
        : '#7dd3fc';
  const strokeWidth = isEmergency ? 1.0 : (isSelected ? 1.0 : 0.4);

  return (
    <g
      transform={`translate(${svgX}, ${svgY}) rotate(${angle})`}
      onClick={(e) => {
        e.stopPropagation();
        onSelect(veh);
      }}
      style={{ cursor: 'pointer' }}
    >
      {/* Emergency Siren Pulse & Halo */}
      {isEmergency && (
        <>
          <circle
            cx="0"
            cy="0"
            r={len * 1.6}
            fill="none"
            stroke="#ef4444"
            strokeWidth="0.8"
            strokeDasharray="3,3"
            opacity="0.8"
          />
          <ellipse
            cx="0"
            cy="0"
            rx={wid * 1.8}
            ry={len * 1.2}
            fill="rgba(239, 68, 68, 0.25)"
          />
        </>
      )}

      {/* Selection Halo */}
      {isSelected && !isEmergency && (
        <circle
          cx="0"
          cy="0"
          r={len + 2}
          fill="none"
          stroke="#38bdf8"
          strokeWidth="0.8"
          strokeDasharray="2,2"
          style={{ animation: 'spin 4s linear infinite' }}
        />
      )}

      {/* Stopped / Queued Warning Glow */}
      {isStopped && !isEmergency && (
        <ellipse
          cx="0"
          cy="0"
          rx={wid * 1.2}
          ry={len * 0.7}
          fill="rgba(244, 63, 94, 0.25)"
        />
      )}

      {/* Vehicle Shadow */}
      <rect
        x={-wid / 2 + 0.3}
        y={-len / 2 + 0.3}
        width={wid}
        height={len}
        rx={wid * 0.3}
        fill="rgba(0,0,0,0.5)"
      />

      {/* Vehicle Main Body */}
      <rect
        x={-wid / 2}
        y={-len / 2}
        width={wid}
        height={len}
        rx={wid * 0.25}
        fill={bodyColor}
        stroke={strokeColor}
        strokeWidth={strokeWidth}
      />

      {/* Windshield and Roof */}
      {isEmergency ? (
        // Emergency Ambulance / Fire Truck Cabin & Lightbar
        <>
          <rect
            x={-wid / 2 + 0.3}
            y={-len / 2 + len * 0.2}
            width={wid - 0.6}
            height={len * 0.6}
            rx={0.3}
            fill="#f8fafc"
          />
          {/* Red Cross */}
          <rect x="-0.3" y={-len * 0.05} width="0.6" height="2.0" fill="#ef4444" />
          <rect x="-0.9" y={len * 0.05} width="1.8" height="0.6" fill="#ef4444" />
          {/* Front Windshield */}
          <rect
            x={-wid / 2 + 0.4}
            y={-len / 2 + len * 0.12}
            width={wid - 0.8}
            height={0.8}
            fill="#0f172a"
          />
          {/* Siren Beacon Light Bar */}
          <rect x={-wid / 2 + 0.3} y={-len * 0.22} width={wid * 0.45} height="0.8" rx="0.2" fill="#38bdf8" stroke="#bae6fd" strokeWidth="0.2" />
          <rect x="0.1" y={-len * 0.22} width={wid * 0.45} height="0.8" rx="0.2" fill="#ef4444" stroke="#fca5a5" strokeWidth="0.2" />
        </>
      ) : isHeavy ? (
        // Truck Cabin & Cargo Bed
        <>
          {/* Cab */}
          <rect
            x={-wid / 2 + 0.2}
            y={-len / 2 + 0.3}
            width={wid - 0.4}
            height={len * 0.32}
            rx={0.3}
            fill="#b45309"
          />
          {/* Windshield */}
          <rect
            x={-wid / 2 + 0.4}
            y={-len / 2 + 0.5}
            width={wid - 0.8}
            height={0.8}
            fill="#0f172a"
          />
          {/* Cargo Container */}
          <rect
            x={-wid / 2 + 0.2}
            y={-len / 2 + len * 0.38}
            width={wid - 0.4}
            height={len * 0.58}
            rx={0.2}
            fill="#78350f"
            stroke="#92400e"
            strokeWidth="0.3"
          />
        </>
      ) : (
        // Standard Car Cabin
        <>
          {/* Front Windshield */}
          <rect
            x={-wid / 2 + 0.3}
            y={-len / 2 + len * 0.22}
            width={wid - 0.6}
            height={len * 0.16}
            rx={0.2}
            fill="#0f172a"
          />
          {/* Roof */}
          <rect
            x={-wid / 2 + 0.35}
            y={-len / 2 + len * 0.38}
            width={wid - 0.7}
            height={len * 0.3}
            rx={0.2}
            fill={isStopped ? '#be123c' : '#0284c7'}
          />
          {/* Rear Windshield */}
          <rect
            x={-wid / 2 + 0.3}
            y={-len / 2 + len * 0.68}
            width={wid - 0.6}
            height={len * 0.12}
            rx={0.2}
            fill="#0f172a"
          />
        </>
      )}

      {/* Headlights (Top / Front of vehicle) */}
      <circle cx={-wid / 2 + 0.45} cy={-len / 2 + 0.3} r="0.45" fill="#ffffff" />
      <circle cx={wid / 2 - 0.45} cy={-len / 2 + 0.3} r="0.45" fill="#ffffff" />

      {/* Taillights / Brake Lights (Bottom / Rear of vehicle) */}
      <circle
        cx={-wid / 2 + 0.45}
        cy={len / 2 - 0.3}
        r={isStopped ? '0.6' : '0.4'}
        fill={isStopped ? '#ff0000' : '#b91c1c'}
        style={isStopped ? { filter: 'drop-shadow(0px 0px 3px #ef4444)' } : {}}
      />
      <circle
        cx={wid / 2 - 0.45}
        cy={len / 2 - 0.3}
        r={isStopped ? '0.6' : '0.4'}
        fill={isStopped ? '#ff0000' : '#b91c1c'}
        style={isStopped ? { filter: 'drop-shadow(0px 0px 3px #ef4444)' } : {}}
      />
    </g>
  );
});

/* ── Smooth Interpolation Animation Wrapper ─────────────────── */
const useSmoothVehicles = (liveVehicles) => {
  const [renderedVehicles, setRenderedVehicles] = useState(liveVehicles || []);
  const prevVehiclesRef = useRef({});
  const targetVehiclesRef = useRef({});
  const animFrameRef = useRef(null);

  useEffect(() => {
    const nextMap = {};
    (liveVehicles || []).forEach((v) => {
      nextMap[v.id] = v;
    });
    targetVehiclesRef.current = nextMap;

    // Remove old keys not in nextMap
    const currentRenderedMap = {};
    renderedVehicles.forEach((v) => {
      if (nextMap[v.id]) currentRenderedMap[v.id] = v;
    });
    prevVehiclesRef.current = currentRenderedMap;
  }, [liveVehicles]);

  useEffect(() => {
    let lastTime = performance.now();

    const animate = (time) => {
      const dt = Math.min((time - lastTime) / 1000, 0.1);
      lastTime = time;

      const targetMap = targetVehiclesRef.current;
      const targetIds = Object.keys(targetMap);

      if (targetIds.length === 0) {
        setRenderedVehicles((prev) => (prev.length === 0 ? prev : []));
      } else {
        const lerpFactor = Math.min(dt * 8.0, 1.0); // smooth spring interpolation
        const updated = targetIds.map((id) => {
          const target = targetMap[id];
          const prev = prevVehiclesRef.current[id];

          if (!prev) {
            prevVehiclesRef.current[id] = target;
            return target;
          }

          // Linear interpolation of X, Y, Angle
          const nx = prev.x + (target.x - prev.x) * lerpFactor;
          const ny = prev.y + (target.y - prev.y) * lerpFactor;

          // Handle angle wrap-around
          let diffAngle = target.angle - prev.angle;
          if (diffAngle > 180) diffAngle -= 360;
          if (diffAngle < -180) diffAngle += 360;
          const nAngle = (prev.angle + diffAngle * lerpFactor + 360) % 360;

          const nextObj = {
            ...target,
            x: nx,
            y: ny,
            angle: nAngle,
          };
          prevVehiclesRef.current[id] = nextObj;
          return nextObj;
        });
        setRenderedVehicles(updated);
      }

      animFrameRef.current = requestAnimationFrame(animate);
    };

    animFrameRef.current = requestAnimationFrame(animate);
    return () => {
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    };
  }, []);

  return renderedVehicles;
};

/* ── Main Digital Twin Intersection Component ────────────────── */
const DigitalTwinIntersection = ({ trafficData, simulationStatus }) => {
  const queues = trafficData?.queues || {};
  const signal = trafficData?.signal || {};
  const speed = trafficData?.speed || {};
  const ai = trafficData?.ai || null;

  const rawVehicles = trafficData?.vehicles_data || [];
  const smoothVehicles = useSmoothVehicles(rawVehicles);

  const [selectedVehicle, setSelectedVehicle] = useState(null);
  const [viewMode, setViewMode] = useState('focus'); // 'focus' (240m), 'corridor' (380m), 'full' (600m)
  const [showSpeedLabels, setShowSpeedLabels] = useState(false);

  const phaseIndex = signal.phase_index ?? 0;
  const phaseName = signal.phase_name || 'NS_GREEN';
  const elapsedSec = signal.elapsed_seconds ?? 0;

  const simTime = simulationStatus?.simulation_time;
  const isRunning = simulationStatus?.running;

  // ViewBox presets
  const viewBox = useMemo(() => {
    switch (viewMode) {
      case 'focus':
        return '190 190 220 220'; // 220m centered on junction
      case 'corridor':
        return '110 110 380 380'; // 380m wide corridor
      case 'full':
      default:
        return '0 0 600 600'; // Full 600m intersection network
    }
  }, [viewMode]);

  // Keep selected vehicle info updated with live stream
  useEffect(() => {
    if (selectedVehicle) {
      const found = rawVehicles.find((v) => v.id === selectedVehicle.id);
      if (found) setSelectedVehicle(found);
      else setSelectedVehicle(null); // Vehicle left simulation
    }
  }, [rawVehicles]);

  const sigNorth = getSignalStateForDirection('north', phaseIndex);
  const sigSouth = getSignalStateForDirection('south', phaseIndex);
  const sigEast = getSignalStateForDirection('east', phaseIndex);
  const sigWest = getSignalStateForDirection('west', phaseIndex);

  // Moving vs Stopped vehicle metrics
  const activeCount = rawVehicles.length;
  const stoppedCount = rawVehicles.filter(
    (v) => (v.speed ?? 0) < 0.2 || (v.waiting_time ?? 0) > 0.5
  ).length;
  const movingCount = activeCount - stoppedCount;

  // Status labels
  const isStopped = simulationStatus?.status === 'stopped';
  const isCompleted = simulationStatus?.status === 'completed';
  const isError = simulationStatus?.status === 'error';

  let statusBadge = null;
  if (isRunning) {
    statusBadge = (
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <div className="dt-live-badge">
          <span className="dt-live-dot" />
          ● LIVE • {activeCount} VEHICLES
        </div>
        <span className="dt-time-label">
          {simTime != null ? `T: ${simTime.toFixed(1)}s` : '--'}
        </span>
      </div>
    );
  } else if (isStopped) {
    statusBadge = (
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <StatusBadge variant="amber">SIMULATION STOPPED</StatusBadge>
        <span className="dt-time-label">
          {simTime != null ? `T: ${simTime.toFixed(1)}s` : '--'}
        </span>
      </div>
    );
  } else if (isCompleted) {
    statusBadge = (
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <StatusBadge variant="cyan">FINAL STATE • {activeCount} VEHICLES</StatusBadge>
        <span className="dt-time-label">
          {simTime != null ? `T: ${simTime.toFixed(1)}s` : '--'}
        </span>
      </div>
    );
  } else if (isError) {
    statusBadge = (
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <StatusBadge variant="red">ERROR</StatusBadge>
      </div>
    );
  } else {
    statusBadge = (
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <StatusBadge variant="gray">READY</StatusBadge>
      </div>
    );
  }

  return (
    <Card
      title="Live Digital Twin — 4-Way Urban Intersection"
      titleIcon={<MapPin size={15} />}
      badge={statusBadge}
      noPadding
    >
      {/* ── Control Bar: View Zoom & Controls ────────────── */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '8px 14px',
          background: 'var(--surface-2)',
          borderBottom: '1px solid var(--border)',
          fontSize: 11,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase' }}>
            View:
          </span>
          <div className="seg-btn-group" style={{ height: 26 }}>
            <button
              className={`seg-btn ${viewMode === 'focus' ? 'active' : ''}`}
              onClick={() => setViewMode('focus')}
              title="Focus on junction center (220m)"
            >
              Junction Focus
            </button>
            <button
              className={`seg-btn ${viewMode === 'corridor' ? 'active' : ''}`}
              onClick={() => setViewMode('corridor')}
              title="Corridor approach view (380m)"
            >
              Corridors
            </button>
            <button
              className={`seg-btn ${viewMode === 'full' ? 'active' : ''}`}
              onClick={() => setViewMode('full')}
              title="Full Network boundary (600m)"
            >
              Full Grid
            </button>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {isRunning ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--text-secondary)' }}>
              <span style={{ color: 'var(--green)', fontWeight: 600 }}>● LIVE:</span>
              <strong style={{ color: 'var(--cyan)' }}>{activeCount} vehicles</strong>
              <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                ({movingCount} moving, {stoppedCount} queued)
              </span>
            </div>
          ) : isStopped ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--amber)', fontSize: 11 }}>
              <span style={{ fontWeight: 600 }}>■ STOPPED:</span>
              <span style={{ color: 'var(--text-muted)', fontSize: 10 }}>
                {activeCount > 0 ? `Captured state (${activeCount} vehicles)` : 'Simulation idle'}
              </span>
            </div>
          ) : isCompleted ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--cyan)', fontSize: 11 }}>
              <span style={{ fontWeight: 600 }}>✓ COMPLETED:</span>
              <span style={{ color: 'var(--text-muted)', fontSize: 10 }}>
                Final snapshot ({activeCount} vehicles)
              </span>
            </div>
          ) : (
            <div style={{ color: 'var(--text-muted)', fontSize: 11 }}>
              Simulation idle & ready
            </div>
          )}
        </div>
      </div>

      {/* ── 2D Digital Twin SVG Map Area ──────────────────── */}
      <div style={{ position: 'relative', width: '100%', background: '#070f1a', overflow: 'hidden' }}>
        <svg
          viewBox={viewBox}
          width="100%"
          style={{
            display: 'block',
            maxHeight: '440px',
            transition: 'all 0.4s ease-in-out',
          }}
          onClick={() => setSelectedVehicle(null)}
        >
          <defs>
            {/* Grid background pattern */}
            <pattern id="dt-grid" width="20" height="20" patternUnits="userSpaceOnUse">
              <path d="M 20 0 L 0 0 0 20" fill="none" stroke="rgba(122, 165, 210, 0.05)" strokeWidth="0.8" />
            </pattern>
            {/* Crosswalk pattern */}
            <pattern id="crosswalk-h" width="4" height="12" patternUnits="userSpaceOnUse">
              <rect width="2.4" height="12" fill="#f8fafc" opacity="0.3" />
            </pattern>
            <pattern id="crosswalk-v" width="12" height="4" patternUnits="userSpaceOnUse">
              <rect width="12" height="2.4" fill="#f8fafc" opacity="0.3" />
            </pattern>
          </defs>

          {/* Background Grid */}
          <rect x="0" y="0" width="600" height="600" fill="#061220" />
          <rect x="0" y="0" width="600" height="600" fill="url(#dt-grid)" />

          {/* Terrain / Surrounding blocks */}
          <rect x="0" y="0" width="289.6" height="289.6" fill="#091829" stroke="rgba(122,165,210,0.1)" strokeWidth="1" />
          <rect x="310.4" y="0" width="289.6" height="289.6" fill="#091829" stroke="rgba(122,165,210,0.1)" strokeWidth="1" />
          <rect x="0" y="310.4" width="289.6" height="289.6" fill="#091829" stroke="rgba(122,165,210,0.1)" strokeWidth="1" />
          <rect x="310.4" y="310.4" width="289.6" height="289.6" fill="#091829" stroke="rgba(122,165,210,0.1)" strokeWidth="1" />

          {/* ── Road Corridors (Asphalt Surface) ─────────────── */}
          {/* North-South Road Corridor: x from 289.6 to 310.4 (width = 20.8m) */}
          <rect x="289.6" y="0" width="20.8" height="600" fill="#131e2b" />
          {/* East-West Road Corridor: y from 289.6 to 310.4 (width = 20.8m) */}
          <rect x="0" y="289.6" width="600" height="20.8" fill="#131e2b" />

          {/* Central Junction Box */}
          <rect x="289.6" y="289.6" width="20.8" height="20.8" fill="#0f1924" />
          <rect x="289.6" y="289.6" width="20.8" height="20.8" fill="none" stroke="rgba(122,165,210,0.2)" strokeWidth="0.8" strokeDasharray="3,3" />

          {/* ── Road Markings ──────────────────────────────── */}
          {/* Double Yellow Dividing Lines */}
          {/* North arm divider */}
          <line x1="299.8" y1="0" x2="299.8" y2="280" stroke="#eab308" strokeWidth="0.6" />
          <line x1="300.2" y1="0" x2="300.2" y2="280" stroke="#eab308" strokeWidth="0.6" />
          {/* South arm divider */}
          <line x1="299.8" y1="320" x2="299.8" y2="600" stroke="#eab308" strokeWidth="0.6" />
          <line x1="300.2" y1="320" x2="300.2" y2="600" stroke="#eab308" strokeWidth="0.6" />
          {/* West arm divider */}
          <line x1="0" y1="299.8" x2="280" y2="299.8" stroke="#eab308" strokeWidth="0.6" />
          <line x1="0" y1="300.2" x2="280" y2="300.2" stroke="#eab308" strokeWidth="0.6" />
          {/* East arm divider */}
          <line x1="320" y1="299.8" x2="600" y2="299.8" stroke="#eab308" strokeWidth="0.6" />
          <line x1="320" y1="300.2" x2="600" y2="300.2" stroke="#eab308" strokeWidth="0.6" />

          {/* White Dashed Lane Dividers */}
          {/* North lanes */}
          <line x1="294.8" y1="0" x2="294.8" y2="280" stroke="#475569" strokeWidth="0.6" strokeDasharray="4,4" />
          <line x1="305.2" y1="0" x2="305.2" y2="280" stroke="#475569" strokeWidth="0.6" strokeDasharray="4,4" />
          {/* South lanes */}
          <line x1="294.8" y1="320" x2="294.8" y2="600" stroke="#475569" strokeWidth="0.6" strokeDasharray="4,4" />
          <line x1="305.2" y1="320" x2="305.2" y2="600" stroke="#475569" strokeWidth="0.6" strokeDasharray="4,4" />
          {/* West lanes */}
          <line x1="0" y1="294.8" x2="280" y2="294.8" stroke="#475569" strokeWidth="0.6" strokeDasharray="4,4" />
          <line x1="0" y1="305.2" x2="280" y2="305.2" stroke="#475569" strokeWidth="0.6" strokeDasharray="4,4" />
          {/* East lanes */}
          <line x1="320" y1="294.8" x2="600" y2="294.8" stroke="#475569" strokeWidth="0.6" strokeDasharray="4,4" />
          <line x1="320" y1="305.2" x2="600" y2="305.2" stroke="#475569" strokeWidth="0.6" strokeDasharray="4,4" />

          {/* Stop Lines (Thick White Solid) */}
          {/* North Incoming Stop Line (y = 289.6) */}
          <line x1="289.6" y1="289.6" x2="300" y2="289.6" stroke="#f8fafc" strokeWidth="1.8" opacity="0.9" />
          {/* South Incoming Stop Line (y = 310.4) */}
          <line x1="300" y1="310.4" x2="310.4" y2="310.4" stroke="#f8fafc" strokeWidth="1.8" opacity="0.9" />
          {/* West Incoming Stop Line (x = 289.6) */}
          <line x1="289.6" y1="300" x2="289.6" y2="310.4" stroke="#f8fafc" strokeWidth="1.8" opacity="0.9" />
          {/* East Incoming Stop Line (x = 310.4) */}
          <line x1="310.4" y1="289.6" x2="310.4" y2="300" stroke="#f8fafc" strokeWidth="1.8" opacity="0.9" />

          {/* Pedestrian Crosswalks (Zebra Stripes) */}
          {/* North Crosswalk */}
          <rect x="289.6" y="278" width="20.8" height="8" fill="url(#crosswalk-h)" />
          {/* South Crosswalk */}
          <rect x="289.6" y="314" width="20.8" height="8" fill="url(#crosswalk-h)" />
          {/* West Crosswalk */}
          <rect x="278" y="289.6" width="8" height="20.8" fill="url(#crosswalk-v)" />
          {/* East Crosswalk */}
          <rect x="314" y="289.6" width="8" height="20.8" fill="url(#crosswalk-v)" />

          {/* Lane Directional Guide Arrows */}
          {/* North approach (heading down) */}
          <polygon points="294.8,268 296.8,262 292.8,262" fill="#64748b" opacity="0.4" />
          <polygon points="297.8,268 299.8,262 295.8,262" fill="#64748b" opacity="0.4" />
          {/* South approach (heading up) */}
          <polygon points="305.2,332 303.2,338 307.2,338" fill="#64748b" opacity="0.4" />
          <polygon points="302.2,332 300.2,338 304.2,338" fill="#64748b" opacity="0.4" />
          {/* West approach (heading right) */}
          <polygon points="268,305.2 262,303.2 262,307.2" fill="#64748b" opacity="0.4" />
          <polygon points="268,302.2 262,300.2 262,304.2" fill="#64748b" opacity="0.4" />
          {/* East approach (heading left) */}
          <polygon points="332,294.8 338,292.8 338,296.8" fill="#64748b" opacity="0.4" />
          <polygon points="332,297.8 338,295.8 338,299.8" fill="#64748b" opacity="0.4" />

          {/* ── Traffic Light Heads at Intersection Approaches ── */}
          {/* North Signal Head (facing incoming southbound traffic) */}
          <TrafficLightHead x={285.5} y={284} state={sigNorth} angle={0} />
          {/* South Signal Head (facing incoming northbound traffic) */}
          <TrafficLightHead x={314.5} y={316} state={sigSouth} angle={180} />
          {/* East Signal Head (facing incoming westbound traffic) */}
          <TrafficLightHead x={316} y={285.5} state={sigEast} angle={90} />
          {/* West Signal Head (facing incoming eastbound traffic) */}
          <TrafficLightHead x={284} y={314.5} state={sigWest} angle={270} />

          {/* ── Live Rendered Vehicles ─────────────────────── */}
          {smoothVehicles.map((veh) => (
            <VehicleNode
              key={veh.id}
              veh={veh}
              isSelected={selectedVehicle?.id === veh.id}
              onSelect={setSelectedVehicle}
            />
          ))}

          {/* Junction Center ID Pin */}
          <circle cx="300" cy="300" r="4.5" fill="rgba(6,20,38,0.9)" stroke="rgba(56, 189, 248, 0.4)" strokeWidth="0.8" />
          <circle cx="300" cy="300" r="1.5" fill="#38bdf8" />
        </svg>

        {/* ── Live Emergency Vehicle Priority HUD Banner ────── */}
        {trafficData?.emergency?.active && (
          <div
            style={{
              position: 'absolute',
              top: 12,
              left: 12,
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              background: 'rgba(239, 68, 68, 0.22)',
              border: '1px solid #ef4444',
              borderRadius: 'var(--radius-sm)',
              padding: '8px 12px',
              backdropFilter: 'blur(8px)',
              boxShadow: '0 0 16px rgba(239, 68, 68, 0.4)',
              zIndex: 25,
            }}
          >
            <div style={{ fontSize: 18 }}>🚨</div>
            <div>
              <div style={{ fontSize: 10.5, fontWeight: 800, color: '#fca5a5', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                EMERGENCY PRIORITY {trafficData.emergency.priority_active ? 'ACTIVE' : 'REQUESTED'}
              </div>
              <div style={{ fontSize: 11, color: '#ffffff', display: 'flex', gap: 10, marginTop: 2, fontVariantNumeric: 'tabular-nums' }}>
                <span>ID: <strong>{trafficData.emergency.vehicle_id}</strong></span>
                <span>Approach: <strong style={{ textTransform: 'uppercase', color: '#fef08a' }}>{trafficData.emergency.approach}</strong></span>
                <span>Distance: <strong>{trafficData.emergency.distance != null ? `${Math.round(trafficData.emergency.distance)}m` : '--'}</strong></span>
                <span>Safety: <strong style={{ color: trafficData.emergency.priority_active ? '#86efac' : '#fef08a' }}>{trafficData.emergency.safety_status}</strong></span>
              </div>
            </div>
          </div>
        )}

        {/* ── Real Directional Queue Overlays ─────────────────── */}
        {/* NORTH */}
        <div className="dir-overlay dir-overlay-north" style={{ borderLeft: `3px solid ${getSignalColor(sigNorth)}` }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6 }}>
            <span className="dir-overlay-title">NORTH APPROACH</span>
            <span style={{ fontSize: 9, fontWeight: 700, color: getSignalColor(sigNorth) }}>
              {sigNorth.toUpperCase()}
            </span>
          </div>
          <div className="dir-overlay-row">
            <span>Queue:</span>
            <span>{queues.north ?? 0} veh</span>
          </div>
        </div>

        {/* SOUTH */}
        <div className="dir-overlay dir-overlay-south" style={{ borderLeft: `3px solid ${getSignalColor(sigSouth)}` }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6 }}>
            <span className="dir-overlay-title">SOUTH APPROACH</span>
            <span style={{ fontSize: 9, fontWeight: 700, color: getSignalColor(sigSouth) }}>
              {sigSouth.toUpperCase()}
            </span>
          </div>
          <div className="dir-overlay-row">
            <span>Queue:</span>
            <span>{queues.south ?? 0} veh</span>
          </div>
        </div>

        {/* EAST */}
        <div className="dir-overlay dir-overlay-east" style={{ borderLeft: `3px solid ${getSignalColor(sigEast)}` }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6 }}>
            <span className="dir-overlay-title">EAST</span>
            <span style={{ fontSize: 9, fontWeight: 700, color: getSignalColor(sigEast) }}>
              {sigEast.toUpperCase()}
            </span>
          </div>
          <div className="dir-overlay-row">
            <span>Queue:</span>
            <span>{queues.east ?? 0}</span>
          </div>
        </div>

        {/* WEST */}
        <div className="dir-overlay dir-overlay-west" style={{ borderLeft: `3px solid ${getSignalColor(sigWest)}` }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6 }}>
            <span className="dir-overlay-title">WEST</span>
            <span style={{ fontSize: 9, fontWeight: 700, color: getSignalColor(sigWest) }}>
              {sigWest.toUpperCase()}
            </span>
          </div>
          <div className="dir-overlay-row">
            <span>Queue:</span>
            <span>{queues.west ?? 0}</span>
          </div>
        </div>

        {/* ── Selected Vehicle Inspector Card (Floating) ───── */}
        {selectedVehicle && (
          <div
            style={{
              position: 'absolute',
              bottom: 12,
              right: 12,
              background: 'rgba(10, 27, 48, 0.95)',
              border: '1px solid var(--border-bright)',
              borderRadius: 'var(--radius-sm)',
              padding: '10px 14px',
              maxWidth: 240,
              backdropFilter: 'blur(8px)',
              boxShadow: 'var(--shadow-lg)',
              zIndex: 20,
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
              <strong style={{ fontSize: 12, color: 'var(--cyan)' }}>
                🚗 {selectedVehicle.id}
              </strong>
              <button
                onClick={() => setSelectedVehicle(null)}
                style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 12 }}
              >
                ✕
              </button>
            </div>
            <div style={{ fontSize: 11, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 8px', color: 'var(--text-secondary)' }}>
              <div>Speed: <strong style={{ color: 'var(--text-primary)' }}>{(selectedVehicle.speed * 3.6).toFixed(1)} km/h</strong></div>
              <div>Wait: <strong style={{ color: selectedVehicle.waiting_time > 0 ? 'var(--amber)' : 'var(--green)' }}>{selectedVehicle.waiting_time.toFixed(1)}s</strong></div>
              <div>Lane: <strong style={{ color: 'var(--text-primary)' }}>{selectedVehicle.lane_id || '--'}</strong></div>
              <div>Edge: <strong style={{ color: 'var(--text-primary)' }}>{selectedVehicle.edge_id || '--'}</strong></div>
              <div style={{ gridColumn: '1 / -1' }}>
                Type: <strong style={{ color: 'var(--text-primary)' }}>{selectedVehicle.vehicle_type || 'standard_car'}</strong>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ── Bottom Live Command Center Metrics Strip ──────── */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(5, 1fr)',
          gap: 8,
          padding: '10px 14px',
          borderTop: '1px solid var(--border)',
          background: 'var(--surface)',
        }}
      >
        <div style={{ fontSize: 11 }}>
          <div style={{ color: 'var(--text-muted)', textTransform: 'uppercase', fontSize: 9.5, fontWeight: 600 }}>
            Current Phase
          </div>
          <strong style={{ color: phaseIndex === 0 || phaseIndex === 2 ? 'var(--green)' : 'var(--amber)' }}>
            {phaseName}
          </strong>
        </div>

        <div style={{ fontSize: 11 }}>
          <div style={{ color: 'var(--text-muted)', textTransform: 'uppercase', fontSize: 9.5, fontWeight: 600 }}>
            Phase Elapsed
          </div>
          <strong style={{ color: 'var(--cyan)', fontVariantNumeric: 'tabular-nums' }}>
            {typeof elapsedSec === 'number' ? `${elapsedSec.toFixed(1)}s` : '--'}
          </strong>
        </div>

        <div style={{ fontSize: 11 }}>
          <div style={{ color: 'var(--text-muted)', textTransform: 'uppercase', fontSize: 9.5, fontWeight: 600 }}>
            Total Queue
          </div>
          <strong style={{ color: (queues.total ?? 0) > 10 ? 'var(--red)' : (queues.total ?? 0) > 5 ? 'var(--amber)' : 'var(--green)' }}>
            {queues.total ?? '--'} vehicles
          </strong>
        </div>

        <div style={{ fontSize: 11 }}>
          <div style={{ color: 'var(--text-muted)', textTransform: 'uppercase', fontSize: 9.5, fontWeight: 600 }}>
            Avg Velocity
          </div>
          <strong style={{ color: 'var(--text-primary)' }}>
            {typeof speed.average_mps === 'number' ? `${speed.average_mps.toFixed(1)} m/s` : '--'}
          </strong>
        </div>

        <div style={{ fontSize: 11 }}>
          <div style={{ color: 'var(--text-muted)', textTransform: 'uppercase', fontSize: 9.5, fontWeight: 600 }}>
            Active Controller
          </div>
          <strong style={{ color: 'var(--purple)' }}>
            {simulationStatus?.controller ? simulationStatus.controller.toUpperCase() : 'FIXED'}
          </strong>
        </div>
      </div>
    </Card>
  );
};

export default DigitalTwinIntersection;
