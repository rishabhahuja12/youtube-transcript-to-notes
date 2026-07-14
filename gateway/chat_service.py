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
    "http://127.0.0.1:8000",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from gateway.content_service import _resolve_course_dir

# ═══════════════════════════════════════════════════════════════════════
#  Pydantic Models
# ═══════════════════════════════════════════════════════════════════════


class ChatRequest(BaseModel):
    """Request body for sending a chat message."""
    course_id: str
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
