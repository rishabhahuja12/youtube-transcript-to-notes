"""
Video download and keyframe extraction utilities for vision-enabled LLM pipelines.
"""
import os
import re
import urllib.request
from typing import List, Dict, Any

def download_video(url: str, output_dir: str, resolution: str = "360p", cancel_event=None) -> str:
    """Download low-res video via yt-dlp.

    Args:
        url (str): The YouTube URL to download.
        output_dir (str): The directory to save the downloaded video.
        resolution (str, optional): The maximum resolution to download. Defaults to "360p".
        cancel_event: Event to interrupt download.

    Returns:
        str: The absolute path to the downloaded video file.
    """
    import yt_dlp
    
    os.makedirs(output_dir, exist_ok=True)
    outtmpl = os.path.join(output_dir, _slugify("video") + ".%(ext)s")
    
    def progress_hook(d):
        if cancel_event and cancel_event.is_set():
            raise Exception("Download cancelled by user")
            
    ydl_opts = {
        # Only download video (no audio) to save bandwidth and bypass ffmpeg merge requirements
        'format': f'bestvideo[ext=mp4][height<={resolution.replace("p", "")}]/bestvideo[height<={resolution.replace("p", "")}]',
        'outtmpl': outtmpl,
        'quiet': True,
        'no_warnings': True,
        'progress_hooks': [progress_hook]
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            return filename
    except Exception as e:
        if "cancelled" in str(e).lower():
            raise Exception("Cancelled by user") from e
        raise

def extract_key_frames(video_path: str, output_dir: str, chapters: List[Dict[str, Any]], cancel_event=None) -> Dict[int, List[str]]:
    """Extract frames using Chapter-Aware Condensation to avoid coding tutorial bloat.
    
    Args:
        video_path (str): The path to the downloaded video.
        output_dir (str): The directory to save the extracted frames.
        chapters (List[Dict[str, Any]]): The list of parsed chapters, sorted by time.
        cancel_event: Event to interrupt extraction.
        
    Returns:
        Dict[int, List[str]]: A dictionary mapping chapter indices to a list of frame paths.
    """
    import cv2
    os.makedirs(output_dir, exist_ok=True)
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise Exception("Could not open video file.")
        
    assigned = {i: [] for i in range(len(chapters))}
    
    if not chapters:
        cap.release()
        return assigned
        
    total_duration = cap.get(cv2.CAP_PROP_FRAME_COUNT) / cap.get(cv2.CAP_PROP_FPS) if cap.get(cv2.CAP_PROP_FPS) else 0

    for i, ch in enumerate(chapters):
        if cancel_event and cancel_event.is_set():
            break
            
        start_sec = ch['time_sec']
        end_sec = chapters[i+1]['time_sec'] if i + 1 < len(chapters) else (max(start_sec + 300, total_duration) if total_duration > 0 else start_sec + 300)
        duration = end_sec - start_sec
        
        # Snipe frames at 30%, 70%, and 95%
        target_secs = [
            start_sec + (duration * 0.3),
            start_sec + (duration * 0.7),
            start_sec + (duration * 0.95)
        ]
        
        chapter_frame_data = []
        
        for sec in target_secs:
            if cancel_event and cancel_event.is_set():
                break
                
            cap.set(cv2.CAP_PROP_POS_MSEC, sec * 1000)
            ret, frame = cap.read()
            if ret:
                # Blur detection (Variance of Laplacian)
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
                if sharpness < 50.0:
                    continue # Skip blurry frame
                    
                hist = cv2.calcHist([frame], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
                cv2.normalize(hist, hist)
                
                chapter_frame_data.append({"frame": frame, "sec": int(sec), "hist": hist})
                
        if not chapter_frame_data:
            continue
            
        # Keep the final state (95%)
        final_data = chapter_frame_data[-1]
        saved_frames = [final_data]
        
        # Compare backwards
        for data in reversed(chapter_frame_data[:-1]):
            similarity = cv2.compareHist(saved_frames[0]["hist"], data["hist"], cv2.HISTCMP_CORREL)
            # If the earlier frame is distinctly different (similarity < 0.85), keep it
            if similarity < 0.85:
                saved_frames.insert(0, data)
                
        # Save the selected frames
        for data in saved_frames:
            filename = _slugify(f"ch_{i}_frame_{data['sec']}s") + ".jpg"
            frame_path = os.path.join(output_dir, filename)
            cv2.imwrite(frame_path, data["frame"])
            assigned[i].append(frame_path)
            
    cap.release()
    return assigned

def _slugify(text: str) -> str:
    """Validate and sanitize filename.
    
    Args:
        text (str): The filename string to sanitize.
        
    Returns:
        str: The sanitized filename string.
    """
    text = text.lower().replace(" ", "-")
    return re.sub(r'[^a-z0-9_\-]', '', text)
