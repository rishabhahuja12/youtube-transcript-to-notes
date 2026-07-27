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

from src.library import resolve_course_dir

# -- Path resolution --------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")

# -- Session Manager --------------------------------------------------------


class ChatSessionManager:
    """Thread-safe session manager for maintaining chat sessions per course directory and model."""

    def __init__(self) -> None:
        self._sessions: Dict[str, Any] = {}
        self._lock = threading.Lock()

    def get_session(self, course_dir: str, model: str) -> Any:
        """Retrieve or create a ChatSession instance for a given course directory and model."""
        session_key = f"{course_dir}::{model}"
        with self._lock:
            if SCRIPT_DIR not in sys.path:
                sys.path.append(SCRIPT_DIR)
            from src.chat import ChatSession

            if session_key not in self._sessions:
                self._sessions[session_key] = ChatSession(course_dir, model)
            return self._sessions[session_key]

    def clear(self) -> None:
        """Clear all active chat session histories."""
        with self._lock:
            for session in self._sessions.values():
                if hasattr(session, "clear_history"):
                    session.clear_history()
            self._sessions.clear()


session_manager = ChatSessionManager()

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
    course_dir = resolve_course_dir(req.course_id)
    session = session_manager.get_session(course_dir, req.model)

    try:
        response = session.send(req.message)
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
    """Clear the active chat sessions.
    
    Returns:
        Dict[str, bool]: Success status.
    """
    session_manager.clear()
    return {"success": True}

