"""
Tests for the FastAPI server REST endpoints.

Uses httpx.AsyncClient to test all routes defined in server.py.
Validates response shapes, status codes, CORS headers, and
path traversal prevention.
"""
import json
import os
import tempfile
from typing import Generator
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from server import app, _load_recent_outputs, _mask_key

# ═══════════════════════════════════════════════════════════════════════
#  Fixtures
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture
def tmp_course_dir(tmp_path: str) -> str:
    """Create a temporary course directory with sample files.

    Returns:
        Path string to the temporary course directory.
    """
    d = tmp_path / "TestCourse"
    d.mkdir()

    # -- Create sample markdown file
    md = d / "Test_Detailed_Notes.md"
    md.write_text(
        "# Sample Notes\n\nHello world.",
        encoding="utf-8",
    )

    # -- Create a sample image
    img = d / "keyframe_001.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0dummy_jpg")

    # -- Create sample knowledge graph HTML
    graph = d / "Test_knowledge_graph.html"
    graph.write_text(
        "<html><body>Graph</body></html>",
        encoding="utf-8",
    )

    # -- Create sample PDF
    pdf = d / "notes.pdf"
    pdf.write_bytes(b"%PDF-dummy")

    return str(d)


@pytest.fixture
def mock_config(
    tmp_course_dir: str, tmp_path: str
) -> Generator:
    """Patch CONFIG_PATH to use a temp config with course dir.

    Args:
        tmp_course_dir: Path to the temporary course directory.
        tmp_path: Pytest built-in tmp_path fixture.
    """
    config_file = tmp_path / "config.json"
    config_data = {
        "recent_outputs": [tmp_course_dir],
    }
    config_file.write_text(
        json.dumps(config_data), encoding="utf-8"
    )
    with patch("server.CONFIG_PATH", str(config_file)):
        yield str(config_file)


@pytest.fixture
def mock_empty_config(tmp_path: str) -> Generator:
    """Patch CONFIG_PATH to use an empty config.

    Args:
        tmp_path: Pytest built-in tmp_path fixture.
    """
    config_file = tmp_path / "config_empty.json"
    config_data = {"recent_outputs": []}
    config_file.write_text(
        json.dumps(config_data), encoding="utf-8"
    )
    with patch("server.CONFIG_PATH", str(config_file)):
        yield str(config_file)


# ═══════════════════════════════════════════════════════════════════════
#  Helper
# ═══════════════════════════════════════════════════════════════════════


def _client() -> AsyncClient:
    """Create an async test client for the FastAPI app.

    Returns:
        An httpx.AsyncClient instance bound to the app.
    """
    transport = ASGITransport(app=app)
    return AsyncClient(
        transport=transport, base_url="http://test"
    )


# ═══════════════════════════════════════════════════════════════════════
#  Library Tests
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_library_returns_list(
    mock_config: str, tmp_course_dir: str
) -> None:
    """GET /api/library should return a list of courses."""
    async with _client() as client:
        resp = await client.get("/api/library")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1
    course = data[0]
    assert "title" in course
    assert "path" in course
    assert "date" in course
    assert "badges" in course


@pytest.mark.asyncio
async def test_library_empty(mock_empty_config: str) -> None:
    """GET /api/library with no courses returns empty list."""
    async with _client() as client:
        resp = await client.get("/api/library")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_library_badges_detected(
    mock_config: str, tmp_course_dir: str
) -> None:
    """Library entries should detect vision/kag/pdf badges."""
    async with _client() as client:
        resp = await client.get("/api/library")
    data = resp.json()
    badges = data[0]["badges"]
    assert badges["vision"] is True  # .jpg exists
    assert badges["kag"] is True  # _knowledge_graph exists
    assert badges["pdf"] is True  # .pdf exists


@pytest.mark.asyncio
async def test_library_add(
    mock_config: str, tmp_course_dir: str
) -> None:
    """POST /api/library/add should return success."""
    async with _client() as client:
        resp = await client.post(
            "/api/library/add",
            json={"path": tmp_course_dir},
        )
    assert resp.status_code == 200
    assert resp.json()["success"] is True


# ═══════════════════════════════════════════════════════════════════════
#  Course Endpoint Tests
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_course_files(
    mock_config: str, tmp_course_dir: str
) -> None:
    """GET /api/course/0/files should list files."""
    async with _client() as client:
        resp = await client.get("/api/course/0/files")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0
    names = [f["name"] for f in data]
    assert "Test_Detailed_Notes.md" in names


@pytest.mark.asyncio
async def test_course_notes(
    mock_config: str, tmp_course_dir: str
) -> None:
    """GET /api/course/0/notes/file.md returns content."""
    async with _client() as client:
        resp = await client.get(
            "/api/course/0/notes/Test_Detailed_Notes.md"
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "content" in data
    assert "Sample Notes" in data["content"]


@pytest.mark.asyncio
async def test_course_notes_nonmd_rejected(
    mock_config: str, tmp_course_dir: str
) -> None:
    """Requesting a non-.md file should return 400."""
    async with _client() as client:
        resp = await client.get(
            "/api/course/0/notes/keyframe_001.jpg"
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_course_graph(
    mock_config: str, tmp_course_dir: str
) -> None:
    """GET /api/course/0/graph returns HTML content."""
    async with _client() as client:
        resp = await client.get("/api/course/0/graph")
    assert resp.status_code == 200
    data = resp.json()
    assert "html" in data
    assert "Graph" in data["html"]


@pytest.mark.asyncio
async def test_course_keyframes(
    mock_config: str, tmp_course_dir: str
) -> None:
    """GET /api/course/0/keyframes returns image list."""
    async with _client() as client:
        resp = await client.get("/api/course/0/keyframes")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["name"] == "keyframe_001.jpg"
    assert "/static/0/keyframe_001.jpg" in data[0]["url"]


@pytest.mark.asyncio
async def test_static_file_serving(
    mock_config: str, tmp_course_dir: str
) -> None:
    """GET /static/0/keyframe_001.jpg serves the file."""
    async with _client() as client:
        resp = await client.get(
            "/static/0/keyframe_001.jpg"
        )
    assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════
#  Path Traversal Prevention Tests
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_invalid_course_id_negative(
    mock_config: str,
) -> None:
    """Negative course_id should return 404."""
    async with _client() as client:
        resp = await client.get("/api/course/-1/files")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_invalid_course_id_out_of_bounds(
    mock_config: str,
) -> None:
    """Out-of-bounds course_id should return 404."""
    async with _client() as client:
        resp = await client.get("/api/course/999/files")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_path_traversal_in_filename(
    mock_config: str,
) -> None:
    """Path traversal in filename should return 403."""
    async with _client() as client:
        resp = await client.get(
            "/api/course/0/notes/../../../etc/passwd.md"
        )
    # FastAPI may normalize the path, but our validation
    # catches '..' or basename mismatch
    assert resp.status_code in (403, 404, 400)


@pytest.mark.asyncio
async def test_path_traversal_static(
    mock_config: str,
) -> None:
    """Path traversal in static filename should be blocked."""
    async with _client() as client:
        resp = await client.get(
            "/static/0/..%2F..%2Fetc%2Fpasswd"
        )
    assert resp.status_code in (403, 404)


# ═══════════════════════════════════════════════════════════════════════
#  Settings Tests
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_settings_health_shape() -> None:
    """GET /api/settings/health returns correct shape."""
    async with _client() as client:
        resp = await client.get("/api/settings/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "ollama" in data
    assert "playwright" in data
    assert "keyring" in data
    assert isinstance(data["ollama"], bool)
    assert isinstance(data["playwright"], bool)
    assert isinstance(data["keyring"], bool)


@pytest.mark.asyncio
async def test_settings_pool_get() -> None:
    """GET /api/settings/pool returns a list."""
    with patch(
        "src.credentials.get_provider_pool_or_legacy"
    ) as mock_pool:
        from src.provider_pool import (
            ProviderPool,
            ProviderConfig,
        )
        pool = ProviderPool([
            ProviderConfig(
                provider="Groq",
                endpoint_url="https://api.groq.com",
                api_key="sk-abcdefgh12345678",
                model_name="llama3",
                capability="text",
            )
        ])
        mock_pool.return_value = pool
        async with _client() as client:
            resp = await client.get("/api/settings/pool")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    if len(data) > 0:
        entry = data[0]
        assert "masked_key" in entry
        # -- Verify key is masked, not full
        assert entry["masked_key"] == "sk-abcde..."
        assert "api_key" not in entry


# ═══════════════════════════════════════════════════════════════════════
#  Pipeline Tests
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_pipeline_cancel() -> None:
    """POST /api/pipeline/cancel sets the cancel event."""
    async with _client() as client:
        resp = await client.post("/api/pipeline/cancel")
    assert resp.status_code == 200
    assert resp.json()["success"] is True


# ═══════════════════════════════════════════════════════════════════════
#  Chat Tests
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_chat_send_invalid_dir() -> None:
    """Chat with invalid course_dir returns 400."""
    async with _client() as client:
        resp = await client.post(
            "/api/chat/send",
            json={
                "course_dir": "/nonexistent/path",
                "message": "Hello",
                "model": "llama3",
            },
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_chat_clear() -> None:
    """POST /api/chat/clear returns success."""
    async with _client() as client:
        resp = await client.post("/api/chat/clear")
    assert resp.status_code == 200
    assert resp.json()["success"] is True


# ═══════════════════════════════════════════════════════════════════════
#  CORS Tests
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cors_allowed_origin() -> None:
    """CORS should allow localhost:5173 origin."""
    async with _client() as client:
        resp = await client.options(
            "/api/library",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert resp.status_code == 200
    assert (
        resp.headers.get("access-control-allow-origin")
        == "http://localhost:5173"
    )


@pytest.mark.asyncio
async def test_cors_disallowed_origin() -> None:
    """CORS should reject non-localhost origins."""
    async with _client() as client:
        resp = await client.options(
            "/api/library",
            headers={
                "Origin": "http://evil.com",
                "Access-Control-Request-Method": "GET",
            },
        )
    # -- CORS middleware will not set the header for
    # disallowed origins
    allowed = resp.headers.get(
        "access-control-allow-origin", ""
    )
    assert allowed != "http://evil.com"
    assert allowed != "*"


# ═══════════════════════════════════════════════════════════════════════
#  Utility Tests
# ═══════════════════════════════════════════════════════════════════════


def test_mask_key_full() -> None:
    """_mask_key masks keys to first 8 chars + '...'."""
    assert _mask_key("sk-abcdefgh12345678") == "sk-abcde..."


def test_mask_key_short() -> None:
    """_mask_key with short key returns partial + '...'."""
    assert _mask_key("abc") == "abc..."


def test_mask_key_empty() -> None:
    """_mask_key with empty string returns empty."""
    assert _mask_key("") == ""


# ═══════════════════════════════════════════════════════════════════════
#  PDF Tests (without Playwright)
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_pdf_export_missing_file() -> None:
    """PDF export with nonexistent md_path returns 400."""
    async with _client() as client:
        resp = await client.post(
            "/api/pdf/export",
            json={
                "md_path": "/nonexistent/file.md",
                "theme": "Textbook",
            },
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_pdf_preview_missing_file() -> None:
    """PDF preview with nonexistent md_path returns 400."""
    async with _client() as client:
        resp = await client.post(
            "/api/pdf/preview",
            json={
                "md_path": "/nonexistent/file.md",
                "theme": "Textbook",
            },
        )
    assert resp.status_code == 400
