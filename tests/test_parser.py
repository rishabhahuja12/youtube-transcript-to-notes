"""
Comprehensive test suite for src/parser.py
"""
import pytest

from src.parser import (
    normalize_timestamp_str,
    parse_time_str,
    clean_title,
    parse_outline_text,
    hms_to_seconds,
    parse_transcript_text,
    dedupe_merge,
    assign_chapters,
)


# ──────────────────────────────────────────────
# normalize_timestamp_str
# ──────────────────────────────────────────────
class TestNormalizeTimestampStr:
    """Tests for normalize_timestamp_str — converts various timestamp
    representations into a canonical H:MM:SS string."""

    def test_already_normalized_hms(self):
        assert normalize_timestamp_str("1:30:45") == "1:30:45"

    def test_zero_padded_hms(self):
        assert normalize_timestamp_str("01:02:03") == "1:02:03"

    def test_mm_ss_only(self):
        # Two-part "M:SS" → "0:05:30"
        assert normalize_timestamp_str("5:30") == "0:05:30"

    def test_pure_digit_five(self):
        # "12345" → zfill(5)="12345" → h=1, m=23, s=45
        assert normalize_timestamp_str("12345") == "1:23:45"

    def test_pure_digit_single_zero(self):
        # "0" is a single digit — it's *all digits* but only one char.
        # zfill(5) → "00000" → h=0, m=00, s=00
        assert normalize_timestamp_str("0") == "0:00:00"

    def test_pure_digit_3600(self):
        # "3600" → zfill(5)="03600" → h=0, m=36, s=00
        assert normalize_timestamp_str("3600") == "0:36:00"

    def test_leading_trailing_whitespace(self):
        assert normalize_timestamp_str("  1:30:45  ") == "1:30:45"

    def test_double_digit_mm_ss(self):
        assert normalize_timestamp_str("12:05") == "0:12:05"


# ──────────────────────────────────────────────
# parse_time_str
# ──────────────────────────────────────────────
class TestParseTimeStr:
    """Tests for parse_time_str — H:MM:SS string → total seconds."""

    def test_zero(self):
        assert parse_time_str("0:00:00") == 0

    def test_one_hour_thirty_min_fortyfive_sec(self):
        assert parse_time_str("1:30:45") == 5445

    def test_five_minutes_thirty_seconds(self):
        assert parse_time_str("0:05:30") == 330

    def test_mm_ss_only(self):
        # Two-part input: treated as M:SS → 0*3600 + 5*60 + 30 = 330
        assert parse_time_str("5:30") == 330

    def test_large_value(self):
        assert parse_time_str("10:00:00") == 36000


# ──────────────────────────────────────────────
# clean_title
# ──────────────────────────────────────────────
class TestCleanTitle:
    """Tests for clean_title — strips dashes, emojis, whitespace."""

    def test_strip_leading_dash(self):
        assert clean_title("- Hello World") == "Hello World"

    def test_strip_em_dash_and_whitespace(self):
        assert clean_title(" — Test ") == "Test"

    def test_strip_emoji(self):
        result = clean_title("🎉 Celebration Time 🎊")
        assert result == "Celebration Time"

    def test_empty_string(self):
        assert clean_title("") == ""

    def test_only_symbols(self):
        assert clean_title("---") == ""

    def test_colon_stripped(self):
        assert clean_title(": Introduction") == "Introduction"


# ──────────────────────────────────────────────
# parse_outline_text
# ──────────────────────────────────────────────
class TestParseOutlineText:
    """Tests for parse_outline_text — raw outline text → list of chapter dicts."""

    def test_standard_youtube_outline(self):
        outline = (
            "0:00 Introduction\n"
            "1:30 Chapter One\n"
            "5:00 Chapter Two\n"
        )
        chapters, warnings = parse_outline_text(outline)
        assert len(chapters) == 3
        assert chapters[0]["title"] == "Introduction"
        assert chapters[0]["time"] == "0:00:00"
        assert chapters[1]["title"] == "Chapter One"
        assert chapters[1]["time"] == "0:01:30"
        assert chapters[2]["title"] == "Chapter Two"

    def test_markdown_link_format(self):
        outline = (
            "[0:00:00](https://youtu.be/abc?t=0) Intro\n"
            "[0:05:30](https://youtu.be/abc?t=330) Deep Dive\n"
            "[0:10:00](https://youtu.be/abc?t=600) Wrap-Up\n"
        )
        chapters, warnings = parse_outline_text(outline)
        assert len(chapters) == 3
        assert chapters[0]["title"] == "Intro"
        assert chapters[1]["title"] == "Deep Dive"
        assert chapters[2]["time"] == "0:10:00"

    def test_sections_grouping(self):
        outline = (
            "Part A\n"
            "0:00 First Topic\n"
            "2:00 Second Topic\n"
            "Part B\n"
            "4:00 Third Topic\n"
        )
        chapters, warnings = parse_outline_text(outline)
        assert len(chapters) == 3
        assert chapters[0]["section"] == "Part A"
        assert chapters[2]["section"] == "Part B"

    def test_empty_input_warns(self):
        chapters, warnings = parse_outline_text("")
        assert len(chapters) < 2
        assert any("Fewer than 2" in w for w in warnings)

    def test_single_chapter_warns(self):
        chapters, warnings = parse_outline_text("0:00 Solo")
        assert len(chapters) == 1
        assert any("Fewer than 2" in w for w in warnings)

    def test_sorted_by_time(self):
        outline = (
            "5:00 Later\n"
            "0:00 Earlier\n"
        )
        chapters, _ = parse_outline_text(outline)
        assert chapters[0]["title"] == "Earlier"
        assert chapters[1]["title"] == "Later"

    def test_duplicate_timestamp_warning(self):
        outline = (
            "0:00 Intro\n"
            "0:00 Also Intro\n"
            "1:00 Next\n"
        )
        _, warnings = parse_outline_text(outline)
        assert any("Duplicate" in w for w in warnings)


# ──────────────────────────────────────────────
# hms_to_seconds
# ──────────────────────────────────────────────
class TestHmsToSeconds:
    """Tests for hms_to_seconds — basic H/M/S → seconds conversion."""

    def test_zero(self):
        assert hms_to_seconds(0, 0, 0) == 0

    def test_one_hour(self):
        assert hms_to_seconds(1, 0, 0) == 3600

    def test_mixed(self):
        assert hms_to_seconds(2, 30, 15) == 9015

    def test_string_args(self):
        assert hms_to_seconds("1", "02", "03") == 3723


# ──────────────────────────────────────────────
# parse_transcript_text
# ──────────────────────────────────────────────
class TestParseTranscriptText:
    """Tests for parse_transcript_text — raw transcript → list of (start, end, text)."""

    def test_normal_transcript(self):
        text = (
            "0:00:00 - 0:00:10\n"
            "Hello world, this is a test.\n"
            "\n"
            "0:00:10 - 0:00:20\n"
            "Second block of text.\n"
        )
        blocks = parse_transcript_text(text)
        assert len(blocks) == 2
        assert blocks[0] == (0, 10, "Hello world, this is a test.")
        assert blocks[1] == (10, 20, "Second block of text.")

    def test_empty_input(self):
        assert parse_transcript_text("") == []

    def test_no_timestamp_blocks(self):
        text = "Just some random text\nwith no timestamps at all.\n"
        assert parse_transcript_text(text) == []

    def test_multi_line_body(self):
        text = (
            "0:00:00 - 0:00:15\n"
            "Line one.\n"
            "Line two.\n"
            "Line three.\n"
        )
        blocks = parse_transcript_text(text)
        assert len(blocks) == 1
        assert blocks[0][2] == "Line one. Line two. Line three."

    def test_blank_body_skipped(self):
        text = (
            "0:00:00 - 0:00:05\n"
            "\n"
            "0:00:05 - 0:00:10\n"
            "Only this block has text.\n"
        )
        blocks = parse_transcript_text(text)
        assert len(blocks) == 1
        assert blocks[0][0] == 5


# ──────────────────────────────────────────────
# dedupe_merge
# ──────────────────────────────────────────────
class TestDedupeMerge:
    """Tests for dedupe_merge — merge overlapping caption windows."""

    def test_empty_input(self):
        assert dedupe_merge([]) == []

    def test_single_block(self):
        blocks = [(0, 10, "hello world")]
        result = dedupe_merge(blocks)
        assert len(result) == 1
        assert result[0] == (0, "hello world")

    def test_overlapping_blocks_deduped(self):
        # dedupe_merge requires >= 3 consecutive matching words to detect overlap
        blocks = [
            (0, 10, "alpha bravo charlie delta echo"),
            (5, 15, "charlie delta echo foxtrot golf"),
        ]
        result = dedupe_merge(blocks)
        # First block kept in full; second should only add new words
        assert len(result) == 2
        assert result[0] == (0, "alpha bravo charlie delta echo")
        assert "foxtrot" in result[1][1]
        assert "golf" in result[1][1]

    def test_non_overlapping_blocks_all_kept(self):
        blocks = [
            (0, 5, "aaa bbb ccc"),
            (10, 15, "xxx yyy zzz"),
        ]
        result = dedupe_merge(blocks)
        assert len(result) == 2
        assert result[0] == (0, "aaa bbb ccc")
        assert result[1] == (10, "xxx yyy zzz")

    def test_three_blocks_sequential_overlap(self):
        blocks = [
            (0, 10, "one two three four"),
            (5, 15, "three four five six"),
            (10, 20, "five six seven eight"),
        ]
        result = dedupe_merge(blocks)
        assert result[0] == (0, "one two three four")
        assert "five" in result[1][1]
        assert "seven" in result[2][1]


# ──────────────────────────────────────────────
# assign_chapters
# ──────────────────────────────────────────────
class TestAssignChapters:
    """Tests for assign_chapters — map merged transcript chunks to chapters."""

    def test_normal_assignment(self):
        chapters = [
            {"time_sec": 0, "title": "Intro"},
            {"time_sec": 60, "title": "Main"},
            {"time_sec": 120, "title": "Outro"},
        ]
        merged = [
            (5, "text in intro"),
            (70, "text in main"),
            (130, "text in outro"),
        ]
        result = assign_chapters(merged, chapters)
        assert result[0] == ["text in intro"]
        assert result[1] == ["text in main"]
        assert result[2] == ["text in outro"]

    def test_text_before_first_chapter(self):
        chapters = [
            {"time_sec": 10, "title": "First"},
            {"time_sec": 60, "title": "Second"},
        ]
        merged = [
            (0, "prelude text"),
            (15, "first chapter text"),
            (65, "second chapter text"),
        ]
        result = assign_chapters(merged, chapters)
        # Text at t=0 is before first chapter (t=10) → assigned to idx 0
        assert "prelude text" in result[0]
        assert "first chapter text" in result[0]
        assert "second chapter text" in result[1]

    def test_empty_chapters(self):
        result = assign_chapters([], [])
        assert result == {}

    def test_all_text_in_single_chapter(self):
        chapters = [{"time_sec": 0, "title": "Everything"}]
        merged = [
            (0, "aaa"),
            (10, "bbb"),
            (100, "ccc"),
        ]
        result = assign_chapters(merged, chapters)
        assert result[0] == ["aaa", "bbb", "ccc"]
