import React, { useState, useEffect, useCallback } from 'react';
import { ListTree } from 'lucide-react';
import Card from '../common/Card';
import wsService from '../../services/websocket';

const MAX_EVENTS = 8;

/* Map WebSocket event types → dot class + readable prefix */
const eventMeta = (type, data) => {
  const ai = data?.data?.ai;

  if (type === 'traffic_update' && ai?.action) {
    return {
      dot:  'event-dot-ai',
      text: `DQN action: ${ai.action}`,
      qvals: Array.isArray(ai.q_values)
        ? `Q-values: [${ai.q_values.map(v => v.toFixed ? v.toFixed(2) : v).join(', ')}]`
        : null,
    };
  }
  if (type === 'traffic_update') {
    const sig = data?.data?.signal;
    if (sig?.phase_name) {
      return { dot: 'event-dot-signal', text: `Signal → ${sig.phase_name}` };
    }
    return { dot: 'event-dot-traffic', text: 'Traffic state updated' };
  }
  if (type === 'status_update') {
    const s = data?.data;
    if (s?.running) return { dot: 'event-dot-sim', text: `Simulation running (${s.controller || ''})` };
    if (s?.status)  return { dot: 'event-dot-sim', text: `Simulation ${s.status}` };
    return { dot: 'event-dot-info', text: 'Status update' };
  }
  if (type === 'simulation_started')   return { dot: 'event-dot-sim',    text: 'Simulation started'   };
  if (type === 'simulation_completed') return { dot: 'event-dot-sim',    text: 'Simulation completed' };
  if (type === 'simulation_stopped')   return { dot: 'event-dot-amber',  text: 'Simulation stopped'   };
  if (type === 'simulation_error')     return { dot: 'event-dot-red',    text: 'Simulation error'     };
  if (type === 'connected')            return { dot: 'event-dot-signal', text: 'WebSocket connected'  };
  if (type === 'disconnected')         return { dot: 'event-dot-red',    text: 'WebSocket disconnected' };
  return { dot: 'event-dot-info', text: type };
};

const TRACKED = [
  'traffic_update', 'status_update',
  'simulation_started', 'simulation_completed', 'simulation_stopped', 'simulation_error',
  'connected', 'disconnected',
];

/* De-duplicate traffic_update events that carry the same signal phase */
const shouldAdd = (events, meta) => {
  if (events.length === 0) return true;
  const last = events[0];
  // Skip duplicate traffic updates with identical text
  if (last.text === meta.text && !meta.qvals) return false;
  return true;
};

const RecentEvents = () => {
  const [events, setEvents] = useState([]);

  const push = useCallback((type, data) => {
    const meta = eventMeta(type, data);
    const entry = {
      id:   Date.now() + Math.random(),
      time: new Date().toLocaleTimeString(undefined, { hour12: false }),
      ...meta,
    };
    setEvents(prev => {
      if (!shouldAdd(prev, meta)) return prev;
      return [entry, ...prev].slice(0, MAX_EVENTS);
    });
  }, []);

  useEffect(() => {
    const handlers = {};
    TRACKED.forEach(type => {
      handlers[type] = (data) => push(type, data);
      wsService.on(type, handlers[type]);
    });
    return () => {
      TRACKED.forEach(type => wsService.off(type, handlers[type]));
    };
  }, [push]);

  return (
    <Card title="Recent Events" titleIcon={<ListTree size={14} />} noPadding>
      <div className="events-body">
        {events.length === 0 ? (
          <div style={{ padding: '16px 14px', fontSize: 12, color: 'var(--text-muted)', textAlign: 'center' }}>
            Waiting for events…
          </div>
        ) : (
          events.map(ev => (
            <div key={ev.id} className="event-row">
              <span className={`event-dot ${ev.dot}`} />
              <div className="event-text" style={{ flex: 1 }}>
                <strong>{ev.text}</strong>
                {ev.qvals && <div className="qval-row">{ev.qvals}</div>}
              </div>
              <span className="event-time">{ev.time}</span>
            </div>
          ))
        )}
      </div>
    </Card>
  );
};

export default RecentEvents;
