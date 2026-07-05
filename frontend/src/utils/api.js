const API_BASE_URL = 'http://localhost:8000';
const WS_BASE_URL = 'ws://localhost:8000';

export const fetchLibrary = async () => {
  const response = await fetch(`${API_BASE_URL}/api/library`);
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
  return await response.json();
};

export const fetchCourse = async (id) => {
  const response = await fetch(`${API_BASE_URL}/api/library/${id}`);
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
  return await response.json();
};

export const fetchNotes = async (id, file) => {
  const response = await fetch(`${API_BASE_URL}/api/library/${id}/notes/${file}`);
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
  return await response.text();
};

export const connectPipelineWebSocket = (onMessage) => {
  let ws;
  let reconnectAttempts = 0;
  const maxReconnectAttempts = 5;

  const connect = () => {
    ws = new WebSocket(`${WS_BASE_URL}/ws/pipeline`);
    
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
  const response = await fetch(`${API_BASE_URL}/api/settings/health`);
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
  return await response.json();
};
