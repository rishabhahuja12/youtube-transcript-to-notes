import React from 'react';
import { LayoutDashboard, Settings, FileText, PlaySquare, Zap } from 'lucide-react';
import { useAppContext } from '../context/AppContext';

const Sidebar = () => {
  const { activeTab, setActiveTab, ollamaStatus } = useAppContext();

  const navItems = [
    { id: 'process', label: 'Process Video', icon: PlaySquare },
    { id: 'library', label: 'My Notes', icon: FileText },
    { id: 'settings', label: 'Settings', icon: Settings },
    { id: 'about', label: 'About', icon: LayoutDashboard },
  ];

  return (
    <aside className="sidebar glass-panel">
      <div className="sidebar-header">
        <div className="brand">
          <Zap size={24} color="hsl(var(--accent-primary))" />
          <span>StudySuite AI</span>
        </div>
      </div>
      
      <nav className="sidebar-nav">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <div 
              key={item.id}
              className={`nav-item ${activeTab === item.id ? 'active' : ''}`}
              onClick={() => setActiveTab(item.id)}
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
