import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
});

// Health
export const getHealth = async () => {
  const response = await api.get('/api/health');
  return response.data;
};

// Controllers
export const getControllers = async () => {
  const response = await api.get('/api/controllers');
  return response.data;
};

// Simulation
export const startSimulation = async (data) => {
  const response = await api.post('/api/simulation/start', data);
  return response.data;
};

export const stopSimulation = async () => {
  const response = await api.post('/api/simulation/stop');
  return response.data;
};

export const getSimulationStatus = async () => {
  const response = await api.get('/api/simulation/status');
  return response.data;
};

export const getSimulationResult = async () => {
  const response = await api.get('/api/simulation/result');
  return response.data;
};

export const triggerEmergencyVehicle = async (data, simulationId = null) => {
  const url = simulationId ? `/api/simulation/${simulationId}/emergency` : '/api/simulation/emergency';
  const response = await api.post(url, data);
  return response.data;
};

export const getEmergencyStatus = async () => {
  const response = await api.get('/api/simulation/emergency/status');
  return response.data;
};

export const getCoordinationStatus = async () => {
  const response = await api.get('/api/simulation/coordination');
  return response.data;
};

export const setCoordinationMode = async (mode) => {
  const response = await api.post('/api/simulation/coordination/mode', { mode });
  return response.data;
};

export const getSimulationHistory = async (params = {}) => {
  const response = await api.get('/api/simulation/history', { params });
  return response.data;
};

export const getSimulationDetail = async (simulationId) => {
  const response = await api.get(`/api/simulation/${simulationId}`);
  return response.data;
};

export const getSimulationSnapshots = async (simulationId, params = {}) => {
  const response = await api.get(`/api/simulation/${simulationId}/snapshots`, { params });
  return response.data;
};

export const getSimulationDecisions = async (simulationId, params = {}) => {
  const response = await api.get(`/api/simulation/${simulationId}/decisions`, { params });
  return response.data;
};

export const getSingleDecision = async (simulationId, decisionId) => {
  const response = await api.get(`/api/simulation/${simulationId}/decisions/${decisionId}`);
  return response.data;
};

export const getSimulationReplay = async (simulationId, params = {}) => {
  const response = await api.get(`/api/simulation/${simulationId}/replay`, { params });
  return response.data;
};


// Traffic
export const getCurrentTraffic = async () => {
  const response = await api.get('/api/traffic/current');
  return response.data;
};

// Analytics
export const getAnalyticsSummary = async () => {
  const response = await api.get('/api/analytics/summary');
  return response.data;
};

export const getControllerComparison = async () => {
  const response = await api.get('/api/analytics/controller-comparison');
  return response.data;
};

export const getCongestionDistribution = async (params = {}) => {
  const response = await api.get('/api/analytics/congestion-distribution', { params });
  return response.data;
};

export const getTrafficTrends = async (params = {}) => {
  const response = await api.get('/api/analytics/traffic-trends', { params });
  return response.data;
};

export const getControllerPerformance = async () => {
  const response = await api.get('/api/analytics/controller-performance');
  return response.data;
};

// Prediction
export const getPredictionStatus = async () => {
  const response = await api.get('/api/prediction/status');
  return response.data;
};

export const trainPredictionModel = async (data = {}) => {
  const response = await api.post('/api/prediction/train', data);
  return response.data;
};

export const getCurrentPrediction = async () => {
  const response = await api.get('/api/prediction/current');
  return response.data;
};

export const predictCongestion = async (data) => {
  const response = await api.post('/api/prediction/predict', data);
  return response.data;
};

export const getPredictionHistory = async (params = {}) => {
  const response = await api.get('/api/prediction/history', { params });
  return response.data;
};

// Scenario Lab
export const getScenarioPresets = async () => {
  const response = await api.get('/api/scenarios/presets');
  return response.data;
};

export const runScenario = async (data) => {
  const response = await api.post('/api/scenarios/run', data);
  return response.data;
};

export const stopScenario = async () => {
  const response = await api.post('/api/scenarios/stop');
  return response.data;
};

export const getScenarioStatus = async (scenarioId) => {
  const endpoint = scenarioId ? `/api/scenarios/status/${scenarioId}` : '/api/scenarios/status';
  const response = await api.get(endpoint);
  return response.data;
};

export const getLatestScenarioResult = async () => {
  const response = await api.get('/api/scenarios/result/latest');
  return response.data;
};

export const getScenarioResult = async (scenarioId) => {
  const response = await api.get(`/api/scenarios/${scenarioId}/result`);
  return response.data;
};

export const getScenarioHistory = async (params = {}) => {
  const response = await api.get('/api/scenarios/history', { params });
  return response.data;
};

export default api;
