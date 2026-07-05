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
from typing import Any, Dict, List

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
    course_id: int
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
    title: str
    path: str
    date: str
    badges: CourseBadges


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


def _add_recent_output(path: str) -> None:
    """Add an output directory path to the recent list.

    Args:
        path: The directory path to store.
    """
    if not path or not os.path.isdir(path):
        return
    data: Dict[str, Any] = {}
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
    except (json.JSONDecodeError, OSError):
        data = {}

    recents = data.get("recent_outputs", [])
    if path in recents:
        recents.remove(path)
    recents.insert(0, path)
    recents = recents[:10]
    data["recent_outputs"] = recents

    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except OSError:
        pass


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
    """Check if Playwright Chromium executable is available.

    Returns:
        True if Playwright chromium browser is installed.
    """
    try:
        venv_site = os.path.join(SCRIPT_DIR, ".venv", "Lib", "site-packages")
        if os.path.exists(venv_site) and venv_site not in sys.path:
            sys.path.append(venv_site)
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            return os.path.exists(p.chromium.executable_path)
    except Exception:
        return False


def _check_keyring() -> bool:
    """Check if keyring has stored credentials.

    Returns:
        True if credentials are stored in keyring.
    """
    try:
        if SCRIPT_DIR not in sys.path:
            sys.path.append(SCRIPT_DIR)
        from src.credentials import has_stored_credentials
        return has_stored_credentials()
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
    outputs = _load_recent_outputs()
    courses: List[CourseInfo] = []
    for path in outputs:
        title = os.path.basename(path) or path
        date = ""
        try:
            stat = os.stat(path)
            from datetime import datetime
            date = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d")
        except OSError:
            date = "Unknown"
        badges = _detect_badges(path)
        courses.append(CourseInfo(title=title, path=path, date=date, badges=badges))
    return courses


@app.post("/content/library/add")
async def add_library_entry(req: LibraryAddRequest) -> Dict[str, bool]:
    """Add a directory path to the library's recent outputs.
    
    Args:
        req: Request containing the path.
        
    Returns:
        Dict[str, bool]: Success status.
    """
    _add_recent_output(req.path)
    return {"success": True}

# ═══════════════════════════════════════════════════════════════════════
#  Course Endpoints
# ═══════════════════════════════════════════════════════════════════════


@app.get("/content/course/{id}/files", response_model=List[FileInfo])
async def get_course_files(id: int) -> List[FileInfo]:
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
async def get_course_notes(id: int, file: str) -> Dict[str, str]:
    """Read and return a markdown file from the course directory.
    
    Args:
        id: Integer index of the course.
        file: The requested filename.
        
    Returns:
        Dict[str, str]: The content of the markdown file.
    """
    course_dir = _resolve_course_dir(id)
    safe_name = os.path.basename(file)
    if safe_name != file or ".." in file:
        logging.error(f"Invalid filename requested: {file}")
        raise HTTPException(status_code=403, detail="Invalid filename.")
    if not safe_name.endswith(".md"):
        logging.error(f"Non-markdown file requested: {safe_name}")
        raise HTTPException(status_code=400, detail="Only .md files can be read.")

    filepath = os.path.join(course_dir, safe_name)
    if not os.path.isfile(filepath):
        logging.error(f"Notes file not found: {filepath}")
        raise HTTPException(status_code=404, detail=f"File not found: {safe_name}")
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError as exc:
        logging.error(f"Error reading file {filepath}: {exc}")
        raise HTTPException(status_code=500, detail=f"Error reading file: {exc}") from exc
    return {"content": content}


@app.get("/content/course/{id}/graph")
async def get_course_graph(id: int) -> Dict[str, str]:
    """Read and return knowledge graph HTML from course dir.
    
    Args:
        id: Integer index of the course.
        
    Returns:
        Dict[str, str]: The HTML content of the knowledge graph.
    """
    course_dir = _resolve_course_dir(id)
    graph_file = None
    try:
        for name in os.listdir(course_dir):
            if "_knowledge_graph" in name.lower() and name.endswith(".html"):
                graph_file = os.path.join(course_dir, name)
                break
    except OSError as exc:
        logging.error(f"Error reading directory {course_dir} for graph: {exc}")
        pass

    if not graph_file or not os.path.isfile(graph_file):
        return {"html": ""}

    try:
        with open(graph_file, "r", encoding="utf-8") as f:
            return {"html": f.read()}
    except OSError as exc:
        logging.error(f"Error reading graph file {graph_file}: {exc}")
        raise HTTPException(status_code=500, detail=f"Error reading graph: {exc}") from exc


@app.get("/content/course/{id}/keyframes", response_model=List[KeyframeInfo])
async def get_course_keyframes(id: int) -> List[KeyframeInfo]:
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
async def serve_static_file(id: int, filename: str) -> FileResponse:
    """Serve a static file from a validated course directory.
    
    Args:
        id: Integer index of the course.
        filename: Name of the file to serve.
        
    Returns:
        FileResponse: The requested static file.
    """
    course_dir = _resolve_course_dir(id)
    safe_name = os.path.basename(filename)
    if safe_name != filename or ".." in filename:
        logging.error(f"Invalid static filename requested: {filename}")
        raise HTTPException(status_code=403, detail="Invalid filename.")

    filepath = os.path.join(course_dir, safe_name)
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
async def store_settings_pool(req: PoolStoreRequest) -> Dict[str, bool]:
    """Store a new provider pool configuration.
    
    Args:
        req: Request containing the pool data.
        
    Returns:
        Dict[str, bool]: Success status.
    """
    try:
        if SCRIPT_DIR not in sys.path:
            sys.path.append(SCRIPT_DIR)
        from src.credentials import store_provider_pool
        pool_json = json.dumps(req.pool)
        success = store_provider_pool(pool_json)
        return {"success": success}
    except Exception as exc:
        logging.error(f"Error storing pool: {exc}")
        raise HTTPException(status_code=500, detail=f"Error storing pool: {exc}") from exc


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

# ═══════════════════════════════════════════════════════════════════════
#  PDF Endpoints
# ═══════════════════════════════════════════════════════════════════════


@app.post("/pdf/export")
async def pdf_export(req: PdfExportRequest) -> Dict[str, str]:
    """Convert a markdown file to PDF using Playwright.
    
    Args:
        req: Request containing the course_id, filename, and theme.
        
    Returns:
        Dict[str, str]: Path to the generated PDF.
    """
    course_dir = _resolve_course_dir(req.course_id)
    safe_name = os.path.basename(req.filename)
    if safe_name != req.filename or ".." in req.filename:
        logging.error(f"Invalid PDF export filename requested: {req.filename}")
        raise HTTPException(status_code=403, detail="Invalid filename.")
    if not safe_name.endswith(".md"):
        logging.error(f"Non-markdown file requested for PDF export: {safe_name}")
        raise HTTPException(status_code=400, detail="Only .md files can be exported.")

    md_path = os.path.join(course_dir, safe_name)
    if not os.path.isfile(md_path):
        logging.error(f"Markdown file not found for PDF export: {md_path}")
        raise HTTPException(status_code=400, detail="Markdown file not found.")

    pdf_path = md_path.rsplit(".", 1)[0] + ".pdf"

    try:
        import asyncio
        asyncio.set_event_loop(asyncio.new_event_loop())

        venv_site = os.path.join(SCRIPT_DIR, ".venv", "Lib", "site-packages")
        if os.path.exists(venv_site) and venv_site not in sys.path:
            sys.path.append(venv_site)

        import markdown
        from playwright.sync_api import sync_playwright

        with open(md_path, "r", encoding="utf-8", errors="replace") as f:
            md_content = f.read()

        html_body = markdown.markdown(md_content, extensions=["fenced_code", "tables"])
        custom_css = _get_shared_pdf_css(req.theme)
        mermaid_script = (
            "<script>"
            "document.querySelectorAll('code.language-mermaid').forEach((block) => {"
            "const graphDef = block.textContent;"
            "const parent = block.parentElement;"
            "parent.outerHTML = '<div class=\"mermaid\">' + graphDef + '</div>';"
            "});"
            "</script>"
        )

        html_content = (
            "<!DOCTYPE html>"
            "<html>"
            "<head>"
            "<meta charset=\"utf-8\">"
            f"<style>{custom_css}</style>"
            "<script src=\"https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js\"></script>"
            "<script>"
            "mermaid.initialize({ startOnLoad: true });"
            "</script>"
            "</head>"
            "<body>"
            f"{html_body}"
            f"{mermaid_script}"
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

        return {"path": pdf_path}
    except Exception as exc:
        logging.error(f"PDF export failed for {md_path}: {exc}")
        raise HTTPException(status_code=500, detail=f"PDF export failed: {exc}") from exc
