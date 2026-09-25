import React, { useState, useEffect } from 'react';
import Sidebar from './components/layout/Sidebar';
import TopHeader from './components/layout/TopHeader';
import Dashboard from './pages/Dashboard';
import Simulation from './pages/Simulation';
import Analytics from './pages/Analytics';
import Reports from './pages/Reports';
import Settings from './pages/Settings';
import { getHealth } from './services/api';

function App() {
  const [currentPage, setCurrentPage] = useState('dashboard');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [backendOnline, setBackendOnline] = useState(null); // null = checking

  // Poll backend health for the top-header status indicator
  useEffect(() => {
    const check = async () => {
      try {
        const data = await getHealth();
        setBackendOnline(data?.status !== 'error');
      } catch {
        setBackendOnline(false);
      }
    };
    check();
    const id = setInterval(check, 30_000);
    return () => clearInterval(id);
  }, []);

  const renderPage = () => {
    switch (currentPage) {
      case 'dashboard':  return <Dashboard  onNavigate={setCurrentPage} />;
      case 'simulation': return <Simulation />;
      case 'analytics':  return <Analytics  onNavigate={setCurrentPage} />;
      case 'reports':    return <Reports />;
      case 'settings':   return <Settings />;
      default:           return <Dashboard  onNavigate={setCurrentPage} />;
    }
  };

  return (
    <div className="app-shell">
      <Sidebar
        currentPage={currentPage}
        onPageChange={setCurrentPage}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />

      <div className="main-wrapper">
        <TopHeader
          currentPage={currentPage}
          isBackendOnline={backendOnline}
          onMenuToggle={() => setSidebarOpen(o => !o)}
        />
        <main className="page-content">
          {renderPage()}
        </main>
      </div>
    </div>
  );
}

export default App;
