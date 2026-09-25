import { useState, useEffect, useCallback, useRef } from 'react';
import wsService from '../services/websocket';
import { getSimulationStatus } from '../services/api';

const WS_URL = import.meta.env.VITE_WS_URL || 'ws://127.0.0.1:8000/ws/traffic';

// How often to poll /simulation/status while stopping (ms)
const STOP_POLL_INTERVAL = 1500;

export const useTrafficWebSocket = () => {
  const [isConnected,      setIsConnected]      = useState(false);
  const [simulationStatus, setSimulationStatus] = useState(null);
  const [trafficData,      setTrafficData]      = useState(null);
  const [lastUpdate,       setLastUpdate]       = useState(null);

  // Track whether we are in a "stopping" state so we can poll for confirmation
  const stopPollRef  = useRef(null);
  const listenersRef = useRef(new Map());

  // ── helper: cancel the stop-confirmation poll ───────────────
  const cancelStopPoll = useCallback(() => {
    if (stopPollRef.current) {
      clearInterval(stopPollRef.current);
      stopPollRef.current = null;
    }
  }, []);

  // ── helper: start polling /simulation/status until not running ──
  const startStopPoll = useCallback(() => {
    cancelStopPoll();
    stopPollRef.current = setInterval(async () => {
      try {
        const s = await getSimulationStatus();
        if (s && !s.running) {
          // Simulation has actually stopped — update state and stop polling
          setSimulationStatus(s);
          cancelStopPoll();
        }
      } catch {
        // Ignore transient errors; keep polling
      }
    }, STOP_POLL_INTERVAL);
  }, [cancelStopPoll]);

  useEffect(() => {
    wsService.connect(WS_URL);

    const handleConnected = () => {
      setIsConnected(true);
    };

    const handleDisconnected = () => {
      setIsConnected(false);
    };

    // Primary source of truth for simulationStatus
    const handleStatusUpdate = (data) => {
      if (data && data.data) {
        setSimulationStatus(data.data);
        // If the status update confirms not running, cancel any stop poll
        if (!data.data.running) {
          cancelStopPoll();
        }
      }
    };

    const handleTrafficUpdate = (data) => {
      if (data && data.data) {
        setTrafficData(data.data);
        setLastUpdate(new Date());
      }
    };

    // ── FIX: handle terminal events by immediately updating simulationStatus
    // rather than only logging. The backend now also sends a status_update after
    // these events, but handling them here provides instant UI feedback even if
    // the status_update is slightly delayed or the WS reconnects.

    const handleSimulationStarted = (data) => {
      console.log('Simulation started:', data);
      // Optimistically mark as running so buttons update instantly
      setSimulationStatus(prev => ({
        ...(prev || {}),
        running: true,
        status: 'running',
        ...(data?.data || {}),
      }));
    };

    const handleSimulationCompleted = (data) => {
      console.log('Simulation completed:', data);
      cancelStopPoll();
      setSimulationStatus(prev => ({
        ...(prev || {}),
        running: false,
        status: 'completed',
        ...(data?.data || {}),
      }));
    };

    const handleSimulationStopped = (data) => {
      console.log('Simulation stopped:', data);
      cancelStopPoll();
      setSimulationStatus(prev => ({
        ...(prev || {}),
        running: false,
        status: 'stopped',
        ...(data?.data || {}),
      }));
    };

    const handleSimulationError = (data) => {
      console.error('Simulation error:', data);
      cancelStopPoll();
      setSimulationStatus(prev => ({
        ...(prev || {}),
        running: false,
        status: 'error',
        ...(data?.data || {}),
      }));
    };

    wsService.on('connected',             handleConnected);
    wsService.on('disconnected',          handleDisconnected);
    wsService.on('status_update',         handleStatusUpdate);
    wsService.on('traffic_update',        handleTrafficUpdate);
    wsService.on('simulation_started',    handleSimulationStarted);
    wsService.on('simulation_completed',  handleSimulationCompleted);
    wsService.on('simulation_stopped',    handleSimulationStopped);
    wsService.on('simulation_error',      handleSimulationError);

    return () => {
      wsService.off('connected',            handleConnected);
      wsService.off('disconnected',         handleDisconnected);
      wsService.off('status_update',        handleStatusUpdate);
      wsService.off('traffic_update',       handleTrafficUpdate);
      wsService.off('simulation_started',   handleSimulationStarted);
      wsService.off('simulation_completed', handleSimulationCompleted);
      wsService.off('simulation_stopped',   handleSimulationStopped);
      wsService.off('simulation_error',     handleSimulationError);
      cancelStopPoll();
    };
  }, [cancelStopPoll]);

  // Expose startStopPoll so SimulationControl can trigger it after POSTing /stop
  const onEvent = useCallback((eventType, callback) => {
    listenersRef.current.set(eventType, callback);
    wsService.on(eventType, callback);
    return () => {
      wsService.off(eventType, callback);
      listenersRef.current.delete(eventType);
    };
  }, []);

  const sendPing = useCallback(() => {
    wsService.sendPing();
  }, []);

  return {
    isConnected,
    simulationStatus,
    trafficData,
    lastUpdate,
    onEvent,
    sendPing,
    startStopPoll,   // used by SimulationControl to activate polling fallback
    cancelStopPoll,  // used to cancel it
  };
};
