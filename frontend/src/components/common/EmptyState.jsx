import React from 'react';
import { Inbox } from 'lucide-react';

const EmptyState = ({ icon: Icon = Inbox, text = 'No data available', sub = '' }) => (
  <div className="empty-state">
    <div className="empty-state-icon">
      <Icon size={32} />
    </div>
    <div className="empty-state-text">{text}</div>
    {sub && <div className="empty-state-sub">{sub}</div>}
  </div>
);

export default EmptyState;
