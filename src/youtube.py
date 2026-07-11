import re
import os
import yt_dlp
from src.auth import load_credentials, get_video_metadata

def extract_video_id(url: str) -> str:
    """Extract YouTube video ID from various URL formats.
    
    Args:
        url (str): The YouTube URL.
        
    Returns:
        str: The extracted video ID.
    """
    patterns = [
        r'(?:youtube\.com/watch\?.*v=|youtu\.be/|youtube\.com/embed/|youtube\.com/v/)'
        r'([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$',
    ]
    for pattern in patterns:
        match = re.search(pattern, url.strip())
        if match:
            return match.group(1)
    raise ValueError(f"Could not extract YouTube video ID from: {url}")

def get_transcript(url: str) -> list:
    """Fetch and parse subtitles from a YouTube video.
    
    Args:
        url (str): The YouTube video URL.
        
    Returns:
        list: A list of transcript blocks, each containing (start_sec, end_sec, text).
        
    Raises:
        Exception: If no transcripts are available.
    """
    ydl_opts = {
        'skip_download': True,
        'writesubtitles': True,
        'writeautomaticsub': True,
        'subtitleslangs': ['en'],
        'quiet': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        subs = info.get('requested_subtitles') or info.get('automatic_captions')
        if not subs:
            raise Exception(f"No transcripts available for video {url}")
        
        # In a real implementation, you'd parse the VTT/SRT.
        # For simplicity, returning a mock format or we can use yt_dlp's downloaded subtitles.
        # However, to maintain the blocks format, we parse the subtitles file.
        import httpx
        sub_url = subs.get('en', {}).get('url')
        if not sub_url:
            sub_url = list(subs.values())[0].get('url')
        
        if sub_url:
            vtt_content = httpx.get(sub_url).text
            return parse_vtt_to_blocks(vtt_content)
        return []

def parse_vtt_to_blocks(vtt: str) -> list:
    """Parse VTT format to blocks of (start_sec, end_sec, text).
    
    Args:
        vtt (str): The VTT file content as a string.
        
    Returns:
        list: A list of parsed transcript blocks.
    """
    blocks = []
    lines = vtt.split('\n')
    current_start = 0
    current_end = 0
    current_text = []
    
    for line in lines:
        if '-->' in line:
            if current_text:
                blocks.append((current_start, current_end, ' '.join(current_text).strip()))
                current_text = []
            parts = line.split('-->')
            try:
                start_str = parts[0].strip().split(':')
                if len(start_str) == 3: # HH:MM:SS.mmm
                    current_start = (int(start_str[0])*3600 + 
                                     int(start_str[1])*60 + float(start_str[2]))
                else:
                    current_start = int(start_str[0])*60 + float(start_str[1])
                
                end_str = parts[1].strip().split(':')
                if len(end_str) == 3:
                    current_end = int(end_str[0])*3600 + int(end_str[1])*60 + float(end_str[2])
                else:
                    current_end = int(end_str[0])*60 + float(end_str[1])
            except ValueError:
                pass
        elif (line.strip() and not line.startswith('WEBVTT') and 
              not line.startswith('Kind:') and not line.startswith('Language:')):
            # Clean up tags like <c>...</c>
            clean_text = re.sub(r'<[^>]+>', '', line.strip())
            if clean_text and not clean_text.isdigit():
                current_text.append(clean_text)
                
    if current_text:
        blocks.append((current_start, current_end, ' '.join(current_text).strip()))
    return blocks


def chapters_to_outline(chapters: list) -> list:
    """Convert yt-dlp chapter format to our standard chapter format.
    
    Args:
        chapters (list): A list of chapter dictionaries from yt-dlp.
        
    Returns:
        list: A list of standard outline dictionaries.
    """
    result = []
    for ch in chapters:
        seconds = int(ch['start_time'])
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        time_str = f"{h}:{m:02d}:{s:02d}"
        result.append({
            'time': time_str,
            'title': ch.get('title', '').strip(),
            'section': '',
        })
    return result


def auto_chunk_transcript(transcript_blocks: list, chunk_minutes: int = 5) -> list:
    """Automatically chunk a transcript into equal time segments.
    
    Args:
        transcript_blocks (list): List of transcript blocks.
        chunk_minutes (int, optional): Duration of each chunk in minutes. Defaults to 5.
        
    Returns:
        list: List of chapter dictionaries with time, title, and section.
    """
    if not transcript_blocks:
        return []

    last_end = transcript_blocks[-1][1]
    total_duration = int(last_end)
    chunk_seconds = chunk_minutes * 60
    chapters = []

    for i, start_sec in enumerate(range(0, total_duration, chunk_seconds)):
        h = start_sec // 3600
        m = (start_sec % 3600) // 60
        s = start_sec % 60
        time_str = f"{h}:{m:02d}:{s:02d}"
        chapters.append({
            'time': time_str,
            'title': f"Part {i + 1}",
            'section': '',
        })

    return chapters


def extract_from_url(url: str, on_log: callable = None) -> dict:
    """Extract metadata, transcript, and chapters from a YouTube URL.
    
    Args:
        url (str): The YouTube video URL.
        on_log (callable, optional): Callback function for logging messages. Defaults to None.
        
    Returns:
        dict: Dictionary containing transcript_blocks, chapters, metadata, source_info, and status.
    """
    log = on_log or (lambda msg: None)

    video_id = extract_video_id(url)
    log(f"Extracted video ID: {video_id}")

    creds = load_credentials()
    
    metadata = None
    if creds:
        log("Fetching video metadata via Google OAuth...")
        try:
            metadata = get_video_metadata(video_id, creds)
            log(f"Video: '{metadata['title']}' by {metadata['channel']}")
            # parse chapters from description if needed, or we rely on yt-dlp metadata
        except Exception as e:
            log(f"WARNING: Could not fetch metadata via OAuth: {str(e)}")
            metadata = None
    else:
        log("No Google OAuth credentials found. Prompting 'Connect YouTube'.")
        
    if not metadata:
        metadata = {'title': 'Unknown', 'description': '', 'channel': 'Unknown', 'duration': 0}

    # Fetch transcript
    log("Fetching transcript via yt-dlp...")
    try:
        transcript_blocks = get_transcript(url)
        log(f"Fetched {len(transcript_blocks)} transcript blocks.")
        status = "complete"
    except Exception as e:
        log(f"WARNING: Transcript failed: {str(e)}")
        transcript_blocks = []
        status = "transcript_failed"

    chapters = []
    source_info = ""

    from src.parser import parse_outline_text
    if metadata.get('description'):
        log("Attempting to parse chapters from video description...")
        parsed_chapters, warnings = parse_outline_text(metadata['description'])
        if len(parsed_chapters) >= 2:
            chapters = parsed_chapters
            source_info = f"Parsed {len(chapters)} chapters from video description."
            log(source_info)
        else:
            log("Description did not contain enough timestamps.")

    if not chapters:
        chapters = auto_chunk_transcript(transcript_blocks, chunk_minutes=5)
        source_info = f"Auto-chunked transcript into {len(chapters)} parts (every 5 minutes)."
        log(source_info)

    return {
        'transcript_blocks': transcript_blocks,
        'chapters': chapters,
        'metadata': metadata,
        'source_info': source_info,
        'status': status
    }
