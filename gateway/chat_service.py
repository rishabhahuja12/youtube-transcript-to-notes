"""
FastAPI microservice for Chat functionality.
Runs on Port 8002.
"""
import json
import logging
import os
import sys
import threading
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# -- Path resolution --------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")

# -- Global state -----------------------------------------------------------

_chat_session: Optional[Any] = None  # Lazily created ChatSession
_chat_lock = threading.Lock()

# -- FastAPI app ------------------------------------------------------------

app = FastAPI(
    title="Chat Service",
    version="1.0.0",
    description="Microservice for Chat.",
)

ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://localhost:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════════════════════════════
#  Helper Functions
# ═══════════════════════════════════════════════════════════════════════


def _load_recent_outputs() -> List[str]:
    """Load the list of recently used output directories.

    Returns:
        List of directory path strings from config.json.
    """
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("recent_outputs", [])
        except (json.JSONDecodeError, OSError):
            return []
    return []


def _resolve_course_dir(course_id: int) -> str:
    """Resolve a course index to a validated directory path.

    Args:
        course_id: Integer index into the recent_outputs list.

    Returns:
        Absolute directory path for the course.

    Raises:
        HTTPException: If the index is out of bounds or invalid.
    """
    outputs = _load_recent_outputs()
    if course_id < 0 or course_id >= len(outputs):
        logging.error(f"Invalid course_id requested: {course_id}")
        raise HTTPException(
            status_code=404,
            detail=f"Invalid course_id: {course_id}",
        )
    course_dir = outputs[course_id]
    if not os.path.isdir(course_dir):
        logging.error(f"Course directory does not exist: {course_dir}")
        raise HTTPException(
            status_code=404,
            detail="Course directory does not exist.",
        )
    return course_dir

# ═══════════════════════════════════════════════════════════════════════
#  Pydantic Models
# ═══════════════════════════════════════════════════════════════════════


class ChatRequest(BaseModel):
    """Request body for sending a chat message."""
    course_id: int
    message: str
    model: str = "llama3"

# ═══════════════════════════════════════════════════════════════════════
#  Chat Endpoints
# ═══════════════════════════════════════════════════════════════════════


@app.post("/chat/send")
async def chat_send(req: ChatRequest) -> Dict[str, str]:
    """Send a chat message via local Ollama.

    Creates or reuses a ChatSession for the specified
    course directory based on the course_id.
    
    Args:
        req: ChatRequest containing course_id, message, and model.
        
    Returns:
        Dict[str, str]: AI response message.
    """
    global _chat_session

    course_dir = _resolve_course_dir(req.course_id)

    with _chat_lock:
        if SCRIPT_DIR not in sys.path:
            sys.path.append(SCRIPT_DIR)
        from src.chat import ChatSession

        # -- Create new session if needed
        if (
            _chat_session is None
            or getattr(_chat_session, "notes_dir", None) != course_dir
            or getattr(_chat_session, "ollama_model", None) != req.model
        ):
            _chat_session = ChatSession(
                course_dir, req.model
            )

        try:
            response = _chat_session.send(req.message)
            return {"response": response}
        except ConnectionError as exc:
            logging.error(f"Connection error in chat: {exc}")
            raise HTTPException(
                status_code=503,
                detail=str(exc),
            ) from exc
        except Exception as exc:
            logging.error(f"Chat error: {exc}")
            raise HTTPException(
                status_code=500,
                detail=f"Chat error: {exc}",
            ) from exc


@app.post("/chat/clear")
async def chat_clear() -> Dict[str, bool]:
    """Clear the active chat session.
    
    Returns:
        Dict[str, bool]: Success status.
    """
    global _chat_session
    with _chat_lock:
        if _chat_session is not None:
            _chat_session.clear_history()
        _chat_session = None
    return {"success": True}
