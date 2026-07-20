"""
Tests for the Content Service REST endpoints.
"""
import json
import os
import tempfile
from typing import Generator
from unittest.mock import patch, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.content_service import app, _load_library_entries, _mask_key

# ═══════════════════════════════════════════════════════════════════════
#  Fixtures
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture
def tmp_course_dir(tmp_path: str) -> str:
    """Create a temporary course directory with sample files."""
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

    return str(d)


@pytest.fixture
def mock_config(
    tmp_course_dir: str, tmp_path: str
) -> Generator:
    """Patch CONFIG_PATH to use a temp config with course dir."""
    config_file = tmp_path / "config.json"
    config_data = {
        "library": [
            {
                "id": "course_test123",
                "path": tmp_course_dir,
                "title": "TestCourse",
                "status": "complete"
            }
        ]
    }
    config_file.write_text(
        json.dumps(config_data), encoding="utf-8"
    )
    with patch("gateway.content_service.CONFIG_PATH", str(config_file)):
        yield str(config_file)


@pytest.fixture
def mock_empty_config(tmp_path: str) -> Generator:
    """Patch CONFIG_PATH to use an empty config."""
    config_file = tmp_path / "config_empty.json"
    config_data = {"recent_outputs": []}
    config_file.write_text(
        json.dumps(config_data), encoding="utf-8"
    )
    with patch("gateway.content_service.CONFIG_PATH", str(config_file)):
        yield str(config_file)

# ═══════════════════════════════════════════════════════════════════════
#  Helper
# ═══════════════════════════════════════════════════════════════════════


def _client() -> AsyncClient:
    """Create an async test client for the FastAPI app."""
    transport = ASGITransport(app=app)
    return AsyncClient(
        transport=transport, base_url="https://test"
    )

# ═══════════════════════════════════════════════════════════════════════
#  Tests
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_library_returns_list(
    mock_config: str, tmp_course_dir: str
) -> None:
    """GET /content/library should return a list of courses."""
    async with _client() as client:
        resp = await client.get("/content/library")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1
    course = data[0]
    assert "title" in course


@pytest.mark.asyncio
async def test_library_empty(mock_empty_config: str) -> None:
    """GET /content/library with no courses returns empty list."""
    async with _client() as client:
        resp = await client.get("/content/library")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_library_add(
    mock_config: str, tmp_course_dir: str
) -> None:
    """POST /content/library/add should return the created entry."""
    async with _client() as client:
        resp = await client.post(
            "/content/library/add",
            json={"path": tmp_course_dir},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert data["path"] == tmp_course_dir


@pytest.mark.asyncio
async def test_course_files(
    mock_config: str, tmp_course_dir: str
) -> None:
    """GET /content/course/0/files should list files."""
    async with _client() as client:
        lib_resp = await client.get("/content/library")
        course_id = lib_resp.json()[0]["id"]
        resp = await client.get(f"/content/course/{course_id}/files")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_course_notes(
    mock_config: str, tmp_course_dir: str
) -> None:
    """GET /content/course/0/notes/file.md returns content."""
    async with _client() as client:
        lib_resp = await client.get("/content/library")
        course_id = lib_resp.json()[0]["id"]
        resp = await client.get(f"/content/course/{course_id}/notes/Test_Detailed_Notes.md")
    assert resp.status_code == 200
    data = resp.json()
    assert "content" in data


@pytest.mark.asyncio
async def test_course_graph(
    mock_config: str, tmp_course_dir: str
) -> None:
    """GET /content/course/0/graph returns HTML content."""
    async with _client() as client:
        lib_resp = await client.get("/content/library")
        course_id = lib_resp.json()[0]["id"]
        resp = await client.get(f"/content/course/{course_id}/graph")
    assert resp.status_code == 200
    data = resp.json()
    assert "html" in data


@pytest.mark.asyncio
async def test_course_keyframes(
    mock_config: str, tmp_course_dir: str
) -> None:
    """GET /content/course/0/keyframes returns image list."""
    async with _client() as client:
        lib_resp = await client.get("/content/library")
        course_id = lib_resp.json()[0]["id"]
        resp = await client.get(f"/content/course/{course_id}/keyframes")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_static_file_serving(
    mock_config: str, tmp_course_dir: str
) -> None:
    """GET /static/0/keyframe_001.jpg serves the file."""
    async with _client() as client:
        lib_resp = await client.get("/content/library")
        course_id = lib_resp.json()[0]["id"]
        resp = await client.get(f"/static/{course_id}/keyframe_001.jpg")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_notes_path_traversal(
    mock_config: str, tmp_course_dir: str
) -> None:
    """GET /content/course/0/notes/../etc returns 403 or 404."""
    async with _client() as client:
        lib_resp = await client.get("/content/library")
        course_id = lib_resp.json()[0]["id"]
        resp = await client.get(f"/content/course/{course_id}/notes/..%2F..%2Fetc%2Fpasswd")
    assert resp.status_code in (403, 404)


@pytest.mark.asyncio
async def test_static_path_traversal(
    mock_config: str, tmp_course_dir: str
) -> None:
    """GET /static/0/../etc returns 403 or 404."""
    async with _client() as client:
        lib_resp = await client.get("/content/library")
        course_id = lib_resp.json()[0]["id"]
        resp = await client.get(f"/static/{course_id}/..%2F..%2Fetc%2Fpasswd")
    assert resp.status_code in (403, 404)


@pytest.mark.asyncio
async def test_settings_health_shape() -> None:
    """GET /settings/health returns correct shape."""
    async with _client() as client:
        resp = await client.get("/settings/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_settings_pool_get() -> None:
    """GET /settings/pool returns a list of configs."""
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
            resp = await client.get("/settings/pool")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    if len(data) > 0:
        entry = data[0]
        assert entry["masked_key"] == "sk-abcde..."


@pytest.mark.asyncio
async def test_settings_pool_post() -> None:
    """POST /settings/pool should return success."""
    with patch("src.credentials.store_provider_pool") as mock_store, patch("src.credentials.get_provider_pool_or_legacy") as mock_get:
        from src.provider_pool import ProviderPool
        mock_get.return_value = ProviderPool([])
        mock_store.return_value = True
        async with _client() as client:
            resp = await client.post(
                "/settings/pool",
                json={
                    "provider": "groq",
                    "endpoint_url": "https://api.groq.com",
                    "api_key": "sk-test",
                    "model_name": "llama3",
                    "capability": "text"
                }
            )
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    mock_store.assert_called_once()


@pytest.mark.asyncio
async def test_settings_pool_post_invalid() -> None:
    """POST /settings/pool should return 422 on validation failure."""
    with patch("src.credentials.get_provider_pool_or_legacy") as mock_get, patch("src.provider_pool.ProviderConfig") as mock_cfg_class:
        from src.provider_pool import ProviderPool
        mock_get.return_value = ProviderPool([])

        # Simulate ProviderConfig raising ValueError
        mock_cfg_class.side_effect = ValueError("Invalid capability")

        async with _client() as client:
            resp = await client.post(
                "/settings/pool",
                json={
                    "provider": "groq",
                    "endpoint_url": "https://api.groq.com",
                    "api_key": "sk-test",
                    "model_name": "llama3",
                    "capability": "invalid_cap"
                }
            )

    assert resp.status_code == 422
    assert "Invalid capability" in resp.json()["detail"]



@pytest.mark.asyncio
async def test_cors_allowed_origin() -> None:
    """CORS should allow localhost:8000 origin."""
    async with _client() as client:
        resp = await client.options(
            "/content/library",
            headers={
                "Origin": "http://localhost:8000",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert resp.status_code == 200


def test_mask_key_full() -> None:
    """_mask_key masks keys > 8 chars to first 8 chars + '...'."""
    assert _mask_key("sk-abcdefgh12345678") == "sk-abcde..."


def test_mask_key_short() -> None:
    """_mask_key masks keys <= 8 chars completely."""
    assert _mask_key("sk-abc") == "******"


def test_mask_key_empty() -> None:
    """_mask_key with empty string returns empty."""
    assert _mask_key("") == ""


@pytest.mark.asyncio
async def test_pdf_export_missing_file(mock_config: str, tmp_course_dir: str) -> None:
    """PDF export with nonexistent md_path returns 400."""
    async with _client() as client:
        lib_resp = await client.get("/content/library")
        course_id = lib_resp.json()[0]["id"]
        resp = await client.post(
            "/pdf/export",
            json={
                "course_id": course_id,
                "filename": "does_not_exist.md",
                "theme": "Textbook",
            },
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_pdf_export_success(mock_config: str, tmp_course_dir: str) -> None:
    """PDF export successfully generates a PDF file."""
    with patch("playwright.sync_api.sync_playwright") as mock_playwright:
        mock_p = MagicMock()
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_playwright.return_value.__enter__.return_value = mock_p
        mock_p.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page

        async with _client() as client:
            lib_resp = await client.get("/content/library")
            course_id = lib_resp.json()[0]["id"]
            resp = await client.post(
                "/pdf/export",
                json={
                    "course_id": course_id,
                    "filename": "Test_Detailed_Notes.md",
                    "theme": "Textbook",
                },
            )
        assert resp.status_code == 200
        assert "path" in resp.json()
        assert resp.json()["path"].endswith(".pdf")
        
        # Verify page.pdf was called
        mock_page.pdf.assert_called_once()
