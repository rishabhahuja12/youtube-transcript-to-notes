export const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const WS_BASE_URL = API_BASE_URL.replace(/^http/, 'ws');

export const fetchLibrary = async () => {
  const response = await fetch(`${API_BASE_URL}/api/content/library`, {
    signal: AbortSignal.timeout(30000)
  });
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
  return await response.json();
};

export const fetchCourse = async (id) => {
  const response = await fetch(`${API_BASE_URL}/api/content/course/${id}/files`, {
    signal: AbortSignal.timeout(30000)
  });
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
  return await response.json();
};

export const fetchNotes = async (id, file) => {
  const response = await fetch(`${API_BASE_URL}/api/content/course/${id}/notes/${file}`, {
    signal: AbortSignal.timeout(30000)
  });
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
  const data = await response.json();
  return data.content;
};

export const addCourseToLibrary = async (url) => {
  const response = await fetch(`${API_BASE_URL}/api/content/library/add`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ path: url }),
    signal: AbortSignal.timeout(30000)
  });
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
  return await response.json();
};

export const startPipeline = async (payload) => {
  const response = await fetch(`${API_BASE_URL}/api/pipeline/start`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(30000)
  });
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
  return await response.json();
};

export const fetchCourseGraph = async (id) => {
  const response = await fetch(`${API_BASE_URL}/api/content/course/${id}/graph`, {
    signal: AbortSignal.timeout(30000)
  });
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
  return await response.json();
};

export const fetchCourseKeyframes = async (id) => {
  const response = await fetch(`${API_BASE_URL}/api/content/course/${id}/keyframes`, {
    signal: AbortSignal.timeout(30000)
  });
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
  return await response.json();
};

export const connectPipelineWebSocket = (onMessage) => {
  let ws;
  let reconnectAttempts = 0;
  const maxReconnectAttempts = 5;

  const connect = () => {
    ws = new WebSocket(`${WS_BASE_URL}/api/pipeline/stream`);
    
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessage(data);
      } catch (error) {
        console.error("WebSocket message parsing error:", error);
      }
    };
    
    ws.onclose = () => {
      if (reconnectAttempts < maxReconnectAttempts) {
        const timeout = Math.pow(2, reconnectAttempts) * 1000;
        setTimeout(connect, timeout);
        reconnectAttempts++;
      } else {
        console.error("WebSocket max reconnect attempts reached");
      }
    };

    ws.onerror = (error) => {
      console.error("WebSocket error:", error);
      ws.close(); // trigger onclose
    };
  };

  connect();
  
  return {
    close: () => {
      reconnectAttempts = maxReconnectAttempts; // prevent reconnect
      if (ws) ws.close();
    }
  };
};

export const fetchOllamaStatus = async () => {
  const response = await fetch(`${API_BASE_URL}/api/settings/health`, {
    signal: AbortSignal.timeout(30000)
  });
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
  return await response.json();
};

export const fetchPoolSettings = async () => {
  const response = await fetch(`${API_BASE_URL}/api/settings/pool`, {
    signal: AbortSignal.timeout(30000)
  });
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
  return await response.json();
};

export const addPoolKey = async (payload) => {
  const response = await fetch(`${API_BASE_URL}/api/settings/pool`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(30000)
  });
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
  return await response.json();
};

export const deletePoolKey = async (index) => {
  const response = await fetch(`${API_BASE_URL}/api/settings/pool/${index}`, {
    method: 'DELETE',
    signal: AbortSignal.timeout(30000)
  });
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
  return await response.json();
};

export const chatWithCourse = async (id, message, model = 'llama3') => {
  const response = await fetch(`${API_BASE_URL}/api/chat/send`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ course_id: id, message, model }),
    signal: AbortSignal.timeout(60000)
  });
  if (!response.ok) {
    let errMsg = `HTTP error! status: ${response.status}`;
    try {
      const errData = await response.json();
      errMsg = errData.detail || errData.message || errMsg;
    } catch (e) {}
    throw new Error(errMsg);
  }
  return await response.json();
};

export const clearChat = async () => {
  const response = await fetch(`${API_BASE_URL}/api/chat/clear`, {
    method: 'POST',
  });
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
  return await response.json();
};

export const generatePdf = async (id, filename, theme = 'Textbook') => {
  const response = await fetch(`${API_BASE_URL}/api/pdf/export`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ course_id: id, filename, theme }),
    signal: AbortSignal.timeout(60000)
  });
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
  return await response.json();
};

export const installPlaywright = async () => {
  const response = await fetch(`${API_BASE_URL}/api/settings/playwright/install`, {
    method: 'POST',
    signal: AbortSignal.timeout(300000) // 5 minutes timeout for installation
  });
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
  return await response.json();
};

export const fetchYouTubeStatus = async () => {
  const response = await fetch(`${API_BASE_URL}/api/settings/youtube/status`, {
    signal: AbortSignal.timeout(30000)
  });
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
  return await response.json();
};

export const connectYouTube = async () => {
  const response = await fetch(`${API_BASE_URL}/api/settings/youtube/connect`, {
    method: 'POST',
    signal: AbortSignal.timeout(300000)
  });
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
  return await response.json();
};

export const disconnectYouTube = async () => {
  const response = await fetch(`${API_BASE_URL}/api/settings/youtube/disconnect`, {
    method: 'POST',
    signal: AbortSignal.timeout(30000)
  });
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
  return await response.json();
  return await response.json();
};

export const browseDirectory = async () => {
  const response = await fetch(`${API_BASE_URL}/api/content/browse-directory`, {
    signal: AbortSignal.timeout(300000) // 5 minutes timeout for user to pick folder
  });
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
  return await response.json();
};
