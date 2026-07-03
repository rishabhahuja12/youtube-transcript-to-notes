"""
Pipeline orchestration for YouTube Transcript → Revision Notes.

This module contains the core pipeline logic extracted from the monolithic
app.py.  It is completely UI-independent: no tkinter imports, no global
variables.  All feedback is delivered through caller-supplied callbacks.
"""
import os
import json
import threading
import hashlib
import re

from src.parser import (
    parse_outline_text,
    parse_time_str,
    parse_transcript_text,
    dedupe_merge,
    assign_chapters,
)
from src.llm_client import (
    call_llm,
    AdaptiveRateLimiter,
    estimate_tokens,
    estimate_pipeline_time,
    get_rate_limit_info,
)


def run_pipeline(
    transcript_path: str,
    timestamps_path: str,
    output_dir: str,
    provider: str,
    endpoint_url: str,
    api_key: str,
    model_name: str,
    cancel_event: threading.Event,
    on_log: callable,
    on_progress: callable,
    video_title: str = None,
) -> dict:
    """Run the full notes-generation pipeline.

    Parameters
    ----------
    transcript_path : str
        Path to the raw YouTube transcript file.
    timestamps_path : str
        Path to the chapter-timestamps / outline file.
    output_dir : str
        Directory where output Markdown files are written.
    provider : str
        LLM provider name (e.g. ``"Ollama"``, ``"OpenAI"``).
    endpoint_url : str
        LLM API endpoint URL.
    api_key : str
        API key (may be empty for local providers).
    model_name : str
        Model identifier to use for generation.
    cancel_event : threading.Event
        Set this event to request graceful cancellation.
    on_log : callable
        ``on_log(message: str)`` – called with human-readable status messages.
    on_progress : callable
        ``on_progress(current: int, total: int)`` – called after each chapter
        is processed (1-indexed *current*).

    Returns
    -------
    dict
        ``{"success": bool, "detailed_path": str, "practical_path": str,
        "error": str | None}``
    """
    detailed_path = ""
    practical_path = ""

    try:
        on_log("=== PIPELINE STARTED ===")
        on_log(f"Active LLM: {provider} / {model_name} @ {endpoint_url}")

        # ------------------------------------------------------------------
        # Step 1: Read and parse chapters from outline
        # ------------------------------------------------------------------
        on_log("Step 1: Parsing outline and normalizing timestamps...")
        with open(timestamps_path, "r", encoding="utf-8", errors="replace") as f:
            outline_text = f.read()

        chapters, warnings = parse_outline_text(outline_text)
        on_log(f"Successfully parsed {len(chapters)} chapters.")
        for w in warnings:
            on_log(f"Warning: {w}")

        if not chapters:
            raise Exception(
                "Zero chapters parsed. Verify that the timestamps outline "
                "contains timestamps."
            )

        for c in chapters:
            c["time_sec"] = parse_time_str(c["time"])
        chapters.sort(key=lambda c: c["time_sec"])

        # ------------------------------------------------------------------
        # Step 2: Parse raw transcript and segment
        # ------------------------------------------------------------------
        on_log("Step 2: Parsing raw transcript and segmenting...")
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
            transcript_text = f.read()

        blocks = parse_transcript_text(transcript_text)
        if not blocks:
            raise Exception(
                "No timestamped caption blocks found in transcript file."
            )

        on_log(f"Parsed {len(blocks)} raw caption blocks. Deduplicating overlaps...")
        merged = dedupe_merge(blocks)
        on_log(f"Deduplication complete. Total continuous chunks: {len(merged)}.")

        on_log("Assigning segments to chapters...")
        chapter_texts = assign_chapters(merged, chapters)

        return _run_llm_pipeline(
            chapters, chapter_texts, output_dir, provider, endpoint_url,
            api_key, model_name, cancel_event, on_log, on_progress,
            video_title=video_title,
        )

    except Exception as e:
        on_log(f"CRITICAL ERROR in pipeline: {str(e)}")
        return {"success": False, "detailed_path": "", "practical_path": "", "error": str(e)}


def run_pipeline_from_data(
    transcript_blocks: list,
    chapters: list,
    output_dir: str,
    provider: str,
    endpoint_url: str,
    api_key: str,
    model_name: str,
    cancel_event,
    on_log: callable,
    on_progress: callable,
    video_title: str = None,
) -> dict:
    """Run the pipeline from pre-extracted data (e.g. YouTube URL extraction).

    Parameters
    ----------
    transcript_blocks : list
        List of ``(start_sec, end_sec, text)`` tuples.
    chapters : list
        List of dicts ``{"time": "H:MM:SS", "title": str, "section": str}``.
    """
    try:
        on_log("=== PIPELINE STARTED ===")
        on_log(f"Active LLM: {provider} / {model_name} @ {endpoint_url}")

        for c in chapters:
            c["time_sec"] = parse_time_str(c["time"])
        chapters.sort(key=lambda c: c["time_sec"])

        on_log(f"Working with {len(transcript_blocks)} transcript blocks and {len(chapters)} chapters.")
        merged = dedupe_merge(transcript_blocks)
        on_log(f"Deduplication complete. Total continuous chunks: {len(merged)}.")

        on_log("Assigning segments to chapters...")
        chapter_texts = assign_chapters(merged, chapters)

        return _run_llm_pipeline(
            chapters, chapter_texts, output_dir, provider, endpoint_url,
            api_key, model_name, cancel_event, on_log, on_progress,
            video_title=video_title,
        )

    except Exception as e:
        on_log(f"CRITICAL ERROR in pipeline: {str(e)}")
        return {"success": False, "detailed_path": "", "practical_path": "", "error": str(e)}


def _run_llm_pipeline(
    chapters, chapter_texts, output_dir, provider, endpoint_url,
    api_key, model_name, cancel_event, on_log, on_progress,
    video_title: str = None,
):
    """Internal shared LLM pipeline: takes parsed chapters + texts, generates notes."""
    detailed_path = ""
    practical_path = ""
    checkpoint_path = os.path.join(output_dir, ".checkpoint.json")

    try:
        # --- Pre-flight estimation ---
        total_words = sum(len(" ".join(chapter_texts[i]).split()) for i in range(len(chapters)))
        estimate = estimate_pipeline_time(total_words, len(chapters), provider)
        on_log(f"Rate limits: {get_rate_limit_info(provider)}")
        on_log(estimate["info"])

        # --- Create rate limiter ---
        limiter = AdaptiveRateLimiter.for_provider(provider)

        # --- Load checkpoint if exists ---
        checkpoint_signature = hashlib.md5(json.dumps(chapters, sort_keys=True).encode("utf-8")).hexdigest()
        completed_notes = {}
        if os.path.exists(checkpoint_path):
            try:
                with open(checkpoint_path, "r", encoding="utf-8") as f:
                    checkpoint = json.load(f)
                if checkpoint.get("signature") == checkpoint_signature:
                    completed_notes = checkpoint.get("completed_notes", {})
                    if completed_notes:
                        on_log(f"✅ Resuming from checkpoint: {len(completed_notes)}/{len(chapters)} chapters already done.")
                else:
                    on_log("Checkpoint signature mismatch, starting fresh.")
            except Exception:
                pass

        # ------------------------------------------------------------------
        # Step 3: Call LLM for each chapter
        # ------------------------------------------------------------------
        on_log("Step 3: Generating detailed revision notes for each chapter...")
        detailed_notes_sections: list[str] = []
        total_chapters = len(chapters)

        for idx, chapter in enumerate(chapters):
            title = chapter["title"]
            time_str = chapter["time"]
            section = chapter.get("section", "")
            ch_text = " ".join(chapter_texts[idx]).strip()
            word_count = len(ch_text.split())

            if cancel_event.is_set():
                on_log("Pipeline cancelled by user.")
                break

            # Check checkpoint — skip if already done
            if str(idx) in completed_notes:
                on_log(f"Chapter {idx + 1}/{total_chapters}: '{title}' — already done (checkpoint), skipping.")
                detailed_notes_sections.append(completed_notes[str(idx)])
                on_progress(idx + 1, total_chapters)
                continue

            on_log(
                f"Processing Chapter {idx + 1}/{total_chapters}: "
                f"'{title}' ({word_count} words)..."
            )

            user_prompt = (
                f'You are generating revision notes for Chapter {idx + 1}: "{title}"\n'
                f"Section: {section}\n"
                f"Start Time: {time_str}\n"
                f"Word Count of transcript segment: {word_count}\n\n"
                f"Transcript segment content:\n---\n{ch_text}\n---\n\n"
                f"Please write detailed study/revision notes in Markdown format.\n\n"
                f"Make sure you structure the notes with:\n"
                f"1. ## {idx + 1}. {title} (include start time: {time_str})\n"
                f"2. Summary (2-4 sentences): What this chapter covers and why it matters.\n"
                f"3. Key concepts / steps: Clean, well-structured explanations of "
                f"definitions, procedures, and steps in order.\n"
                f"4. Syntax / commands / formulas: Give actual correct syntax/formulas "
                f"in code blocks (e.g. Excel formula syntax, SQL code, etc.) where "
                f"relevant, even if only described verbally.\n"
                f"5. Examples: Concrete worked examples mentioned in the text or "
                f"constructed by you to match the concepts.\n"
                f"6. Common pitfalls / gotchas.\n"
                f"7. Quick revision recap: A bulleted summary cheat-sheet of key takeaways.\n\n"
                f"Add value using your own domain knowledge to correct any transcription "
                f"errors, explain concepts clearly, and write mathematically/syntactically "
                f"correct code or formulas."
            )

            est_tokens = estimate_tokens(ch_text + user_prompt)
            max_retries = 3
            retry_delay = 20  # seconds
            response = None
            pipeline_cancelled = False

            for attempt in range(max_retries):
                # Wait for rate limiter inside the retry loop
                if not limiter.wait_if_needed(est_tokens, cancel_event, on_log):
                    on_log("Pipeline cancelled by user.")
                    pipeline_cancelled = True
                    break

                try:
                    response = call_llm(
                        provider=provider,
                        endpoint_url=endpoint_url,
                        api_key=api_key,
                        model_name=model_name,
                        system_prompt=(
                            "You are an expert technical note-writer and instructional "
                            "designer. Your task is to write highly detailed, clear, and "
                            "structured revision notes for a chapter of a video course "
                            "based on its transcript segment."
                        ),
                        user_prompt=user_prompt,
                    )
                    # Update rate limiter with actual output tokens
                    if response:
                        actual_tokens = est_tokens + estimate_tokens(response)
                        limiter.record_actual_tokens(actual_tokens)
                    break  # Success!
                except Exception as e:
                    if attempt < max_retries - 1:
                        err_str = str(e)
                        # Try to parse exact retry delay from Gemini's error
                        match = re.search(r"Please retry in ([\d\.]+)s", err_str)
                        if match:
                            try:
                                retry_delay = float(match.group(1)) + 2.0  # +2s buffer
                            except ValueError:
                                pass
                                
                        on_log(
                            f"API Error (Attempt {attempt + 1}/{max_retries}): {e}"
                        )
                        on_log(
                            f"Cooling down for {retry_delay:.1f} seconds..."
                        )
                        # Interruptible cooldown
                        if cancel_event.wait(retry_delay):
                            pipeline_cancelled = True
                            break
                        retry_delay *= 2  # Exponential backoff (for the next attempt, if any)
                    else:
                        on_log(
                            f"WARNING: Failed to generate notes for Chapter "
                            f"{idx + 1} after {max_retries} attempts: {e}"
                        )
                        response = None
            
            if pipeline_cancelled:
                break

            if response:
                detailed_notes_sections.append(response)
                completed_notes[str(idx)] = response
            else:
                fallback = (
                    f"## {idx + 1}. {title} (Start Time: {time_str})\n\n"
                    f"### Summary\n"
                    f"[Could not generate notes using LLM due to repeated "
                    f"errors/rate limits.]\n\n"
                    f"### Transcript Snippet\n"
                    f"{ch_text[:500]}..."
                )
                detailed_notes_sections.append(fallback)

            # Save checkpoint after each chapter
            try:
                with open(checkpoint_path, "w", encoding="utf-8") as f:
                    json.dump({"signature": checkpoint_signature, "completed_notes": completed_notes}, f)
            except Exception:
                pass

            # Report progress after each chapter
            on_progress(idx + 1, total_chapters)

            if cancel_event.is_set():
                on_log("Pipeline cancelled by user.")
                break

        # ------------------------------------------------------------------
        # Assemble Course_Detailed_Notes.md
        # ------------------------------------------------------------------
        on_log("Assembling Course_Detailed_Notes.md...")
        title_intro = (
            f"# {video_title or 'Course'} Detailed Revision Notes\n\n"
            "This document contains comprehensive chapter-by-chapter revision "
            "notes and study material.\n\n"
            "## Table of Contents\n"
        )

        sections_map: dict[str, list] = {}
        for idx, chapter in enumerate(chapters):
            sec = chapter.get("section", "").strip() or "General"
            if sec not in sections_map:
                sections_map[sec] = []
            sections_map[sec].append(
                (idx + 1, chapter["title"], chapter["time"])
            )

        toc = ""
        has_real_sections = len(sections_map) > 1 or (
            len(sections_map) == 1 and "General" not in sections_map
        )

        if has_real_sections:
            for sec, chs in sections_map.items():
                toc += f"- **{sec}**\n"
                for num, ch_title, t_str in chs:
                    slug = _slugify(ch_title)
                    toc += (
                        f"  - [{num}. {ch_title}](#{num}-{slug}) "
                        f"(Start: {t_str})\n"
                    )
        else:
            for idx, chapter in enumerate(chapters):
                ch_title = chapter["title"]
                slug = _slugify(ch_title)
                toc += (
                    f"- [{idx + 1}. {ch_title}](#{idx + 1}-{slug}) "
                    f"(Start: {chapter['time']})\n"
                )

        toc += "\n---\n\n"

        full_detailed_content = (
            title_intro + toc + "\n\n".join(detailed_notes_sections)
        )

        slug = _slugify(video_title) if video_title else "Course"
        detailed_path = os.path.join(output_dir, f"{slug}_Detailed_Notes.md")
        with open(detailed_path, "w", encoding="utf-8") as f:
            f.write(full_detailed_content)
        on_log(f"Detailed notes saved to: {detailed_path}")

        # ------------------------------------------------------------------
        # Step 4: Call LLM to generate Practical Cheat-sheet
        # ------------------------------------------------------------------
        on_log("Step 4: Generating Course Practical Cheat-Sheet & Summary...")

        course_chapters_outline = ""
        for idx, chapter in enumerate(chapters):
            sec = (
                f" [{chapter['section']}]" if chapter.get("section") else ""
            )
            course_chapters_outline += (
                f"- Chapter {idx + 1}: {chapter['title']} "
                f"(Starts: {chapter['time']}){sec}\n"
            )

        # Include actual generated notes content (first 15 000 chars) so the
        # cheat-sheet prompt has real substance rather than just an outline.
        notes_excerpt = "\n\n".join(detailed_notes_sections)[:15000]

        user_prompt_summary = (
            f"We have generated detailed revision notes for the course. "
            f"Here is the course chapter outline:\n{course_chapters_outline}\n\n"
            f"Below is an excerpt of the actual detailed notes content "
            f"(first ~15 000 characters) for additional context:\n"
            f"---\n{notes_excerpt}\n---\n\n"
            f'Based on the course outline and the notes above, generate a '
            f'comprehensive, standalone '
            f'"{video_title or "Course"} Practical Cheat-Sheet & Summary".\n\n'
            f"This cheat-sheet must focus only on the most important, "
            f"high-impact features and techniques covered in the course "
            f'(the "must-know" elements for real-world application).\n\n'
            f"It must include:\n"
            f"1. Summary Tables: Side-by-side comparisons of key tools or "
            f"functions (e.g. VLOOKUP vs XLOOKUP, standard vs array formulas, "
            f"etc.).\n"
            f"2. Visual Aids & Mockups: Mermaid diagrams (graph TD, graph LR, "
            f"etc.) or ASCII diagrams illustrating structures of data "
            f"pipelines, schemas, relationships, or workflows.\n"
            f"3. Short Theory: Concise explanations of what each key feature "
            f"does and why it is used.\n"
            f"4. Step-by-Step Practical Instructions: Explicit steps (keyboard "
            f"shortcuts, paths, settings) to execute the operations.\n"
            f"5. Key Shortcuts Cheat-Sheet: A quick reference table of "
            f"essential keyboard shortcuts taught.\n\n"
            f"Make this extremely clean, professional, and directly useful as "
            f"a high-impact reference guide. Output only the Markdown content."
        )

        try:
            if cancel_event.is_set():
                practical_summary = (
                    f"# {video_title or 'Course'} Practical Cheat-Sheet & Summary\n\n"
                    "[Skipped due to pipeline cancellation]\n"
                )
            else:
                practical_summary = call_llm(
                    provider=provider,
                    endpoint_url=endpoint_url,
                    api_key=api_key,
                    model_name=model_name,
                    system_prompt=(
                        "You are an expert technical note-writer and "
                        "instructional designer. Your task is to write a "
                        "practical executive summary and cheat-sheet for a "
                        "course based on its chapters and overall content."
                    ),
                    user_prompt=user_prompt_summary,
                )
        except Exception as e:
            on_log(f"ERROR generating practical summary: {e}")
            practical_summary = (
                f"# {video_title or 'Course'} Practical Cheat-Sheet & Summary\n\n"
                f"[Failed to generate cheat-sheet using LLM: {e}]\n"
            )

        practical_path = os.path.join(output_dir, f"{slug}_Practical_Notes.md")
        with open(practical_path, "w", encoding="utf-8") as f:
            f.write(practical_summary)
        on_log(f"Practical notes saved to: {practical_path}")

        on_log("=== PIPELINE COMPLETED SUCCESSFULLY ===")
        # Clean up checkpoint file on success
        if os.path.exists(checkpoint_path):
            try:
                os.remove(checkpoint_path)
            except Exception:
                pass
        return {
            "success": True,
            "detailed_path": detailed_path,
            "practical_path": practical_path,
            "error": None,
        }

    except Exception as e:
        on_log(f"CRITICAL ERROR in pipeline: {e}")
        return {
            "success": False,
            "detailed_path": detailed_path,
            "practical_path": practical_path,
            "error": str(e),
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _slugify(title: str) -> str:
    """Convert a chapter title into a Markdown-anchor-compatible slug."""
    title = title.lower().replace(" ", "-")
    return re.sub(r'[^a-z0-9_\-]', '', title)
