"""
Tests for the Chat Service REST endpoints.
"""
from typing import Generator
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.chat_service import app

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
async def test_chat_send_invalid_dir() -> None:
    async with _client() as client:
        resp = await client.post(
            "/chat/send",
            json={
                "course_dir": "/nonexistent/path",
                "message": "Hello",
                "model": "llama3",
            },
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_chat_clear() -> None:
    async with _client() as client:
        resp = await client.post("/chat/clear")
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_cors_allowed_origin() -> None:
    async with _client() as client:
        resp = await client.options(
            "/chat/send",
            headers={
                "Origin": "http://localhost:8000",
                "Access-Control-Request-Method": "POST",
            },
        )
    assert resp.status_code == 200
