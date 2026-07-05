import React, { useState } from 'react';
import { Terminal, ChevronUp, ChevronDown, X } from 'lucide-react';
import { useAppContext } from '../context/AppContext';

const FooterDock = () => {
  const { progress, currentStep, logs } = useAppContext();
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  return (
    <div className="footer-dock glass-panel">
      <div className={`log-drawer ${isDrawerOpen ? 'open' : ''}`}>
        <div className="log-header">
          <span>System Logs</span>
          <button 
            className="log-drawer-toggle" 
            style={{ border: 'none', padding: '0.25rem' }}
            onClick={() => setIsDrawerOpen(false)}
          >
            <X size={16} />
          </button>
        </div>
        <div className="log-content">
          {logs.length === 0 ? (
            <div className="log-entry info">System ready. Waiting for tasks...</div>
          ) : (
            logs.map((log) => (
              <div key={log.id} className={`log-entry ${log.type}`}>
                <span style={{ opacity: 0.5, marginRight: '8px' }}>[{log.time}]</span>
                {log.message}
              </div>
            ))
          )}
        </div>
      </div>

      <div className="footer-content">
        <div className="progress-section">
          <div className="step-label">
            <span>{currentStep}</span>
            <span>{progress}%</span>
          </div>
          <div className="progress-bar-bg">
            <div 
              className="progress-bar-fill" 
              style={{ width: `${progress}%` }}
            ></div>
          </div>
        </div>

        <button 
          className="log-drawer-toggle"
          onClick={() => setIsDrawerOpen(!isDrawerOpen)}
        >
          <Terminal size={16} />
          <span>Logs</span>
          {isDrawerOpen ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
        </button>
      </div>
    </div>
  );
};

export default FooterDock;
