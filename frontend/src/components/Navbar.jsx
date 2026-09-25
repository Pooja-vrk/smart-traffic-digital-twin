import React from 'react';

const Navbar = ({ currentPage, onPageChange }) => {
  const navItems = [
    { id: 'dashboard', label: 'Dashboard' },
    { id: 'simulation', label: 'Simulation' },
    { id: 'analytics', label: 'Analytics' },
  ];

  return (
    <nav className="navbar">
      <div className="navbar-container">
        <div className="navbar-brand">
          <h1 className="navbar-title">Smart Traffic Digital Twin</h1>
          <p className="navbar-subtitle">AI-Driven Traffic Flow Management</p>
        </div>
        <div className="navbar-nav">
          {navItems.map((item) => (
            <button
              key={item.id}
              className={`navbar-link ${currentPage === item.id ? 'active' : ''}`}
              onClick={() => onPageChange(item.id)}
              aria-label={`Navigate to ${item.label}`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>
    </nav>
  );
};

export default Navbar;
