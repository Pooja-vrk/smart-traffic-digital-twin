import React, { useState } from 'react';
import { Settings as SettingsIcon, Monitor, RefreshCw, LayoutDashboard, Info } from 'lucide-react';
import Card from '../components/common/Card';
import StatusBadge from '../components/common/StatusBadge';

/* Simple toggle switch */
const Toggle = ({ checked, onChange }) => (
  <button
    role="switch"
    aria-checked={checked}
    onClick={() => onChange(!checked)}
    style={{
      width: 38,
      height: 20,
      borderRadius: 10,
      border: 'none',
      cursor: 'pointer',
      background: checked ? 'var(--blue)' : 'var(--surface-2)',
      outline: '1px solid var(--border)',
      position: 'relative',
      transition: 'background 0.2s',
      flexShrink: 0,
    }}
  >
    <span style={{
      position: 'absolute',
      top: 2,
      left: checked ? 18 : 2,
      width: 16,
      height: 16,
      borderRadius: '50%',
      background: '#fff',
      transition: 'left 0.2s',
      boxShadow: '0 1px 3px rgba(0,0,0,0.4)',
    }} />
  </button>
);

const SettingRow = ({ label, desc, control }) => (
  <div className="settings-row">
    <div>
      <div className="settings-label">{label}</div>
      {desc && <div className="settings-desc">{desc}</div>}
    </div>
    <div className="settings-control">{control}</div>
  </div>
);

const Settings = () => {
  const [compactMode,      setCompactMode]      = useState(false);
  const [autoRefresh,      setAutoRefresh]       = useState(true);
  const [showChartLegend,  setShowChartLegend]  = useState(true);
  const [chartAnimations,  setChartAnimations]  = useState(false);
  const [refreshInterval,  setRefreshInterval]  = useState('30');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, maxWidth: 680 }}>

      {/* Display */}
      <Card title="Display" titleIcon={<Monitor size={14} />} noPadding>
        <div>
          <SettingRow
            label="Compact Mode"
            desc="Reduce card padding for denser information layout"
            control={<Toggle checked={compactMode} onChange={setCompactMode} />}
          />
          <SettingRow
            label="Show Chart Legends"
            desc="Display colour legends on all metric charts"
            control={<Toggle checked={showChartLegend} onChange={setShowChartLegend} />}
          />
          <SettingRow
            label="Chart Animations"
            desc="Enable entry animations on Recharts line/bar charts (disable for performance)"
            control={<Toggle checked={chartAnimations} onChange={setChartAnimations} />}
          />
        </div>
      </Card>

      {/* Data refresh */}
      <Card title="Data Refresh" titleIcon={<RefreshCw size={14} />} noPadding>
        <div>
          <SettingRow
            label="Auto-Refresh Analytics"
            desc="Automatically reload Analytics page data in the background"
            control={<Toggle checked={autoRefresh} onChange={setAutoRefresh} />}
          />
          <SettingRow
            label="Health Check Interval"
            desc="Frequency of backend health polling (seconds)"
            control={
              <select
                className="form-select"
                value={refreshInterval}
                onChange={e => setRefreshInterval(e.target.value)}
                style={{ width: 90 }}
              >
                <option value="15">15 s</option>
                <option value="30">30 s</option>
                <option value="60">60 s</option>
              </select>
            }
          />
        </div>
      </Card>

      {/* Dashboard layout */}
      <Card title="Dashboard Preferences" titleIcon={<LayoutDashboard size={14} />} noPadding>
        <div>
          <SettingRow
            label="Default Controller"
            desc="Pre-selected controller when the Simulation page loads"
            control={
              <select className="form-select" style={{ width: 130 }}>
                <option value="dqn">DQN (AI)</option>
                <option value="adaptive">Adaptive</option>
                <option value="fixed">Fixed-Time</option>
              </select>
            }
          />
          <SettingRow
            label="Default Duration"
            desc="Default simulation step count (seconds)"
            control={
              <select className="form-select" style={{ width: 90 }}>
                <option value="300">300 s</option>
                <option value="500">500 s</option>
                <option value="600">600 s</option>
              </select>
            }
          />
        </div>
      </Card>

      {/* System info */}
      <Card title="System Information" titleIcon={<Info size={14} />} noPadding>
        <div>
          <SettingRow
            label="Application"
            control={<span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Smart Traffic Digital Twin v1.0</span>}
          />
          <SettingRow
            label="Backend API"
            control={
              <span style={{ fontSize: 12, color: 'var(--text-muted)', fontFamily: 'monospace' }}>
                {import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'}
              </span>
            }
          />
          <SettingRow
            label="WebSocket"
            control={
              <span style={{ fontSize: 12, color: 'var(--text-muted)', fontFamily: 'monospace' }}>
                {import.meta.env.VITE_WS_URL || 'ws://127.0.0.1:8000/ws/traffic'}
              </span>
            }
          />
          <SettingRow
            label="AI Controller"
            control={<StatusBadge variant="cyan">DQN (Deep Q-Network)</StatusBadge>}
          />
          <SettingRow
            label="Simulation Engine"
            control={<StatusBadge variant="blue">SUMO / TraCI</StatusBadge>}
          />
          <SettingRow
            label="Database"
            control={<StatusBadge variant="green">MongoDB</StatusBadge>}
          />
        </div>
      </Card>

      <div style={{ fontSize: 11, color: 'var(--text-muted)', textAlign: 'center', paddingBottom: 8 }}>
        Settings are UI-only preferences. Backend configuration is managed via environment variables.
      </div>
    </div>
  );
};

export default Settings;
