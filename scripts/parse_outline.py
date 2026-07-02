#!/usr/bin/env python3
"""
parse_outline.py

Best-effort auto-parser that turns a raw, arbitrarily-formatted chapter/timestamp
outline (pasted YouTube description, markdown chapter list, plain "00:00 Title"
lines, etc.) into a normalized chapters.json.

Handles:
  - Markdown link style:   [0:11:19](https://youtu.be/xyz&t=679s) - Excel Install
  - Plain style:           0:11:19 Excel Install   /   0:11:19 - Excel Install
  - YouTube native chapter format: 00:00 Title   (MM:SS or HH:MM:SS)
  - Section headers interspersed as non-timestamp lines (e.g. "1️⃣ Spreadsheets Intro")
    -> attached to subsequent chapters as "section" until the next header.
  - Single-blob paste where everything landed on one line (no real newlines):
    handled by inserting line breaks before every detected timestamp/section marker
    before parsing.

This is best-effort. It always prints a diagnostic summary so you can sanity-check
(or hand-fix) the result before running the rest of the pipeline. It is NOT meant to
silently produce a perfect result on every possible format -- if it gets something
wrong, edit the resulting JSON directly, or feed it a cleaner outline.

Usage:
    python3 parse_outline.py outline.txt -o chapters.json
    python3 parse_outline.py outline.txt          # prints JSON to stdout
"""

import argparse
import json
import re
import sys
from pathlib import Path

TIME_RE = r"\d{1,2}(?::\d{2}){1,2}"

LINK_LINE_RE = re.compile(
    rf"\[({TIME_RE})\]\(https?://[^\)]+\)\s*[-–—:]?\s*(.*)"
)
BARE_LINE_RE = re.compile(
    rf"^\(?({TIME_RE})\)?\s*[-–—:]?\s*(.*)$"
)

# Rough emoji / pictographic ranges, used to detect section-header lines and to
# find likely section-marker boundaries when re-splitting a flattened single-line blob.
EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\u2600-\u27BF"
    "\u2B00-\u2BFF"
    "\uFE0F"
    "\u20E3"
    "]"
)


def parse_time_str(t):
    parts = [int(p) for p in t.strip().split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, s = parts[-3:]
    return h * 3600 + m * 60 + s


def reflow_blob_to_lines(text):
    """
    If the outline arrived as one giant blob (no real newlines separating entries),
    insert line breaks before each timestamp marker and before emoji-led section
    headers so the line-based parser below can work on it.
    """
    if text.count("\n") >= 3:
        return text  # already reasonably line-based, leave it alone

    # Break before every timestamp occurrence (bracketed or bare).
    text = re.sub(rf"(?=\[?{TIME_RE}\]?)", "\n", text)
    # Break before emoji runs (likely section headers), so they land on their own line.
    text = re.sub(rf"(?=(?:{EMOJI_RE.pattern})+\s*[A-Za-z#])", "\n", text)
    return text


def clean_title(title):
    title = title.strip(" -–—:\t")
    title = EMOJI_RE.sub("", title).strip()
    return title


def parse_outline_text(text):
    """
    Returns (chapters, warnings) where chapters is a list of
    {"time": "H:MM:SS", "title": ..., "section": ...} sorted by time.
    """
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
            time_str, title = m.group(1), clean_title(m.group(2))
            if not title:
                warnings.append(f"Chapter at {time_str} has an empty title after cleanup -- check manually.")
                title = f"(untitled @ {time_str})"
            chapters.append({"time": time_str, "title": title, "section": current_section})
        else:
            # Not a chapter line -- likely a section header (or junk). Only treat as a
            # section header if it has real text after stripping emoji/symbols.
            candidate = clean_title(line)
            if candidate and len(candidate) < 80:
                current_section = candidate

    # Sort by resolved seconds, keep stable order for ties.
    chapters.sort(key=lambda c: parse_time_str(c["time"]))

    # Sanity checks
    if len(chapters) < 2:
        warnings.append("Fewer than 2 chapters detected -- outline format likely wasn't recognized. Check the input or build chapters.json by hand.")

    seen_times = set()
    for c in chapters:
        if c["time"] in seen_times:
            warnings.append(f"Duplicate timestamp {c['time']} -- check for a parsing artifact.")
        seen_times.add(c["time"])

    return chapters, warnings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outline", help="Path to raw outline text (any filename)")
    ap.add_argument("-o", "--output", help="Where to write chapters.json (default: stdout)")
    args = ap.parse_args()

    text = Path(args.outline).read_text(encoding="utf-8", errors="replace")
    chapters, warnings = parse_outline_text(text)

    print(f"Parsed {len(chapters)} chapters.", file=sys.stderr)
    for w in warnings:
        print(f"WARNING: {w}", file=sys.stderr)

    print("\nPreview:", file=sys.stderr)
    for c in chapters[:8]:
        sec = f"  [{c['section']}]" if c["section"] else ""
        print(f"  {c['time']:>10}  {c['title']}{sec}", file=sys.stderr)
    if len(chapters) > 8:
        print(f"  ... and {len(chapters) - 8} more", file=sys.stderr)

    out_json = json.dumps(chapters, indent=2)
    if args.output:
        Path(args.output).write_text(out_json, encoding="utf-8")
        print(f"\nWrote {args.output}", file=sys.stderr)
    else:
        print(out_json)


if __name__ == "__main__":
    main()
