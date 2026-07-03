"""
Parsing and segmentation utilities for YouTube transcripts and chapter outlines.
"""
import re
from difflib import SequenceMatcher

# Parser Regular Expressions
TIME_RE = r"(?:\d{1,2}(?::\d{2}){1,2}|\d{5,6})"

LINK_LINE_RE = re.compile(
    rf"\[({TIME_RE})\]\(https?://[^\)]+\)\s*[-–—:]?\s*(.*)"
)
BARE_LINE_RE = re.compile(
    rf"^\(?({TIME_RE})\)?\s*[-–—:]?\s*(.*)$"
)

EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\u2600-\u27BF"
    "\u2B00-\u2BFF"
    "\uFE0F"
    "\u20E3"
    "]"
)

TIMESTAMP_LINE_RE = re.compile(
    r"^(\d{1,2}):(\d{2}):(\d{2})\s*[-–—]\s*(\d{1,2}):(\d{2}):(\d{2})\s*$"
)


def normalize_timestamp_str(t_str):
    """Normalize timestamp string into H:MM:SS or HH:MM:SS format."""
    t_str = t_str.strip()
    if t_str.isdigit():
        val = t_str.zfill(5)
        if len(val) == 5:
            h = val[0]
            m = val[1:3]
            s = val[3:5]
        else:
            h = val[:-4]
            m = val[-4:-2]
            s = val[-2:]
        return f"{int(h)}:{m}:{s}"
    
    parts = t_str.split(":")
    if len(parts) == 1:
        try:
            sec = int(t_str)
            h = sec // 3600
            m = (sec % 3600) // 60
            s = sec % 60
            return f"{h}:{m:02d}:{s:02d}"
        except ValueError:
            return t_str
    elif len(parts) == 2:
        return f"0:{int(parts[0]):02d}:{int(parts[1]):02d}"
    elif len(parts) == 3:
        return f"{int(parts[0])}:{int(parts[1]):02d}:{int(parts[2]):02d}"
    return t_str

def parse_time_str(t):
    """Convert H:MM:SS or HH:MM:SS format to absolute seconds."""
    parts = [int(p) for p in t.strip().split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, s = parts[-3:]
    return h * 3600 + m * 60 + s

def reflow_blob_to_lines(text):
    """Add line breaks to flattened/single-line outlines for correct parsing."""
    if text.count("\n") >= 3:
        return text
    text = re.sub(rf"(?=\[?{TIME_RE}\]?)", "\n", text)
    text = re.sub(rf"(?=(?:{EMOJI_RE.pattern})+\s*[A-Za-z#])", "\n", text)
    return text

def clean_title(title):
    """Clean markdown links, emojis, and symbols from chapter titles."""
    title = title.strip(" -–—:\t")
    title = EMOJI_RE.sub("", title).strip()
    return title

def parse_outline_text(text):
    """Parse raw outline into normalized chapter information."""
    text = reflow_blob_to_lines(text)
    lines = [l.strip() for l in text.splitlines()]
    lines = [l for l in lines if l]

    chapters = []
    current_section = ""
    warnings = []

    for line in lines:
        m = LINK_LINE_RE.search(line)
        if not m:
            m = BARE_LINE_RE.match(line)
        if m and m.group(1):
            time_str = m.group(1)
            norm_time = normalize_timestamp_str(time_str)
            title = clean_title(m.group(2))
            if not title:
                warnings.append(f"Chapter at {time_str} has an empty title after cleanup.")
                title = f"(untitled @ {norm_time})"
            chapters.append({"time": norm_time, "title": title, "section": current_section})
        else:
            candidate = clean_title(line)
            if candidate and len(candidate) < 80 and not any(x in candidate.lower() for x in ["course outline", "table of contents", "timestamps"]):
                current_section = candidate

    chapters.sort(key=lambda c: parse_time_str(c["time"]))

    if len(chapters) < 2:
        warnings.append("Fewer than 2 chapters detected; the format might not have been recognized.")

    seen_times = set()
    for c in chapters:
        if c["time"] in seen_times:
            warnings.append(f"Duplicate timestamp {c['time']} found.")
        seen_times.add(c["time"])

    return chapters, warnings

def hms_to_seconds(h, m, s):
    return int(h) * 3600 + int(m) * 60 + int(s)

def parse_transcript_text(text):
    """Parse raw timestamped transcript into blocks of (start_sec, end_sec, text)."""
    blocks = []
    lines = text.splitlines()

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].strip()
        m = TIMESTAMP_LINE_RE.match(line)
        if m:
            start = hms_to_seconds(m.group(1), m.group(2), m.group(3))
            end = hms_to_seconds(m.group(4), m.group(5), m.group(6))
            i += 1
            text_lines = []
            while i < n and not TIMESTAMP_LINE_RE.match(lines[i].strip()):
                if lines[i].strip():
                    text_lines.append(lines[i].strip())
                i += 1
            text_val = " ".join(text_lines).strip()
            if text_val:
                blocks.append((start, end, text_val))
        else:
            i += 1
    return blocks

def dedupe_merge(blocks):
    """Merge overlapping caption windows using SequenceMatcher sequence comparison."""
    if not blocks:
        return []

    merged = []
    accumulated_words = blocks[0][2].split()
    merged.append((blocks[0][0], blocks[0][2]))

    for (start, end, text) in blocks[1:]:
        new_words = text.split()

        max_check = min(len(accumulated_words), len(new_words), 120)
        tail = accumulated_words[-max_check:] if max_check else []

        matcher = SequenceMatcher(None, tail, new_words[:max_check], autojunk=False)
        match = matcher.find_longest_match(0, len(tail), 0, len(new_words[:max_check]))

        skip = 0
        if match.size >= 3:
            skip = match.b + match.size

        new_chunk_words = new_words[skip:]
        if new_chunk_words:
            new_chunk = " ".join(new_chunk_words)
            merged.append((start, new_chunk))
            accumulated_words.extend(new_chunk_words)

    return merged

def assign_chapters(merged, chapters):
    """Assign merged transcript chunks to chapters according to timestamps."""
    chapter_starts = [c["time_sec"] for c in chapters]
    result = {i: [] for i in range(len(chapters))}

    for start_sec, text_chunk in merged:
        idx = 0
        for i, cstart in enumerate(chapter_starts):
            if cstart <= start_sec:
                idx = i
            else:
                break
        result[idx].append(text_chunk)

    return result
