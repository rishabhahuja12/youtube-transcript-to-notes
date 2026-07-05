import pytest
import time
import threading
from fastapi.testclient import TestClient
from gateway.pipeline_service import app, cancel_event
import gateway.pipeline_service as ps

client = TestClient(app)

def test_pipeline_start_missing_fields():
    # output_dir is required
    response = client.post("/pipeline/start", json={
        "transcript_path": "a.txt",
        "timestamps_path": "b.txt"
    })
    assert response.status_code == 422 # validation error

def test_pipeline_start_mocked(monkeypatch):
    
    # Mock to avoid loading real credentials
    monkeypatch.setattr(ps, "get_provider_pool_or_legacy", lambda: None)
    
    # We won't let the thread really run run_pipeline
    def mock_worker(*args, **kwargs):
        time.sleep(0.5)
    
    monkeypatch.setattr(ps, "pipeline_worker", mock_worker)
    
    # reset thread state
    ps.pipeline_thread = None
    ps.cancel_event.clear()
    
    response = client.post("/pipeline/start", json={
        "transcript_path": "t.txt",
        "timestamps_path": "t.txt",
        "output_dir": "out"
    })
    
    assert response.status_code == 200
    assert response.json()["success"] == True
    
    # Test duplicate start
    response = client.post("/pipeline/start", json={
        "transcript_path": "t.txt",
        "timestamps_path": "t.txt",
        "output_dir": "out"
    })
    assert response.status_code == 200
    assert response.json()["success"] == False
    assert "already running" in response.json()["error"]
    
    # reset
    ps.pipeline_thread = None

def test_pipeline_cancel():
    cancel_event.clear()
    assert not cancel_event.is_set()
    
    response = client.post("/pipeline/cancel")
    assert response.status_code == 200
    assert response.json()["success"] == True
    assert cancel_event.is_set()

def test_websocket_stream():
    import asyncio
    from gateway.pipeline_service import broadcast_message
    
    with client.websocket_connect("/pipeline/stream") as websocket:
        try:
            # We must use the current event loop or a new one to run the broadcast
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            
        loop.run_until_complete(broadcast_message({"type": "log", "msg": "hello from test"}))
        
        data = websocket.receive_json()
        assert data["type"] == "log"
        assert data["msg"] == "hello from test"
