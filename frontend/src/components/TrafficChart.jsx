import React from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';

const TrafficChart = ({ data, dataKey, name, color, unit = '' }) => {
  if (!data || data.length === 0) {
    return (
      <div className="card traffic-chart">
        <h3 className="traffic-chart-title">{name}</h3>
        <div className="traffic-chart-empty">No data available</div>
      </div>
    );
  }

  const chartData = data.map((item) => ({
    time: typeof item.simulation_time === 'number' ? item.simulation_time.toFixed(0) : String(item.simulation_time ?? ''),
    value: item[dataKey],
  }));

  return (
    <div className="card traffic-chart">
      <h3 className="traffic-chart-title">{name}</h3>
      <div className="traffic-chart-container">
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
            <XAxis 
              dataKey="time" 
              stroke="#94a3b8"
              label={{ value: 'Time (s)', position: 'insideBottom', offset: -5 }}
            />
            <YAxis 
              stroke="#94a3b8"
              label={{ value: unit, angle: -90, position: 'insideLeft' }}
            />
            <Tooltip 
              contentStyle={{ 
                backgroundColor: '#1e293b', 
                border: '1px solid #475569',
                borderRadius: '8px'
              }}
              itemStyle={{ color: '#f8fafc' }}
            />
            <Legend />
            <Line 
              type="monotone" 
              dataKey="value" 
              stroke={color} 
              strokeWidth={2}
              dot={false}
              name={name}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default TrafficChart;
