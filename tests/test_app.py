"""Unit tests for app.py public helper functions and utilities."""

import json
import os
from unittest.mock import MagicMock

import pytest

from app import (
    _get_shared_pdf_css,
    add_recent_output,
    check_ollama_status,
    get_powerup_time_hint,
    load_recent_outputs,
)


def test_load_recent_outputs_nonexistent(tmp_path, monkeypatch):
    """Test load_recent_outputs returns empty list when config does not exist."""
    fake_config = str(tmp_path / "nonexistent_config.json")
    monkeypatch.setattr("app.CONFIG_PATH", fake_config)
    assert load_recent_outputs() == []


def test_load_and_add_recent_output(tmp_path, monkeypatch):
    """Test adding recent output directory and loading it back."""
    fake_config = str(tmp_path / "config.json")
    monkeypatch.setattr("app.CONFIG_PATH", fake_config)

    test_dir1 = str(tmp_path / "course1")
    test_dir2 = str(tmp_path / "course2")
    os.makedirs(test_dir1, exist_ok=True)
    os.makedirs(test_dir2, exist_ok=True)

    add_recent_output(test_dir1)
    recents = load_recent_outputs()
    assert len(recents) == 1
    assert recents[0] == test_dir1

    # Add second directory
    add_recent_output(test_dir2)
    recents = load_recent_outputs()
    assert len(recents) == 2
    assert recents[0] == test_dir2


def test_add_recent_output_invalid(tmp_path, monkeypatch):
    """Test adding invalid or non-existent path is ignored."""
    fake_config = str(tmp_path / "config.json")
    monkeypatch.setattr("app.CONFIG_PATH", fake_config)

    add_recent_output("")
    add_recent_output("/non/existent/path/for/sure/12345")
    assert load_recent_outputs() == []


def test_get_shared_pdf_css_themes():
    """Test _get_shared_pdf_css returns valid CSS for all themes."""
    for theme in ["Textbook", "ChatGPT Dark", "Minimal Mono"]:
        css = _get_shared_pdf_css(theme)
        assert isinstance(css, str)
        assert "body" in css
        assert "@page" in css


def test_check_ollama_status_success(monkeypatch):
    """Test check_ollama_status happy path returning True."""
    mock_response = MagicMock()
    mock_response.getcode.return_value = 200

    def mock_urlopen(*args, **kwargs):
        return mock_response

    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
    assert check_ollama_status() is True


def test_check_ollama_status_failure(monkeypatch):
    """Test check_ollama_status error path returning False when offline."""

    def mock_urlopen(*args, **kwargs):
        raise Exception("Connection refused")

    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
    assert check_ollama_status() is False


def test_get_powerup_time_hint():
    """Test get_powerup_time_hint formatting for vision, KAG, and PDF."""
    assert "+ ~35s" in get_powerup_time_hint("vision", 600)
    assert "+ ~70s" in get_powerup_time_hint("vision", 1200)
    assert "+ ~15s" in get_powerup_time_hint("kag", 600)
    assert "+ ~5s" in get_powerup_time_hint("pdf")
    assert "+ 0s" in get_powerup_time_hint("unknown")
