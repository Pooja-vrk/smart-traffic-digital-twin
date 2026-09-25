import React from 'react';
import { Server, Wifi, Database } from 'lucide-react';
import Card from '../common/Card';
import StatusBadge from '../common/StatusBadge';

const Row = ({ icon: Icon, label, ok, unknown }) => {
  let variant = 'gray';
  let text    = 'Unknown';

  if (unknown) {
    variant = 'gray';
    text    = 'Unknown';
  } else if (ok) {
    variant = 'green';
    text    = label === 'WebSocket' ? 'Connected' : 'Online';
  } else {
    variant = 'red';
    text    = label === 'WebSocket' ? 'Disconnected' : 'Offline';
  }

  return (
    <div className="sys-status-row">
      <span className="sys-status-label">
        <Icon size={13} style={{ opacity: 0.7 }} />
        {label}
      </span>
      <StatusBadge variant={variant}>{text}</StatusBadge>
    </div>
  );
};

/**
 * Props:
 *   backend  – bool | null
 *   websocket – bool
 *   mongodb  – bool | undefined   (undefined → hidden)
 */
const SystemStatus = ({ backend, websocket, mongodb }) => (
  <Card title="System Status" titleIcon={<Server size={14} />} noPadding>
    <div className="sys-status-body">
      <Row icon={Server}   label="Backend"   ok={backend}   unknown={backend === null} />
      <Row icon={Wifi}     label="WebSocket" ok={websocket} />
      {mongodb !== undefined && (
        <Row icon={Database} label="MongoDB" ok={mongodb} />
      )}
    </div>
  </Card>
);

export default SystemStatus;
