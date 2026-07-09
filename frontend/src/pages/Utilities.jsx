import React, { useState } from 'react';
import { Wrench, FileText, Download, Play, CheckCircle } from 'lucide-react';
import { API_BASE_URL, installPlaywright } from '../utils/api';
import './Utilities.css';

const Utilities = () => {
  const [pdfPath, setPdfPath] = useState('');
  const [theme, setTheme] = useState('Textbook');
  const [status, setStatus] = useState(null); // { type: 'success' | 'error', message: '' }
  const [isExporting, setIsExporting] = useState(false);

  const handleExport = async () => {
    if (!pdfPath) {
      setStatus({ type: 'error', message: 'Please enter a valid file path.' });
      return;
    }
    
    setIsExporting(true);
    setStatus(null);
    try {
      const response = await fetch(`${API_BASE_URL}/api/pdf/export_external`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_path: pdfPath, theme }),
      });
      
      if (!response.ok) throw new Error(`Export failed: ${response.statusText}`);
      const data = await response.json();
      
      setStatus({ type: 'success', message: `PDF successfully exported to: ${data.path}` });
    } catch (err) {
      console.error(err);
      setStatus({ type: 'error', message: err.message || 'Failed to export PDF.' });
    } finally {
      setIsExporting(false);
    }
  };

  const [isInstalling, setIsInstalling] = useState(false);

  const handleInstallPlaywright = async () => {
    setIsInstalling(true);
    setStatus(null);
    try {
      await installPlaywright();
      setStatus({ type: 'success', message: 'Playwright installed successfully. System Health should now reflect it.' });
    } catch (err) {
      console.error(err);
      setStatus({ type: 'error', message: err.message || 'Failed to install Playwright.' });
    } finally {
      setIsInstalling(false);
    }
  };

  return (
    <div className="utilities-container">
      <div className="page-title">
        <Wrench size={32} />
        <h1>Utilities</h1>
      </div>

      {status && (
        <div className={`status-alert ${status.type}`}>
          {status.type === 'success' ? <CheckCircle size={20} /> : null}
          <p>{status.message}</p>
        </div>
      )}

      {/* External MD to PDF Tool */}
      <section className="utility-card">
        <div className="utility-header">
          <h2>
            <FileText size={24} />
            Convert External .md to PDF
          </h2>
          <p>Convert any Markdown file on your system to a beautifully formatted PDF.</p>
        </div>
        
        <div className="utility-body">
          <div>
            <label className="form-label">Absolute File Path (.md)</label>
            <input 
              type="text" 
              className="form-input"
              placeholder="C:\Users\Username\Documents\notes.md"
              value={pdfPath}
              onChange={(e) => setPdfPath(e.target.value)}
            />
          </div>
          
          <div>
            <label className="form-label">Select Theme</label>
            <div className="theme-grid">
              {['Textbook', 'ChatGPT Dark', 'Minimal Mono'].map(t => (
                <button
                  key={t}
                  onClick={() => setTheme(t)}
                  className={`theme-btn ${theme === t ? 'active' : ''}`}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>
          
          <div style={{ display: 'flex', justifyContent: 'flex-end', paddingTop: '8px' }}>
            <button 
              onClick={handleExport}
              disabled={isExporting || !pdfPath}
              className="primary-button"
            >
              {isExporting ? (
                <>
                  <div className="spinner"></div>
                  Converting...
                </>
              ) : (
                <>
                  <Download size={20} />
                  Export PDF
                </>
              )}
            </button>
          </div>
        </div>
      </section>

      {/* Playwright Auto-Installer */}
      <section className="utility-card">
        <div className="utility-header">
          <h2>
            <Download size={24} />
            Playwright Installer
          </h2>
          <p>
            Playwright is required for PDF exports. If it's not installed or missing browser binaries, use this tool to install them automatically.
          </p>
        </div>
        <div className="utility-body">
          <button 
            className="install-btn"
            onClick={handleInstallPlaywright}
            disabled={isInstalling}
          >
            {isInstalling ? (
              <>
                <div className="spinner"></div>
                Installing (This takes a few minutes)...
              </>
            ) : (
              <>
                <Play size={18} />
                Run Playwright Install
              </>
            )}
          </button>
        </div>
      </section>
    </div>
  );
};

export default Utilities;
