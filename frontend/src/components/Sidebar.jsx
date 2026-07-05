import React from 'react';
import { LayoutDashboard, Settings, FileText, PlaySquare, Zap } from 'lucide-react';
import { useAppContext } from '../context/AppContext';

const Sidebar = () => {
  const { currentScreen, setCurrentScreen, ollamaStatus } = useAppContext();

  const navItems = [
    { id: 'library', label: 'Library', icon: FileText },
    { id: 'newPipeline', label: 'New Pipeline', icon: PlaySquare },
    { id: 'settings', label: 'Settings', icon: Settings },
    { id: 'utilities', label: 'Utilities', icon: LayoutDashboard },
  ];

  return (
    <aside className="sidebar glass-panel">
      <div className="sidebar-header">
        <div className="brand">
          <Zap size={24} color="var(--accent)" />
          <span>StudySuite AI</span>
        </div>
      </div>
      
      <nav className="sidebar-nav">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <div 
              key={item.id}
              className={`nav-item ${currentScreen === item.id ? 'active' : ''}`}
              onClick={() => setCurrentScreen(item.id)}
              onKeyDown={(e) => e.key === 'Enter' && setCurrentScreen(item.id)}
              role="button"
              tabIndex={0}
            >
              <Icon />
              <span>{item.label}</span>
            </div>
          );
        })}
      </nav>

      <div className="sidebar-footer">
        <div className="status-pill">
          <div className={`status-indicator ${ollamaStatus}`}></div>
          <span>Ollama: {ollamaStatus === 'online' ? 'Connected' : ollamaStatus === 'offline' ? 'Disconnected' : 'Checking...'}</span>
        </div>
      </div>
    </aside>
  );
};

export default Sidebar;
