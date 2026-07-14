"""
Tests for the Chat Service REST endpoints.
"""
import json
from typing import Generator
from unittest.mock import patch, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.chat_service import app

# ═══════════════════════════════════════════════════════════════════════
#  Fixtures
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture
def tmp_course_dir(tmp_path: str) -> str:
    """Create a temporary course directory."""
    d = tmp_path / "TestCourse"
    d.mkdir()
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


# ═══════════════════════════════════════════════════════════════════════
#  Helper
# ═══════════════════════════════════════════════════════════════════════


def _client() -> AsyncClient:
    """Create an async test client for the FastAPI app."""
    transport = ASGITransport(app=app)
    return AsyncClient(
        transport=transport, base_url="http://test"
    )

# ═══════════════════════════════════════════════════════════════════════
#  Tests
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_chat_send_invalid_dir(mock_config: str) -> None:
    """Chat with invalid course_id returns 404."""
    async with _client() as client:
        resp = await client.post(
            "/chat/send",
            json={
                "course_id": "999",
                "message": "Hello",
                "model": "llama3",
            },
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_chat_send_success(mock_config: str, tmp_course_dir: str) -> None:
    """Chat successfully sends a message."""
    from gateway.content_service import _load_library_entries
    course_id = _load_library_entries()[0]["id"]
    
    with patch("src.chat.ChatSession") as mock_chat_class:
        mock_instance = MagicMock()
        mock_instance.send.return_value = "Mock response"
        # Setup properties to avoid re-creation mismatch
        type(mock_instance).notes_dir = str(tmp_course_dir)
        type(mock_instance).ollama_model = "llama3"
        mock_chat_class.return_value = mock_instance

        async with _client() as client:
            resp = await client.post(
                "/chat/send",
                json={
                    "course_id": course_id,
                    "message": "Hello",
                    "model": "llama3",
                },
            )
        assert resp.status_code == 200
        assert resp.json()["response"] == "Mock response"
        mock_instance.send.assert_called_once_with("Hello")


@pytest.mark.asyncio
async def test_chat_clear() -> None:
    """POST /chat/clear returns success."""
    async with _client() as client:
        resp = await client.post("/chat/clear")
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_cors_allowed_origin() -> None:
    """CORS should allow localhost:8000 origin."""
    async with _client() as client:
        resp = await client.options(
            "/chat/send",
            headers={
                "Origin": "http://localhost:8000",
                "Access-Control-Request-Method": "POST",
            },
        )
    assert resp.status_code == 200
