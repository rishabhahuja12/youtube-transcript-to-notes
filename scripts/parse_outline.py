#!/usr/bin/env python3
"""
parse_outline.py — CLI wrapper for the outline parser.

Turns a raw chapter/timestamp outline into a normalized chapters.json.

Usage:
    python parse_outline.py outline.txt -o chapters.json
    python parse_outline.py outline.txt          # prints JSON to stdout
"""
import argparse
import json
import sys
from pathlib import Path

# Add parent directory to path so we can import from src/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.parser import parse_outline_text


def main():
    ap = argparse.ArgumentParser(description="Parse a raw chapter outline into structured JSON.")
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
