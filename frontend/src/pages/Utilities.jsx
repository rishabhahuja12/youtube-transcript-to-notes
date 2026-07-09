import React, { useState } from 'react';
import { Wrench, FileText, Download, Play, CheckCircle } from 'lucide-react';
import { API_BASE_URL, installPlaywright } from '../utils/api';

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
      // NOTE: We're reusing the /api/pdf/export endpoint but modifying it to accept absolute paths, 
      // or we can add a new endpoint /api/pdf/export_external. Let's assume /api/pdf/export_external is available.
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
    <div className="utilities-page max-w-4xl mx-auto p-6 space-y-8">
      <div className="flex items-center space-x-3 mb-6 border-b border-[var(--panel)] pb-4">
        <Wrench className="w-8 h-8 text-[var(--ink)]" />
        <h1 className="text-3xl font-bold text-[var(--ink)]">Utilities</h1>
      </div>

      {status && (
        <div className={`p-4 rounded-lg border flex items-start gap-3 ${
          status.type === 'success' 
            ? 'bg-green-900/20 border-green-500/50 text-green-300' 
            : 'bg-red-900/20 border-red-500/50 text-red-300'
        }`}>
          {status.type === 'success' ? <CheckCircle className="w-5 h-5 mt-0.5" /> : null}
          <p>{status.message}</p>
        </div>
      )}

      {/* External MD to PDF Tool */}
      <section className="bg-[var(--surface)] border border-[var(--panel)] rounded-xl overflow-hidden">
        <div className="p-6 border-b border-[var(--panel)]">
          <h2 className="text-xl font-semibold text-[var(--ink)] flex items-center gap-2">
            <FileText className="w-5 h-5" />
            Convert External .md to PDF
          </h2>
          <p className="text-sm text-gray-400 mt-1">Convert any Markdown file on your system to a beautifully formatted PDF.</p>
        </div>
        
        <div className="p-6 space-y-5">
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-2">Absolute File Path (.md)</label>
            <input 
              type="text" 
              className="w-full bg-[var(--background)] border border-[var(--panel)] text-[var(--ink)] rounded-lg p-3 focus:border-[var(--accent)] outline-none font-mono"
              placeholder="C:\Users\Username\Documents\notes.md"
              value={pdfPath}
              onChange={(e) => setPdfPath(e.target.value)}
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-2">Select Theme</label>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              {['Textbook', 'ChatGPT Dark', 'Minimal Mono'].map(t => (
                <button
                  key={t}
                  onClick={() => setTheme(t)}
                  className={`p-3 rounded-lg border text-left transition-all ${
                    theme === t 
                      ? 'bg-[var(--accent)]/10 border-[var(--accent)] text-[var(--ink)]' 
                      : 'bg-[var(--background)] border-[var(--panel)] text-gray-400 hover:border-gray-500'
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>
          
          <div className="pt-2 flex justify-end">
            <button 
              onClick={handleExport}
              disabled={isExporting || !pdfPath}
              className="flex items-center gap-2 bg-[var(--accent)] text-white px-6 py-3 rounded-lg hover:bg-blue-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-medium"
            >
              {isExporting ? (
                <>
                  <div className="animate-spin rounded-full h-5 w-5 border-2 border-white/30 border-t-white"></div>
                  Converting...
                </>
              ) : (
                <>
                  <Download className="w-5 h-5" />
                  Export PDF
                </>
              )}
            </button>
          </div>
        </div>
      </section>

      {/* Playwright Auto-Installer */}
      <section className="bg-[var(--surface)] border border-[var(--panel)] rounded-xl overflow-hidden p-6">
        <h2 className="text-xl font-semibold text-[var(--ink)] flex items-center gap-2 mb-2">
          <Download className="w-5 h-5" />
          Playwright Installer
        </h2>
        <p className="text-sm text-gray-400 mb-4">
          Playwright is required for PDF exports. If it's not installed or missing browser binaries, use this tool to install them automatically.
        </p>
        <button 
          className="flex items-center gap-2 bg-[var(--panel)] text-[var(--ink)] px-4 py-2 rounded-lg hover:bg-gray-700 transition-colors disabled:opacity-50"
          onClick={handleInstallPlaywright}
          disabled={isInstalling}
        >
          {isInstalling ? (
            <>
              <div className="animate-spin rounded-full h-4 w-4 border-2 border-[var(--ink)]/30 border-t-[var(--ink)]"></div>
              Installing (This takes a few minutes)...
            </>
          ) : (
            <>
              <Play className="w-4 h-4" />
              Run Playwright Install
            </>
          )}
        </button>
      </section>
    </div>
  );
};

export default Utilities;
