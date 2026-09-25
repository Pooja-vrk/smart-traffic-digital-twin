export const formatDecimal = (value, decimals = 1, fallback = '--') => {
  if (value === null || value === undefined || typeof value !== 'number' || isNaN(value)) {
    return fallback;
  }
  return value.toFixed(decimals);
};

export const formatSpeed = (mps, fallback = '--') => {
  if (mps === null || mps === undefined || typeof mps !== 'number' || isNaN(mps)) return fallback;
  return `${mps.toFixed(2)} m/s`;
};

export const formatSeconds = (seconds, decimals = 1, fallback = '--') => {
  if (seconds === null || seconds === undefined || typeof seconds !== 'number' || isNaN(seconds)) return fallback;
  return `${seconds.toFixed(decimals)}s`;
};

export const formatTime = (seconds, fallback = '--') => {
  if (seconds === null || seconds === undefined || typeof seconds !== 'number' || isNaN(seconds)) return fallback;
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}m ${secs}s`;
};

export const formatPercentage = (value, decimals = 1, fallback = '--') => {
  if (value === null || value === undefined || typeof value !== 'number' || isNaN(value)) return fallback;
  return `${value.toFixed(decimals)}%`;
};

export const formatNumber = (value, fallback = '--') => {
  if (value === null || value === undefined || typeof value !== 'number' || isNaN(value)) return fallback;
  return value.toLocaleString();
};

export const getCongestionColor = (level) => {
  const colors = {
    'FREE_FLOW': '#22c55e',
    'LOW': '#84cc16',
    'MODERATE': '#eab308',
    'HIGH': '#f97316',
    'SEVERE': '#ef4444',
    'UNKNOWN': '#6b7280',
  };
  return colors[level] || colors['UNKNOWN'];
};

export const getCongestionLabel = (level) => {
  const labels = {
    'FREE_FLOW': 'Free Flow',
    'LOW': 'Low',
    'MODERATE': 'Moderate',
    'HIGH': 'High',
    'SEVERE': 'Severe',
    'UNKNOWN': 'Unknown',
  };
  return labels[level] || labels['UNKNOWN'];
};

export const getSignalColor = (state) => {
  const colors = {
    'green': '#22c55e',
    'yellow': '#eab308',
    'red': '#ef4444',
  };
  return colors[state] || '#6b7280';
};

export const getControllerLabel = (controller) => {
  const labels = {
    'fixed': 'Fixed-Time',
    'adaptive': 'Adaptive',
    'dqn': 'DQN (AI)',
  };
  return labels[controller] || controller;
};

export const getStatusColor = (status) => {
  const colors = {
    'idle': '#6b7280',
    'starting': '#3b82f6',
    'running': '#22c55e',
    'stopping': '#f59e0b',
    'completed': '#10b981',
    'stopped': '#6b7280',
    'error': '#ef4444',
  };
  return colors[status] || '#6b7280';
};

export const calculateCongestionScore = (queues, waiting, speed) => {
  if (!queues || !waiting || !speed) return null;

  const totalQueue = typeof queues.total === 'number' ? queues.total : null;
  const avgWaiting = typeof waiting.average_seconds === 'number' ? waiting.average_seconds : null;
  const avgSpeed = typeof speed.average_mps === 'number' ? speed.average_mps : null;

  if (totalQueue === null || avgWaiting === null || avgSpeed === null) return null;

  const queueScore = Math.min((totalQueue / 20) * 60, 60);
  const waitingScore = Math.min((avgWaiting / 30) * 15, 15);
  const speedScore = Math.min((1 / (avgSpeed + 0.1)) * 5, 5);

  return Math.min(queueScore + waitingScore + speedScore, 100);
};

export const classifyCongestion = (score) => {
  if (score === null || score === undefined || typeof score !== 'number' || isNaN(score)) return 'UNKNOWN';
  if (score <= 20) return 'FREE_FLOW';
  if (score <= 40) return 'LOW';
  if (score <= 60) return 'MODERATE';
  if (score <= 80) return 'HIGH';
  return 'SEVERE';
};
