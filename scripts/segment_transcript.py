#!/usr/bin/env python3
"""
segment_transcript.py — CLI wrapper for transcript segmentation.

Takes a raw YouTube-style transcript and a chapters.json, produces one clean
deduplicated text block per chapter.

Usage:
    python segment_transcript.py --transcript transcript.txt --chapters chapters.json --out chapters_out
"""
import argparse
import json
import re
import sys
from pathlib import Path

# Add parent directory to path so we can import from src/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.parser import parse_time_str, parse_transcript_text, dedupe_merge, assign_chapters


def slugify(text):
    """Create a filesystem-safe slug from a title."""
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[\s_-]+", "_", text)[:50]


def main():
    ap = argparse.ArgumentParser(description="Segment a transcript by chapter timestamps.")
    ap.add_argument("--transcript", required=True, help="Path to raw transcript file")
    ap.add_argument("--chapters", required=True, help="Path to chapters.json")
    ap.add_argument("--out", required=True, help="Output directory")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    chapters = json.loads(Path(args.chapters).read_text(encoding="utf-8"))
    for c in chapters:
        c["time_sec"] = parse_time_str(c["time"])
    chapters.sort(key=lambda c: c["time_sec"])

    transcript_text = Path(args.transcript).read_text(encoding="utf-8", errors="replace")
    blocks = parse_transcript_text(transcript_text)
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