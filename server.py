"""
FastAPI server wrapping the existing src/ backend package.

Exposes REST endpoints for library management, course content,
settings, chat, pipeline control, and PDF export.
All course_id parameters are integer indices into the recent_outputs
list to prevent path traversal attacks.
"""
import json
import os
import sys
import tempfile
import threading
import urllib.request
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

# -- Path resolution --------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")

# -- Global state -----------------------------------------------------------

cancel_event = threading.Event()
_chat_session: Optional[Any] = None  # Lazily created ChatSession
_chat_lock = threading.Lock()

# -- FastAPI app ------------------------------------------------------------

app = FastAPI(
    title="YouTube Transcript-to-Notes API",
    version="2.0.0",
    description="REST API for the YouTube Study Suite.",
)

ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:8000",
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


class ChatRequest(BaseModel):
    """Request body for sending a chat message."""
    course_dir: str
    message: str
    model: str = "llama3"


class PdfExportRequest(BaseModel):
    """Request body for exporting markdown to PDF."""
    md_path: str
    pdf_path: str = ""
    theme: str = "Textbook"


class PdfPreviewRequest(BaseModel):
    """Request body for previewing markdown as PDF."""
    md_path: str
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
        raise HTTPException(
            status_code=404,
            detail=f"Invalid course_id: {course_id}",
        )
    course_dir = outputs[course_id]
    if not os.path.isdir(course_dir):
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
        req = urllib.request.urlopen(
            "http://localhost:11434", timeout=2
        )
        return req.getcode() == 200
    except Exception:
        return False


def _check_playwright() -> bool:
    """Check if Playwright Chromium executable is available.

    Returns:
        True if Playwright chromium browser is installed.
    """
    try:
        venv_site = os.path.join(
            SCRIPT_DIR, ".venv", "Lib", "site-packages"
        )
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

    has_vision = any(
        f.lower().endswith((".jpg", ".png", ".jpeg"))
        for f in files
    )
    has_kag = any(
        "_knowledge_graph" in f.lower() for f in files
    )
    has_pdf = any(f.lower().endswith(".pdf") for f in files)

    return CourseBadges(
        vision=has_vision, kag=has_kag, pdf=has_pdf
    )


def _mask_key(key: str) -> str:
    """Mask an API key for safe display.

    Args:
        key: The raw API key.

    Returns:
        Masked string showing only the first 8 characters.
    """
    if not key:
        return ""
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
    table {
        width: 100%; border-collapse: collapse; margin: 1em 0;
    }
    @page { margin: 20mm; }
    """
    if theme == "Textbook":
        return base_css + """
        body { color: #1f2937; }
        h1 {
            color: #1e3a8a; font-size: 24pt;
            border-bottom: 3px solid #3b82f6;
        }
        h2 {
            color: #2563eb; font-size: 18pt;
            border-bottom: 1px solid #d1d5db;
        }
        pre {
            background-color: #f8fafc; padding: 12px;
            border-left: 4px solid #94a3b8;
        }
        blockquote {
            border-left: 4px solid #3b82f6;
            background-color: #eff6ff; padding: 10px;
        }
        th {
            background-color: #e2e8f0; padding: 8px;
            border: 1px solid #cbd5e1;
        }
        td { padding: 8px; border: 1px solid #cbd5e1; }
        """
    elif theme == "ChatGPT Dark":
        return base_css + """
        @page { margin: 0; }
        body {
            color: #ececf1; background-color: #212121;
            padding: 20mm;
        }
        h1 {
            color: #ffffff; font-size: 24pt;
            border-bottom: 1px solid #4d4d4d;
        }
        h2 {
            color: #f9f9f9; font-size: 18pt;
            border-bottom: 1px solid #3d3d3d;
        }
        pre {
            background-color: #0d0d0d; padding: 12px;
            border-left: 4px solid #10a37f;
        }
        blockquote {
            border-left: 4px solid #10a37f;
            background-color: #2f2f2f; padding: 10px;
        }
        th {
            background-color: #2f2f2f; padding: 8px;
            border: 1px solid #4d4d4d; color: #fff;
        }
        td { padding: 8px; border: 1px solid #4d4d4d; }
        """
    else:  # Minimal Mono
        return base_css + """
        body {
            font-family: 'Courier New', Courier, monospace;
            color: #000;
        }
        h1, h2, h3 {
            color: #000; text-transform: uppercase;
            border-bottom: 1px solid #000;
        }
        pre {
            background-color: #fff; padding: 12px;
            border: 1px solid #000;
        }
        blockquote {
            border-left: 4px solid #000; padding: 10px;
        }
        th, td { border: 1px solid #000; padding: 8px; }
        """


# ═══════════════════════════════════════════════════════════════════════
#  Library Endpoints
# ═══════════════════════════════════════════════════════════════════════


@app.get("/api/library", response_model=List[CourseInfo])
async def get_library() -> List[CourseInfo]:
    """Return the list of courses in the library.

    Reads recent_outputs from config.json and detects
    feature badges for each course directory.
    """
    outputs = _load_recent_outputs()
    courses: List[CourseInfo] = []
    for path in outputs:
        title = os.path.basename(path) or path
        date = ""
        try:
            stat = os.stat(path)
            from datetime import datetime
            date = datetime.fromtimestamp(
                stat.st_mtime
            ).strftime("%Y-%m-%d")
        except OSError:
            date = "Unknown"
        badges = _detect_badges(path)
        courses.append(CourseInfo(
            title=title, path=path, date=date, badges=badges
        ))
    return courses


@app.post("/api/library/add")
async def add_library_entry(
    req: LibraryAddRequest,
) -> Dict[str, bool]:
    """Add a directory path to the library's recent outputs."""
    _add_recent_output(req.path)
    return {"success": True}


# ═══════════════════════════════════════════════════════════════════════
#  Course Endpoints
# ═══════════════════════════════════════════════════════════════════════


@app.get(
    "/api/course/{course_id}/files",
    response_model=List[FileInfo],
)
async def get_course_files(course_id: int) -> List[FileInfo]:
    """List files in a course output directory.

    Args:
        course_id: Integer index into the recent_outputs list.
    """
    course_dir = _resolve_course_dir(course_id)
    files: List[FileInfo] = []
    try:
        for name in sorted(os.listdir(course_dir)):
            full = os.path.join(course_dir, name)
            ftype = "directory" if os.path.isdir(full) else "file"
            size = (
                os.path.getsize(full)
                if os.path.isfile(full)
                else 0
            )
            files.append(FileInfo(
                name=name, type=ftype, size=size
            ))
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Error reading directory: {exc}",
        ) from exc
    return files


@app.get("/api/course/{course_id}/notes/{filename}")
async def get_course_notes(
    course_id: int, filename: str
) -> Dict[str, str]:
    """Read and return a markdown file from the course directory.

    Args:
        course_id: Integer index into the recent_outputs list.
        filename: Name of the .md file to read.
    """
    course_dir = _resolve_course_dir(course_id)

    # -- Validate filename to prevent path traversal
    safe_name = os.path.basename(filename)
    if safe_name != filename or ".." in filename:
        raise HTTPException(
            status_code=403,
            detail="Invalid filename.",
        )
    if not safe_name.endswith(".md"):
        raise HTTPException(
            status_code=400,
            detail="Only .md files can be read.",
        )

    filepath = os.path.join(course_dir, safe_name)
    if not os.path.isfile(filepath):
        raise HTTPException(
            status_code=404,
            detail=f"File not found: {safe_name}",
        )
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Error reading file: {exc}",
        ) from exc
    return {"content": content}


@app.get("/api/course/{course_id}/graph")
async def get_course_graph(course_id: int) -> Dict[str, str]:
    """Read and return knowledge graph HTML from course dir.

    Args:
        course_id: Integer index into the recent_outputs list.
    """
    course_dir = _resolve_course_dir(course_id)

    # -- Find the knowledge graph HTML file
    graph_file = None
    try:
        for name in os.listdir(course_dir):
            if "_knowledge_graph" in name.lower() and (
                name.endswith(".html")
            ):
                graph_file = os.path.join(course_dir, name)
                break
    except OSError:
        pass

    if not graph_file or not os.path.isfile(graph_file):
        return {"html": ""}

    try:
        with open(graph_file, "r", encoding="utf-8") as f:
            return {"html": f.read()}
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Error reading graph: {exc}",
        ) from exc


@app.get(
    "/api/course/{course_id}/keyframes",
    response_model=List[KeyframeInfo],
)
async def get_course_keyframes(
    course_id: int,
) -> List[KeyframeInfo]:
    """List keyframe images in the course directory.

    Args:
        course_id: Integer index into the recent_outputs list.
    """
    course_dir = _resolve_course_dir(course_id)
    keyframes: List[KeyframeInfo] = []
    image_exts = (".jpg", ".jpeg", ".png")
    try:
        for name in sorted(os.listdir(course_dir)):
            if name.lower().endswith(image_exts):
                url = f"/static/{course_id}/{name}"
                keyframes.append(
                    KeyframeInfo(name=name, url=url)
                )
    except OSError:
        pass
    return keyframes


# -- Static file serving for course images ---------------------------------


@app.get("/static/{course_id}/{filename}")
async def serve_static_file(
    course_id: int, filename: str
) -> FileResponse:
    """Serve a static file from a validated course directory.

    Only serves image files from directories that exist in
    the recent_outputs list to prevent path traversal.

    Args:
        course_id: Integer index into the recent_outputs list.
        filename: Name of the file to serve.
    """
    course_dir = _resolve_course_dir(course_id)

    # -- Validate filename to prevent traversal
    safe_name = os.path.basename(filename)
    if safe_name != filename or ".." in filename:
        raise HTTPException(
            status_code=403,
            detail="Invalid filename.",
        )

    filepath = os.path.join(course_dir, safe_name)
    if not os.path.isfile(filepath):
        raise HTTPException(
            status_code=404,
            detail="File not found.",
        )

    return FileResponse(filepath)


# ═══════════════════════════════════════════════════════════════════════
#  Settings Endpoints
# ═══════════════════════════════════════════════════════════════════════


@app.get("/api/settings/pool")
async def get_settings_pool() -> List[Dict[str, str]]:
    """Return the provider pool config with masked API keys.

    Never sends full API keys to the frontend.
    """
    try:
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
        raise HTTPException(
            status_code=500,
            detail=f"Error loading pool: {exc}",
        ) from exc


@app.post("/api/settings/pool")
async def store_settings_pool(
    req: PoolStoreRequest,
) -> Dict[str, bool]:
    """Store a new provider pool configuration.

    Args:
        req: PoolStoreRequest with pool config list.
    """
    try:
        from src.credentials import store_provider_pool
        pool_json = json.dumps(req.pool)
        success = store_provider_pool(pool_json)
        return {"success": success}
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Error storing pool: {exc}",
        ) from exc


@app.get(
    "/api/settings/health",
    response_model=HealthStatus,
)
async def get_settings_health() -> HealthStatus:
    """Check system health: Ollama, Playwright, Keyring."""
    return HealthStatus(
        ollama=_check_ollama(),
        playwright=_check_playwright(),
        keyring=_check_keyring(),
    )


# ═══════════════════════════════════════════════════════════════════════
#  Pipeline Endpoints
# ═══════════════════════════════════════════════════════════════════════


@app.post("/api/pipeline/cancel")
async def cancel_pipeline() -> Dict[str, bool]:
    """Set the global cancel event to stop a running pipeline."""
    cancel_event.set()
    return {"success": True}


# ═══════════════════════════════════════════════════════════════════════
#  Chat Endpoints
# ═══════════════════════════════════════════════════════════════════════


@app.post("/api/chat/send")
async def chat_send(
    req: ChatRequest,
) -> Dict[str, str]:
    """Send a chat message via local Ollama.

    Creates or reuses a ChatSession for the specified
    course directory.

    Args:
        req: ChatRequest with course_dir, message, and model.
    """
    global _chat_session

    if not os.path.isdir(req.course_dir):
        raise HTTPException(
            status_code=400,
            detail="Invalid course directory.",
        )

    with _chat_lock:
        from src.chat import ChatSession

        # -- Create new session if needed
        if (
            _chat_session is None
            or _chat_session.notes_dir != req.course_dir
            or _chat_session.ollama_model != req.model
        ):
            _chat_session = ChatSession(
                req.course_dir, req.model
            )

    try:
        response = _chat_session.send(req.message)
        return {"response": response}
    except ConnectionError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Chat error: {exc}",
        ) from exc


@app.post("/api/chat/clear")
async def chat_clear() -> Dict[str, bool]:
    """Clear the active chat session."""
    global _chat_session
    with _chat_lock:
        if _chat_session is not None:
            _chat_session.clear_history()
        _chat_session = None
    return {"success": True}


# ═══════════════════════════════════════════════════════════════════════
#  PDF Endpoints
# ═══════════════════════════════════════════════════════════════════════


@app.post("/api/pdf/export")
async def pdf_export(
    req: PdfExportRequest,
) -> Dict[str, str]:
    """Convert a markdown file to PDF using Playwright.

    Args:
        req: PdfExportRequest with md_path, pdf_path, theme.
    """
    if not os.path.isfile(req.md_path):
        raise HTTPException(
            status_code=400,
            detail="Markdown file not found.",
        )

    pdf_path = req.pdf_path
    if not pdf_path:
        pdf_path = req.md_path.rsplit(".", 1)[0] + ".pdf"

    try:
        import asyncio
        asyncio.set_event_loop(asyncio.new_event_loop())

        venv_site = os.path.join(
            SCRIPT_DIR, ".venv", "Lib", "site-packages"
        )
        if (
            os.path.exists(venv_site)
            and venv_site not in sys.path
        ):
            sys.path.append(venv_site)

        import markdown
        from playwright.sync_api import sync_playwright

        with open(
            req.md_path, "r", encoding="utf-8", errors="replace"
        ) as f:
            md_content = f.read()

        html_body = markdown.markdown(
            md_content, extensions=["fenced_code", "tables"]
        )
        custom_css = _get_shared_pdf_css(req.theme)
        mermaid_script = """
        <script>
            document.querySelectorAll(
                'code.language-mermaid'
            ).forEach(function(c) {
                var pre = c.parentNode;
                var div = document.createElement('div');
                div.className = 'mermaid';
                div.textContent = c.textContent;
                pre.parentNode.replaceChild(div, pre);
            });
            mermaid.initialize({startOnLoad:true});
        </script>
        """
        cdn = (
            '<script src="https://cdn.jsdelivr.net/npm/'
            'mermaid/dist/mermaid.min.js"></script>'
        )
        full_html = (
            f"<html><head><style>{custom_css}</style>"
            f"{cdn}</head>"
            f"<body>{html_body}{mermaid_script}</body>"
            f"</html>"
        )

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_content(full_html)
            page.pdf(
                path=pdf_path,
                format="A4",
                print_background=True,
            )
            browser.close()

        return {"path": pdf_path}

    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Playwright or markdown not installed. "
                f"Install them first: {exc}"
            ),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"PDF export failed: {exc}",
        ) from exc


@app.post("/api/pdf/preview")
async def pdf_preview(
    req: PdfPreviewRequest,
) -> Dict[str, str]:
    """Generate a temp PDF preview from a markdown file.

    Args:
        req: PdfPreviewRequest with md_path and theme.
    """
    if not os.path.isfile(req.md_path):
        raise HTTPException(
            status_code=400,
            detail="Markdown file not found.",
        )

    try:
        import asyncio
        asyncio.set_event_loop(asyncio.new_event_loop())

        venv_site = os.path.join(
            SCRIPT_DIR, ".venv", "Lib", "site-packages"
        )
        if (
            os.path.exists(venv_site)
            and venv_site not in sys.path
        ):
            sys.path.append(venv_site)

        import markdown
        from playwright.sync_api import sync_playwright

        with open(
            req.md_path, "r", encoding="utf-8", errors="replace"
        ) as f:
            md_content = f.read()

        html_body = markdown.markdown(
            md_content, extensions=["fenced_code", "tables"]
        )
        custom_css = _get_shared_pdf_css(req.theme)
        temp_pdf = os.path.join(
            tempfile.gettempdir(),
            "transcriptor_preview.pdf",
        )
        full_html = (
            f"<html><head><style>{custom_css}</style>"
            f"</head><body>{html_body}</body></html>"
        )

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_content(full_html)
            page.pdf(
                path=temp_pdf,
                format="A4",
                print_background=True,
            )
            browser.close()

        return {"path": temp_pdf}

    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Playwright or markdown not installed. "
                f"Install them first: {exc}"
            ),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"PDF preview failed: {exc}",
        ) from exc


# ═══════════════════════════════════════════════════════════════════════
#  Run Server
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
