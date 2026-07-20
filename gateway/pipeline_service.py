import asyncio
import logging
import os
import threading
from typing import Optional, Callable, Any

from fastapi import APIRouter, FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.pipeline import run_pipeline, run_pipeline_from_data
from src.provider_pool import ProviderPool
from src.credentials import get_provider_pool_or_legacy
from gateway.pipeline_jobs import job_manager, PipelineJob

app = FastAPI(title="Pipeline Service", description="Handles pipeline execution", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", 
        "http://localhost:8000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

router = APIRouter(prefix="/pipeline", tags=["pipeline"])

class PipelineStartRequest(BaseModel):
    """Request schema for starting a pipeline job."""
    transcript_path: str = ""
    timestamps_path: str = ""
    output_dir: str
    video_title: Optional[str] = "Course"
    enable_multimodal: bool = False
    youtube_url: Optional[str] = ""
    enable_kag: bool = False
    # Added fields to support URL pipeline
    is_url_pipeline: bool = False
    transcript_blocks: Optional[list] = []
    chapters: Optional[list] = []
    
    model_config = {
        "extra": "forbid"
    }

class PipelineResponse(BaseModel):
    """Response schema for pipeline start and cancel endpoints."""
    success: bool
    message: str
    error: Optional[str] = None
    job_id: Optional[str] = None

async def broadcast_message(job: PipelineJob, message: dict) -> None:
    """Broadcast a JSON message to all connected WebSocket clients for a job."""
    message["job_id"] = job.job_id
    job_manager.record_event(job, message)
    disconnected = []
    
    # Use a snapshot of subscribers to avoid set mutation errors
    subscribers = set(job.subscribers)
    for ws in subscribers:
        try:
            await ws.send_json(message)
        except Exception as e:
            logging.error(f"Error broadcasting to a websocket: {e}")
            disconnected.append(ws)
    for ws in disconnected:
        if ws in job.subscribers:
            job.subscribers.remove(ws)

def get_on_log_callback(job: PipelineJob, loop: asyncio.AbstractEventLoop) -> Callable[[str], None]:
    def on_log(message: str) -> None:
        msg = {"type": "log", "level": "info", "message": message}
        asyncio.run_coroutine_threadsafe(broadcast_message(job, msg), loop)
    return on_log

def get_on_progress_callback(job: PipelineJob, loop: asyncio.AbstractEventLoop) -> Callable[[int, int], None]:
    def on_progress(current: int, total: int, step: str = "Processing...") -> None:
        msg = {"type": "progress", "current": current, "total": total}
        asyncio.run_coroutine_threadsafe(broadcast_message(job, msg), loop)
    return on_progress
    
def get_on_phase_callback(job: PipelineJob, loop: asyncio.AbstractEventLoop) -> Callable[[str, str], None]:
    def on_phase(phase: str, status: str) -> None:
        msg = {"type": "phase", "phase": phase, "status": status}
        asyncio.run_coroutine_threadsafe(broadcast_message(job, msg), loop)
    return on_phase

def pipeline_worker(job: PipelineJob, request: PipelineStartRequest, pool: ProviderPool, loop: asyncio.AbstractEventLoop) -> None:
    try:
        on_log = get_on_log_callback(job, loop)
        on_progress = get_on_progress_callback(job, loop)
        on_phase = get_on_phase_callback(job, loop)
        
        if request.is_url_pipeline and request.youtube_url:
            on_log("Fetching YouTube data...")
            from src.youtube import extract_from_url
            yt_data = extract_from_url(request.youtube_url, on_log=on_log)
            if yt_data.get("status") in ("transcript_failed", "metadata_failed", "invalid_url"):
                on_log(f"Extraction failed with status: {yt_data.get('status')}. Halting pipeline.")
                msg = {"type": "terminal", "status": "failed", "result": {"error": f"Extraction failed: {yt_data.get('status')}"}}
                job_manager.finalize_job(job, "failed", {"error": f"Extraction failed: {yt_data.get('status')}"})
                asyncio.run_coroutine_threadsafe(broadcast_message(job, msg), loop)
                return

            transcript_blocks = yt_data['transcript_blocks']
            chapters = yt_data['chapters']
            video_title = request.video_title or yt_data.get('metadata', {}).get('title', 'Course')
            
            on_log(f"Got {len(transcript_blocks)} transcript blocks and {len(chapters)} chapters")
            
            result = run_pipeline_from_data(
                transcript_blocks=transcript_blocks,
                chapters=chapters,
                output_dir=request.output_dir,
                pool=pool,
                cancel_event=job.cancel_event,
                on_log=on_log,
                on_progress=on_progress,
                video_title=video_title,
                enable_multimodal=request.enable_multimodal,
                youtube_url=request.youtube_url,
                enable_kag=request.enable_kag,
                on_phase=on_phase
            )
        elif request.is_url_pipeline:
            result = run_pipeline_from_data(
                transcript_blocks=request.transcript_blocks,
                chapters=request.chapters,
                output_dir=request.output_dir,
                pool=pool,
                cancel_event=job.cancel_event,
                on_log=on_log,
                on_progress=on_progress,
                video_title=request.video_title,
                enable_multimodal=request.enable_multimodal,
                youtube_url=request.youtube_url,
                enable_kag=request.enable_kag,
                on_phase=on_phase
            )
        else:
            result = run_pipeline(
                transcript_path=request.transcript_path,
                timestamps_path=request.timestamps_path,
                output_dir=request.output_dir,
                pool=pool,
                cancel_event=job.cancel_event,
                on_log=on_log,
                on_progress=on_progress,
                video_title=request.video_title,
                enable_multimodal=request.enable_multimodal,
                youtube_url=request.youtube_url,
                enable_kag=request.enable_kag,
                on_phase=on_phase
            )
        
        status = result.get("status", "complete" if result.get("success") else "failed")
        course_path = result.get("course_dir") or (os.path.dirname(result.get("detailed_path", "")) if result.get("detailed_path") else "")
        success = result.get("success", False)
        course_record = None
        if success and course_path and os.path.isdir(course_path):
            from gateway.content_service import _add_library_entry
            course_record = _add_library_entry(course_path)
            result["course_record"] = course_record
        
        job_manager.finalize_job(job, status, result)
        msg = {"type": "terminal", "status": status, "result": result}
        asyncio.run_coroutine_threadsafe(broadcast_message(job, msg), loop)
    except Exception as e:
        logging.error(f"Pipeline worker failed: {e}")
        error_result = {"error": str(e)}
        job_manager.finalize_job(job, "failed", error_result)
        msg = {"type": "terminal", "status": "failed", "result": error_result}
        asyncio.run_coroutine_threadsafe(broadcast_message(job, msg), loop)


@router.post("/start", response_model=PipelineResponse)
async def start_pipeline(request: PipelineStartRequest) -> PipelineResponse:
    try:
        new_job = job_manager.create_job()
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
        
    try:
        pool = get_provider_pool_or_legacy()
    except Exception as e:
        # if fails, clean up job? It will just stay running until timeout, but let's finalize it
        job_manager.finalize_job(new_job, "failed", {"error": f"Failed to load API keys: {e}"})
        return PipelineResponse(success=False, message="Keys error", error=f"Failed to load API keys: {e}")

    loop = asyncio.get_running_loop()
    worker_thread = threading.Thread(
        target=pipeline_worker,
        args=(new_job, request, pool, loop),
        daemon=True
    )
    new_job.worker_thread = worker_thread
    worker_thread.start()
    
    return PipelineResponse(success=True, message="Pipeline started in background", job_id=new_job.job_id)

@router.post("/{job_id}/cancel", response_model=PipelineResponse)
async def cancel_pipeline(job_id: str) -> PipelineResponse:
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    if job.status != "running":
        raise HTTPException(status_code=409, detail="Job is already in a terminal state")
        
    job.cancel_event.set()
    return PipelineResponse(success=True, message="Cancel requested", job_id=job.job_id)

@router.websocket("/stream/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str) -> None:
    job = job_manager.get_job(job_id)
    if not job:
        await websocket.close(code=4004, reason="Job not found")
        return

    await websocket.accept()
    
    # Send snapshot
    await websocket.send_json({
        "type": "snapshot",
        "job_id": job.job_id,
        "status": job.status,
        "result": job.result
    })
    
    # Replay events
    for event in list(job.event_journal):
        await websocket.send_json(event)
        
    job.subscribers.add(websocket)
    
    # If job is already terminal, close after replay — no need to keep the socket open
    if job.status in ("complete", "degraded", "failed", "cancelled"):
        job.subscribers.discard(websocket)
        await websocket.close()
        return
        
    try:
        while True:
            msg = await websocket.receive()
            if msg.get("type") == "websocket.disconnect":
                break
    except Exception:
        pass
    finally:
        job.subscribers.discard(websocket)





app.include_router(router)
