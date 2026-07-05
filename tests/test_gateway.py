import pytest
import httpx
import websockets
from fastapi.testclient import TestClient
from websockets.exceptions import ConnectionClosed
from unittest.mock import patch, MagicMock

from gateway.gateway import app

client = TestClient(app)

@pytest.mark.asyncio
async def test_gateway_routing(monkeypatch):
    class MockResponse:
        def __init__(self, content, status_code, headers=None):
            self.content = content
            self.status_code = status_code
            self.headers = headers or {}
        
        async def aread(self):
            return self.content

    # We need to mock httpx.AsyncClient.send
    async def mock_send(self, request, **kwargs):
        url = str(request.url)
        if "8003/content/library" in url:
            return MockResponse(b'{"library": []}', 200)
        elif "8003/settings/pool" in url:
            return MockResponse(b'{"settings": {}}', 200)
        elif "8003/pdf/export" in url:
            return MockResponse(b'{"pdf": "done"}', 200)
        elif "8002/chat/send" in url:
            return MockResponse(b'{"chat": "hello"}', 200)
        elif "8001/pipeline/start" in url:
            return MockResponse(b'{"pipeline": "started"}', 200)
        elif "8003/static/image.png" in url:
            return MockResponse(b'image data', 200)
        return MockResponse(b"Not Found", 404)

    monkeypatch.setattr(httpx.AsyncClient, "send", mock_send)

    # Test Content
    resp = client.get("/api/content/library")
    assert resp.status_code == 200
    assert resp.json() == {"library": []}
    
    # Test Settings
    resp = client.get("/api/settings/pool")
    assert resp.status_code == 200
    assert resp.json() == {"settings": {}}
    
    # Test PDF
    resp = client.post("/api/pdf/export")
    assert resp.status_code == 200
    assert resp.json() == {"pdf": "done"}

    # Test Chat
    resp = client.post("/api/chat/send")
    assert resp.status_code == 200
    assert resp.json() == {"chat": "hello"}
    
    # Test Pipeline
    resp = client.post("/api/pipeline/start")
    assert resp.status_code == 200
    assert resp.json() == {"pipeline": "started"}

    # Test Static
    resp = client.get("/static/image.png")
    assert resp.status_code == 200
    assert resp.content == b'image data'

def test_cors_headers():
    response = client.options(
        "/api/content/library",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"

@pytest.mark.asyncio
async def test_websocket_proxy():
    mock_ws = MagicMock()
    mock_ws.recv = MagicMock(side_effect=ConnectionClosed(None, None))
    mock_ws.__aenter__.return_value = mock_ws
    
    with patch("websockets.connect", return_value=mock_ws):
        with client.websocket_connect("/ws/pipeline") as websocket:
            websocket.send_text("test")
            # The background task will catch ConnectionClosed and finish
            pass
