"""
FastAPI microservice for Content Management.
Runs on Port 8003.
"""
import json
import logging
import os
import subprocess
import sys
import tempfile
import urllib.request
import uuid
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
import platform
from datetime import datetime


from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

# -- Path resolution --------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from src.library import (
    CONFIG_PATH,
    CourseBadges,
    _with_library_lock,
    load_library_entries as _load_library_entries,
    add_library_entry as _add_library_entry,
    remove_library_entry as _remove_library_entry,
    resolve_course_dir as _resolve_course_dir,
    detect_badges as _detect_badges,
)
from src.pdf import (
    convert_md_to_pdf as _convert_md_to_pdf,
    get_shared_pdf_css as _get_shared_pdf_css,
)


# -- FastAPI app ------------------------------------------------------------

app = FastAPI(
    title="Content Service",
    version="1.0.0",
    description="Microservice for content management.",
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


class LibraryAddRequest(BaseModel):
    """Request body for adding a path to the library."""
    path: str


class PdfExportRequest(BaseModel):
    """Request body for exporting markdown to PDF."""
    course_id: str
    filename: str
    theme: str = "Textbook"


class PoolStoreRequest(BaseModel):
    """Request body for storing provider pool config."""
    pool: list


class CourseInfo(BaseModel):
    """Summary info for a single course in the library."""
    id: str
    title: str
    path: str
    date: str
    badges: CourseBadges
    status: str = "complete"
    created_at: str = ""



class FileInfo(BaseModel):
    """Metadata for a file inside a course directory."""
    name: str
    type: str
    size: int


class KeyframeInfo(BaseModel):
    """A single keyframe image reference."""
    name: str
    url: str


class HealthStatus(BaseModel):
    """System health check results."""
    ollama: bool
    playwright: bool
    keyring: bool

# ═══════════════════════════════════════════════════════════════════════
#  Helper Functions
# ═══════════════════════════════════════════════════════════════════════



def resolve_within_root(root: Path, user_path: str) -> Path:
    """Resolve and validate user path to stay relative to root directory."""
    candidate = (root / str(user_path)).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise HTTPException(status_code=403, detail="Invalid path.")
    return candidate


def _check_ollama() -> bool:
    """Check if the local Ollama server is running.

    Returns:
        True if Ollama responds on localhost:11434.
    """
    try:
        req = urllib.request.urlopen("http://localhost:11434", timeout=2)
        return req.getcode() == 200
    except Exception:
        return False


def _check_playwright() -> bool:
    """Check if Playwright Chromium executable is available without booting the driver."""
    import platform
    try:
        system = platform.system()
        if system == "Windows":
            base = os.path.expanduser("~\\AppData\\Local\\ms-playwright")
        elif system == "Darwin":
            base = os.path.expanduser("~/Library/Caches/ms-playwright")
        else:
            base = os.path.expanduser("~/.cache/ms-playwright")
            
        if not os.path.exists(base):
            return False
            
        for folder in os.listdir(base):
            if folder.startswith("chromium-"):
                return True
        return False
    except Exception:
        return False


def _check_keyring() -> bool:
    """Check if keyring secure storage is available and functional.

    Returns:
        True if keyring is installed and working.
    """
    try:
        if SCRIPT_DIR not in sys.path:
            sys.path.append(SCRIPT_DIR)
        from src.credentials import is_keyring_available
        return is_keyring_available()
    except Exception:
        return False


def _mask_key(key: str) -> str:
    """Mask an API key for safe display.

    Args:
        key: The raw API key.

    Returns:
        Masked string. If length <= 8, returns all asterisks. Otherwise first 8 chars + '...'.
    """
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return key[:8] + "..."

# ═══════════════════════════════════════════════════════════════════════
#  Library Endpoints
# ═══════════════════════════════════════════════════════════════════════


@app.get("/content/library", response_model=List[CourseInfo])
async def get_library() -> List[CourseInfo]:
    """Return the list of courses in the library.
    
    Returns:
        List[CourseInfo]: List of course objects with metadata.
    """
    entries = _load_library_entries()
    courses: List[CourseInfo] = []
    for entry in entries:
        path = entry.get("path", "")
        title = entry.get("title", os.path.basename(path) or path)
        date = ""
        try:
            stat = os.stat(path)
            from datetime import datetime
            date = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d")
        except OSError:
            date = "Unknown"
        badges = _detect_badges(path)
        courses.append(CourseInfo(
            id=entry.get("id"),
            title=title,
            path=path,
            date=date,
            badges=badges,
            status=entry.get("status", "complete"),
            created_at=entry.get("created_at", "")
        ))
    return courses


@app.post("/content/library/add")
async def add_library_entry(req: LibraryAddRequest) -> Dict[str, Any]:
    """Add a directory path to the library's recent outputs."""
    import uuid
    from datetime import datetime
    
    path = os.path.abspath(req.path)
    title = os.path.basename(path) or path
    badges = _detect_badges(path)
    
    entry_data = {
        "id": f"course_{uuid.uuid4().hex}",
        "path": path,
        "title": title,
        "status": "complete",
        "badges": badges.model_dump() if hasattr(badges, "model_dump") else badges.dict(),
        "created_at": datetime.utcnow().isoformat() + "Z"
    }
    
    entry = _add_library_entry(entry_data)
    return entry


@app.delete("/content/library/{course_id}")
async def delete_library_entry(course_id: str) -> Dict[str, bool]:
    """Remove a course from the library."""
    success = _remove_library_entry(course_id)
    if not success:
        raise HTTPException(status_code=404, detail="Course not found.")
    return {"success": True}

@app.get("/content/browse-directory")
def browse_directory(path: Optional[str] = None) -> Dict[str, str]:
    """Open native OS folder picker dialog or return resolved path."""
    if path and os.path.exists(path):
        return {"path": os.path.abspath(path)}

    if sys.platform == "win32":
        import base64
        ps_code = """
Add-Type -AssemblyName System.Windows.Forms
$f = New-Object System.Windows.Forms.FolderBrowserDialog
$f.Description = "Select Output Directory"
if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
    Write-Output $f.SelectedPath
}
"""
        encoded = base64.b64encode(ps_code.encode("utf-16le")).decode("utf-8")
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-EncodedCommand", encoded],
                capture_output=True,
                text=True,
                timeout=120
            )
            selected = res.stdout.strip()
            if selected and os.path.exists(selected):
                return {"path": os.path.abspath(selected)}
        except Exception as exc:
            logging.warning(f"PowerShell folder dialog failed: {exc}")

    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        selected = filedialog.askdirectory(title="Select Output Directory")
        root.destroy()
        if selected:
            return {"path": os.path.abspath(selected)}
    except Exception as exc:
        logging.warning(f"Tkinter folder dialog failed: {exc}")

    fallback = os.path.abspath(os.path.join(SCRIPT_DIR, "output"))
    return {"path": fallback}


@app.get("/content/user-presets")
def get_user_presets() -> Dict[str, str]:
    """Return common user directory paths for quick preset selection."""
    home = os.path.expanduser("~")
    default_out = os.path.abspath(os.path.join(SCRIPT_DIR, "output"))
    desktop = os.path.join(home, "Desktop")
    documents = os.path.join(home, "Documents")
    downloads = os.path.join(home, "Downloads")

    presets = {
        "Default Output": default_out,
        "Desktop": os.path.abspath(desktop) if os.path.exists(desktop) else home,
        "Documents": os.path.abspath(documents) if os.path.exists(documents) else home,
        "Downloads": os.path.abspath(downloads) if os.path.exists(downloads) else home,
    }
    return presets


def _get_windows_drives() -> List[Dict[str, str]]:
    """Return all active logical drive letters on Windows using kernel32 API."""
    drives = []
    if sys.platform == "win32":
        try:
            import ctypes
            import string
            bitmask = ctypes.windll.kernel32.GetLogicalDrives()
            for letter in string.ascii_uppercase:
                if bitmask & 1:
                    d = f"{letter}:\\"
                    drives.append({"name": f"Local Disk ({letter}:)", "path": d})
                bitmask >>= 1
        except Exception as exc:
            logging.warning(f"ctypes drive detection failed: {exc}")
            import string
            for letter in string.ascii_uppercase:
                d = f"{letter}:\\"
                if os.path.exists(d):
                    drives.append({"name": f"Local Disk ({letter}:)", "path": d})
    return drives


@app.get("/content/list-directories")
def list_directories(path: Optional[str] = None) -> Dict[str, Any]:
    """Safely list available subdirectories on disk for in-app folder picker."""
    all_drives = _get_windows_drives() if sys.platform == "win32" else []

    if not path or not path.strip():
        if sys.platform == "win32":
            return {
                "current_path": "",
                "parent_path": "",
                "subdirectories": all_drives,
                "drives": all_drives
            }
        else:
            path = "/"

    target_path = os.path.abspath(path.strip())
    if not os.path.exists(target_path) or not os.path.isdir(target_path):
        target_path = os.path.expanduser("~")

    parent_path = os.path.dirname(target_path)
    if parent_path == target_path or (sys.platform == "win32" and len(target_path) <= 3 and target_path.endswith(":\\")):
        parent_path = ""

    subdirs = []
    try:
        with os.scandir(target_path) as entries:
            for entry in entries:
                try:
                    if entry.name.startswith('$') or entry.name.startswith('.'):
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        subdirs.append({
                            "name": entry.name,
                            "path": os.path.abspath(entry.path)
                        })
                except (PermissionError, OSError):
                    continue
    except (PermissionError, OSError) as exc:
        logging.warning(f"Permission error scanning directory {target_path}: {exc}")

    subdirs.sort(key=lambda s: s["name"].lower())

    return {
        "current_path": target_path,
        "parent_path": parent_path,
        "subdirectories": subdirs,
        "drives": all_drives
    }


@app.get("/content/browse-file")
def browse_file(path: Optional[str] = None) -> Dict[str, str]:
    """Open native OS file picker dialog or return resolved path."""
    if path and os.path.isfile(path):
        return {"path": os.path.abspath(path)}

    if sys.platform == "win32":
        import base64
        ps_code = """
Add-Type -AssemblyName System.Windows.Forms
$f = New-Object System.Windows.Forms.OpenFileDialog
$f.Title = "Select File"
if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
    Write-Output $f.FileName
}
"""
        encoded = base64.b64encode(ps_code.encode("utf-16le")).decode("utf-8")
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-EncodedCommand", encoded],
                capture_output=True,
                text=True,
                timeout=120
            )
            selected = res.stdout.strip()
            if selected and os.path.isfile(selected):
                return {"path": os.path.abspath(selected)}
        except Exception as exc:
            logging.warning(f"PowerShell file dialog failed: {exc}")

    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        selected = filedialog.askopenfilename(title="Select File")
        root.destroy()
        if selected:
            return {"path": os.path.abspath(selected)}
    except Exception as exc:
        logging.warning(f"Tkinter file dialog failed: {exc}")

    return {"path": ""}

# ═══════════════════════════════════════════════════════════════════════
#  Course Endpoints
# ═══════════════════════════════════════════════════════════════════════


@app.get("/content/course/{id}/files", response_model=List[FileInfo])
async def get_course_files(id: str) -> List[FileInfo]:
    """List files in a course output directory.
    
    Args:
        id: Integer index of the course in recent outputs.
        
    Returns:
        List[FileInfo]: List of files in the course directory.
    """
    course_dir = _resolve_course_dir(id)
    files: List[FileInfo] = []
    try:
        for name in sorted(os.listdir(course_dir)):
            full = os.path.join(course_dir, name)
            ftype = "directory" if os.path.isdir(full) else "file"
            size = os.path.getsize(full) if os.path.isfile(full) else 0
            files.append(FileInfo(name=name, type=ftype, size=size))
    except OSError as exc:
        logging.error(f"Error reading directory {course_dir}: {exc}")
        raise HTTPException(status_code=500, detail=f"Error reading directory: {exc}") from exc
    return files


@app.get("/content/course/{id}/notes/{file}")
async def get_course_notes(id: str, file: str) -> Dict[str, str]:
    """Read and return a markdown file from the course directory.
    
    Args:
        id: Course UUID.
        file: The requested filename.
        
    Returns:
        Dict[str, str]: The content of the markdown file.
    """
    course_dir = _resolve_course_dir(id)
    course_root = Path(course_dir).resolve()
    try:
        requested_path = resolve_within_root(course_root, file)
    except Exception:
        logging.error(f"Path traversal blocked: {file}")
        raise HTTPException(status_code=403, detail="Invalid filename.")
        
    if not requested_path.name.endswith(".md"):
        logging.error(f"Non-markdown file requested: {requested_path.name}")
        raise HTTPException(status_code=400, detail="Only .md files can be read.")
        
    filepath = str(requested_path)
    if not os.path.isfile(filepath):
        logging.error(f"Notes file not found: {filepath}")
        raise HTTPException(status_code=404, detail=f"File not found: {file}")
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError as exc:
        logging.error(f"Error reading file {filepath}: {exc}")
        raise HTTPException(status_code=500, detail=f"Error reading file: {exc}") from exc
    return {"content": content}


@app.get("/content/course/{id}/graph")
async def get_course_graph(id: str) -> Dict[str, str]:
    """Read and return knowledge graph HTML from course dir.
    
    Args:
        id: Integer index of the course.
        
    Returns:
        Dict[str, str]: The HTML content of the knowledge graph.
    """
    course_dir = _resolve_course_dir(id)
    course_root = Path(course_dir).resolve()
    graph_file = None
    try:
        for name in os.listdir(course_dir):
            if "_knowledge_graph" in name.lower() and name.endswith(".html"):
                candidate = resolve_within_root(course_root, name)
                if candidate.is_file():
                    graph_file = str(candidate)
                    break
    except Exception as exc:
        logging.error(f"Error reading directory {course_dir} for graph: {exc}")
        pass

    if not graph_file:
        return {"html": ""}

    try:
        with open(graph_file, "r", encoding="utf-8") as f:
            return {"html": f.read()}
    except OSError as exc:
        logging.error(f"Error reading graph file {graph_file}: {exc}")
        raise HTTPException(status_code=500, detail=f"Error reading graph: {exc}") from exc


@app.get("/content/course/{id}/keyframes", response_model=List[KeyframeInfo])
async def get_course_keyframes(id: str) -> List[KeyframeInfo]:
    """List keyframe images in the course directory.
    
    Args:
        id: Integer index of the course.
        
    Returns:
        List[KeyframeInfo]: List of keyframe images.
    """
    course_dir = _resolve_course_dir(id)
    keyframes: List[KeyframeInfo] = []
    image_exts = (".jpg", ".jpeg", ".png")
    try:
        for name in sorted(os.listdir(course_dir)):
            if name.lower().endswith(image_exts):
                url = f"/static/{id}/{name}"
                keyframes.append(KeyframeInfo(name=name, url=url))
    except OSError as exc:
        logging.error(f"Error reading directory {course_dir} for keyframes: {exc}")
        pass
    return keyframes


@app.get("/static/{id}/{filename}")
async def serve_static_file(id: str, filename: str) -> FileResponse:
    """Serve a static file from a validated course directory.
    
    Args:
        id: Course UUID.
        filename: Name of the file to serve.
        
    Returns:
        FileResponse: The requested static file.
    """
    course_dir = _resolve_course_dir(id)
    course_root = Path(course_dir).resolve()
    try:
        requested_path = resolve_within_root(course_root, filename)
    except Exception:
        logging.error(f"Path traversal blocked: {filename}")
        raise HTTPException(status_code=403, detail="Invalid filename.")
        
    filepath = str(requested_path)
    if not os.path.isfile(filepath):
        logging.error(f"Static file not found: {filepath}")
        raise HTTPException(status_code=404, detail="File not found.")

    return FileResponse(filepath)


@app.delete("/content/file/{id}/{filename}")
async def delete_course_file(id: str, filename: str) -> Dict[str, bool]:
    """Safely delete a file from a validated course directory."""
    course_dir = _resolve_course_dir(id)
    course_root = Path(course_dir).resolve()
    try:
        requested_path = resolve_within_root(course_root, filename)
    except Exception:
        logging.error(f"Path traversal blocked for delete: {filename}")
        raise HTTPException(status_code=403, detail="Invalid filename.")
        
    filepath = str(requested_path)
    if not os.path.isfile(filepath):
        raise HTTPException(status_code=404, detail="File not found.")

    try:
        os.remove(filepath)
        return {"success": True}
    except OSError as exc:
        logging.error(f"Error removing file {filepath}: {exc}")
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {exc}") from exc

# ═══════════════════════════════════════════════════════════════════════
#  Settings Endpoints
# ═══════════════════════════════════════════════════════════════════════


@app.get("/settings/pool")
async def get_settings_pool() -> List[Dict[str, Any]]:
    """Return the provider pool config with masked API keys.
    
    Returns:
        List[Dict[str, Any]]: Pool configurations.
    """
    try:
        if SCRIPT_DIR not in sys.path:
            sys.path.append(SCRIPT_DIR)
        from src.credentials import get_provider_pool_or_legacy
        pool = get_provider_pool_or_legacy()
        result = []
        for cfg in pool.configs:
            result.append({
                "provider": cfg.provider,
                "endpoint_url": cfg.endpoint_url,
                "masked_key": _mask_key(cfg.api_key),
                "model_name": cfg.model_name,
                "capability": cfg.capability,
                "rpm_limit": cfg.rpm_limit,
                "tpm_limit": cfg.tpm_limit,
            })
        return result
    except Exception as exc:
        logging.error(f"Error loading pool: {exc}")
        raise HTTPException(status_code=500, detail=f"Error loading pool: {exc}") from exc


@app.post("/settings/pool")
async def add_settings_pool_key(req: dict) -> Dict[str, bool]:
    """Add a new provider key to the pool.
    
    Args:
        req: Dictionary containing the new key details.
        
    Returns:
        Dict[str, bool]: Success status.
    """
    try:
        if SCRIPT_DIR not in sys.path:
            sys.path.append(SCRIPT_DIR)
        from src.credentials import get_provider_pool_or_legacy, store_provider_pool
        from src.provider_pool import ProviderConfig
        pool = get_provider_pool_or_legacy()
        # Ensure we add it as a ProviderConfig
        cfg = ProviderConfig(
            provider=req.get("provider", "openai"),
            endpoint_url=req.get("endpoint_url", ""),
            api_key=req.get("api_key", ""),
            model_name=req.get("model_name", ""),
            capability=req.get("capability", "text"),
            rpm_limit=req.get("rpm_limit"),
            tpm_limit=req.get("tpm_limit"),
        )
        cfg.validate()
        pool.configs.append(cfg)
        success = store_provider_pool(pool.to_json())
        return {"success": success}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logging.error(f"Error adding to pool: {exc}")
        raise HTTPException(status_code=500, detail=f"Error adding to pool: {exc}") from exc


@app.delete("/settings/pool/{index}")
async def delete_settings_pool_key(index: int) -> Dict[str, bool]:
    """Delete a key from the provider pool by index.
    
    Args:
        index: The index of the config to remove.
        
    Returns:
        Dict[str, bool]: Success status.
    """
    try:
        if SCRIPT_DIR not in sys.path:
            sys.path.append(SCRIPT_DIR)
        from src.credentials import get_provider_pool_or_legacy, store_provider_pool
        pool = get_provider_pool_or_legacy()
        if 0 <= index < len(pool.configs):
            pool.configs.pop(index)
            success = store_provider_pool(pool.to_json())
            return {"success": success}
        return {"success": False}
    except Exception as exc:
        logging.error(f"Error deleting from pool: {exc}")
        raise HTTPException(status_code=500, detail=f"Error deleting from pool: {exc}") from exc


@app.patch("/settings/pool/{index}/limits")
async def update_settings_pool_limits(index: int, req: dict) -> Dict[str, bool]:
    """Update only rate limits for a saved provider; credentials are untouched."""
    try:
        if SCRIPT_DIR not in sys.path:
            sys.path.append(SCRIPT_DIR)
        from src.credentials import get_provider_pool_or_legacy, store_provider_pool
        pool = get_provider_pool_or_legacy()
        if not (0 <= index < len(pool.configs)):
            return {"success": False}
        config = pool.configs[index]
        config.rpm_limit = req.get("rpm_limit")
        config.tpm_limit = req.get("tpm_limit")
        config.validate()
        return {"success": store_provider_pool(pool.to_json())}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logging.error(f"Error updating provider limits: {exc}")
        raise HTTPException(status_code=500, detail=f"Error updating provider limits: {exc}") from exc


@app.get("/settings/youtube/status")
async def get_youtube_status() -> Dict[str, bool]:
    """Return YouTube authentication status."""
    try:
        from src.auth import load_credentials
        creds = load_credentials()
        return {"connected": creds is not None}
    except Exception:
        return {"connected": False}


@app.post("/settings/youtube/connect")
def connect_youtube_endpoint() -> Dict[str, bool]:
    """Trigger YouTube OAuth login flow."""
    from src.auth import connect_youtube
    try:
        connect_youtube()
        return {"connected": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/settings/youtube/disconnect")
async def disconnect_youtube_endpoint() -> Dict[str, bool]:
    """Disconnect YouTube integration."""
    from src.auth import disconnect_youtube
    disconnect_youtube()
    return {"connected": False}


# ═══════════════════════════════════════════════════════════════════════
#  PDF Endpoints
# ═══════════════════════════════════════════════════════════════════════


@app.get("/settings/health", response_model=HealthStatus)
async def get_settings_health() -> HealthStatus:
    """Check system health: Ollama, Playwright, Keyring.
    
    Returns:
        HealthStatus: Status of various system components.
    """
    import asyncio
    ollama, playwright, keyring = await asyncio.gather(
        asyncio.to_thread(_check_ollama),
        asyncio.to_thread(_check_playwright),
        asyncio.to_thread(_check_keyring),
    )
    return HealthStatus(ollama=ollama, playwright=playwright, keyring=keyring)


@app.post("/pdf/export")
async def pdf_export(req: PdfExportRequest) -> Dict[str, str]:
    """Convert a markdown file to PDF using Playwright.
    
    Args:
        req: Request containing the course_id, filename, and theme.
        
    Returns:
        Dict[str, str]: Path to the generated PDF.
    """
    course_dir = _resolve_course_dir(req.course_id)
    course_root = Path(course_dir).resolve()
    try:
        requested_path = resolve_within_root(course_root, req.filename)
    except Exception:
        logging.error(f"Path traversal blocked for PDF: {req.filename}")
        raise HTTPException(status_code=403, detail="Invalid filename.")
        
    if not requested_path.name.endswith(".md"):
        logging.error(f"Non-markdown file requested for PDF export: {requested_path.name}")
        raise HTTPException(status_code=400, detail="Only .md files can be exported.")

    md_path = str(requested_path)
    if not os.path.isfile(md_path):
        logging.error(f"Markdown file not found for PDF export: {md_path}")
        raise HTTPException(status_code=400, detail="Markdown file not found.")

    pdf_path = md_path.rsplit(".", 1)[0] + ".pdf"

    try:
        _convert_md_to_pdf(md_path, req.theme, pdf_path)
        return {"path": pdf_path}
    except Exception as exc:
        logging.error(f"PDF export failed for {md_path}: {exc}")
        raise HTTPException(status_code=500, detail=f"PDF export failed: {exc}") from exc


class ExternalPdfExportRequest(BaseModel):
    """Request body for exporting external markdown to PDF."""
    file_path: str
    theme: str = "Textbook"


@app.post("/pdf/export_external")
async def pdf_export_external(req: ExternalPdfExportRequest) -> Dict[str, str]:
    """Convert an external markdown file to PDF using Playwright."""
    md_path = req.file_path
    if not os.path.isfile(md_path):
        raise HTTPException(status_code=400, detail="File not found.")
    if not md_path.lower().endswith(".md"):
        raise HTTPException(status_code=400, detail="Only .md files can be exported.")
        
    pdf_path = md_path.rsplit(".", 1)[0] + ".pdf"

    try:
        _convert_md_to_pdf(md_path, req.theme, pdf_path)
        return {"path": pdf_path}
    except Exception as exc:
        logging.error(f"External PDF export failed for {md_path}: {exc}")
        raise HTTPException(status_code=500, detail=f"External PDF export failed: {exc}") from exc


@app.post("/settings/playwright/install")
def install_playwright() -> Dict[str, bool]:
    """Install Playwright browsers automatically."""
    try:
        import subprocess
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            cwd=SCRIPT_DIR,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        return {"success": True}
    except Exception as exc:
        logging.error(f"Playwright install failed: {exc}")
        raise HTTPException(status_code=500, detail=f"Install failed: {exc}") from exc
