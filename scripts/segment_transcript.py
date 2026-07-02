#!/usr/bin/env python3
"""
segment_transcript.py

Takes a raw YouTube-style transcript (timestamped, overlapping caption windows)
and a JSON list of chapters (with start timestamps), and produces one clean,
deduplicated block of transcript text per chapter.

Usage:
    python segment_transcript.py --transcript transcript.txt --chapters chapters.json --out chapters_out

Input transcript format (repeating blocks):
    00:00:00 - 00:00:51
    <caption text ...>
    <blank line>
    00:00:26 - 00:01:20
    <caption text, overlapping with previous block ...>
    ...

chapters.json format:
    [
      {"time": "0:00:00", "title": "Welcome", "section": "Intro"},
      {"time": "0:07:19", "title": "What is Excel?", "section": "Intro"},
      ...
    ]
    Must be sorted by time ascending. "section" is optional (top-level grouping).

Output:
    <out>/chapters.json          -- chapter list with computed end times & word counts
    <out>/chapter_XX_<slug>.txt  -- deduplicated raw transcript text for that chapter
"""

import argparse
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

TIMESTAMP_LINE_RE = re.compile(
    r"^(\d{1,2}):(\d{2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2}):(\d{2})\s*$"
)


def hms_to_seconds(h, m, s):
    return int(h) * 3600 + int(m) * 60 + int(s)


def parse_time_str(t):
    """Parse 'H:MM:SS' or 'HH:MM:SS' or 'MM:SS' into seconds."""
    parts = [int(p) for p in t.strip().split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, s = parts[-3:]
    return h * 3600 + m * 60 + s


def parse_transcript(path):
    """Parse the raw transcript file into a list of (start_sec, end_sec, text) blocks."""
    blocks = []
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()

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
            text = " ".join(text_lines).strip()
            if text:
                blocks.append((start, end, text))
        else:
            i += 1
    return blocks


def dedupe_merge(blocks):
    """
    Merge overlapping caption windows into one continuous transcript,
    keeping start-time markers so we can later split by chapter.

    Returns a list of (approx_start_sec, new_text_chunk) tuples covering
    the whole video with duplicate text removed.
    """
    if not blocks:
        return []

    merged = []
    accumulated_words = blocks[0][2].split()
    merged.append((blocks[0][0], blocks[0][2]))

    for (start, end, text) in blocks[1:]:
        new_words = text.split()

        # Find overlap between tail of accumulated words and head of new_words
        # using a sliding comparison (bounded for performance).
        max_check = min(len(accumulated_words), len(new_words), 120)
        tail = accumulated_words[-max_check:] if max_check else []

        matcher = SequenceMatcher(None, tail, new_words[:max_check], autojunk=False)
        match = matcher.find_longest_match(0, len(tail), 0, len(new_words[:max_check]))

        skip = 0
        if match.size >= 3:  # require a meaningful overlap before trusting it
            skip = match.b + match.size

        new_chunk_words = new_words[skip:]
        if new_chunk_words:
            new_chunk = " ".join(new_chunk_words)
            merged.append((start, new_chunk))
            accumulated_words.extend(new_chunk_words)
        # if nothing new, this block was fully contained in previous -> skip

    return merged


def assign_chapters(merged, chapters):
    """
    chapters: list of dicts with 'time' (seconds) already resolved, sorted ascending.
    merged: list of (start_sec, text_chunk) sorted ascending by start_sec.

    Returns dict: chapter_index -> list of text chunks
    """
    chapter_starts = [c["time_sec"] for c in chapters]
    result = {i: [] for i in range(len(chapters))}

    for start_sec, text_chunk in merged:
        # find the last chapter whose start <= start_sec
        idx = 0
        for i, cstart in enumerate(chapter_starts):
            if cstart <= start_sec:
                idx = i
            else:
                break
        result[idx].append(text_chunk)

    return result


def slugify(text):
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[\s_-]+", "_", text)[:50]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--chapters", required=True, help="Path to chapters.json")
    ap.add_argument("--out", required=True, help="Output directory")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    chapters = json.loads(Path(args.chapters).read_text(encoding="utf-8"))
    for c in chapters:
        c["time_sec"] = parse_time_str(c["time"])
    chapters.sort(key=lambda c: c["time_sec"])

    blocks = parse_transcript(args.transcript)
    if not blocks:
        print("ERROR: no timestamped blocks found in transcript.", file=sys.stderr)
        sys.exit(1)

    merged = dedupe_merge(blocks)
    chapter_texts = assign_chapters(merged, chapters)

    manifest = []
    for i, c in enumerate(chapters):
        text = " ".join(chapter_texts[i]).strip()
        word_count = len(text.split())
        fname = f"chapter_{i+1:02d}_{slugify(c['title'])}.txt"
        (out_dir / fname).write_text(text, encoding="utf-8")

        end_sec = chapters[i + 1]["time_sec"] if i + 1 < len(chapters) else None
        manifest.append({
            "index": i + 1,
            "title": c["title"],
            "section": c.get("section", ""),
            "start_sec": c["time_sec"],
            "start_hms": c["time"],
            "end_sec": end_sec,
            "word_count": word_count,
            "file": fname,
        })

    (out_dir / "chapters_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    print(f"Parsed {len(blocks)} raw caption blocks -> {len(merged)} deduped chunks.")
    print(f"Wrote {len(chapters)} chapter files to {out_dir}/")
    low_word = [m for m in manifest if m["word_count"] < 30]
    if low_word:
        print("\nWARNING: these chapters have very little text (check timestamp alignment):")
        for m in low_word:
            print(f"  - #{m['index']} {m['title']} ({m['word_count']} words)")


if __name__ == "__main__":
    main()