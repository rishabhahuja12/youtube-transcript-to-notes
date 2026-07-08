import React, { useState } from 'react';
import PowerUpCard from '../components/PowerUpCard';
import { useAppContext } from '../context/AppContext';
import { startPipeline, connectPipelineWebSocket } from '../utils/api';
import { Video, Folder, Rocket, AlertCircle, Camera, Share2, FileText, Play, Check } from 'lucide-react';

const extractVideoId = (url) => {
  const match = url.match(/(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})/);
  return match ? match[1] : null;
};

const NewPipeline = () => {
  const { setPipelineStatus, setCurrentScreen, addLog, setPipelineProgress, pipelineStatus, setActiveCourseDir } = useAppContext();
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
      
      const wsConnection = connectPipelineWebSocket((msg) => {
        if (msg.type === 'log') {
          addLog(msg.message, msg.level || 'info');
        } else if (msg.type === 'progress') {
          setPipelineProgress({ current: msg.current, total: msg.total });
        } else if (msg.type === 'complete') {
          if (wsConnection) wsConnection.close();
          setPipelineStatus('completed');
          addLog('Pipeline completed successfully!', 'success');
          if (msg.course_dir) setActiveCourseDir(msg.course_dir);
          setCurrentScreen('courseWorkspace');
        } else if (msg.type === 'error') {
          if (wsConnection) wsConnection.close();
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
      <div className="pipeline-layout-3col">
        <div className="pipeline-main-area">
          <div className="page-header">
            <h2>New Pipeline</h2>
          </div>
          
          <div className="pipeline-form-preview-row">
            <div className="pipeline-col-form">
              <form className="pipeline-form" id="pipeline-form" onSubmit={handleSubmit}>
        <div className="form-group">
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
            <small className="field-hint">Defaults to ~/StudySuite/Output</small>
          </div>
        </div>
          </form>
        </div>
      

            <div className="pipeline-col-preview">
              {inputType === 'youtube' && url && extractVideoId(url) ? (
                <div className="preview-panel filled-panel">
                  <div className="preview-thumbnail">
                    <img 
                      src={`https://img.youtube.com/vi/${extractVideoId(url)}/maxresdefault.jpg`} 
                      alt="Thumbnail" 
                      onError={(e) => { 
                        e.target.style.display='none'; 
                        e.target.nextSibling.style.display='flex'; 
                      }} 
                    />
                    <div className="play-placeholder" style={{display: 'none', alignItems: 'center', justifyContent: 'center', width: '100%', height: '100%', color: 'var(--text-muted)'}}>
                      <Play size={24} />
                    </div>
                    <div className="duration-badge mono-text">0:00</div>
                  </div>
                  <div className="preview-info">
                    <div className="preview-title">Ready for processing</div>
                    <div className="preview-channel mono-text">YouTube Video</div>
                  </div>
                  <div className="preview-outputs">
                    <div className="output-label mono-text">DEFAULT OUTPUTS</div>
                    <ul className="output-list">
                      <li><Check size={14} className="muted-icon" /> Full-text transcript</li>
                      <li><Check size={14} className="muted-icon" /> Chapter-based study notes</li>
                    </ul>
                  </div>
                </div>
              ) : (
                <div className="preview-panel empty-panel panel-card">
                  <Play size={32} className="muted-icon" />
                </div>
              )}
            </div>
          </div>

          <div className="pipeline-button-row">
            <button type="submit" form="pipeline-form" className="primary-button start-pipeline-button" disabled={isSubmitting || pipelineStatus === 'running'}>
              <Rocket size={20} />
              {isSubmitting || pipelineStatus === 'running' ? 'Starting pipeline...' : 'Start pipeline'}
            </button>
          </div>
        </div>

        <div className="pipeline-col-powerups">
          <div className="power-ups-header">
            <h3>Power-Ups</h3>
          </div>
          <div className="power-ups-stack">
            <PowerUpCard 
              icon={<Camera size={24} />} 
              title="Vision Engine" 
              description="Extract keyframes and text from video frames" 
              isActive={powerUps.vision} 
              onToggle={() => togglePowerUp('vision')} 
            />
            <PowerUpCard 
              icon={<Share2 size={24} />} 
              title="Knowledge Graph" 
              description="Build entity relationships from transcript" 
              isActive={powerUps.kag} 
              onToggle={() => togglePowerUp('kag')} 
            />
            <PowerUpCard 
              icon={<FileText size={24} />} 
              title="Auto PDF Export" 
              description="Generate formatted study guide on completion" 
              isActive={powerUps.pdf} 
              onToggle={() => togglePowerUp('pdf')} 
            />
          </div>
        </div>
      </div>
    </div>
  );
};

export default NewPipeline;
