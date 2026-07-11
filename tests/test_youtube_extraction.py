import pytest
from unittest.mock import patch, MagicMock
from src.auth import get_video_metadata
from src.youtube import extract_from_url, extract_video_id, get_transcript, chapters_to_outline, auto_chunk_transcript, parse_vtt_to_blocks

def test_extract_video_id():
    assert extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_video_id("youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_video_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    
    with pytest.raises(ValueError):
        extract_video_id("invalid_url")

@patch("src.auth.build")
def test_get_video_metadata(mock_build):
    mock_yt = MagicMock()
    mock_videos = MagicMock()
    mock_list = MagicMock()
    
    mock_build.return_value = mock_yt
    mock_yt.videos.return_value = mock_videos
    mock_videos.list.return_value = mock_list
    
    mock_list.execute.return_value = {
        "items": [
            {
                "snippet": {
                    "title": "Test Video",
                    "channelTitle": "Test Channel",
                    "description": "Test description"
                },
                "contentDetails": {
                    "duration": "PT1H2M3S"
                }
            }
        ]
    }
    
    creds = MagicMock()
    metadata = get_video_metadata("test_id", creds)
    
    assert metadata["title"] == "Test Video"
    assert metadata["channel"] == "Test Channel"
    assert metadata["description"] == "Test description"
    assert metadata["duration"] == 3723

@patch("src.youtube.yt_dlp.YoutubeDL")
@patch("src.youtube.httpx.get")
def test_get_transcript(mock_get, mock_ytdl):
    mock_instance = MagicMock()
    mock_ytdl.return_value.__enter__.return_value = mock_instance
    
    mock_instance.extract_info.return_value = {
        "requested_subtitles": {
            "en": {"url": "http://example.com/subs.vtt"}
        }
    }
    
    mock_response = MagicMock()
    mock_response.text = "WEBVTT\n\n00:00:00.000 --> 00:00:05.000\nHello world!"
    mock_get.return_value = mock_response
    
    blocks = get_transcript("url")
    assert len(blocks) == 1
    assert blocks[0] == (0.0, 5.0, "Hello world!")

@patch("src.youtube.load_credentials")
@patch("src.youtube.get_video_metadata")
@patch("src.youtube.get_transcript")
def test_extract_from_url_success(mock_get_transcript, mock_get_video_metadata, mock_load_credentials):
    mock_load_credentials.return_value = MagicMock()
    mock_get_video_metadata.return_value = {
        "title": "Test Title",
        "channel": "Test Channel",
        "description": "0:00 Intro\n1:00 Middle\n2:00 End",
        "duration": 120
    }
    mock_get_transcript.return_value = [(0.0, 5.0, "Hello")]
    
    result = extract_from_url("dQw4w9WgXcQ")
    
    assert result["status"] == "complete"
    assert result["metadata"]["title"] == "Test Title"
    assert len(result["chapters"]) >= 2
    assert result["transcript_blocks"] == [(0.0, 5.0, "Hello")]

@patch("src.youtube.load_credentials")
@patch("src.youtube.get_video_metadata")
@patch("src.youtube.get_transcript")
def test_extract_from_url_transcript_failed(mock_get_transcript, mock_get_video_metadata, mock_load_credentials):
    mock_load_credentials.return_value = MagicMock()
    mock_get_video_metadata.return_value = {
        "title": "Test Title",
        "channel": "Test Channel",
        "description": "",
        "duration": 120
    }
    mock_get_transcript.side_effect = Exception("No subs")
    
    result = extract_from_url("dQw4w9WgXcQ")
    
    assert result["status"] == "transcript_failed"
    assert result["transcript_blocks"] == []
    assert len(result["chapters"]) == 0
