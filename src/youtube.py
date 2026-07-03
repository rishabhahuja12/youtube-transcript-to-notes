"""
YouTube data extraction for the Transcript-to-Notes pipeline.

Uses youtube-transcript-api for lightweight transcript fetching and
yt-dlp for video metadata (chapters, description, title).
"""
import re
import os


def extract_video_id(url: str) -> str:
    """Extract YouTube video ID from various URL formats.
    Supports: youtube.com/watch?v=, youtu.be/, youtube.com/embed/, etc.
    Returns the video ID string or raises ValueError."""
    # Handle multiple YouTube URL formats
    patterns = [
        r'(?:youtube\.com/watch\?.*v=|youtu\.be/|youtube\.com/embed/|youtube\.com/v/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$',  # Bare video ID
    ]
    for pattern in patterns:
        match = re.search(pattern, url.strip())
        if match:
            return match.group(1)
    raise ValueError(f"Could not extract YouTube video ID from: {url}")


def fetch_transcript(video_id: str, language: str = 'en') -> list:
    """Fetch transcript using youtube-transcript-api.
    Returns list of dicts: [{text, start, duration}, ...]
    Tries: manual en -> auto-generated en -> any available language.
    Raises ImportError if library not installed, Exception on failure."""
    from youtube_transcript_api import YouTubeTranscriptApi

    try:
        # Try to get the requested language transcript
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=[language])
        return transcript
    except Exception:
        pass

    try:
        # Fallback: try any available transcript
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        # Prefer manual transcripts
        for t in transcript_list:
            if not t.is_generated:
                return t.fetch()
        # Fall back to auto-generated
        for t in transcript_list:
            if t.is_generated:
                return t.fetch()
    except Exception as e:
        raise Exception(f"Could not fetch transcript for video {video_id}: {str(e)}")

    raise Exception(f"No transcripts available for video {video_id}")


def fetch_metadata(url: str) -> dict:
    """Fetch video metadata using yt-dlp (no video download).
    Returns dict with keys: title, description, uploader, duration, chapters, upload_date.
    chapters is a list of {start_time: float, end_time: float, title: str}.
    Raises ImportError if yt-dlp not installed."""
    import yt_dlp

    ydl_opts = {
        'skip_download': True,
        'quiet': True,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    return {
        'title': info.get('title', 'Unknown'),
        'description': info.get('description', ''),
        'uploader': info.get('uploader', 'Unknown'),
        'duration': info.get('duration', 0),
        'chapters': info.get('chapters') or [],
        'upload_date': info.get('upload_date', ''),
    }


def transcript_to_blocks(transcript_entries: list) -> list:
    """Convert youtube-transcript-api entries into our standard (start_sec, end_sec, text) blocks.
    Input: [{text: str, start: float, duration: float}, ...]
    Output: [(start_sec, end_sec, text), ...]"""
    blocks = []
    for entry in transcript_entries:
        start = int(entry['start'])
        duration = entry.get('duration', 0)
        end = int(entry['start'] + duration)
        text = entry['text'].strip()
        if text:
            blocks.append((start, end, text))
    return blocks


def chapters_to_outline(chapters: list) -> list:
    """Convert yt-dlp chapter format to our standard chapter format.
    Input: [{start_time: float, end_time: float, title: str}, ...]
    Output: [{time: str, title: str, section: str}, ...] (H:MM:SS format)"""
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


def auto_chunk_transcript(transcript_entries: list, chunk_minutes: int = 5) -> list:
    """If no chapters are available, create artificial chapter boundaries
    by splitting the transcript every N minutes.
    Returns chapter list in standard format."""
    if not transcript_entries:
        return []

    total_duration = int(transcript_entries[-1]['start'] + transcript_entries[-1].get('duration', 0))
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
    """Full extraction pipeline from a YouTube URL.

    Returns dict with:
        - transcript_blocks: list of (start_sec, end_sec, text)
        - chapters: list of {time, title, section}
        - metadata: {title, uploader, duration, ...}
        - source_info: str describing what was used
    """
    log = on_log or (lambda msg: None)

    video_id = extract_video_id(url)
    log(f"Extracted video ID: {video_id}")

    # Step 1: Fetch metadata (chapters, title, description)
    log("Fetching video metadata via yt-dlp...")
    try:
        metadata = fetch_metadata(url)
        log(f"Video: '{metadata['title']}' by {metadata['uploader']} ({metadata['duration'] // 60} min)")
    except Exception as e:
        log(f"WARNING: Could not fetch metadata: {str(e)}")
        metadata = {'title': 'Unknown', 'description': '', 'uploader': 'Unknown', 'duration': 0, 'chapters': [], 'upload_date': ''}

    # Step 2: Fetch transcript
    log("Fetching transcript via youtube-transcript-api...")
    transcript_entries = fetch_transcript(video_id)
    log(f"Fetched {len(transcript_entries)} transcript entries.")

    transcript_blocks = transcript_to_blocks(transcript_entries)

    # Step 3: Get chapters (yt-dlp metadata -> description parsing -> auto-chunk)
    chapters = []
    source_info = ""

    if metadata['chapters']:
        chapters = chapters_to_outline(metadata['chapters'])
        source_info = f"Extracted {len(chapters)} chapters from YouTube chapter markers."
        log(source_info)
    else:
        log("No YouTube chapter markers found.")
        # Try parsing description for timestamps
        from src.parser import parse_outline_text
        if metadata['description']:
            log("Attempting to parse chapters from video description...")
            parsed_chapters, warnings = parse_outline_text(metadata['description'])
            if len(parsed_chapters) >= 2:
                chapters = parsed_chapters
                source_info = f"Parsed {len(chapters)} chapters from video description."
                log(source_info)
                for w in warnings:
                    log(f"  Warning: {w}")
            else:
                log("Description did not contain enough timestamps.")

        if not chapters:
            # Auto-chunk as last resort
            chapters = auto_chunk_transcript(transcript_entries, chunk_minutes=5)
            source_info = f"Auto-chunked transcript into {len(chapters)} parts (every 5 minutes)."
            log(source_info)

    return {
        'transcript_blocks': transcript_blocks,
        'chapters': chapters,
        'metadata': metadata,
        'source_info': source_info,
    }
