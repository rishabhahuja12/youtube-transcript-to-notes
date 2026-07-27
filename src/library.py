"""
Library management and course output metadata helpers.

Provides thread-safe access to library configuration entries, badge detection,
and course directory resolution for microservices and pipeline execution.
"""

import json
import logging
import os
import platform
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from fastapi import HTTPException
from pydantic import BaseModel

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")


class CourseBadges(BaseModel):
    """Feature badges for a course."""
    vision: bool = False
    kag: bool = False
    pdf: bool = False


def _with_library_lock(func):
    """Execute a function holding a cross-process lock on config.json.lock"""
    def wrapper(*args, **kwargs):
        lock_path = CONFIG_PATH + ".lock"
        if platform.system() == "Windows":
            import msvcrt
            with open(lock_path, "a") as f:
                msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    return func(*args, **kwargs)
                finally:
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            with open(lock_path, "a") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    return func(*args, **kwargs)
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    return wrapper


@_with_library_lock
def load_library_entries() -> List[Dict[str, Any]]:
    """Load the list of library entries, migrating recent_outputs if needed.

    Returns:
        List[Dict[str, Any]]: List of library course entry dictionaries.
    """
    if not os.path.exists(CONFIG_PATH):
        return []
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        entries = data.get("library", [])
        dirty = False

        # Migrate recent_outputs if they exist
        if "recent_outputs" in data:
            for p in data["recent_outputs"]:
                if not any(e.get("path") == p for e in entries):
                    entries.append({
                        "id": f"course_{uuid.uuid4().hex}",
                        "path": p,
                        "title": os.path.basename(p) or p,
                        "status": "complete",
                        "badges": {"vision": False, "kag": False, "pdf": False},
                        "created_at": datetime.utcnow().isoformat() + "Z"
                    })
            del data["recent_outputs"]
            data["library"] = entries
            dirty = True

        if dirty:
            fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(CONFIG_PATH), text=True)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            os.replace(tmp_path, CONFIG_PATH)

        return entries
    except (json.JSONDecodeError, OSError):
        return []


@_with_library_lock
def add_library_entry(entry_data: Dict[str, Any]) -> Dict[str, Any]:
    """Add or update an output directory path in the library.

    Args:
        entry_data: Course metadata dictionary containing path and title.

    Returns:
        Dict[str, Any]: Saved entry dictionary.
    """
    path = entry_data.get("path")
    if not path:
        return {}

    path = os.path.abspath(path)
    entry_data["path"] = path

    data = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    entries = data.get("library", [])
    # Remove existing entry with same path if it exists
    entries = [e for e in entries if e.get("path") != path]

    entries.insert(0, entry_data)
    data["library"] = entries

    try:
        fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(CONFIG_PATH), text=True)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        os.replace(tmp_path, CONFIG_PATH)
    except OSError as e:
        logging.error(f"Error saving library: {e}")

    return entry_data


def resolve_course_dir(course_id: str) -> str:
    """Resolve a course ID to a validated directory path.

    Args:
        course_id: Unique course string identifier.

    Returns:
        str: Absolute filesystem path to course directory.

    Raises:
        HTTPException: If course ID is not found or directory does not exist.
    """
    entries = load_library_entries()
    for entry in entries:
        if str(entry.get("id")) == str(course_id):
            course_dir = entry.get("path")
            if not os.path.isdir(course_dir):
                raise HTTPException(status_code=404, detail="Course directory does not exist.")
            return course_dir
    raise HTTPException(status_code=404, detail=f"Invalid course_id: {course_id}")


def detect_badges(course_dir: str) -> CourseBadges:
    """Detect which features were used for a course.

    Args:
        course_dir: Path to the course output directory.

    Returns:
        CourseBadges: Pydantic model with vision/kag/pdf flags.
    """
    try:
        files = os.listdir(course_dir)
    except OSError:
        return CourseBadges()

    has_vision = any(f.lower().endswith((".jpg", ".png", ".jpeg")) for f in files)
    has_kag = any("_knowledge_graph" in f.lower() for f in files)
    has_pdf = any(f.lower().endswith(".pdf") for f in files)

    return CourseBadges(vision=has_vision, kag=has_kag, pdf=has_pdf)
