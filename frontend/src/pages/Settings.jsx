import React, { useState, useEffect } from 'react';
import { fetchOllamaStatus, fetchPoolSettings, addPoolKey, deletePoolKey, fetchYouTubeStatus, connectYouTube, disconnectYouTube } from '../utils/api';
import { Settings as SettingsIcon, Server, Shield, Database, Key, Activity, Trash2, Plus, PlayCircle } from 'lucide-react';
import './Settings.css';

const Settings = () => {
  const [activeTab, setActiveTab] = useState('text');
  const [poolConfigs, setPoolConfigs] = useState([]);
  const [healthStatus, setHealthStatus] = useState({ ollama: false, playwright: false, keyring: false });
  const [youtubeConnected, setYoutubeConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [newKey, setNewKey] = useState({
    provider: 'groq',
    api_key: '',
    endpoint_url: '',
    model_name: '',
    capability: 'text'
  });

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const [healthData, ytData, poolData] = await Promise.all([
        fetchOllamaStatus().catch(err => { console.error(err); return healthStatus; }),
        fetchYouTubeStatus().catch(err => { console.error(err); return { connected: false }; }),
        fetchPoolSettings()
      ]);

      setHealthStatus(healthData);
      setYoutubeConnected(ytData.connected);
      setPoolConfigs(poolData);
      setError(null);
    } catch (err) {
      console.error(err);
      setError('Failed to load settings data.');
    } finally {
      setLoading(false);
    }
  };

  const handleConnectYoutube = async () => {
    try {
      const res = await connectYouTube();
      setYoutubeConnected(res.connected);
    } catch (err) {
      console.error(err);
      setError('Failed to connect YouTube.');
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
    let endpoint_url = '';
    if (provider === 'groq') endpoint_url = 'https://api.groq.com/openai/v1';
    if (provider === 'gemini') endpoint_url = 'https://generativelanguage.googleapis.com/v1beta/openai/';
    if (provider === 'ollama') endpoint_url = 'http://localhost:11434/v1';
    setNewKey({...newKey, provider, endpoint_url});
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
        setNewKey({ provider: 'groq', api_key: '', endpoint_url: '', model_name: '', capability: activeTab });
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

  const filteredPool = poolConfigs.filter(cfg => cfg.capability === activeTab);

  if (loading) {
    return (
      <div className="settings-container" style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '400px' }}>
        <div style={{ color: 'var(--text-secondary)', fontSize: '1.2rem' }}>Loading settings...</div>
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
          <Activity size={24} style={{ marginRight: '8px', verticalAlign: 'middle' }} />
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
          <PlayCircle size={24} style={{ marginRight: '8px', verticalAlign: 'middle' }} />
          YouTube Connection
        </h2>
        <div className="health-card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h3 style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              YouTube API
              <span style={{ 
                width: '8px', 
                height: '8px', 
                borderRadius: '50%', 
                background: youtubeConnected ? 'var(--connected)' : '#dc3545' 
              }}></span>
            </h3>
            <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', marginTop: '4px' }}>
              Connect via Google OAuth for reliable metadata and chapters.
            </p>
            <p className={`health-status ${youtubeConnected ? 'success' : 'error'}`}>
              {youtubeConnected ? 'YouTube: connected' : 'Not connected'}
            </p>
          </div>
          <div>
            {youtubeConnected ? (
              <button onClick={handleDisconnectYoutube} className="secondary-button" style={{ borderColor: '#dc3545', color: '#dc3545' }}>Disconnect</button>
            ) : (
              <button onClick={handleConnectYoutube} className="primary-button">Connect your YouTube</button>
            )}
          </div>
        </div>
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
          <h3 style={{ marginBottom: '16px' }}>
            {activeTab === 'text' ? 'Text Generation Providers' : 'Vision/Multimodal Providers'}
          </h3>
          
          <div className="key-list">
            {loading && poolConfigs.length === 0 ? (
              <p style={{ color: 'var(--text-muted)' }}>Loading providers...</p>
            ) : filteredPool.length === 0 ? (
              <p style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>No {activeTab} providers configured.</p>
            ) : (
              filteredPool.map((cfg, idx) => (
                <div key={idx} className="key-item">
                  <div className="key-info">
                    <Key size={20} color="var(--accent)" />
                    <div>
                      <p className="key-provider">{cfg.provider}</p>
                      <p className="key-masked">{cfg.masked_key}</p>
                    </div>
                  </div>
                  <button 
                    onClick={() => handleRemoveKey(poolConfigs.indexOf(cfg))}
                    className="delete-btn"
                  >
                    <Trash2 size={20} />
                  </button>
                </div>
              ))
            )}
          </div>

          <form onSubmit={handleAddKey} className="add-form">
            <h4 style={{ marginBottom: '16px' }}>Add New Provider</h4>
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
                placeholder="Endpoint URL (Optional)" 
                className="form-input"
                value={newKey.endpoint_url}
                onChange={e => setNewKey({...newKey, endpoint_url: e.target.value})}
              />
              
              <input 
                type="text" 
                placeholder="Model Name (Optional)" 
                className="form-input"
                value={newKey.model_name}
                onChange={e => setNewKey({...newKey, model_name: e.target.value})}
              />
            </div>
            <button type="submit" className="primary-button" style={{ width: 'auto' }}>
              <Plus size={18} />
              Add Provider
            </button>
          </form>
        </div>
      </section>
    </div>
  );
};

const HealthCard = ({ title, status, icon, desc }) => (
  <div className="health-card">
    <div className={`health-icon-wrapper ${status ? 'success' : 'error'}`}>
      {icon}
    </div>
    <div>
      <h3 style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        {title}
        <span style={{ 
          width: '8px', 
          height: '8px', 
          borderRadius: '50%', 
          background: status ? 'var(--connected)' : '#dc3545' 
        }}></span>
      </h3>
      <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', marginTop: '4px' }}>{desc}</p>
      <p className={`health-status ${status ? 'success' : 'error'}`}>
        {status ? 'Online & Ready' : 'Unavailable'}
      </p>
    </div>
  </div>
);

export default Settings;
