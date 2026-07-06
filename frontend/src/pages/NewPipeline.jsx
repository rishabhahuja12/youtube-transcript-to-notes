import React, { useState } from 'react';
import PowerUpCard from '../components/PowerUpCard';
import { useAppContext } from '../context/AppContext';
import { startPipeline, connectPipelineWebSocket } from '../utils/api';
import { Video, Folder, Rocket, AlertCircle } from 'lucide-react';

const NewPipeline = () => {
  const { setPipelineStatus, setCurrentScreen, addLog, setPipelineProgress } = useAppContext();
  const [inputType, setInputType] = useState('youtube'); // 'youtube' or 'local'
  const [url, setUrl] = useState('');
  const [topic, setTopic] = useState('');
  const [outputDir, setOutputDir] = useState('');
  
  const [powerUps, setPowerUps] = useState({
    vision: false,
    kag: false,
    pdf: false
  });

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const togglePowerUp = (key) => {
    setPowerUps(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!url) {
      setError("Please enter a valid URL or path");
      return;
    }
    
    if (inputType === 'youtube') {
      const ytRegex = /^(https?:\/\/)?(www\.)?(youtube\.com|youtu\.?be)\/.+$/;
      if (!ytRegex.test(url)) {
        setError("Please enter a valid YouTube URL");
        return;
      }
    }

    try {
      setIsSubmitting(true);
      setError(null);
      
      const payload = {
        url,
        topic,
        outputDir,
        powerUps
      };
      
      await startPipeline(payload);
      setPipelineStatus('running');
      
      connectPipelineWebSocket((msg) => {
        if (msg.type === 'log') {
          addLog(msg.message, msg.level || 'info');
        } else if (msg.type === 'progress') {
          setPipelineProgress({ current: msg.current, total: msg.total });
        } else if (msg.type === 'complete') {
          setPipelineStatus('completed');
          addLog('Pipeline completed successfully!', 'success');
          setCurrentScreen('courseWorkspace');
        } else if (msg.type === 'error') {
          setPipelineStatus('error');
          addLog(`Pipeline error: ${msg.message}`, 'error');
        }
      });
      
      
    } catch (err) {
      setError(err.message || 'Failed to start pipeline');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="new-pipeline-page fade-in">
      <div className="page-header">
        <h2>New Pipeline</h2>
      </div>

      <form className="pipeline-form" onSubmit={handleSubmit}>
        <div className="form-group glass-card">
          <div className="segment-control">
            <button 
              type="button"
              className={`segment-button ${inputType === 'youtube' ? 'active' : ''}`}
              onClick={() => setInputType('youtube')}
            >
              <Video size={18} />
              YouTube URL
            </button>
            <button 
              type="button"
              className={`segment-button ${inputType === 'local' ? 'active' : ''}`}
              onClick={() => setInputType('local')}
            >
              <Folder size={18} />
              Local Files
            </button>
          </div>

          <div className="input-field">
            <label htmlFor="source-url">
              {inputType === 'youtube' ? 'YouTube Video or Playlist URL' : 'Local Directory Path'}
            </label>
            <input 
              id="source-url"
              type="text" 
              className="text-input" 
              placeholder={inputType === 'youtube' ? 'https://youtube.com/watch?v=...' : 'C:\\path\\to\\files'}
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              required
            />
          </div>
          
          <div className="input-field">
            <label htmlFor="topic">Topic / Title (Optional)</label>
            <input 
              id="topic"
              type="text" 
              className="text-input" 
              placeholder="e.g. Advanced Machine Learning"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
            />
          </div>

          <div className="input-field">
            <label htmlFor="output-dir">Output Directory (Optional)</label>
            <input 
              id="output-dir"
              type="text" 
              className="text-input" 
              placeholder="Leave blank for default"
              value={outputDir}
              onChange={(e) => setOutputDir(e.target.value)}
            />
            <small className="field-hint">Enter full path</small>
          </div>
        </div>

        <div className="power-ups-section">
          <h3>Power-Ups</h3>
          <div className="power-ups-grid">
            <PowerUpCard 
              icon="📸" 
              title="Vision Engine" 
              description="Extract keyframes and text from video frames" 
              timeHint="~35s" 
              isActive={powerUps.vision} 
              onToggle={() => togglePowerUp('vision')} 
            />
            <PowerUpCard 
              icon="🕸️" 
              title="Knowledge Graph" 
              description="Build relationship graphs from entities" 
              timeHint="~15s" 
              isActive={powerUps.kag} 
              onToggle={() => togglePowerUp('kag')} 
            />
            <PowerUpCard 
              icon="📄" 
              title="Auto PDF Export" 
              description="Generate styled PDF notes immediately" 
              timeHint="~5s" 
              isActive={powerUps.pdf} 
              onToggle={() => togglePowerUp('pdf')} 
            />
          </div>
        </div>
        
        {error && (
          <div className="error-message">
            <AlertCircle size={18} />
            <span>{error}</span>
          </div>
        )}

        <button type="submit" className="primary-button start-pipeline-button" disabled={isSubmitting}>
          <Rocket size={20} />
          {isSubmitting ? 'Starting Pipeline...' : 'Start Pipeline Processing'}
        </button>
      </form>
    </div>
  );
};

export default NewPipeline;
