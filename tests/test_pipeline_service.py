import pytest
import time
import threading
from fastapi.testclient import TestClient
from gateway.pipeline_service import app, PipelineJob
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
    def mock_worker(job, request, pool, loop):
        time.sleep(0.5)
        job.status = "completed"
    
    monkeypatch.setattr(ps, "pipeline_worker", mock_worker)
    
    # reset state
    with ps.job_lock:
        ps.active_job = None
    
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
    
    # wait for completion
    time.sleep(0.6)

def test_pipeline_cancel(monkeypatch):
    monkeypatch.setattr(ps, "get_provider_pool_or_legacy", lambda: None)
    
    # start a new job
    with ps.job_lock:
        ps.active_job = PipelineJob(job_id="test", status="running")
        
    response = client.post("/pipeline/cancel")
    assert response.status_code == 200
    assert response.json()["success"] == True
    assert ps.active_job.cancel_event.is_set()

def test_websocket_stream(monkeypatch):
    import asyncio
    from gateway.pipeline_service import broadcast_message
    
    with ps.job_lock:
        ps.active_job = PipelineJob(job_id="test-ws", status="running")
    
    with client.websocket_connect("/pipeline/stream") as websocket:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            
        loop.run_until_complete(broadcast_message(ps.active_job, {"type": "log", "message": "hello from test"}))
        
        data = websocket.receive_json()
        assert data["type"] == "log"
        assert data["message"] == "hello from test"
        assert data["job_id"] == "test-ws"
