import asyncio
import json
import logging
import os
import threading
import uuid
from typing import Optional, Callable, Any
from dataclasses import dataclass, field

from fastapi import APIRouter, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.pipeline import run_pipeline, run_pipeline_from_data
from src.provider_pool import ProviderPool
from src.credentials import get_provider_pool_or_legacy

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

class PipelineResponse(BaseModel):
    """Response schema for pipeline start and cancel endpoints."""
    success: bool
    message: str
    error: Optional[str] = None
    job_id: Optional[str] = None

@dataclass
class PipelineJob:
    job_id: str
    status: str
    cancel_event: threading.Event = field(default_factory=threading.Event)
    worker_thread: Optional[threading.Thread] = None
    result: Optional[dict] = None
    websockets: list[WebSocket] = field(default_factory=list)

# Global state
job_lock = threading.Lock()
active_job: Optional[PipelineJob] = None

async def broadcast_message(job: PipelineJob, message: dict) -> None:
    """Broadcast a JSON message to all connected WebSocket clients for a job.
    
    Args:
        job: The active PipelineJob
        message: The message dictionary to send.
    """
    message["job_id"] = job.job_id
    disconnected = []
    for ws in job.websockets:
        try:
            await ws.send_json(message)
        except Exception as e:
            logging.error(f"Error broadcasting to a websocket: {e}")
            disconnected.append(ws)
    for ws in disconnected:
        if ws in job.websockets:
            job.websockets.remove(ws)

def get_on_log_callback(job: PipelineJob, loop: asyncio.AbstractEventLoop) -> Callable[[str], None]:
    def on_log(message: str) -> None:
        msg = {"type": "log", "message": message}
        asyncio.run_coroutine_threadsafe(broadcast_message(job, msg), loop)
    return on_log

def get_on_progress_callback(job: PipelineJob, loop: asyncio.AbstractEventLoop) -> Callable[[int, int], None]:
    def on_progress(current: int, total: int, step: str = "Processing...") -> None:
        msg = {"type": "progress", "current": current, "total": total, "step": step}
        asyncio.run_coroutine_threadsafe(broadcast_message(job, msg), loop)
    return on_progress
    
def get_on_phase_callback(job: PipelineJob, loop: asyncio.AbstractEventLoop) -> Callable[[str, str], None]:
    def on_phase(phase: str, status: str) -> None:
        msg = {"type": "phase", "phase": phase, "status": status}
        asyncio.run_coroutine_threadsafe(broadcast_message(job, msg), loop)
    return on_phase

def pipeline_worker(job: PipelineJob, request: PipelineStartRequest, pool: ProviderPool, loop: asyncio.AbstractEventLoop) -> None:
    global active_job
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
                msg = {"type": "error", "message": f"Extraction failed: {yt_data.get('status')}"}
                asyncio.run_coroutine_threadsafe(broadcast_message(job, msg), loop)
                job.status = "failed"
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
        
        job.result = result
        job.status = result.get("status", "completed" if result.get("success") else "failed")
        course_path = result.get("course_dir") or (os.path.dirname(result.get("detailed_path", "")) if result.get("detailed_path") else "")
        success = result.get("success", False)
        course_record = None
        if success and course_path and os.path.isdir(course_path):
            from gateway.content_service import _add_library_entry
            course_record = _add_library_entry(course_path)
        msg = {"type": "complete", "success": success, "status": job.status, "course_dir": course_path, "course_record": course_record, "result": result}
        asyncio.run_coroutine_threadsafe(broadcast_message(job, msg), loop)
    except Exception as e:
        logging.error(f"Pipeline worker failed: {e}")
        job.status = "failed"
        msg = {"type": "error", "message": str(e)}
        asyncio.run_coroutine_threadsafe(broadcast_message(job, msg), loop)
    finally:
        with job_lock:
            # We don't clear active_job so /stream clients can still read it if they connect right after.
            # They will see it is finished and maybe disconnect or just receive the final status.
            pass

@router.post("/start", response_model=PipelineResponse)
async def start_pipeline(request: PipelineStartRequest) -> PipelineResponse:
    global active_job
    
    with job_lock:
        if active_job and active_job.status == "running":
            return PipelineResponse(success=False, message="Already running", error="Pipeline already running", job_id=active_job.job_id)
            
        try:
            pool = get_provider_pool_or_legacy()
        except Exception as e:
            return PipelineResponse(success=False, message="Keys error", error=f"Failed to load API keys: {e}")
            
        job_id = uuid.uuid4().hex
        new_job = PipelineJob(job_id=job_id, status="running")
        active_job = new_job

    loop = asyncio.get_running_loop()
    
    worker_thread = threading.Thread(
        target=pipeline_worker,
        args=(new_job, request, pool, loop),
        daemon=True
    )
    new_job.worker_thread = worker_thread
    worker_thread.start()
    
    return PipelineResponse(success=True, message="Pipeline started in background", job_id=job_id)

@router.post("/cancel", response_model=PipelineResponse)
async def cancel_pipeline() -> PipelineResponse:
    with job_lock:
        if not active_job or active_job.status != "running":
            return PipelineResponse(success=False, message="No active job running")
        active_job.cancel_event.set()
        return PipelineResponse(success=True, message="Cancel requested", job_id=active_job.job_id)

@router.websocket("/stream")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    
    with job_lock:
        current_job = active_job
        if current_job:
            current_job.websockets.append(websocket)
            
    if not current_job:
        await websocket.close(reason="No active job")
        return
        
    try:
        while True:
            _ = await websocket.receive_text()
    except WebSocketDisconnect:
        if current_job and websocket in current_job.websockets:
            current_job.websockets.remove(websocket)
    except Exception as e:
        logging.error(f"Error in pipeline stream websocket: {e}")
        if current_job and websocket in current_job.websockets:
            current_job.websockets.remove(websocket)

app.include_router(router)
