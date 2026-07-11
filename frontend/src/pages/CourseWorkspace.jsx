import React, { useState, useEffect, useRef } from 'react';
import { useAppContext } from '../context/AppContext';
import { fetchCourse, fetchNotes, fetchCourseGraph, fetchCourseKeyframes, chatWithCourse, clearChat, generatePdf, API_BASE_URL } from '../utils/api';
import ChatBubble from '../components/ChatBubble';
import ThemeCard from '../components/ThemeCard';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import mermaid from 'mermaid';
import { ArrowLeft, Send, Download, RefreshCw, FileText, MessageSquare, Share2, File, Image as ImageIcon, Eye } from 'lucide-react';

mermaid.initialize({
  startOnLoad: false,
  theme: 'dark',
});

const MermaidChart = ({ code }) => {
  const chartRef = useRef(null);
  
  useEffect(() => {
    if (chartRef.current && code) {
      const renderGraph = async () => {
        try {
          const { svg } = await mermaid.render(`mermaid-graph-${Date.now()}`, code);
          if (chartRef.current) chartRef.current.innerHTML = svg;
        } catch (err) {
          console.error("Mermaid render error:", err);
        }
      };
      renderGraph();
    }
  }, [code]);

  return <div className="mermaid-container" ref={chartRef} style={{ width: '100%', display: 'flex', justifyContent: 'center', padding: 'var(--space-xl)' }} />;
};

const PDF_THEMES = [
  {
    id: 'textbook',
    name: 'Textbook',
    description: 'Clean, academic style with blue accents.',
  },
  {
    id: 'chatgpt-dark',
    name: 'ChatGPT Dark',
    description: 'Dark mode matching standard AI interfaces.',
  },
  {
    id: 'minimal-mono',
    name: 'Minimal Mono',
    description: 'High contrast black & white typewriter style.',
  }
];

const CourseWorkspace = () => {
  const { activeCourseDir, setCurrentScreen } = useAppContext();
  const [activeTab, setActiveTab] = useState('notes');
  const [courseFiles, setCourseFiles] = useState([]);
  const [loading, setLoading] = useState(true);
  
  // Notes State
  const [mdFiles, setMdFiles] = useState([]);
  const [selectedMdFile, setSelectedMdFile] = useState(null);
  const [notesContent, setNotesContent] = useState('');
  
  // Chat State
  const [chatMessages, setChatMessages] = useState([]);
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [selectedModel, setSelectedModel] = useState('llama3');
  const messagesEndRef = useRef(null);

  // Graph State
  const [mermaidCode, setMermaidCode] = useState('');
  
  // PDF State
  const [selectedTheme, setSelectedTheme] = useState(PDF_THEMES[0].name);
  const [pdfGenerating, setPdfGenerating] = useState(false);
  const [generatedPdfPath, setGeneratedPdfPath] = useState(null);

  // Keyframes State
  const [keyframes, setKeyframes] = useState([]);

  useEffect(() => {
    if (!activeCourseDir) {
      setCurrentScreen('library');
      return;
    }
    loadCourseData();
  }, [activeCourseDir]);

  const loadCourseData = async () => {
    setLoading(true);
    try {
      const files = await fetchCourse(activeCourseDir.id);
      setCourseFiles(files);
      
      // Load Notes
      const allMdFiles = files.filter(f => f.name.endsWith('.md'));
      setMdFiles(allMdFiles);
      if (allMdFiles.length > 0) {
        setSelectedMdFile(allMdFiles[0].name);
        const notes = await fetchNotes(activeCourseDir.id, allMdFiles[0].name);
        setNotesContent(notes);
      }
      
      // Load Graph
      if (activeCourseDir.badges?.kag) {
        const graph = await fetchCourseGraph(activeCourseDir.id);
        const match = graph.html.match(/<div class="mermaid">([\s\S]*?)<\/div>/);
        if (match && match[1]) {
          setMermaidCode(match[1].trim());
        }
      }
      
      // Load Keyframes
      if (activeCourseDir.badges?.vision) {
        const frames = await fetchCourseKeyframes(activeCourseDir.id);
        setKeyframes(frames);
      }
      
    } catch (error) {
      console.error("Failed to load course data:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages]);

  const handleNotesChange = async (e) => {
    const filename = e.target.value;
    setSelectedMdFile(filename);
    try {
      const notes = await fetchNotes(activeCourseDir.id, filename);
      setNotesContent(notes);
    } catch (error) {
      console.error("Failed to load selected notes:", error);
    }
  };

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!chatInput.trim() || chatLoading) return;

    const userMessage = chatInput.trim();
    setChatInput('');
    setChatMessages(prev => [...prev, { text: userMessage, isUser: true }]);
    setChatLoading(true);

    try {
      const res = await chatWithCourse(activeCourseDir.id, userMessage, selectedModel);
      setChatMessages(prev => [...prev, { text: res.response, isUser: false }]);
    } catch (error) {
      setChatMessages(prev => [...prev, { text: error.message || 'Error connecting to chat service.', isUser: false, isError: true }]);
    } finally {
      setChatLoading(false);
    }
  };

  const handleClearChat = async () => {
    try {
      await clearChat();
      setChatMessages([]);
    } catch (error) {
      console.error("Failed to clear chat:", error);
    }
  };

  const handleGeneratePdf = async () => {
    const mdFile = courseFiles.find(f => f.name.endsWith('.md'));
    if (!mdFile) return;

    setPdfGenerating(true);
    try {
      const res = await generatePdf(activeCourseDir.id, mdFile.name, selectedTheme);
      setGeneratedPdfPath(res.path);
    } catch (error) {
      console.error("Failed to generate PDF:", error);
    } finally {
      setPdfGenerating(false);
    }
  };

  if (!activeCourseDir || loading) {
    return (
      <div className="workspace-loading">
        <RefreshCw className="loader-spin" size={32} />
        <p>Loading workspace...</p>
      </div>
    );
  }

  const tabs = [
    { id: 'notes', label: 'Notes', icon: <FileText size={16} /> },
    { id: 'chat', label: 'Chat', icon: <MessageSquare size={16} /> },
    { id: 'graph', label: 'Graph', icon: <Share2 size={16} /> },
    { id: 'pdf', label: 'Export PDF', icon: <File size={16} /> },
    { id: 'keyframes', label: 'Keyframes', icon: <ImageIcon size={16} /> }
  ];

  return (
    <div className="course-workspace fade-in">
      <div className="workspace-header">
        <button className="back-button" onClick={() => setCurrentScreen('library')}>
          <ArrowLeft size={20} />
          <span>Back to Library</span>
        </button>
        <h2 className="serif-heading workspace-title">{activeCourseDir.title}</h2>
        
        <div className="segment-control workspace-tabs">
          {tabs.map(tab => (
            <button
              key={tab.id}
              className={`segment-button ${activeTab === tab.id ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.icon}
              <span>{tab.label}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="workspace-content">
        {/* Notes Tab */}
        {activeTab === 'notes' && (
          <div className="tab-pane notes-pane panel-card">
            {mdFiles.length > 1 && (
              <div className="notes-selector" style={{ marginBottom: 'var(--space-lg)' }}>
                <select 
                  className="text-input" 
                  value={selectedMdFile || ''} 
                  onChange={handleNotesChange}
                  style={{ width: 'auto', padding: 'var(--space-sm) var(--space-md)' }}
                >
                  {mdFiles.map(f => (
                    <option key={f.name} value={f.name}>{f.name}</option>
                  ))}
                </select>
              </div>
            )}
            {notesContent ? (
              <div className="markdown-body">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  rehypePlugins={[rehypeHighlight]}
                >
                  {notesContent}
                </ReactMarkdown>
              </div>
            ) : (
              <div className="empty-state">No notes available for this course.</div>
            )}
          </div>
        )}

        {/* Chat Tab */}
        {activeTab === 'chat' && (
          <div className="tab-pane chat-pane panel-card">
            <div className="chat-header">
              <div style={{ display: 'flex', gap: 'var(--space-md)', alignItems: 'center' }}>
                <h3>Ask Questions</h3>
                <select 
                  className="text-input" 
                  value={selectedModel} 
                  onChange={e => setSelectedModel(e.target.value)}
                  style={{ width: 'auto', padding: 'var(--space-xs) var(--space-sm)' }}
                >
                  <option value="llama3">llama3</option>
                  <option value="phi3">phi3</option>
                  <option value="qwen2.5:3b">qwen2.5:3b</option>
                </select>
              </div>
              <button className="secondary-button clear-chat-btn" onClick={handleClearChat}>
                Clear History
              </button>
            </div>
            <div className="chat-messages">
              {chatMessages.length === 0 ? (
                <div className="empty-state">
                  <MessageSquare size={48} className="muted-icon" />
                  <p>Ask anything about the course content.</p>
                </div>
              ) : (
                chatMessages.map((msg, idx) => (
                  <ChatBubble key={idx} message={msg.text} isUser={msg.isUser} />
                ))
              )}
              {chatLoading && (
                <div className="chat-bubble-container ai-message">
                  <div className="chat-avatar"><div className="avatar-circle ai-avatar">AI</div></div>
                  <div className="chat-bubble ai-bubble typing-indicator">
                    <span>.</span><span>.</span><span>.</span>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
            <form className="chat-input-form" onSubmit={handleSendMessage}>
              <input
                type="text"
                className="text-input chat-input-field"
                placeholder="Ask a question..."
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                disabled={chatLoading}
              />
              <button type="submit" className="primary-button send-btn" disabled={!chatInput.trim() || chatLoading}>
                <Send size={18} />
              </button>
            </form>
          </div>
        )}

        {/* Graph Tab */}
        {activeTab === 'graph' && (
          <div className="tab-pane graph-pane panel-card">
            {mermaidCode ? (
              <MermaidChart code={mermaidCode} />
            ) : (
              <div className="empty-state">
                <Share2 size={48} className="muted-icon" />
                <p>No knowledge graph generated for this course.</p>
              </div>
            )}
          </div>
        )}

        {/* PDF Tab */}
        {activeTab === 'pdf' && (
          <div className="tab-pane pdf-pane">
            <div className="pdf-config-panel panel-card">
              <h3 className="serif-heading">Export as PDF</h3>
              <p className="text-secondary">Choose a visual theme for your exported study guide.</p>
              
              <div className="theme-grid">
                {PDF_THEMES.map(theme => (
                  <ThemeCard 
                    key={theme.name}
                    theme={theme}
                    isSelected={selectedTheme === theme.name}
                    onClick={() => setSelectedTheme(theme.name)}
                  />
                ))}
              </div>
              
              <div className="pdf-actions" style={{ display: 'flex', gap: 'var(--space-md)', flexWrap: 'wrap', alignItems: 'center' }}>
                <button 
                  className="secondary-button" 
                  onClick={() => {
                    const mdFile = courseFiles.find(f => f.name.endsWith('.md'));
                    if (mdFile) {
                      const pdfName = mdFile.name.replace('.md', '.pdf');
                      window.open(`${API_BASE_URL}/static/${activeCourseDir.id}/${encodeURIComponent(pdfName)}`, '_blank');
                    }
                  }}
                  disabled={!generatedPdfPath && !courseFiles.some(f => f.name.endsWith('.pdf'))}
                >
                  <Eye size={18} /> Preview PDF
                </button>
                <button 
                  className="primary-button" 
                  onClick={handleGeneratePdf}
                  disabled={pdfGenerating || !courseFiles.find(f => f.name.endsWith('.md'))}
                >
                  {pdfGenerating ? (
                    <><RefreshCw size={18} className="loader-spin" /> Generating...</>
                  ) : (
                    <><Download size={18} /> Export PDF</>
                  )}
                </button>
                {generatedPdfPath && (
                  <span className="success-text" style={{ marginLeft: 'var(--space-md)' }}>✓ Saved to {generatedPdfPath}</span>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Keyframes Tab */}
        {activeTab === 'keyframes' && (
          <div className="tab-pane keyframes-pane">
            {keyframes.length > 0 ? (
              <div className="keyframes-grid">
                {keyframes.map((frame, idx) => (
                  <div key={idx} className="keyframe-card panel-card">
                    <img src={`${API_BASE_URL}${frame.url}`} alt={frame.name} loading="lazy" />
                    <div className="keyframe-name">{frame.name}</div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-state panel-card">
                <ImageIcon size={48} className="muted-icon" />
                <p>No keyframes extracted for this course.</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default CourseWorkspace;
