---
name: transcript-chapter-notes
description: Turns a full timestamped video/podcast transcript plus a chapter/timestamp outline into polished, chapter-by-chapter revision notes as Markdown files. Use this whenever the user has (or can paste) a raw transcript with timestamps and a list of chapter timestamps/titles (e.g. a YouTube "Course Outline" or chapter list) and wants notes, summaries, a study guide, or revision material organized by chapter/section. Trigger on phrases like "make notes from this transcript", "chapter-wise notes", "turn this lecture transcript into notes", "study guide from this video", "summarize this course by chapter", or any request to convert a long transcript + timestamps into structured, revision-ready notes. Do NOT use for short transcripts with no chapter structure, or for simple one-shot summarization requests that don't reference timestamps/chapters.
---

# Transcript → Chapter-wise Revision Notes

Converts a long, raw, timestamped transcript (e.g. auto-generated YouTube captions,
often with overlapping/duplicated caption windows) into clean, chapter-by-chapter
study notes in Markdown, enriched with Claude's own knowledge (definitions, examples,
syntax, gotchas, revision summaries) — not just a compressed re-statement of the transcript.

## When this skill applies

- The user has a transcript file (or pastes transcript text) that includes timestamps.
- The user has (or can provide) a chapter outline: a list of timestamps + titles,
  such as a YouTube video description's "Course Outline" / chapter markers.
- The user wants organized notes, a study guide, or revision material — not just a
  single summary paragraph.

If there's no chapter/timestamp structure at all, this skill doesn't apply — just
summarize normally instead.

## Overview of the workflow

1. **Get the two inputs**: raw transcript + chapter outline.
2. **Normalize the chapter outline into `chapters.json`** (Claude does this directly —
   outline formats vary too much for a fixed parser).
3. **Run `scripts/segment_transcript.py`** to deduplicate overlapping caption windows
   and split the transcript into one clean text block per chapter.
4. **For each chapter, write revision notes** using the chapter's transcript text —
   this is the step where Claude adds real value beyond mechanical extraction.
5. **Compile into final Markdown file(s)** and deliver to the user.

---

## Step 1: Get the inputs

Check the conversation and any uploaded files first — don't ask for something already
provided.

- **Transcript**: Expected format is repeating blocks of:
  ```
  HH:MM:SS - HH:MM:SS
  <caption text...>

  HH:MM:SS - HH:MM:SS
  <caption text...>
  ```
  Consecutive blocks commonly overlap (rolling caption windows) — this is handled
  automatically in Step 3, don't try to dedupe it by hand.

  If the transcript is in a different format (e.g. `[00:00:00] text`, SRT/VTT, or
  plain paragraphs with occasional timestamps), still proceed: adapt by either
  reformatting it to the expected format with a quick script, or parsing it directly
  yourself if it's short enough — segment_transcript.py's parser regex is
  `^(H)?H:MM:SS - (H)?H:MM:SS$` for the marker lines. For SRT/VTT, convert first.

- **Chapter outline**: Whatever the user pastes/uploads — YouTube description text,
  a bullet list, a table, etc. Formats vary wildly (emojis, markdown links, nested
  sections). Don't try to regex this — read it yourself and extract it.

If either input is missing, ask for it (don't guess a transcript into existence).

## Step 2: Normalize the chapter outline into chapters.json

Read the outline and produce a JSON array, sorted by time ascending:

```json
[
  {"time": "0:00:00", "title": "Welcome", "section": "Intro"},
  {"time": "0:03:53", "title": "What is Excel?", "section": "Intro"},
  {"time": "0:11:19", "title": "Excel Install", "section": "Excel Setup"}
]
```

- `time`: `H:MM:SS` or `HH:MM:SS`, the chapter's **start** time.
- `title`: the chapter/lesson title, cleaned up (strip markdown link syntax, emoji,
  leading dashes).
- `section`: the higher-level grouping the chapter belongs to, if the outline has one
  (e.g. numbered/emoji section headers like "1️⃣ Spreadsheets Intro" grouping several
  chapters underneath). If the outline is flat, omit or leave blank.

Save this as `chapters.json` in your working directory. Double check count and order
against the source outline before moving on — a misparsed timestamp silently shifts
every chapter's boundaries.

## Step 3: Segment the transcript

Run:

```bash
python3 scripts/segment_transcript.py \
  --transcript <path-to-transcript> \
  --chapters chapters.json \
  --out chapter_segments
```

This produces:
- `chapter_segments/chapter_NN_<slug>.txt` — deduplicated raw transcript text for
  each chapter (one file per chapter, in order).
- `chapter_segments/chapters_manifest.json` — chapter metadata: title, section,
  start/end seconds, word count, filename.

**Check the script's stdout.** It warns about chapters with suspiciously low word
counts (<30 words) — this usually means a timestamp in `chapters.json` didn't match
the transcript's actual timeline (e.g. transcript starts at a different offset, or a
timestamp was mistyped). Investigate and re-run rather than silently producing a
near-empty chapter's notes.

For very long courses (3+ hours, 20+ chapters), read the manifest first to get a
sense of scale before diving into Step 4.

## Step 4: Write revision notes per chapter

This is the core value-add step — **do not just compress or lightly reword the
transcript text.** For each chapter, read its segment file and produce notes that
would actually help someone revise the material later, without needing to rewatch.

For each chapter, write a Markdown section with (adapt structure to content —
not every chapter needs every subsection, especially short intro/narrative chapters):

- **`## <Chapter number>. <Title>`** heading, with the timestamp range and a link
  back to the video moment if a base video URL is available (`?t=<seconds>s`).
- **Summary** (2-4 sentences): what this chapter covers and why it matters.
- **Key concepts / steps**: the actual substance — definitions, procedures, steps in
  order. Use your own knowledge of the subject to state these precisely and
  correctly, even if the transcript's phrasing (especially auto-captions) is loose,
  informal, or has transcription errors. Fix obvious caption errors silently based
  on context (e.g. "Micosoft" → "Microsoft", "squel" → "SQL").
- **Syntax / commands / formulas**, when the chapter is technical: give the actual
  correct syntax in a code block, even if the transcript only describes it verbally.
  E.g. if the transcript talks about "using an IF function inside an array formula",
  include the real formula syntax, not just prose.
- **Examples**: concrete worked examples if the transcript mentions specific ones,
  otherwise a short illustrative example you construct that matches the taught
  concept.
- **Common pitfalls / gotchas**: anything the speaker warns about, plus, if useful,
  pitfalls you know are common for this topic even if unstated.
- **Quick revision recap**: a tight bullet list or mini cheat-sheet — the thing
  someone re-reads 5 minutes before an exam/interview instead of the full section.

Keep notes dense and useful, not padded. A 3-minute narrative "Welcome" chapter
should get a few lines, not a forced 6-subsection template. A 20-minute technical
chapter (e.g. "Logical Functions") deserves the full treatment with real syntax.

Work chapter by chapter, in order. For long courses, it's fine to batch a few
chapters per response/turn rather than trying to hold the entire course in your head
at once — prioritize quality over speed.

## Step 5: Compile and deliver

Default output: **one combined Markdown file** for the whole course/video, with:
- A title and short intro.
- A table of contents (linking to each chapter's heading), organized by `section`
  if the outline had sections.
- All chapter notes in order, using `##` for chapters and `#`/`---` dividers for
  top-level sections.

If the course is very long (roughly 15+ chapters) or the user asks for it, offer the
alternative of **one Markdown file per chapter** (in a folder) plus an index file —
ask which they'd prefer if it's ambiguous and the course is long; otherwise default
to the single combined file.

Save output(s) to `/mnt/user-data/outputs/`, then use `present_files` to deliver.
Don't use the docx skill unless the user explicitly asks for a Word doc — Markdown
is the default and preferred output per the user's instructions.

## Step 6: Create Practical Executive Summary & Cheat-Sheet

At the end of the consolidated notes, append a dedicated section titled `# Practical Executive Summary & Cheat-Sheet`. This section must focus only on the most important, high-impact features and techniques covered in the course (the "must-know" elements for real-world application). 

It must include:
1. **Summary Tables**: Side-by-side comparisons of key tools or functions (e.g., standard vs. array formulas, `VLOOKUP` vs. `XLOOKUP`, Merge vs. Append in Power Query).
2. **Visual Aids & Mockups**: ASCII grids or Mermaid diagrams illustrating the structure of sheets, data pipelines (ETL in Power Query), or data models (One-to-Many relationships in Power Pivot).
3. **Short Theory**: Concise explanations of what each key feature does and why it is used.
4. **Step-by-Step Practical Instructions**: Explicit steps (keyboard shortcuts, ribbon paths, settings adjustments) to execute the operations.
5. **Key Shortcuts Cheat-Sheet**: A quick reference table of essential keyboard shortcuts taught in the course.

This summary acts as a high-impact reference guide that a user can rely on for interviews, exams, or projects without wading through the detailed chapter notes.

## Notes on quality


- Never fabricate specifics (numbers, names, exact function syntax) that aren't
  either stated in the transcript or standard, verifiable knowledge about the
  subject. It's fine to add a well-known correct formula or fact; it's not fine to
  invent a plausible-sounding one.
- Preserve the instructor's actual examples/data when present (e.g. a specific
  worked formula or dataset column they used) rather than replacing them with
  generic ones.
- If a chapter's transcript text seems to run into the next chapter's content (bleed
  from imperfect chapter boundaries), use judgment to keep notes clean — it's fine
  to leave a stray sentence or two of overlap, but don't duplicate huge blocks across
  two chapters' notes.