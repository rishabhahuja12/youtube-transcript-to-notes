"""
FastAPI microservice for Content Management.
Runs on Port 8003.
"""
import json
import logging
import os
import sys
import tempfile
import urllib.request
import uuid
import re
from pathlib import Path
from typing import Any, Dict, List
import platform
from datetime import datetime


from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

# -- Path resolution --------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")

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


class CourseBadges(BaseModel):
    """Feature badges for a course."""
    vision: bool = False
    kag: bool = False
    pdf: bool = False


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
    candidate = (root / str(user_path)).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise HTTPException(status_code=403, detail="Invalid path.")
    return candidate

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
def _load_library_entries() -> List[Dict[str, Any]]:
    """Load the list of library entries, migrating recent_outputs if needed."""
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
                # Ensure no duplicates by path
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
def _add_library_entry(entry_data: Dict[str, Any]) -> Dict[str, Any]:
    """Add or update an output directory path in the library."""
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

def _resolve_course_dir(course_id: str) -> str:
    """Resolve a course ID to a validated directory path."""
    entries = _load_library_entries()
    for entry in entries:
        if str(entry.get("id")) == str(course_id):
            course_dir = entry.get("path")
            if not os.path.isdir(course_dir):
                raise HTTPException(status_code=404, detail="Course directory does not exist.")
            return course_dir
    raise HTTPException(status_code=404, detail=f"Invalid course_id: {course_id}")


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


def _detect_badges(course_dir: str) -> CourseBadges:
    """Detect which features were used for a course.

    Args:
        course_dir: Path to the course output directory.

    Returns:
        CourseBadges with vision/kag/pdf flags.
    """
    try:
        files = os.listdir(course_dir)
    except OSError:
        return CourseBadges()

    has_vision = any(f.lower().endswith((".jpg", ".png", ".jpeg")) for f in files)
    has_kag = any("_knowledge_graph" in f.lower() for f in files)
    has_pdf = any(f.lower().endswith(".pdf") for f in files)

    return CourseBadges(vision=has_vision, kag=has_kag, pdf=has_pdf)


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


def _get_shared_pdf_css(theme: str = "Textbook") -> str:
    """Get CSS rules for Markdown to PDF conversion.

    Args:
        theme: Visual theme name.

    Returns:
        Custom CSS styling block string.
    """
    base_css = """
    body {
        font-family: 'Segoe UI', Helvetica, sans-serif;
        line-height: 1.5;
    }
    h1 { break-before: page; margin-top: 0; }
    h1:first-of-type { break-before: auto; }
    h1, h2, h3, h4 { break-after: avoid; }
    pre, blockquote, table, tr { break-inside: avoid; }
    table { width: 100%; border-collapse: collapse; margin: 1em 0; }
    @page { margin: 20mm; }
    """
    if theme == "Textbook":
        return base_css + """
        body { color: #1f2937; }
        h1 { color: #1e3a8a; font-size: 24pt; border-bottom: 3px solid #3b82f6; }
        h2 { color: #2563eb; font-size: 18pt; border-bottom: 1px solid #d1d5db; }
        pre { background-color: #f8fafc; padding: 12px; border-left: 4px solid #94a3b8; }
        blockquote { border-left: 4px solid #3b82f6; background-color: #eff6ff; padding: 10px; }
        th { background-color: #e2e8f0; padding: 8px; border: 1px solid #cbd5e1; }
        td { padding: 8px; border: 1px solid #cbd5e1; }
        """
    elif theme == "ChatGPT Dark":
        return base_css + """
        @page { margin: 0; }
        body { color: #ececf1; background-color: #212121; padding: 20mm; }
        h1 { color: #ffffff; font-size: 24pt; border-bottom: 1px solid #4d4d4d; }
        h2 { color: #f9f9f9; font-size: 18pt; border-bottom: 1px solid #3d3d3d; }
        pre { background-color: #0d0d0d; padding: 12px; border-left: 4px solid #10a37f; }
        blockquote { border-left: 4px solid #10a37f; background-color: #2f2f2f; padding: 10px; }
        th { background-color: #2f2f2f; padding: 8px; border: 1px solid #4d4d4d; color: #fff; }
        td { padding: 8px; border: 1px solid #4d4d4d; }
        """
    else:  # Minimal Mono
        return base_css + """
        body { font-family: 'Courier New', Courier, monospace; color: #000; }
        h1, h2, h3 { color: #000; text-transform: uppercase; border-bottom: 1px solid #000; }
        pre { background-color: #fff; padding: 12px; border: 1px solid #000; }
        blockquote { border-left: 4px solid #000; padding: 10px; }
        th, td { border: 1px solid #000; padding: 8px; }
        """

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

@app.get("/content/browse-directory")
def browse_directory() -> Dict[str, str]:
    """Open a native file dialog to pick a directory."""
    import tkinter as tk
    from tkinter import filedialog
    
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    
    directory = filedialog.askdirectory(title="Select Output Directory")
    root.destroy()
    
    return {"path": directory}

@app.get("/content/browse-file")
def browse_file() -> Dict[str, str]:
    """Open a native file dialog to pick a file."""
    import tkinter as tk
    from tkinter import filedialog
    
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    
    file_path = filedialog.askopenfilename(title="Select File")
    root.destroy()
    
    return {"path": file_path}

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

# ═══════════════════════════════════════════════════════════════════════
#  Settings Endpoints
# ═══════════════════════════════════════════════════════════════════════


@app.get("/settings/pool")
async def get_settings_pool() -> List[Dict[str, str]]:
    """Return the provider pool config with masked API keys.
    
    Returns:
        List[Dict[str, str]]: Pool configurations.
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
            capability=req.get("capability", "text")
        )
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


@app.get("/settings/health", response_model=HealthStatus)
async def get_settings_health() -> HealthStatus:
    """Check system health: Ollama, Playwright, Keyring.
    
    Returns:
        HealthStatus: Status of various system components.
    """
    return HealthStatus(
        ollama=_check_ollama(),
        playwright=_check_playwright(),
        keyring=_check_keyring(),
    )

@app.get("/settings/youtube/status")
async def get_youtube_status():
    try:
        from src.auth import load_credentials
        creds = load_credentials()
        return {"connected": creds is not None}
    except Exception:
        return {"connected": False}

@app.post("/settings/youtube/connect")
def connect_youtube_endpoint():
    from src.auth import connect_youtube
    try:
        creds = connect_youtube()
        return {"connected": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/settings/youtube/disconnect")
async def disconnect_youtube_endpoint():
    from src.auth import TOKEN_JSON_PATH, LEGACY_TOKEN_PICKLE_PATH
    import os
    if os.path.exists(TOKEN_JSON_PATH):
        try: os.remove(TOKEN_JSON_PATH)
        except OSError: pass
    if os.path.exists(LEGACY_TOKEN_PICKLE_PATH):
        try: os.remove(LEGACY_TOKEN_PICKLE_PATH)
        except OSError: pass
    return {"connected": False}

# ═══════════════════════════════════════════════════════════════════════
#  PDF Endpoints
# ═══════════════════════════════════════════════════════════════════════


def _convert_md_to_pdf(md_path: str, theme: str, pdf_path: str) -> None:
    """Helper to convert a markdown file to a PDF."""
    import asyncio
    asyncio.set_event_loop(asyncio.new_event_loop())

    venv_site = os.path.join(SCRIPT_DIR, ".venv", "Lib", "site-packages")
    if os.path.exists(venv_site) and venv_site not in sys.path:
        sys.path.append(venv_site)

    import markdown
    from playwright.sync_api import sync_playwright

    with open(md_path, "r", encoding="utf-8", errors="replace") as f:
        md_content = f.read()

    # Sanitize markdown: escape any raw script/iframe tags to prevent XSS before rendering
    md_content = re.sub(r'<(/?(?:script|iframe|object|embed|applet|style)[^>]*)>', r'&lt;\1&gt;', md_content, flags=re.IGNORECASE)

    html_body = markdown.markdown(md_content, extensions=["fenced_code", "tables"])
    custom_css = _get_shared_pdf_css(theme)

    html_content = (
        "<!DOCTYPE html>"
        "<html>"
        "<head>"
        "<meta charset=\"utf-8\">"
        "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'; img-src data: file:; script-src 'none'\">"
        f"<style>{custom_css}</style>"
        "</head>"
        "<body>"
        f"{html_body}"
        "</body>"
        "</html>"
    )

    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".html", encoding="utf-8") as f:
        f.write(html_content)
        temp_html = f.name

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"file://{temp_html}", wait_until="networkidle")
            page.pdf(path=pdf_path, format="A4", print_background=True, prefer_css_page_size=True)
            browser.close()
    finally:
        if os.path.exists(temp_html):
            os.remove(temp_html)


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
