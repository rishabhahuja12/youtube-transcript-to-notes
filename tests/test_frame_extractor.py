import os
import pytest
from unittest.mock import patch, MagicMock
from src.frame_extractor import download_video, extract_key_frames, assign_frames_to_chapters, _slugify

def test_slugify():
    assert _slugify("Hello World!") == "hello-world"
    assert _slugify("frame_10s.jpg") == "frame_10sjpg"
    assert _slugify("../traversal/file.txt") == "traversalfiletxt"

def test_assign_frames_to_chapters():
    frames = [
        {"path": "frame_0.jpg", "timestamp_sec": 0},
        {"path": "frame_15.jpg", "timestamp_sec": 15},
        {"path": "frame_45.jpg", "timestamp_sec": 45},
        {"path": "frame_75.jpg", "timestamp_sec": 75}
    ]
    chapters = [
        {"title": "Intro", "time_sec": 0},
        {"title": "Middle", "time_sec": 30},
        {"title": "End", "time_sec": 60}
    ]
    
    assigned = assign_frames_to_chapters(frames, chapters)
    
    assert len(assigned) == 3
    assert assigned[0] == ["frame_0.jpg", "frame_15.jpg"]
    assert assigned[1] == ["frame_45.jpg"]
    assert assigned[2] == ["frame_75.jpg"]

def test_assign_frames_empty():
    assert assign_frames_to_chapters([], [{"time_sec": 0}]) == {0: []}
    assert assign_frames_to_chapters([{"path": "f.jpg", "timestamp_sec": 10}], []) == {}

@patch("yt_dlp.YoutubeDL")
def test_download_video_happy_path(mock_ytdl):
    mock_instance = MagicMock()
    mock_ytdl.return_value.__enter__.return_value = mock_instance
    mock_instance.extract_info.return_value = {"id": "123"}
    mock_instance.prepare_filename.return_value = "/fake/dir/video.mp4"
    
    res = download_video("http://youtube.com/watch?v=123", "/fake/dir")
    assert res == "/fake/dir/video.mp4"
    mock_instance.extract_info.assert_called_once_with("http://youtube.com/watch?v=123", download=True)

@patch("yt_dlp.YoutubeDL")
def test_download_video_error_path(mock_ytdl):
    mock_instance = MagicMock()
    mock_ytdl.return_value.__enter__.return_value = mock_instance
    mock_instance.extract_info.side_effect = Exception("Download failed")
    
    with pytest.raises(Exception, match="Download failed"):
        download_video("http://youtube.com/watch?v=123", "/fake/dir")

@patch("cv2.imwrite")
@patch("cv2.absdiff")
@patch("cv2.cvtColor")
@patch("cv2.VideoCapture")
@patch("src.frame_extractor.os.makedirs")
def test_extract_key_frames_happy_path(mock_makedirs, mock_videocapture, mock_cvtcolor, mock_absdiff, mock_imwrite):
    mock_cap = MagicMock()
    mock_videocapture.return_value = mock_cap
    mock_cap.isOpened.return_value = True
    mock_cap.get.return_value = 30.0 # fps
    
    import numpy as np
    fake_frame1 = np.zeros((10, 10, 3), dtype=np.uint8)
    fake_frame2 = np.ones((10, 10, 3), dtype=np.uint8) * 255
    
    # Return 2 frames, then stop
    mock_cap.read.side_effect = [(True, fake_frame1), (True, fake_frame2), (False, None)]
    
    mock_cvtcolor.side_effect = lambda frame, code: frame[:,:,0] # mock grayscale
    mock_absdiff.return_value = np.ones((10, 10), dtype=np.uint8) * 50 # difference is large
    
    frames = extract_key_frames("video.mp4", "/fake/dir", method="scene_change", interval=1)
    
    assert len(frames) > 0
    assert "path" in frames[0]
    assert "timestamp_sec" in frames[0]
    mock_imwrite.assert_called()

@patch("cv2.VideoCapture")
def test_extract_key_frames_error_path(mock_videocapture):
    mock_cap = MagicMock()
    mock_videocapture.return_value = mock_cap
    mock_cap.isOpened.return_value = False
    
    with pytest.raises(Exception, match="Could not open video file."):
        extract_key_frames("invalid.mp4", "/fake/dir")
