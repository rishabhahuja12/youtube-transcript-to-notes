import React, { useState, useRef, useEffect } from 'react';
import { Terminal, ChevronUp, ChevronDown, X } from 'lucide-react';
import { useAppContext } from '../context/AppContext';

const FooterDock = () => {
  const { pipelineProgress, pipelineStatus, pipelineLogs } = useAppContext();
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const logsEndRef = useRef(null);

  useEffect(() => {
    if (isDrawerOpen && logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [pipelineLogs, isDrawerOpen]);

  const percent = pipelineProgress.total > 0 
    ? Math.round((pipelineProgress.current / pipelineProgress.total) * 100) 
    : 0;

  return (
    <div className="footer-dock glass-panel">
      <div className={`log-drawer ${isDrawerOpen ? 'open' : ''}`}>
        <div className="log-header">
          <span>System Logs</span>
          <button 
            className="log-drawer-toggle log-drawer-close" 
            onClick={() => setIsDrawerOpen(false)}
            aria-label="Close logs"
          >
            <X size={16} />
          </button>
        </div>
        <div className="log-content">
          {pipelineLogs.length === 0 ? (
            <div className="log-entry info">System ready. Waiting for tasks...</div>
          ) : (
            pipelineLogs.map((log) => (
              <div key={log.id} className={`log-entry ${log.type}`}>
                <span className="log-time">[{log.time}]</span>
                {log.message}
              </div>
            ))
          )}
          <div ref={logsEndRef} />
        </div>
      </div>

      <div className="footer-content">
        <div className="progress-section">
          <div className="step-label">
            <span>{pipelineStatus}</span>
            <span>{percent}%</span>
          </div>
          <div className="progress-bar-bg">
            <div 
              className={`progress-bar-fill w-${percent}`}
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
