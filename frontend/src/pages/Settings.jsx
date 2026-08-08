import React, { useState, useEffect } from 'react';
import { fetchOllamaStatus, fetchPoolSettings, addPoolKey, deletePoolKey, updateProviderLimits, fetchYouTubeStatus, connectYouTube, disconnectYouTube } from '../utils/api';
import { Settings as SettingsIcon, Server, Shield, Database, Key, Activity, Trash2, Plus, PlayCircle, Sliders, Check, X, RotateCcw, Zap, RefreshCw } from 'lucide-react';
import HealthCard from '../components/HealthCard';
import './Settings.css';

const PROVIDER_ENDPOINTS = {
  groq: 'https://api.groq.com/openai/v1',
  gemini: 'https://generativelanguage.googleapis.com/v1beta/openai/',
  openrouter: 'https://openrouter.ai/api/v1',
  ollama: 'http://localhost:11434/v1'
};

const RECOMMENDED_LIMITS = {
  groq: { rpm_limit: 30, tpm_limit: 12000 },
  gemini: { rpm_limit: 15, tpm_limit: 1000000 },
  openrouter: { rpm_limit: 18, tpm_limit: 50000 },
  ollama: { rpm_limit: 9999, tpm_limit: 999999 }
};

const Settings = () => {
  const [activeTab, setActiveTab] = useState('text');
  const [poolConfigs, setPoolConfigs] = useState([]);
  const [healthStatus, setHealthStatus] = useState({ ollama: false, playwright: false, keyring: false });
  const [youtubeConnected, setYoutubeConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [editingLimits, setEditingLimits] = useState(null);

  const [newKey, setNewKey] = useState({
    provider: 'groq',
    api_key: '',
    endpoint_url: PROVIDER_ENDPOINTS.groq,
    model_name: '',
    capability: 'text',
    ...RECOMMENDED_LIMITS.groq
  });

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => {
    let mounted = true;

    const refreshOllamaStatus = async () => {
      try {
        const data = await fetchOllamaStatus();
        if (mounted) {
          setHealthStatus(prev => ({ ...prev, ollama: data.ollama === true }));
        }
      } catch (err) {
        if (mounted) {
          setHealthStatus(prev => ({ ...prev, ollama: false }));
        }
      }
    };

    const interval = setInterval(refreshOllamaStatus, 15000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const [ytData, poolData] = await Promise.all([
        fetchYouTubeStatus().catch(err => { console.error(err); return { connected: false }; }),
        fetchPoolSettings()
      ]);

      setYoutubeConnected(ytData.connected);
      setPoolConfigs(poolData);
      setError(null);
      setLoading(false);
      fetchOllamaStatus().then(setHealthStatus).catch(err => console.error(err));
    } catch (err) {
      console.error(err);
      setError('Failed to load settings data.');
    } finally {
      setLoading(false);
    }
  };

  const [isConnectingYt, setIsConnectingYt] = useState(false);

  useEffect(() => {
    let pollTimer;
    if (isConnectingYt) {
      pollTimer = setInterval(async () => {
        try {
          const ytStatus = await fetchYouTubeStatus();
          if (ytStatus && ytStatus.connected) {
            setYoutubeConnected(true);
            setIsConnectingYt(false);
          }
        } catch (e) {}
      }, 2000);
    }
    return () => {
      if (pollTimer) clearInterval(pollTimer);
    };
  }, [isConnectingYt]);

  const handleConnectYoutube = async () => {
    try {
      setIsConnectingYt(true);
      setError(null);
      const res = await connectYouTube();
      // Backend tries to open browser via os.startfile, but as a safety net
      // the frontend also opens the auth URL if provided
      if (res && res.auth_url) {
        window.open(res.auth_url, '_blank');
      }
    } catch (err) {
      console.error(err);
      setError('Failed to start YouTube connection: ' + (err.message || 'Error triggering login'));
      setIsConnectingYt(false);
    }
  };

  const handleDisconnectYoutube = async () => {
    try {
      const res = await disconnectYouTube();
      setYoutubeConnected(res.connected);
    } catch (err) {
      console.error(err);
      setError('Failed to disconnect YouTube.');
    }
  };

  
  const handleProviderChange = (e) => {
    const provider = e.target.value;
    const endpoint_url = PROVIDER_ENDPOINTS[provider] || '';
    setNewKey({...newKey, provider, endpoint_url, ...RECOMMENDED_LIMITS[provider]});
  };

  const handleAddKey = async (e) => {
    e.preventDefault();
    if (newKey.endpoint_url) {
       if ((newKey.provider === 'groq' || newKey.provider === 'gemini') && !newKey.endpoint_url.startsWith('https://')) {
          setError('Endpoint for Groq/Gemini must start with https://');
          return;
       }
       if (newKey.provider === 'ollama' && !newKey.endpoint_url.startsWith('http://localhost')) {
          setError('Endpoint for Ollama must start with http://localhost');
          return;
       }
    }

    try {
      const res = await addPoolKey(newKey);
      if (res && res.success) {
        setNewKey({ provider: 'groq', api_key: '', endpoint_url: PROVIDER_ENDPOINTS.groq, model_name: '', capability: activeTab, ...RECOMMENDED_LIMITS.groq });
        await loadData();
      } else {
        setError(res?.error || 'Keyring storage failed. Could not save provider configuration.');
      }
    } catch (err) {
      console.error(err);
      setError(err.message || 'Keyring storage failed. Could not save provider configuration.');
    }
  };

  const handleRemoveKey = async (indexToRemove) => {
    try {
      await deletePoolKey(indexToRemove);
      await loadData();
    } catch (err) {
      console.error(err);
      setError('Failed to remove key.');
    }
  };

  const handleSaveLimits = async (index, limits) => {
    try {
      await updateProviderLimits(index, {
        rpm_limit: Number(limits.rpm_limit),
        tpm_limit: Number(limits.tpm_limit)
      });
      setEditingLimits(null);
      await loadData();
    } catch (err) {
      setError(err.message || 'Failed to update rate limits.');
    }
  };

  const filteredPool = poolConfigs.filter(cfg => cfg.capability === activeTab);

  if (loading) {
    return (
      <div className="settings-container settings-loading-container">
        <div className="settings-loading-text">Loading settings...</div>
      </div>
    );
  }

  return (
    <div className="settings-container">
      <div className="page-title">
        <SettingsIcon size={32} />
        <h1>Settings & Health</h1>
      </div>

      {error && (
        <div className="status-alert error">
          {error}
        </div>
      )}

      {/* Health Cards */}
      <section>
        <h2>
          <Activity size={24} className="header-icon" />
          System Health
        </h2>
        <div className="health-grid">
          <HealthCard 
            title="Ollama" 
            status={healthStatus.ollama} 
            icon={<Server size={24} />}
            desc="Local LLM Server"
          />
          <HealthCard 
            title="Playwright" 
            status={healthStatus.playwright} 
            icon={<Database size={24} />}
            desc="PDF Export Engine"
          />
          <HealthCard 
            title="Keyring" 
            status={healthStatus.keyring} 
            icon={<Shield size={24} />}
            desc="Secure Storage"
          />
        </div>
      </section>

      <section>
        <h2>
          <PlayCircle size={24} className="header-icon" />
          YouTube Connection
        </h2>
        <div className="health-card youtube-card-row">
          <div>
            <h3 className="health-card-title">
              YouTube API
              <span className={`status-indicator ${youtubeConnected ? 'online' : 'error'}`}></span>
            </h3>
            <p className="health-card-desc">
              Connect via Google OAuth for reliable metadata and chapters.
            </p>
            <p className={`health-status ${youtubeConnected ? 'success' : 'error'}`}>
              {youtubeConnected ? 'YouTube: connected' : 'Not connected'}
            </p>
          </div>
          <div>
            {youtubeConnected ? (
              <button onClick={handleDisconnectYoutube} className="secondary-button disconnect-button" disabled={isConnectingYt}>Disconnect</button>
            ) : (
              <button onClick={handleConnectYoutube} className="primary-button" disabled={isConnectingYt} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                {isConnectingYt ? (
                  <>
                    <RefreshCw size={16} className="loader-spin" /> Opening Google Login...
                  </>
                ) : (
                  'Connect your YouTube'
                )}
              </button>
            )}
          </div>
        </div>
        {isConnectingYt && (
          <div className="status-alert info" style={{ marginTop: '12px', fontSize: '0.85rem', lineHeight: '1.5' }}>
            💡 <strong>Google OAuth Login Opened:</strong>
            <ol style={{ margin: '6px 0 0 18px', padding: 0 }}>
              <li>Sign in to your Google Account in the opened browser tab.</li>
              <li>If Google displays <em>"Google hasn't verified this app"</em>, click <strong>Advanced</strong> ➔ <strong>Go to YT Transcriptor (unsafe)</strong> ➔ <strong>Allow</strong>.</li>
              <li>Once allowed, YouTube status will automatically update to <strong>Connected</strong>!</li>
            </ol>
          </div>
        )}
      </section>

      {/* API Keys */}
      <section className="pool-section">
        <div className="tab-group">
          <button
            onClick={() => { setActiveTab('text'); setNewKey(prev => ({...prev, capability: 'text'})) }}
            className={`tab-btn ${activeTab === 'text' ? 'active' : ''}`}
          >
            Text Models
          </button>
          <button
            onClick={() => { setActiveTab('vision'); setNewKey(prev => ({...prev, capability: 'vision'})) }}
            className={`tab-btn ${activeTab === 'vision' ? 'active' : ''}`}
          >
            Vision Models
          </button>
        </div>

        <div className="pool-content">
          <h3 className="section-subheading">
            {activeTab === 'text' ? 'Text Generation Providers' : 'Vision/Multimodal Providers'}
          </h3>
          
          <div className="key-list">
            {loading && poolConfigs.length === 0 ? (
              <p className="muted-text">Loading providers...</p>
            ) : filteredPool.length === 0 ? (
              <p className="muted-text-italic">No {activeTab} providers configured.</p>
            ) : (
              filteredPool.map((cfg) => {
                const realIndex = poolConfigs.indexOf(cfg);
                const isEditing = editingLimits?.index === realIndex;
                const recommended = RECOMMENDED_LIMITS[cfg.provider] || { rpm_limit: 30, tpm_limit: 12000 };

                return (
                  <div key={realIndex} className={`key-item ${isEditing ? 'is-editing' : ''}`}>
                    {!isEditing ? (
                      <div className="key-item-normal">
                        <div className="key-main">
                          <div className="provider-badge-icon">
                            <Key size={18} />
                          </div>
                          <div className="key-details">
                            <div className="key-header-line">
                              <span className="key-provider-title">{cfg.provider}</span>
                              <span className="key-model-tag">{cfg.model_name}</span>
                            </div>
                            <div className="key-sub-line">
                              <span className="key-masked">{cfg.masked_key}</span>
                              <span className="key-limit-chip">
                                <Zap size={12} />
                                {cfg.rpm_limit || recommended.rpm_limit} RPM · {cfg.tpm_limit || recommended.tpm_limit} TPM
                              </span>
                            </div>
                          </div>
                        </div>

                        <div className="key-actions">
                          <button
                            type="button"
                            className="secondary-button edit-limits-button"
                            onClick={() => setEditingLimits({
                              index: realIndex,
                              rpm_limit: cfg.rpm_limit || recommended.rpm_limit,
                              tpm_limit: cfg.tpm_limit || recommended.tpm_limit
                            })}
                            title="Configure RPM & TPM rate limits"
                          >
                            <Sliders size={15} />
                            <span>Edit Limits</span>
                          </button>
                          <button 
                            type="button"
                            onClick={() => handleRemoveKey(realIndex)}
                            className="delete-btn"
                            title={`Remove ${cfg.provider} provider`}
                          >
                            <Trash2 size={16} />
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="key-item-edit-card">
                        <div className="edit-card-header">
                          <div className="edit-card-title">
                            <Sliders size={18} className="edit-title-icon" />
                            <h4>Configure Limits — <span className="provider-name-accent">{cfg.provider}</span> ({cfg.model_name})</h4>
                          </div>
                          <button 
                            type="button" 
                            className="icon-cancel-button"
                            onClick={() => setEditingLimits(null)}
                            title="Cancel editing"
                          >
                            <X size={16} />
                          </button>
                        </div>

                        <div className="edit-card-grid">
                          <div className="edit-field-group">
                            <label className="edit-field-label">
                              <Activity size={14} /> Requests / Minute (RPM)
                            </label>
                            <input 
                              type="number" 
                              min="1" 
                              className="form-input edit-number-input"
                              value={editingLimits.rpm_limit} 
                              onChange={e => setEditingLimits({...editingLimits, rpm_limit: e.target.value})} 
                              placeholder="e.g. 30"
                            />
                            <span className="field-hint">Max API calls in 60s sliding window</span>
                          </div>

                          <div className="edit-field-group">
                            <label className="edit-field-label">
                              <Zap size={14} /> Tokens / Minute (TPM)
                            </label>
                            <input 
                              type="number" 
                              min="1" 
                              className="form-input edit-number-input"
                              value={editingLimits.tpm_limit} 
                              onChange={e => setEditingLimits({...editingLimits, tpm_limit: e.target.value})} 
                              placeholder="e.g. 12000"
                            />
                            <span className="field-hint">Max total tokens processed per minute</span>
                          </div>
                        </div>

                        <div className="edit-card-footer">
                          <button 
                            type="button" 
                            className="preset-pill-button"
                            onClick={() => setEditingLimits({
                              ...editingLimits,
                              rpm_limit: recommended.rpm_limit,
                              tpm_limit: recommended.tpm_limit
                            })}
                          >
                            <RotateCcw size={13} /> Reset to recommended ({recommended.rpm_limit} RPM / {recommended.tpm_limit} TPM)
                          </button>

                          <div className="edit-footer-actions">
                            <button 
                              type="button" 
                              className="secondary-button"
                              onClick={() => setEditingLimits(null)}
                            >
                              Cancel
                            </button>
                            <button 
                              type="button" 
                              className="primary-button"
                              onClick={() => handleSaveLimits(editingLimits.index, editingLimits)}
                            >
                              <Check size={16} /> Save Limits
                            </button>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>

          <form onSubmit={handleAddKey} className="add-form">
            <h4 className="form-subheading">Add New Provider</h4>
            <div className="form-grid">
              <select 
                className="form-input"
                value={newKey.provider}
                onChange={handleProviderChange}
              >
                <option value="groq">Groq</option>
                <option value="gemini">Gemini</option>
                <option value="openrouter">OpenRouter</option>
                <option value="ollama">Ollama (Local)</option>
              </select>
              
              <input 
                type="text" 
                placeholder="API Key" 
                className="form-input"
                value={newKey.api_key}
                onChange={e => setNewKey({...newKey, api_key: e.target.value})}
                required={newKey.provider !== 'ollama'}
              />
              
              <input 
                type="text" 
                placeholder="Endpoint URL" 
                className="form-input"
                value={newKey.endpoint_url}
                onChange={e => setNewKey({...newKey, endpoint_url: e.target.value})}
                required
              />

              <details className="rate-limit-settings">
                <summary>Advanced rate limits</summary>
                <div className="rate-limit-grid">
                  <label>
                    RPM limit
                    <input type="number" min="1" className="form-input" value={newKey.rpm_limit} onChange={e => setNewKey({...newKey, rpm_limit: Number(e.target.value)})} required />
                  </label>
                  <label>
                    TPM limit
                    <input type="number" min="1" className="form-input" value={newKey.tpm_limit} onChange={e => setNewKey({...newKey, tpm_limit: Number(e.target.value)})} required />
                  </label>
                </div>
                <button type="button" className="secondary-button" onClick={() => setNewKey({...newKey, ...RECOMMENDED_LIMITS[newKey.provider]})}>
                  Use recommended limits
                </button>
              </details>
              
              <input 
                type="text" 
                placeholder="Model Name" 
                className="form-input"
                value={newKey.model_name}
                onChange={e => setNewKey({...newKey, model_name: e.target.value})}
                required
              />
            </div>
            <button type="submit" className="primary-button submit-auto-width">
              <Plus size={18} />
              Add Provider
            </button>
          </form>
        </div>
      </section>
    </div>
  );
};

export default Settings;
