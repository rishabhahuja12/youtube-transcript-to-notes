import React, { useState, useEffect, useRef } from 'react';
import PowerUpCard from '../components/PowerUpCard';
import { useAppContext } from '../context/AppContext';
import { startPipeline, cancelPipeline, connectPipelineWebSocket, browseDirectory, browseFile, fetchPoolSettings, fetchOllamaStatus } from '../utils/api';
import { Video, Folder, Rocket, AlertCircle, Camera, Share2, FileText, Play, Check, File } from 'lucide-react';

const extractVideoId = (url) => {
  if (!url) return null;
  const match = url.match(/(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})/);
  return match ? match[1] : null;
};

const NewPipeline = () => {
  const { setPipelineStatus, setCurrentScreen, addLog, setPipelineProgress, pipelineStatus, setActiveCourseDir, pipelineProgress } = useAppContext();
  const [inputType, setInputType] = useState('youtube');
  const [url, setUrl] = useState('');
  const [topic, setTopic] = useState('');
  const [outputDir, setOutputDir] = useState('');
  
  const [transcriptPath, setTranscriptPath] = useState('');
  const [outlinePath, setOutlinePath] = useState('');
  
  const [powerUps, setPowerUps] = useState({
    vision: false,
    kag: false,
    pdf: false
  });

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);
  
  const wsRef = useRef(null);
  
  const { activeJobId, setActiveJobId } = useAppContext();
  const [pipelinePhase, setPipelinePhase] = useState(null);
  
  useEffect(() => {
    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  const handleCancel = async () => {
    if (activeJobId && pipelineStatus === 'running') {
      try {
        await cancelPipeline(activeJobId);
      } catch (err) {
        addLog(`Cancel failed: ${err.message}`, 'error');
      }
    }
  };

  const [youtubeStatus, setYoutubeStatus] = React.useState(false);
  React.useEffect(() => {
    import('../utils/api').then(({fetchYouTubeStatus}) => {
      fetchYouTubeStatus().then(res => setYoutubeStatus(res.connected)).catch(() => {});
    });
  }, []);

  const handleBrowseDir = async () => {
    try {
      const data = await browseDirectory();
      if (data && data.path) setOutputDir(data.path);
    } catch (err) {
      console.error('Browse failed:', err);
    }
  };
  
  const handleBrowseTranscript = async () => {
    try {
      const data = await browseFile();
      if (data && data.path) setTranscriptPath(data.path);
    } catch (err) {
      console.error('Browse file failed:', err);
    }
  };

  const handleBrowseOutline = async () => {
    try {
      const data = await browseFile();
      if (data && data.path) setOutlinePath(data.path);
    } catch (err) {
      console.error('Browse file failed:', err);
    }
  };

  const togglePowerUp = (key) => {
    setPowerUps(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    // Preflight Validation
    if (!outputDir) {
       setError("Please select an output directory.");
       return;
    }
    
    let poolSettings = [];
    let health = { playwright: false };
    try {
       poolSettings = await fetchPoolSettings();
       health = await fetchOllamaStatus();
    } catch (err) {
       console.error("Failed to fetch settings", err);
    }
    
    const hasText = poolSettings.some(c => c.capability === 'text');
    const hasVision = poolSettings.some(c => c.capability === 'vision');
    
    if (!hasText) {
       setError("No text providers configured in the pool. Please add a text provider in Settings.");
       return;
    }
    if (powerUps.vision && !hasVision) {
       setError("Vision power-up selected but no vision provider is configured. Please add one in Settings.");
       return;
    }
    if (powerUps.pdf && !health.playwright) {
       console.warn("Playwright not installed, PDF might fail or degrade.");
       // Not a hard blocker, just a warning, but we can set a warning state if we wanted.
    }
    
    if (inputType === 'youtube') {
      if (!url) {
        setError("Please enter a valid YouTube URL");
        return;
      }
      const ytRegex = /^(https?:\/\/)?(www\.)?(youtube\.com|youtu\.?be)\/.+$/;
      if (!ytRegex.test(url)) {
        setError("Please enter a valid YouTube URL");
        return;
      }
      if (!youtubeStatus) {
         setError("YouTube OAuth is not connected. Connect in Settings.");
         return;
      }
    } else {
      if (!transcriptPath || !outlinePath) {
         setError("Please select both a transcript and an outline file for Local mode.");
         return;
      }
    }

    try {
      setIsSubmitting(true);
      setError(null);
      setPipelineProgress({ current: 0, total: 100 });
      
      const isYoutube = inputType === 'youtube';
      const payload = {
        output_dir: outputDir,
        youtube_url: isYoutube ? url : "",
        transcript_path: !isYoutube ? transcriptPath : "",
        timestamps_path: !isYoutube ? outlinePath : "", 
        is_url_pipeline: isYoutube,
        video_title: topic.trim() === '' ? null : topic,
        enable_multimodal: powerUps.vision || false,
        enable_kag: powerUps.kag || false,
        enable_pdf: powerUps.pdf || false
      };
      
      const res = await startPipeline(payload);
      if (!res.success) {
         throw new Error(res.error || res.message || "Failed to start");
      }
      const jobId = res.job_id;
      setActiveJobId(jobId);
      setPipelineStatus('running');
      setPipelinePhase(null);
      
      wsRef.current = connectPipelineWebSocket(jobId, (msg) => {
        if (msg.job_id && msg.job_id !== jobId) return;
        
        if (msg.type === 'snapshot') {
          if (msg.status === 'running') setPipelineStatus('running');
          else if (['complete', 'degraded', 'failed', 'cancelled'].includes(msg.status)) {
             handleTerminalState(msg.status, msg.result);
          }
        } else if (msg.type === 'log') {
          addLog(msg.message, msg.level || 'info');
        } else if (msg.type === 'progress') {
          setPipelineProgress({ current: msg.current, total: msg.total });
        } else if (msg.type === 'phase') {
          setPipelinePhase({ phase: msg.phase, status: msg.status });
          addLog(`Phase ${msg.phase} status: ${msg.status}`, 'info');
        } else if (msg.type === 'terminal') {
          handleTerminalState(msg.status, msg.result);
        } else if (msg.type === 'error') {
          handleTerminalState('failed', { error: msg.message });
        }
      });
      
      const handleTerminalState = (status, result) => {
        if (wsRef.current) wsRef.current.close();
        
        if (status === 'complete' || status === 'degraded') {
           setPipelineStatus(status);
           if (status === 'complete') addLog('Pipeline completed successfully!', 'success');
           if (status === 'degraded') addLog('Pipeline completed with degraded output.', 'warning');
           
           if (result && result.course_record) {
              setActiveCourseDir(result.course_record);
           }
           setCurrentScreen('courseWorkspace');
        } else if (status === 'failed') {
           setPipelineStatus('failed');
           addLog(`Pipeline failed: ${result?.error || 'Unknown error'}`, 'error');
           setError(result?.error || 'Pipeline failed to complete');
        } else if (status === 'cancelled') {
           setPipelineStatus('cancelled');
           addLog('Pipeline cancelled by user.', 'info');
           // Keep user on pipeline screen, no error language
           setError(null);
        }
      };
      
    } catch (err) {
      setError(err.message || 'Failed to start pipeline');
      setPipelineStatus('failed');
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
             <label htmlFor="output-dir">Output Directory (Required)</label>
             <div className="input-group">
               <button 
                 type="button" 
                 onClick={handleBrowseDir} 
                 className="secondary-button browse-button"
               >
                 <Folder size={18} /> {outputDir || "Browse Output Directory"}
               </button>
             </div>
          </div>

          {inputType === 'youtube' ? (
              <div className="input-field">
                <label htmlFor="source-url">YouTube Video or Playlist URL</label>
                <input 
                  id="source-url"
                  type="text" 
                  className="text-input" 
                  placeholder="https://youtube.com/watch?v=..."
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  required
                />
              </div>
          ) : (
             <>
                <div className="input-field">
                   <label>Transcript File (Required)</label>
                   <button type="button" onClick={handleBrowseTranscript} className="secondary-button browse-button">
                      <File size={18} /> {transcriptPath ? transcriptPath.split('\\').pop() : "Select Transcript File"}
                   </button>
                </div>
                <div className="input-field">
                   <label>Chapter Outline File (Required)</label>
                   <button type="button" onClick={handleBrowseOutline} className="secondary-button browse-button">
                      <File size={18} /> {outlinePath ? outlinePath.split('\\').pop() : "Select Outline File"}
                   </button>
                </div>
             </>
          )}
          
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
                    <div className="play-placeholder">
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
          
          {pipelineStatus === 'running' && (
             <div className="status-panel panel-card">
                <h3 className="serif-heading">Job Status: {pipelineStatus}</h3>
                {pipelinePhase && <p>Phase: {pipelinePhase.phase} ({pipelinePhase.status})</p>}
                <p>Progress: {pipelineProgress?.current || 0} / {pipelineProgress?.total || 100}</p>
             </div>
          )}
          {pipelineStatus === 'cancelled' && (
             <div className="status-panel panel-card">
                <h3 className="serif-heading">Job Cancelled</h3>
                <p>You can start a new job or modify your settings.</p>
             </div>
          )}

          <div className="pipeline-button-row">
            {error && (
               <div className={`status-alert ${error.includes("retry") ? "warning" : "error"}`}>
                  {error}
                  {error.includes("Connect YouTube") && (
                     <button type="button" onClick={() => setCurrentScreen('settings')} className="alert-link">
                        Go to Settings
                     </button>
                  )}
                  {error.includes("retry") && (
                     <button type="button" onClick={handleSubmit} className="alert-link">
                        Retry
                     </button>
                  )}
               </div>
            )}
            {pipelineStatus === 'running' && (
               <button type="button" onClick={handleCancel} className="secondary-button" style={{marginRight: '1rem'}}>
                  Cancel Pipeline
               </button>
            )}
            <button type="submit" form="pipeline-form" className="primary-button start-pipeline-button" 
               disabled={isSubmitting || pipelineStatus === 'running'}>
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
