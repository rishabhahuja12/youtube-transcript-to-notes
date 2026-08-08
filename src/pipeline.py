"""
Pipeline orchestration for YouTube Transcript → Revision Notes.

This module contains the core pipeline logic extracted from the monolithic
app.py. It is completely UI-independent: no tkinter imports, no global
variables. All feedback is delivered through caller-supplied callbacks.
"""
import os
import json
import threading
import hashlib
import re
from typing import Tuple, Optional, Any, Dict

from src.hooks import get_hook_manager
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
    RateLimitError,
    AuthenticationError,
    InvalidRequestError,
    ProviderUnavailableError,
    LLMError,
)
from src.provider_pool import ProviderPool


def run_pipeline(
    transcript_path: str,
    timestamps_path: str,
    output_dir: str,
    pool: ProviderPool,
    cancel_event: threading.Event,
    on_log: callable,
    on_progress: callable,
    video_title: str = None,
    enable_multimodal: bool = False,
    youtube_url: str = None,
    enable_kag: bool = False,
    enable_pdf: bool = False,
    on_phase: callable = None,
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
    pool : ProviderPool
        Pool of LLM API configurations.
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
        ``{"success": bool, "status": str, "detailed_path": str, "practical_path": str,
        "error": str | None}``
    """
    hook_mgr = get_hook_manager()
    hook_mgr.register("on_log", on_log)
    hook_mgr.register("on_progress", on_progress)
    if on_phase:
        hook_mgr.register("on_phase", on_phase)

    def safe_on_log(msg: str) -> None:
        hook_mgr.trigger_on_log(msg)

    def safe_on_progress(current: int, total: int, step: str = "Processing...") -> None:
        hook_mgr.trigger_on_progress(current, total, step)

    def safe_on_phase(phase: str, status: str) -> None:
        hook_mgr.trigger_on_phase(phase, status)

    hook_mgr.pre_pipeline({
        "video_title": video_title,
        "output_dir": output_dir,
        "enable_multimodal": enable_multimodal,
        "enable_kag": enable_kag,
        "enable_pdf": enable_pdf,
    })

    try:
        if cancel_event.is_set():
            safe_on_phase("transcript", "cancelled")
            res = {"success": False, "status": "cancelled", "course_dir": "", "detailed_path": "", "practical_path": "", "error": "Cancelled by user"}
            hook_mgr.post_pipeline(res)
            return res
            
        safe_on_phase("transcript", "running")
        active_pool = pool.get_vision_pool() if enable_multimodal else pool.get_text_pool()
        if active_pool.total == 0:
            if enable_multimodal:
                raise ValueError("You requested Vision features but have no Vision models in your API pool.")
            raise ValueError("No text API keys configured.")

        safe_on_log("=== PIPELINE STARTED ===")

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

        slug = _slugify(video_title) if video_title else "Course"
        course_dir = os.path.abspath(os.path.join(output_dir, slug))
        os.makedirs(course_dir, exist_ok=True)

        chapter_frames = None
        if enable_multimodal and youtube_url:
            try:
                on_log("Step 2.5: Downloading video and extracting frames...")
                from src.frame_extractor import download_video, extract_key_frames
                frames_dir = os.path.join(course_dir, "frames")
                video_path = download_video(youtube_url, frames_dir, cancel_event=cancel_event)
                on_log(f"Video downloaded to {video_path}, extracting smart frames...")
                chapter_frames = extract_key_frames(video_path, frames_dir, chapters, cancel_event=cancel_event)
                on_log("Frame extraction complete.")
                # Clean up video file to save disk space
                try:
                    os.remove(video_path)
                except OSError as e:
                    on_log(f"WARNING: Cleanup failed for {video_path}: {e}")
            except Exception as e:
                on_log(f"WARNING: Frame extraction failed: {e}. Continuing without visuals.")
                chapter_frames = None

        if on_phase: on_phase("transcript", "complete")
        res = _run_llm_pipeline(
            chapters, chapter_texts, course_dir, pool, active_pool, cancel_event, on_log, on_progress,
            video_title=video_title, chapter_frames=chapter_frames, enable_kag=enable_kag, enable_pdf=enable_pdf, on_phase=on_phase
        )
        hook_mgr.post_pipeline(res)
        return res

    except Exception as e:
        if on_phase: on_phase("transcript", "failed")
        on_log(f"CRITICAL ERROR in pipeline: {str(e)}")
        res = {"success": False, "status": "failed", "course_dir": "", "detailed_path": "", "practical_path": "", "error": str(e)}
        hook_mgr.post_pipeline(res)
        return res


def run_pipeline_from_data(
    transcript_blocks: list,
    chapters: list,
    output_dir: str,
    pool: ProviderPool,
    cancel_event: threading.Event,
    on_log: callable,
    on_progress: callable,
    video_title: str = None,
    enable_multimodal: bool = False,
    youtube_url: str = None,
    enable_kag: bool = False,
    enable_pdf: bool = False,
    on_phase: callable = None,
) -> dict:
    """Run notes-generation pipeline from pre-parsed data."""
    hook_mgr = get_hook_manager()
    hook_mgr.register("on_log", on_log)
    hook_mgr.register("on_progress", on_progress)
    if on_phase:
        hook_mgr.register("on_phase", on_phase)

    def safe_on_log(msg: str) -> None:
        hook_mgr.trigger_on_log(msg)

    def safe_on_progress(current: int, total: int, step: str = "Processing...") -> None:
        hook_mgr.trigger_on_progress(current, total, step)

    def safe_on_phase(phase: str, status: str) -> None:
        hook_mgr.trigger_on_phase(phase, status)

    hook_mgr.pre_pipeline({
        "video_title": video_title,
        "output_dir": output_dir,
        "enable_multimodal": enable_multimodal,
        "enable_kag": enable_kag,
        "enable_pdf": enable_pdf,
    })

    try:
        if cancel_event.is_set():
            safe_on_phase("transcript", "cancelled")
            res = {"success": False, "status": "cancelled", "course_dir": "", "detailed_path": "", "practical_path": "", "error": "Cancelled by user"}
            hook_mgr.post_pipeline(res)
            return res

        safe_on_phase("transcript", "running")
        active_pool = pool.get_vision_pool() if enable_multimodal else pool.get_text_pool()
        if active_pool.total == 0:
            if enable_multimodal:
                raise ValueError("You requested Vision features but have no Vision models in your API pool.")
            raise ValueError("No text API keys configured.")

        safe_on_log("=== PIPELINE STARTED ===")
        safe_on_log(f"Working with {len(transcript_blocks)} transcript blocks and {len(chapters)} chapters.")

        for c in chapters:
            c["time_sec"] = parse_time_str(c["time"])
        chapters.sort(key=lambda c: c["time_sec"])

        merged = dedupe_merge(transcript_blocks)
        on_log(f"Deduplication complete. Total continuous chunks: {len(merged)}.")

        on_log("Assigning segments to chapters...")
        chapter_texts = assign_chapters(merged, chapters)

        slug = _slugify(video_title) if video_title else "Course"
        course_dir = os.path.abspath(os.path.join(output_dir, slug))
        os.makedirs(course_dir, exist_ok=True)

        chapter_frames = None
        if enable_multimodal and youtube_url:
            try:
                on_log("Step 2.5: Downloading video and extracting frames...")
                from src.frame_extractor import download_video, extract_key_frames
                frames_dir = os.path.join(course_dir, "frames")
                video_path = download_video(youtube_url, frames_dir, cancel_event=cancel_event)
                on_log(f"Video downloaded to {video_path}, extracting smart frames...")
                chapter_frames = extract_key_frames(video_path, frames_dir, chapters, cancel_event=cancel_event)
                on_log("Frame extraction complete.")
                try:
                    os.remove(video_path)
                except OSError as e:
                    on_log(f"WARNING: Cleanup failed for {video_path}: {e}")
            except Exception as e:
                on_log(f"WARNING: Frame extraction failed: {e}. Continuing without visuals.")
                chapter_frames = None

        if on_phase: on_phase("transcript", "complete")
        res = _run_llm_pipeline(
            chapters, chapter_texts, course_dir, pool, active_pool, cancel_event, on_log, on_progress,
            video_title=video_title, chapter_frames=chapter_frames, enable_kag=enable_kag, enable_pdf=enable_pdf, on_phase=on_phase
        )
        hook_mgr.post_pipeline(res)
        return res

    except Exception as e:
        if on_phase: on_phase("transcript", "failed")
        on_log(f"CRITICAL ERROR in pipeline: {str(e)}")
        res = {"success": False, "status": "failed", "course_dir": "", "detailed_path": "", "practical_path": "", "error": str(e)}
        hook_mgr.post_pipeline(res)
        return res


def _process_chapter_notes(
    chapters: list,
    chapter_texts: list,
    course_dir: str,
    active_pool: ProviderPool,
    cancel_event: threading.Event,
    on_log: callable,
    on_progress: callable,
    video_title: Optional[str] = None,
    chapter_frames: Optional[dict] = None,
    on_phase: Optional[callable] = None,
) -> Tuple[Optional[dict], str, str, str]:
    """Process chapter notes: estimation, checkpointing, LLM calls, and assembly into detailed notes file."""
    os.makedirs(course_dir, exist_ok=True)
    checkpoint_path = os.path.join(course_dir, ".checkpoint.json")
    final_status = "complete"

    total_words = sum(
        len(" ".join(chapter_texts[i]).split()) for i in range(len(chapters))
    )
    estimate = estimate_pipeline_time(
        total_words,
        len(chapters),
        active_pool.current.provider,
        active_pool.current.rpm_limit,
        active_pool.current.tpm_limit,
    )
    on_log(f"Rate limits: {get_rate_limit_info(active_pool.current.provider, active_pool.current.rpm_limit, active_pool.current.tpm_limit)}")
    on_log(estimate["info"])

    limiter = AdaptiveRateLimiter.for_config(active_pool.current)

    dump_str = json.dumps(chapters, sort_keys=True).encode("utf-8")
    checkpoint_signature = hashlib.md5(dump_str).hexdigest()
    completed_notes = {}
    if os.path.exists(checkpoint_path):
        try:
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                checkpoint = json.load(f)
            if checkpoint.get("signature") == checkpoint_signature:
                completed_notes = checkpoint.get("completed_notes", {})
                if completed_notes:
                    on_log(
                        f"✅ Resuming from checkpoint: {len(completed_notes)}/"
                        f"{len(chapters)} chapters already done."
                    )
            else:
                on_log("Checkpoint signature mismatch, starting fresh.")
        except (OSError, json.JSONDecodeError) as e:
            on_log(f"WARNING: Failed to read checkpoint: {e}")

    if on_phase: on_phase("notes", "running")
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
            if on_phase: on_phase("notes", "cancelled")
            on_log("Pipeline cancelled by user.")
            return {
                "success": False,
                "status": "cancelled",
                "course_dir": course_dir,
                "detailed_path": "",
                "practical_path": "",
                "kag_html_path": "",
                "pdf_path": "",
                "error": "Cancelled by user"
            }, "", "", "cancelled"

        if str(idx) in completed_notes:
            on_log(
                f"Chapter {idx + 1}/{total_chapters}: '{title}' "
                f"— already done (checkpoint), skipping."
            )
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

        assigned_frames = chapter_frames.get(idx, []) if chapter_frames else []
        if assigned_frames:
            user_prompt += (
                f"\n\nAttached are key visual frames from this chapter. "
                f"Use them to enhance the notes if they contain relevant visual "
                f"information (e.g. diagrams, slide text)."
            )

        est_tokens = estimate_tokens(ch_text + user_prompt)
        max_retries = 3
        retry_delay = 20
        response = None
        fallback_reason = "Max retries exceeded"

        for attempt in range(max_retries):
            if not limiter.wait_if_needed(est_tokens, cancel_event, on_log):
                if on_phase: on_phase("notes", "cancelled")
                on_log("Pipeline cancelled by user.")
                return {
                    "success": False,
                    "status": "cancelled",
                    "course_dir": course_dir,
                    "detailed_path": "",
                    "practical_path": "",
                    "kag_html_path": "",
                    "pdf_path": "",
                    "error": "Cancelled by user"
                }, "", "", "cancelled"

            try:
                response = call_llm(
                    provider=active_pool.current.provider,
                    endpoint_url=active_pool.current.endpoint_url,
                    api_key=active_pool.current.api_key,
                    model_name=active_pool.current.model_name,
                    system_prompt=(
                        "You are an expert technical note-writer and instructional "
                        "designer. Your task is to write highly detailed, clear, and "
                        "structured revision notes for a chapter of a video course "
                        "based on its transcript segment."
                    ),
                    user_prompt=user_prompt,
                    images=assigned_frames,
                )
                if response:
                    actual_tokens = est_tokens + estimate_tokens(response)
                    limiter.record_actual_tokens(actual_tokens)
                break
            except RateLimitError as e:
                if active_pool.rotate():
                    on_log(f"Rate limit hit. Switching to {active_pool.current_label()}...")
                    limiter = AdaptiveRateLimiter.for_config(active_pool.current)
                    continue
                
                err_str = str(e)
                match = re.search(r"Please retry in ([\d\.]+)s", err_str)
                if match:
                    try:
                        retry_delay = float(match.group(1)) + 2.0
                    except ValueError:
                        pass
                        
                on_log(f"All API configs exhausted. Cooling down for {retry_delay:.1f}s...")
                if cancel_event.wait(retry_delay):
                    if on_phase: on_phase("notes", "cancelled")
                    return { "success": False, "status": "cancelled", "course_dir": course_dir, "detailed_path": "", "practical_path": "", "kag_html_path": "", "pdf_path": "", "error": "Cancelled by user" }, "", "", "cancelled"
                active_pool.reset_cycle()
                limiter = AdaptiveRateLimiter.for_config(active_pool.current)
                retry_delay *= 2
                fallback_reason = str(e)
            except ProviderUnavailableError as e:
                if active_pool.rotate():
                    on_log(f"Provider unavailable. Switching to {active_pool.current_label()}...")
                    limiter = AdaptiveRateLimiter.for_config(active_pool.current)
                    continue
                if attempt < max_retries - 1:
                    on_log(f"Network/timeout error: {e}. Retrying in {retry_delay}s...")
                    if cancel_event.wait(retry_delay):
                        if on_phase: on_phase("notes", "cancelled")
                        return { "success": False, "status": "cancelled", "course_dir": course_dir, "detailed_path": "", "practical_path": "", "kag_html_path": "", "pdf_path": "", "error": "Cancelled by user" }, "", "", "cancelled"
                    retry_delay *= 2
                else:
                    on_log(f"WARNING: Network error after {max_retries} attempts: {e}")
                    response = None
                fallback_reason = str(e)
            except AuthenticationError as e:
                current_endpoint = active_pool.current.endpoint_url
                current_key = active_pool.current.api_key
                has_new = False
                while active_pool.rotate():
                    if active_pool.current.endpoint_url == current_endpoint and active_pool.current.api_key == current_key:
                        continue
                    has_new = True
                    break
                if has_new:
                    on_log(f"Authentication error. Switching to {active_pool.current_label()}...")
                    limiter = AdaptiveRateLimiter.for_config(active_pool.current)
                    continue
                else:
                    on_log(f"WARNING: Auth error for Chapter {idx + 1}: {e} (No eligible configs left)")
                    response = None
                    fallback_reason = str(e)
                    break
            except InvalidRequestError as e:
                if active_pool.rotate():
                    on_log(f"Invalid request error. Switching to {active_pool.current_label()}...")
                    limiter = AdaptiveRateLimiter.for_config(active_pool.current)
                    continue
                else:
                    on_log(f"WARNING: Invalid request error for Chapter {idx + 1}: {e} (No eligible configs left)")
                    response = None
                    fallback_reason = str(e)
                    break
            except Exception as e:
                on_log(f"WARNING: Unexpected error for Chapter {idx + 1}: {e}")
                response = None
                fallback_reason = str(e)
                break
        
        if response:
            if assigned_frames:
                frame_markdown = "\n\n### Key Visuals\n"
                for frame_path in assigned_frames:
                    frame_name = os.path.basename(frame_path)
                    frame_markdown += f"![Chapter {idx+1} - Slide](frames/{frame_name})\n"
                response += frame_markdown
            detailed_notes_sections.append(response)
            completed_notes[str(idx)] = response
        else:
            fallback = (
                f"## {idx + 1}. {title} (Start Time: {time_str})\n\n"
                f"### Summary\n"
                f"[Could not generate notes using LLM. Reason: {fallback_reason}]\n\n"
                f"### Transcript Snippet\n"
                f"{ch_text[:500]}..."
            )
            detailed_notes_sections.append(fallback)
            final_status = "degraded"

        try:
            with open(checkpoint_path, "w", encoding="utf-8") as f:
                json.dump({
                    "signature": checkpoint_signature, 
                    "completed_notes": completed_notes
                }, f)
        except OSError as e:
            on_log(f"WARNING: Failed to write checkpoint: {e}")

        on_progress(idx + 1, total_chapters)

        if cancel_event.is_set():
            if on_phase: on_phase("notes", "cancelled")
            on_log("Pipeline cancelled by user.")
            return {
                "success": False,
                "status": "cancelled",
                "course_dir": course_dir,
                "detailed_path": "",
                "practical_path": "",
                "kag_html_path": "",
                "pdf_path": "",
                "error": "Cancelled by user"
            }, "", "", "cancelled"

    num_successful_chapters = sum(1 for s in detailed_notes_sections if "Could not generate notes using LLM" not in s)
    if num_successful_chapters == 0:
        if on_phase: on_phase("notes", "failed")
        on_log("Failed to generate any detailed notes. Pipeline failed.")
        return {
            "success": False,
            "status": "failed",
            "course_dir": course_dir,
            "detailed_path": "",
            "practical_path": "",
            "kag_html_path": "",
            "pdf_path": "",
            "error": "Failed to generate any required detailed notes."
        }, "", "", "failed"
        
    if on_phase: on_phase("notes", "complete")

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
    detailed_path = os.path.join(course_dir, f"{slug}_Detailed_Notes.md")
    with open(detailed_path, "w", encoding="utf-8") as f:
        f.write(full_detailed_content)
    on_log(f"Detailed notes saved to: {detailed_path}")

    return None, detailed_path, full_detailed_content, final_status


def _generate_practical_cheatsheet(
    chapters: list,
    detailed_notes_content: str,
    course_dir: str,
    active_pool: ProviderPool,
    cancel_event: threading.Event,
    on_log: callable,
    video_title: Optional[str] = None,
    on_phase: Optional[callable] = None,
    current_status: str = "complete",
) -> Tuple[Optional[dict], str, str]:
    """Generate Course Practical Cheat-Sheet & Summary."""
    if on_phase: on_phase("practical", "running")
    on_log("Step 4: Generating Course Practical Cheat-Sheet & Summary...")

    slug = _slugify(video_title) if video_title else "Course"

    course_chapters_outline = ""
    for idx, chapter in enumerate(chapters):
        sec = f" [{chapter['section']}]" if chapter.get("section") else ""
        course_chapters_outline += (
            f"- Chapter {idx + 1}: {chapter['title']} "
            f"(Starts: {chapter['time']}){sec}\n"
        )

    notes_excerpt = detailed_notes_content[:15000]

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

    max_retries = 3
    retry_delay = 20
    practical_summary = None
    system_prompt_summary = (
        "You are an expert technical note-writer and "
        "instructional designer. Your task is to write a "
        "practical executive summary and cheat-sheet for a "
        "course based on its chapters and overall content."
    )
    limiter = AdaptiveRateLimiter.for_config(active_pool.current)
    est_tokens_summary = estimate_tokens(user_prompt_summary + system_prompt_summary)
    fallback_reason_summary = "Max retries exceeded"

    for attempt in range(max_retries):
        if cancel_event.is_set():
            if on_phase: on_phase("practical", "cancelled")
            on_log("Pipeline cancelled by user.")
            return {
                "success": False,
                "status": "cancelled",
                "course_dir": course_dir,
                "detailed_path": "",
                "practical_path": "",
                "kag_html_path": "",
                "pdf_path": "",
                "error": "Cancelled by user"
            }, "", "cancelled"
        
        if not limiter.wait_if_needed(est_tokens_summary, cancel_event, on_log):
            if on_phase: on_phase("practical", "cancelled")
            on_log("Pipeline cancelled by user.")
            return {
                "success": False,
                "status": "cancelled",
                "course_dir": course_dir,
                "detailed_path": "",
                "practical_path": "",
                "kag_html_path": "",
                "pdf_path": "",
                "error": "Cancelled by user"
            }, "", "cancelled"

        try:
            practical_summary = call_llm(
                provider=active_pool.current.provider,
                endpoint_url=active_pool.current.endpoint_url,
                api_key=active_pool.current.api_key,
                model_name=active_pool.current.model_name,
                system_prompt=system_prompt_summary,
                user_prompt=user_prompt_summary,
            )
            if practical_summary:
                actual_tokens = est_tokens_summary + estimate_tokens(practical_summary)
                limiter.record_actual_tokens(actual_tokens)
            break
        except RateLimitError as e:
            if active_pool.rotate():
                on_log(f"Rate limit hit. Switching to {active_pool.current_label()}...")
                limiter = AdaptiveRateLimiter.for_config(active_pool.current)
                continue
            
            err_str = str(e)
            match = re.search(r"Please retry in ([\d\.]+)s", err_str)
            if match:
                try:
                    retry_delay = float(match.group(1)) + 2.0
                except ValueError:
                    pass
                    
            on_log(f"All API configs exhausted. Cooling down for {retry_delay:.1f}s...")
            if cancel_event.wait(retry_delay):
                if on_phase: on_phase("practical", "cancelled")
                return { "success": False, "status": "cancelled", "course_dir": course_dir, "detailed_path": "", "practical_path": "", "kag_html_path": "", "pdf_path": "", "error": "Cancelled by user" }, "", "cancelled"
            active_pool.reset_cycle()
            limiter = AdaptiveRateLimiter.for_config(active_pool.current)
            retry_delay *= 2
            fallback_reason_summary = str(e)
        except ProviderUnavailableError as e:
            if active_pool.rotate():
                on_log(f"Provider unavailable. Switching to {active_pool.current_label()}...")
                limiter = AdaptiveRateLimiter.for_config(active_pool.current)
                continue
            if attempt < max_retries - 1:
                on_log(f"Network/timeout error: {e}. Retrying in {retry_delay}s...")
                if cancel_event.wait(retry_delay):
                    if on_phase: on_phase("practical", "cancelled")
                    return { "success": False, "status": "cancelled", "course_dir": course_dir, "detailed_path": "", "practical_path": "", "kag_html_path": "", "pdf_path": "", "error": "Cancelled by user" }, "", "cancelled"
                retry_delay *= 2
            else:
                on_log(f"ERROR: Failed to generate practical summary after {max_retries} attempts: {e}")
                practical_summary = None
            fallback_reason_summary = str(e)
        except AuthenticationError as e:
            current_endpoint = active_pool.current.endpoint_url
            current_key = active_pool.current.api_key
            has_new = False
            while active_pool.rotate():
                if active_pool.current.endpoint_url == current_endpoint and active_pool.current.api_key == current_key:
                    continue
                has_new = True
                break
            if has_new:
                on_log(f"Authentication error. Switching to {active_pool.current_label()}...")
                limiter = AdaptiveRateLimiter.for_config(active_pool.current)
                continue
            else:
                on_log(f"ERROR: Auth error generating practical summary: {e} (No eligible configs left)")
                practical_summary = None
                fallback_reason_summary = str(e)
                break
        except InvalidRequestError as e:
            if active_pool.rotate():
                on_log(f"Invalid request error. Switching to {active_pool.current_label()}...")
                limiter = AdaptiveRateLimiter.for_config(active_pool.current)
                continue
            else:
                on_log(f"ERROR: Invalid request error generating practical summary: {e} (No eligible configs left)")
                practical_summary = None
                fallback_reason_summary = str(e)
                break
        except Exception as e:
            on_log(f"ERROR: Unexpected error generating practical summary: {e}")
            practical_summary = None
            fallback_reason_summary = str(e)
            break
            
    is_summary_degraded = not practical_summary
    final_status = current_status
    if is_summary_degraded:
        practical_summary = (
            f"# {video_title or 'Course'} Practical Cheat-Sheet & Summary\n\n"
            f"[Failed to generate cheat-sheet using LLM: {fallback_reason_summary}]\n"
        )
        final_status = "degraded"

    if not is_summary_degraded:
        if on_phase: on_phase("practical", "complete")
    else:
        if on_phase: on_phase("practical", "degraded")

    practical_path = os.path.join(course_dir, f"{slug}_Practical_Notes.md")
    with open(practical_path, "w", encoding="utf-8") as f:
        f.write(practical_summary)
    on_log(f"Practical notes saved to: {practical_path}")

    return None, practical_path, final_status


def _generate_knowledge_graph(
    full_detailed_content: str,
    course_dir: str,
    original_pool: ProviderPool,
    slug: str,
    cancel_event: threading.Event,
    on_log: callable,
    on_phase: Optional[callable] = None,
    current_status: str = "complete",
) -> Tuple[Optional[dict], str, str]:
    """Generate Knowledge Graph HTML and JSON artifacts."""
    if cancel_event.is_set():
        if on_phase: on_phase("kag", "cancelled")
        on_log("Pipeline cancelled by user.")
        return {
            "success": False,
            "status": "cancelled",
            "course_dir": course_dir,
            "detailed_path": "",
            "practical_path": "",
            "kag_html_path": "",
            "pdf_path": "",
            "error": "Cancelled by user"
        }, "", "cancelled"

    if on_phase: on_phase("kag", "running")
    on_log("Step 5: Generating Knowledge Graph...")
    final_status = current_status
    kag_html_path = ""
    try:
        from src.knowledge_graph import extract_concepts, build_graph, render_html
        on_log("Extracting concepts for Knowledge Graph...")
        text_pool = original_pool.get_text_pool()
        if text_pool.total == 0:
            raise ValueError("No text API keys configured for KAG.")
            
        graph_data = extract_concepts(
            full_detailed_content, text_pool.current, on_log
        )
        kag_json_path = os.path.join(course_dir, f"{slug}_knowledge_graph.json")
        kag_html_path = os.path.join(course_dir, f"{slug}_knowledge_graph.html")
        with open(kag_json_path, "w", encoding="utf-8") as f:
            json.dump(graph_data, f, indent=2)
        html_content = render_html(graph_data)
        with open(kag_html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        on_log(f"Knowledge Graph saved to: {kag_html_path}")
        if on_phase: on_phase("kag", "complete")
    except Exception as e:
        on_log(f"WARNING: Knowledge Graph generation failed: {e}. Skipping.")
        if on_phase: on_phase("kag", "degraded")
        final_status = "degraded"

    return None, kag_html_path, final_status


def _generate_pdf(
    detailed_path: str,
    cancel_event: threading.Event,
    on_log: callable,
    on_phase: Optional[callable] = None,
    current_status: str = "complete",
) -> Tuple[Optional[dict], str, str]:
    """Generate PDF export using src.pdf."""
    if cancel_event.is_set():
        if on_phase: on_phase("pdf", "cancelled")
        on_log("Pipeline cancelled by user.")
        return {
            "success": False,
            "status": "cancelled",
            "course_dir": "",
            "detailed_path": detailed_path,
            "practical_path": "",
            "kag_html_path": "",
            "pdf_path": "",
            "error": "Cancelled by user"
        }, "", "cancelled"

    if on_phase: on_phase("pdf", "running")
    on_log("Step 6: Generating PDF from detailed notes...")
    final_status = current_status
    pdf_path = ""
    try:
        from src.pdf import convert_md_to_pdf
        pdf_target = detailed_path.rsplit(".", 1)[0] + ".pdf"
        convert_md_to_pdf(detailed_path, "Textbook", pdf_target)
        pdf_path = pdf_target
        on_log(f"PDF saved to: {pdf_path}")
        if on_phase: on_phase("pdf", "complete")
    except Exception as e:
        on_log(f"WARNING: PDF generation failed: {e}. Skipping.")
        if on_phase: on_phase("pdf", "degraded")
        final_status = "degraded"

    return None, pdf_path, final_status


def _run_llm_pipeline(
    chapters: list,
    chapter_texts: list,
    course_dir: str,
    original_pool: ProviderPool,
    active_pool: ProviderPool,
    cancel_event: threading.Event,
    on_log: callable,
    on_progress: callable,
    video_title: str = None,
    chapter_frames: dict = None,
    enable_kag: bool = False,
    enable_pdf: bool = False,
    on_phase: callable = None,
) -> dict:
    """Internal shared LLM pipeline: takes parsed chapters + texts, generates notes."""
    detailed_path = ""
    practical_path = ""
    kag_html_path = ""
    pdf_path = ""
    checkpoint_path = os.path.join(course_dir, ".checkpoint.json")

    try:
        early_err, detailed_path, full_detailed_content, status = _process_chapter_notes(
            chapters, chapter_texts, course_dir, active_pool, cancel_event, on_log, on_progress,
            video_title=video_title, chapter_frames=chapter_frames, on_phase=on_phase
        )
        if early_err is not None:
            return early_err

        early_err, practical_path, status = _generate_practical_cheatsheet(
            chapters, full_detailed_content, course_dir, active_pool, cancel_event, on_log,
            video_title=video_title, on_phase=on_phase, current_status=status
        )
        if early_err is not None:
            return early_err

        slug = _slugify(video_title) if video_title else "Course"
        if enable_kag:
            early_err, kag_html_path, status = _generate_knowledge_graph(
                full_detailed_content, course_dir, original_pool, slug, cancel_event, on_log,
                on_phase=on_phase, current_status=status
            )
            if early_err is not None:
                return early_err

        if enable_pdf:
            early_err, pdf_path, status = _generate_pdf(
                detailed_path, cancel_event, on_log, on_phase=on_phase, current_status=status
            )
            if early_err is not None:
                return early_err

        on_log("=== PIPELINE COMPLETED SUCCESSFULLY ===")
        if os.path.exists(checkpoint_path):
            try:
                os.remove(checkpoint_path)
            except OSError as e:
                on_log(f"WARNING: Checkpoint cleanup failed: {e}")

        return {
            "success": True,
            "status": status,
            "course_dir": course_dir,
            "detailed_path": detailed_path,
            "practical_path": practical_path,
            "kag_html_path": kag_html_path,
            "pdf_path": pdf_path,
            "error": None,
        }

    except Exception as e:
        on_log(f"CRITICAL ERROR in pipeline: {e}")
        return {
            "success": False,
            "status": "failed",
            "course_dir": course_dir if 'course_dir' in locals() else "",
            "detailed_path": detailed_path,
            "practical_path": practical_path,
            "kag_html_path": kag_html_path if 'kag_html_path' in locals() else "",
            "pdf_path": pdf_path if 'pdf_path' in locals() else "",
            "error": str(e),
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _slugify(title: str) -> str:
    """Convert a chapter title into a Markdown-anchor-compatible slug."""
    title = title.lower().replace(" ", "-")
    return re.sub(r'[^a-z0-9_\-]', '', title)
