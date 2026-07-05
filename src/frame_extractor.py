import os
import re
import urllib.request
from typing import List, Dict

def download_video(url: str, output_dir: str, resolution: str = "360p") -> str:
    """Download low-res video via yt-dlp.

    Args:
        url (str): The YouTube URL to download.
        output_dir (str): The directory to save the downloaded video.
        resolution (str, optional): The maximum resolution to download. Defaults to "360p".

    Returns:
        str: The absolute path to the downloaded video file.
    """
    import yt_dlp
    
    os.makedirs(output_dir, exist_ok=True)
    outtmpl = os.path.join(output_dir, _slugify("video") + ".%(ext)s")
    
    ydl_opts = {
        'format': f'bestvideo[height<={resolution.replace("p", "")}]+bestaudio/best',
        'outtmpl': outtmpl,
        'quiet': True,
        'no_warnings': True,
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return filename

def extract_key_frames(video_path: str, output_dir: str, method: str = "scene_change", interval: int = 30) -> List[Dict]:
    """Extract frames from video.
    
    Args:
        video_path (str): The path to the downloaded video.
        output_dir (str): The directory to save the extracted frames.
        method (str, optional): The method of extraction ("scene_change" or "interval"). Defaults to "scene_change".
        interval (int, optional): The extraction interval in seconds. Defaults to 30.
        
    Returns:
        List[Dict]: A list of dictionaries containing 'path' (str) and 'timestamp_sec' (int).
    """
    import cv2
    os.makedirs(output_dir, exist_ok=True)
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise Exception("Could not open video file.")
        
    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 0:
        fps = 30.0 # fallback
        
    frames = []
    
    if method == "scene_change":
        # simple threshold-based scene change detection
        # fallback to interval if not enough scene changes are found
        prev_frame_gray = None
        current_sec = 0
        last_extracted_sec = -interval
        frame_idx = 0
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
                
            current_sec = int(frame_idx / fps)
            
            # extract every interval anyway, or if scene change is high
            extract = False
            
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if prev_frame_gray is not None:
                diff = cv2.absdiff(prev_frame_gray, gray)
                mean_diff = diff.mean()
                if mean_diff > 30 and (current_sec - last_extracted_sec) >= 5: # at least 5s apart
                    extract = True
            
            if (current_sec - last_extracted_sec) >= interval:
                extract = True
                
            if extract:
                filename = _slugify(f"frame_{current_sec}s") + ".jpg"
                frame_path = os.path.join(output_dir, filename)
                cv2.imwrite(frame_path, frame)
                frames.append({"path": frame_path, "timestamp_sec": current_sec})
                last_extracted_sec = current_sec
                
            prev_frame_gray = gray
            frame_idx += int(fps) # skip to next second for speed if possible? No, we need to read sequentially for diff.
            # actually to speed up we can skip frames
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            
    cap.release()
    return frames

def assign_frames_to_chapters(frames: List[Dict], chapters: List[Dict]) -> Dict[int, List[str]]:
    """Map frames to chapter indices by timestamp range.
    
    Args:
        frames (List[Dict]): The list of extracted frames.
        chapters (List[Dict]): The list of parsed chapters, sorted by time.
        
    Returns:
        Dict[int, List[str]]: A dictionary mapping chapter indices to a list of frame paths.
    """
    assigned = {i: [] for i in range(len(chapters))}
    
    if not chapters:
        return assigned
        
    for frame in frames:
        t = frame["timestamp_sec"]
        # Find the chapter this frame belongs to
        assigned_idx = 0
        for i, ch in enumerate(chapters):
            if t >= ch["time_sec"]:
                assigned_idx = i
            else:
                break
        assigned[assigned_idx].append(frame["path"])
        
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
