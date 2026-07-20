import pytest
import time
import threading
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from gateway.pipeline_service import app
import gateway.pipeline_service as ps
from gateway.pipeline_jobs import job_manager, PipelineJob

client = TestClient(app)

def test_pipeline_start_missing_fields():
    # output_dir is required
    response = client.post("/pipeline/start", json={
        "transcript_path": "a.txt",
        "timestamps_path": "b.txt"
    })
    assert response.status_code == 422 # validation error

def test_pipeline_start_uses_timestamps_path():
    response = client.post("/pipeline/start", json={
        "outline_path": "a.txt",
        "output_dir": "out"
    })
    assert response.status_code == 422 # outline_path should fail validation if not accepted properly

def test_pipeline_start_mocked(monkeypatch):
    from src.provider_pool import ProviderPool
    monkeypatch.setattr("gateway.pipeline_service.get_provider_pool_or_legacy", lambda: ProviderPool([]))
    monkeypatch.setattr("gateway.pipeline_service.threading.Thread", MagicMock())

    
    with job_manager._lock:
        job_manager._current_job = None
    
    response = client.post("/pipeline/start", json={
        "transcript_path": "t.txt",
        "timestamps_path": "t.txt",
        "output_dir": "out"
    })
    
    assert response.status_code == 200
    assert response.json()["success"] == True
    
    # Test duplicate start (HTTP 409 expected)
    response_conflict = client.post("/pipeline/start", json={
        "transcript_path": "t.txt",
        "timestamps_path": "t.txt",
        "output_dir": "out"
    })
    assert response_conflict.status_code == 409


def test_start_conflict_returns_409(monkeypatch):
    with job_manager._lock:
        job_manager._current_job = PipelineJob(job_id="test", status="running")
        
    response = client.post("/pipeline/start", json={
        "timestamps_path": "t.txt",
        "output_dir": "out"
    })
    assert response.status_code == 409

def test_cancel_unknown_job_returns_404():
    response = client.post("/pipeline/unknown-job-id/cancel")
    assert response.status_code == 404

def test_cancel_terminal_job_returns_409():
    with job_manager._lock:
        job = PipelineJob(job_id="test2", status="complete")
        job_manager._current_job = job
        
    response = client.post("/pipeline/test2/cancel")
    assert response.status_code == 409

def test_pipeline_cancel(monkeypatch):
    with job_manager._lock:
        job = PipelineJob(job_id="test3", status="running")
        job_manager._current_job = job
        
    response = client.post("/pipeline/test3/cancel")
    assert response.status_code == 200
    assert response.json()["success"] == True
    assert job.cancel_event.is_set()

def test_websocket_stream_event_journal():
    """Verify that recorded events are stored in the event journal for replay."""
    with job_manager._lock:
        job = PipelineJob(job_id="test-journal", status="running")
        job_manager._current_job = job
        job_manager.record_event(job, {"type": "log", "message": "hello"})
        job_manager.record_event(job, {"type": "phase", "phase": "extraction", "status": "running"})

    # Verify events are in the journal in order
    journal = list(job.event_journal)
    assert len(journal) == 2
    assert journal[0]["type"] == "log"
    assert journal[0]["message"] == "hello"
    assert journal[1]["type"] == "phase"








def test_status_values_are_canonical():
    with job_manager._lock:
        job = PipelineJob(job_id="test-canon", status="running")
        job_manager._current_job = job
    
    # ensure it doesn't emit 'completed' when finalized
    job_manager.finalize_job(job, "complete", {})
    assert job.status == "complete"
