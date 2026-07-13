import asyncio
import json
import logging
import os
import threading
from typing import Optional, Callable, Any

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


# Global state
cancel_event = threading.Event()
active_websockets: list[WebSocket] = []
pipeline_thread: Optional[threading.Thread] = None

async def broadcast_message(message: dict) -> None:
    """Broadcast a JSON message to all connected WebSocket clients.
    
    Args:
        message: The message dictionary to send.
    """
    disconnected = []
    for ws in active_websockets:
        try:
            await ws.send_json(message)
        except Exception as e:
            logging.error(f"Error broadcasting to a websocket: {e}")
            disconnected.append(ws)
    for ws in disconnected:
        if ws in active_websockets:
            active_websockets.remove(ws)

def get_on_log_callback(loop: asyncio.AbstractEventLoop) -> Callable[[str], None]:
    """Create a thread-safe logging callback for the pipeline.
    
    Args:
        loop: The asyncio event loop running the fastAPI app.
        
    Returns:
        A callable that takes a string message and broadcasts it.
    """
    def on_log(message: str) -> None:
        msg = {"type": "log", "message": message}
        asyncio.run_coroutine_threadsafe(broadcast_message(msg), loop)
    return on_log

def get_on_progress_callback(loop: asyncio.AbstractEventLoop) -> Callable[[int, int], None]:
    """Create a thread-safe progress callback for the pipeline.
    
    Args:
        loop: The asyncio event loop running the fastAPI app.
        
    Returns:
        A callable that takes current and total ints and broadcasts them.
    """
    def on_progress(current: int, total: int, step: str = "Processing...") -> None:
        msg = {"type": "progress", "current": current, "total": total, "step": step}
        asyncio.run_coroutine_threadsafe(broadcast_message(msg), loop)
    return on_progress

def pipeline_worker(request: PipelineStartRequest, pool: ProviderPool, loop: asyncio.AbstractEventLoop) -> None:
    """Run the pipeline in a background thread.
    
    Args:
        request: The pipeline start request parameters.
        pool: The LLM provider pool to use.
        loop: The asyncio event loop for broadcasting updates.
    """
    global active_websockets
    try:
        on_log = get_on_log_callback(loop)
        on_progress = get_on_progress_callback(loop)
        
        if request.is_url_pipeline and request.youtube_url:
            # Fetch transcript and chapters from YouTube first
            on_log("Fetching YouTube data...")
            from src.youtube import extract_from_url
            yt_data = extract_from_url(request.youtube_url, on_log=on_log)
            if yt_data.get("status") == "transcript_failed":
                on_log("Transcript extraction failed. Halting pipeline.")
                msg = {"type": "error", "message": "Transcript extraction failed"}
                asyncio.run_coroutine_threadsafe(broadcast_message(msg), loop)
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
                cancel_event=cancel_event,
                on_log=on_log,
                on_progress=on_progress,
                video_title=video_title,
                enable_multimodal=request.enable_multimodal,
                youtube_url=request.youtube_url,
                enable_kag=request.enable_kag
            )
        elif request.is_url_pipeline:
            result = run_pipeline_from_data(
                transcript_blocks=request.transcript_blocks,
                chapters=request.chapters,
                output_dir=request.output_dir,
                pool=pool,
                cancel_event=cancel_event,
                on_log=on_log,
                on_progress=on_progress,
                video_title=request.video_title,
                enable_multimodal=request.enable_multimodal,
                youtube_url=request.youtube_url,
                enable_kag=request.enable_kag
            )
        else:
            result = run_pipeline(
                transcript_path=request.transcript_path,
                timestamps_path=request.timestamps_path,
                output_dir=request.output_dir,
                pool=pool,
                cancel_event=cancel_event,
                on_log=on_log,
                on_progress=on_progress,
                video_title=request.video_title,
                enable_multimodal=request.enable_multimodal,
                youtube_url=request.youtube_url,
                enable_kag=request.enable_kag
            )
        
        course_path = result.get("course_dir") or (os.path.dirname(result.get("detailed_path", "")) if result.get("detailed_path") else "")
        success = result.get("success", False)
        if success and course_path and os.path.isdir(course_path):
            from gateway.content_service import _add_recent_output
            _add_recent_output(course_path)
        msg = {"type": "complete", "success": success, "course_dir": course_path, "result": result}
        asyncio.run_coroutine_threadsafe(broadcast_message(msg), loop)
    except Exception as e:
        logging.error(f"Pipeline worker failed: {e}")
        msg = {"type": "error", "message": str(e)}
        asyncio.run_coroutine_threadsafe(broadcast_message(msg), loop)

@router.post("/start", response_model=PipelineResponse)
async def start_pipeline(request: PipelineStartRequest) -> PipelineResponse:
    """Start the video transcript pipeline in a background thread.
    
    Args:
        request: Pipeline start configuration.
        
    Returns:
        PipelineResponse: Success status and message.
    """
    global pipeline_thread
    global cancel_event
    
    if pipeline_thread and pipeline_thread.is_alive():
        return PipelineResponse(success=False, message="Already running", error="Pipeline already running")
        
    cancel_event.clear()
    
    try:
        pool = get_provider_pool_or_legacy()
    except Exception as e:
        return PipelineResponse(success=False, message="Keys error", error=f"Failed to load API keys: {e}")
        
    loop = asyncio.get_running_loop()
    
    pipeline_thread = threading.Thread(
        target=pipeline_worker,
        args=(request, pool, loop),
        daemon=True
    )
    pipeline_thread.start()
    
    return PipelineResponse(success=True, message="Pipeline started in background")

@router.post("/cancel", response_model=PipelineResponse)
async def cancel_pipeline() -> PipelineResponse:
    """Request the running pipeline to cancel execution.
    
    Returns:
        PipelineResponse: Success status and message.
    """
    global cancel_event
    cancel_event.set()
    return PipelineResponse(success=True, message="Cancel requested")

@router.websocket("/stream")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for streaming pipeline logs and progress.
    
    Args:
        websocket: The FastAPI websocket connection.
    """
    await websocket.accept()
    active_websockets.append(websocket)
    try:
        while True:
            # Keep connection alive, wait for client to disconnect or ping
            _ = await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in active_websockets:
            active_websockets.remove(websocket)
    except Exception as e:
        logging.error(f"Error in pipeline stream websocket: {e}")
        if websocket in active_websockets:
            active_websockets.remove(websocket)

app.include_router(router)
