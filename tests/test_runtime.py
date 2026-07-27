from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import runtime


def test_bundled_node_is_preferred(tmp_path, monkeypatch):
    node = tmp_path / "runtime" / "node" / "node.exe"
    node.parent.mkdir(parents=True)
    node.touch()
    monkeypatch.setattr(runtime, "application_root", lambda: tmp_path)
    monkeypatch.setattr(runtime.shutil, "which", lambda _: "C:/system/node.exe")
    assert runtime.resolve_node() == str(node)


def test_system_node_is_developer_fallback(monkeypatch):
    monkeypatch.setattr(runtime, "runtime_root", lambda: Path("missing-runtime"))
    monkeypatch.setattr(runtime.shutil, "which", lambda _: "C:/system/node.exe")
    assert runtime.resolve_node() == "C:/system/node.exe"


def test_missing_provider_is_clear_error(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "application_root", lambda: tmp_path)
    with pytest.raises(runtime.RuntimeSetupError, match="PO Token provider is missing"):
        runtime.resolve_pot_server()


def test_ping_failure_terminates_provider(monkeypatch):
    process = MagicMock()
    process.poll.return_value = None
    process.wait.side_effect = [None]
    clock = iter([0, 11])
    monkeypatch.setattr(runtime.time, "monotonic", lambda: next(clock))
    with pytest.raises(runtime.RuntimeSetupError, match="did not respond"):
        runtime.wait_for_pot_server(process, timeout=10)


def test_transcript_options_use_provider_and_no_credentials(monkeypatch):
    import src.youtube as youtube

    monkeypatch.setattr(youtube, "resolve_node", lambda: "bundled-node.exe")
    with patch("src.youtube.yt_dlp.YoutubeDL") as ydl:
        instance = ydl.return_value.__enter__.return_value
        instance.extract_info.return_value = {
            "requested_subtitles": {"en": {"url": "http://example/subs.vtt"}}
        }
        with patch("src.youtube.httpx.Client") as client_cls:
            response = client_cls.return_value.__enter__.return_value.get.return_value
            response.text = "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHello"
            youtube.get_transcript("url")
        options = ydl.call_args.args[0]
        assert options["js_runtimes"]["node"]["path"] == "bundled-node.exe"
        assert options["extractor_args"]["youtubepot-bgutilhttp"]["base_url"] == [runtime.POT_BASE_URL]
        assert "cookiefile" not in options
        assert "cookiesfrombrowser" not in options
        assert "proxy" not in options
