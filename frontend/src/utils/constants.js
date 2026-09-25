export const CONTROLLERS = [
  { id: 'fixed', name: 'Fixed-Time', type: 'baseline' },
  { id: 'adaptive', name: 'Adaptive', type: 'adaptive' },
  { id: 'dqn', name: 'DQN (AI)', type: 'reinforcement_learning' },
];

export const CONGESTION_LEVELS = [
  { id: 'FREE_FLOW', label: 'Free Flow', color: '#22c55e' },
  { id: 'LOW', label: 'Low', color: '#84cc16' },
  { id: 'MODERATE', label: 'Moderate', color: '#eab308' },
  { id: 'HIGH', label: 'High', color: '#f97316' },
  { id: 'SEVERE', label: 'Severe', color: '#ef4444' },
];

export const SIGNAL_PHASES = [
  { id: 0, name: 'NS_GREEN', label: 'North-South Green', state: 'green' },
  { id: 1, name: 'NS_YELLOW', label: 'North-South Yellow', state: 'yellow' },
  { id: 2, name: 'EW_GREEN', label: 'East-West Green', state: 'green' },
  { id: 3, name: 'EW_YELLOW', label: 'East-West Yellow', state: 'yellow' },
];

export const SIMULATION_DEFAULTS = {
  steps: 300,
  seed: 42,
  gui: false,
};

export const POLLING_INTERVALS = {
  HEALTH: 30000,
  SIMULATION_STATUS: 1000,
  TRAFFIC: 1000,
  ANALYTICS: 60000,
};

export const CHART_COLORS = {
  primary: '#2563eb',
  secondary: '#10b981',
  tertiary: '#f59e0b',
  quaternary: '#ef4444',
  purple: '#8b5cf6',
  pink: '#ec4899',
};
