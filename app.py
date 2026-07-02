#!/usr/bin/env python3
"""
YouTube Transcript to Notes Pipeline
=====================================
Desktop application that parses YouTube transcripts, segments them by chapter
timestamps, and generates structured revision notes using an LLM provider.

Configuration is loaded from a .env file in the project root.
See .env.example for setup instructions.
"""
import os
import sys
import re
import json
import threading
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox
from difflib import SequenceMatcher
import urllib.request
import urllib.error
import customtkinter as ctk

# Application Constants
APP_VERSION = "1.0.0"
LLM_TIMEOUT_SECONDS = 180  # Max seconds to wait for a single LLM response

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

# ----------------- Core Helper Functions -----------------

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

# ----------------- LLM Request Sender -----------------

def call_llm(provider, endpoint_url, api_key, model_name, system_prompt, user_prompt):
    """Make raw POST HTTP call to Ollama or OpenAI compatible endpoint."""
    url = endpoint_url.strip()
    headers = {
        "Content-Type": "application/json"
    }
    
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})
    
    if provider == "Ollama":
        # Normalize Ollama native URL or OpenAI compatible URL
        if not (url.endswith("/api/chat") or url.endswith("/v1/chat/completions") or "/api/" in url or "/v1/" in url):
            url = url.rstrip("/") + "/api/chat"
            
        if "/api/chat" in url:
            payload = {
                "model": model_name,
                "messages": messages,
                "stream": False
            }
        else:
            payload = {
                "model": model_name,
                "messages": messages
            }
    else:
        # OpenAI Compatible
        if not (url.endswith("/chat/completions") or "/v1" in url):
            url = url.rstrip("/") + "/v1/chat/completions"
        elif url.endswith("/v1") or url.endswith("/v1/"):
            url = url.rstrip("/") + "/chat/completions"
            
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
            
        payload = {
            "model": model_name,
            "messages": messages
        }
        
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req, timeout=LLM_TIMEOUT_SECONDS) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            if "choices" in res_data:
                return res_data["choices"][0]["message"]["content"]
            elif "message" in res_data:
                return res_data["message"]["content"]
            elif "response" in res_data:
                return res_data["response"]
            else:
                return str(res_data)
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="ignore")
        raise Exception(f"HTTP {e.code} Error: {e.reason}\nResponse: {err_msg}")
    except Exception as e:
        raise Exception(f"Connection failure: {str(e)}")

# ----------------- UI Application Setup -----------------

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

root = ctk.CTk()
root.title(f"YouTube Transcript to Notes Pipeline v{APP_VERSION}")
root.geometry("1200x800")
root.minsize(1050, 750)

# Global variables for UI entries
transcript_path_var = tk.StringVar()
timestamps_path_var = tk.StringVar()
output_dir_var = tk.StringVar()

# Path resolution
script_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(script_dir, ".env")
env_example_path = os.path.join(script_dir, ".env.example")
config_path = os.path.join(script_dir, "config.json")

def parse_env_file(filepath):
    """Parse a .env file into a dictionary. Ignores comments and blank lines."""
    env_vars = {}
    if not os.path.exists(filepath):
        return env_vars
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    env_vars[key.strip()] = value.strip()
    except Exception:
        pass
    return env_vars

def get_llm_config():
    """Load LLM configuration from .env file. Returns (provider, endpoint_url, api_key, model_name)."""
    env = parse_env_file(env_path)
    provider = env.get("PROVIDER", "Ollama")
    endpoint_url = env.get("ENDPOINT_URL", "http://localhost:11434")
    api_key = env.get("API_KEY", "")
    model_name = env.get("MODEL_NAME", "llama3")
    return provider, endpoint_url, api_key, model_name

def check_env_and_show_help():
    """On first run, if .env is missing or has no MODEL_NAME, show a help popup."""
    env = parse_env_file(env_path)
    if not env or not env.get("MODEL_NAME"):
        # Create .env from .env.example if it doesn't exist
        if not os.path.exists(env_path) and os.path.exists(env_example_path):
            try:
                import shutil
                shutil.copy2(env_example_path, env_path)
            except Exception:
                pass
        # Show help dialog
        root.after(500, _show_env_help_popup)

def _show_env_help_popup():
    """Display a one-time help window explaining how to configure the .env file."""
    help_win = ctk.CTkToplevel(root)
    help_win.title("Setup Required")
    help_win.geometry("620x480")
    help_win.resizable(False, False)
    help_win.transient(root)
    help_win.grab_set()
    help_win.attributes("-topmost", True)

    ctk.CTkLabel(
        help_win, text="Welcome! Let's set up your LLM provider.",
        font=("Segoe UI", 16, "bold"), text_color="#3b82f6"
    ).pack(pady=(20, 5), padx=20, anchor="w")

    ctk.CTkLabel(
        help_win,
        text="This app needs an LLM endpoint to generate notes.\n"
             "Your credentials are stored locally in a .env file\n"
             "that is gitignored and never committed.",
        font=("Segoe UI", 11), text_color="#a1a1aa", justify="left"
    ).pack(padx=20, anchor="w", pady=(0, 10))

    ctk.CTkLabel(
        help_win, text=f"Config file location:",
        font=("Segoe UI", 11, "bold"), text_color="#f4f4f5"
    ).pack(padx=20, anchor="w")

    path_entry = ctk.CTkEntry(help_win, font=("Consolas", 10), width=560, state="normal")
    path_entry.pack(padx=20, pady=(2, 10), anchor="w")
    path_entry.insert(0, env_path)
    path_entry.configure(state="disabled")

    help_text = (
        "Open the .env file in any text editor and fill in:\n\n"
        "  PROVIDER=Ollama                      (or 'OpenAI Compatible')\n"
        "  ENDPOINT_URL=http://localhost:11434   (your API endpoint)\n"
        "  API_KEY=                              (leave blank for Ollama)\n"
        "  MODEL_NAME=llama3                     (your model name)\n\n"
        "See .env.example for more provider examples (Grok, OpenRouter, Groq).\n"
        "After editing, restart the app or just click Start."
    )
    help_textbox = ctk.CTkTextbox(
        help_win, font=("Consolas", 11), fg_color="#18181b",
        text_color="#10b981", height=160, corner_radius=8
    )
    help_textbox.pack(padx=20, fill="x")
    help_textbox.insert("1.0", help_text)
    help_textbox.configure(state="disabled")

    def open_env_file():
        """Open .env in the default text editor."""
        try:
            os.startfile(env_path)
        except Exception:
            log_message(f"Could not auto-open .env. Please open manually: {env_path}")

    btn_frame = ctk.CTkFrame(help_win, fg_color="transparent")
    btn_frame.pack(pady=15, padx=20, fill="x")

    ctk.CTkButton(
        btn_frame, text="Open .env File", font=("Segoe UI", 11, "bold"),
        fg_color="#3f3f46", hover_color="#52525b", command=open_env_file
    ).pack(side="left", padx=(0, 10))

    ctk.CTkButton(
        btn_frame, text="Got it, close", font=("Segoe UI", 11, "bold"),
        fg_color="#3b82f6", hover_color="#2563eb", command=help_win.destroy
    ).pack(side="right")

# Thread-safe console log
def log_message(msg):
    def append_log():
        console_text.configure(state="normal")
        console_text.insert(tk.END, msg + "\n")
        console_text.see(tk.END)
        console_text.configure(state="disabled")
    root.after(0, append_log)

# Configuration File Functions (file paths only, LLM config lives in .env)
def load_config():
    """Load saved file paths from config.json (no LLM credentials stored here)."""
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                transcript_path_var.set(data.get("transcript_path", ""))
                timestamps_path_var.set(data.get("timestamps_path", ""))
                output_dir_var.set(data.get("output_dir", ""))
        except Exception as e:
            print(f"Error loading configuration: {e}")

def save_config(silent=False):
    """Save file paths to config.json. LLM credentials are NOT stored here."""
    data = {
        "transcript_path": transcript_path_var.get().strip(),
        "timestamps_path": timestamps_path_var.get().strip(),
        "output_dir": output_dir_var.get().strip()
    }
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        if not silent:
            log_message("File paths saved to config.json")
    except Exception as e:
        log_message(f"Error saving configuration: {str(e)}")

# Browse handlers
def browse_transcript():
    path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
    if path:
        transcript_path_var.set(path)

def browse_timestamps():
    path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
    if path:
        timestamps_path_var.set(path)

def browse_output_dir():
    path = filedialog.askdirectory()
    if path:
        output_dir_var.set(path)

# Running the pipeline in background thread
def start_pipeline_thread():
    """Validate inputs, read LLM config from .env, and launch the pipeline thread."""
    # Auto-save file paths
    save_config(silent=True)
    
    transcript_path = transcript_path_var.get().strip()
    timestamps_path = timestamps_path_var.get().strip()
    output_dir = output_dir_var.get().strip()
    
    # Load LLM config from .env
    provider, endpoint_url, api_key, model_name = get_llm_config()
    
    if not transcript_path or not os.path.exists(transcript_path):
        messagebox.showerror("Validation Error", "Please provide a valid transcript file path.")
        return
    if not timestamps_path or not os.path.exists(timestamps_path):
        messagebox.showerror("Validation Error", "Please provide a valid timestamps file path.")
        return
    if not output_dir or not os.path.isdir(output_dir):
        messagebox.showerror("Validation Error", "Please provide a valid output directory.")
        return
    if not endpoint_url:
        messagebox.showerror("Validation Error", "No ENDPOINT_URL found in .env file. Please configure it.")
        return
    if not model_name:
        messagebox.showerror("Validation Error", "No MODEL_NAME found in .env file. Please configure it.")
        return

    start_btn.configure(state="disabled", text="Running...")
    
    def process():
        try:
            log_message("=== PIPELINE STARTED ===")
            
            # Step 1: Read and parse chapters from outline
            log_message("Step 1: Parsing outline and normalizing timestamps...")
            with open(timestamps_path, "r", encoding="utf-8", errors="replace") as f:
                outline_text = f.read()
                
            chapters, warnings = parse_outline_text(outline_text)
            log_message(f"Successfully parsed {len(chapters)} chapters.")
            for w in warnings:
                log_message(f"Warning: {w}")
                
            if not chapters:
                raise Exception("Zero chapters parsed. Verify that the timestamps outline contains timestamps.")
                
            for c in chapters:
                c["time_sec"] = parse_time_str(c["time"])
            chapters.sort(key=lambda c: c["time_sec"])
            
            # Step 2: Parse raw transcript and segment
            log_message("Step 2: Parsing raw transcript and segmenting...")
            with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
                transcript_text = f.read()
                
            blocks = parse_transcript_text(transcript_text)
            if not blocks:
                raise Exception("No timestamped caption blocks found in transcript file.")
                
            log_message(f"Parsed {len(blocks)} raw caption blocks. Deduplicating overlaps...")
            merged = dedupe_merge(blocks)
            log_message(f"Deduplication complete. Total continuous chunks: {len(merged)}.")
            
            log_message("Assigning segments to chapters...")
            chapter_texts = assign_chapters(merged, chapters)
            
            # Step 3: Call LLM for each chapter
            log_message("Step 3: Generating detailed revision notes for each chapter...")
            detailed_notes_sections = []
            
            for idx, chapter in enumerate(chapters):
                title = chapter["title"]
                time_str = chapter["time"]
                section = chapter.get("section", "")
                ch_text = " ".join(chapter_texts[idx]).strip()
                word_count = len(ch_text.split())
                
                log_message(f"Processing Chapter {idx+1}/{len(chapters)}: '{title}' ({word_count} words)...")
                
                user_prompt = f"""You are generating revision notes for Chapter {idx+1}: "{title}"
Section: {section}
Start Time: {time_str}
Word Count of transcript segment: {word_count}

Transcript segment content:
---
{ch_text}
---

Please write detailed study/revision notes in Markdown format.

Make sure you structure the notes with:
1. ## {idx+1}. {title} (include start time: {time_str})
2. Summary (2-4 sentences): What this chapter covers and why it matters.
3. Key concepts / steps: Clean, well-structured explanations of definitions, procedures, and steps in order.
4. Syntax / commands / formulas: Give actual correct syntax/formulas in code blocks (e.g. Excel formula syntax, SQL code, etc.) where relevant, even if only described verbally.
5. Examples: Concrete worked examples mentioned in the text or constructed by you to match the concepts.
6. Common pitfalls / gotchas.
7. Quick revision recap: A bulleted summary cheat-sheet of key takeaways.

Add value using your own domain knowledge to correct any transcription errors, explain concepts clearly, and write mathematically/syntactically correct code or formulas."""
                
                try:
                    response = call_llm(
                        provider=provider,
                        endpoint_url=endpoint_url,
                        api_key=api_key,
                        model_name=model_name,
                        system_prompt="You are an expert technical note-writer and instructional designer. Your task is to write highly detailed, clear, and structured revision notes for a chapter of a video course based on its transcript segment.",
                        user_prompt=user_prompt
                    )
                    detailed_notes_sections.append(response)
                except Exception as e:
                    log_message(f"WARNING: Failed to generate notes for Chapter {idx+1}: {str(e)}")
                    fallback = f"""## {idx+1}. {title} (Start Time: {time_str})

### Summary
[Could not generate notes using LLM due to error: {str(e)}]

### Transcript Snippet
{ch_text[:500]}..."""
                    detailed_notes_sections.append(fallback)
                    
            # Assemble Course_Detailed_Notes.md
            log_message("Assembling Course_Detailed_Notes.md...")
            title_intro = f"# Course Detailed Revision Notes\n\nThis document contains comprehensive chapter-by-chapter revision notes and study material.\n\n## Table of Contents\n"
            
            sections_map = {}
            for idx, chapter in enumerate(chapters):
                sec = chapter.get("section", "").strip() or "General"
                if sec not in sections_map:
                    sections_map[sec] = []
                sections_map[sec].append((idx + 1, chapter["title"], chapter["time"]))
                
            toc = ""
            has_real_sections = len(sections_map) > 1 or (len(sections_map) == 1 and "General" not in sections_map)
            
            if has_real_sections:
                for sec, chs in sections_map.items():
                    toc += f"- **{sec}**\n"
                    for num, ch_title, time_str in chs:
                        slug = ch_title.lower().replace(" ", "-").replace("?", "").replace("&", "").replace("(", "").replace(")", "").replace(".", "")
                        toc += f"  - [{num}. {ch_title}](#{num}-{slug}) (Start: {time_str})\n"
            else:
                for idx, chapter in enumerate(chapters):
                    ch_title = chapter["title"]
                    slug = ch_title.lower().replace(" ", "-").replace("?", "").replace("&", "").replace("(", "").replace(")", "").replace(".", "")
                    toc += f"- [{idx+1}. {ch_title}](#{idx+1}-{slug}) (Start: {chapter['time']})\n"
                    
            toc += "\n---\n\n"
            
            full_detailed_content = title_intro + toc + "\n\n".join(detailed_notes_sections)
            
            detailed_path = os.path.join(output_dir, "Course_Detailed_Notes.md")
            with open(detailed_path, "w", encoding="utf-8") as f:
                f.write(full_detailed_content)
            log_message(f"Detailed notes saved to: {detailed_path}")
            
            # Step 4: Call LLM to generate Practical Cheat-sheet
            log_message("Step 4: Generating Course Practical Cheat-Sheet & Summary...")
            course_chapters_outline = ""
            for idx, chapter in enumerate(chapters):
                sec = f" [{chapter['section']}]" if chapter.get('section') else ""
                course_chapters_outline += f"- Chapter {idx+1}: {chapter['title']} (Starts: {chapter['time']}){sec}\n"
                
            user_prompt_summary = f"""We have generated detailed revision notes for the course. Here is a brief outline of the course chapters:
{course_chapters_outline}

Based on the course outline and details, generate a comprehensive, standalone "# Course Practical Cheat-Sheet & Summary".

This cheat-sheet must focus only on the most important, high-impact features and techniques covered in the course (the "must-know" elements for real-world application).

It must include:
1. Summary Tables: Side-by-side comparisons of key tools or functions (e.g. VLOOKUP vs XLOOKUP, standard vs array formulas, etc.).
2. Visual Aids & Mockups: Mermaid diagrams (graph TD, graph LR, etc.) or ASCII diagrams illustrating structures of data pipelines, schemas, relationships, or workflows.
3. Short Theory: Concise explanations of what each key feature does and why it is used.
4. Step-by-Step Practical Instructions: Explicit steps (keyboard shortcuts, paths, settings) to execute the operations.
5. Key Shortcuts Cheat-Sheet: A quick reference table of essential keyboard shortcuts taught.

Make this extremely clean, professional, and directly useful as a high-impact reference guide. Output only the Markdown content."""

            try:
                practical_summary = call_llm(
                    provider=provider,
                    endpoint_url=endpoint_url,
                    api_key=api_key,
                    model_name=model_name,
                    system_prompt="You are an expert technical note-writer and instructional designer. Your task is to write a practical executive summary and cheat-sheet for a course based on its chapters and overall content.",
                    user_prompt=user_prompt_summary
                )
            except Exception as e:
                log_message(f"ERROR generating practical summary: {str(e)}")
                practical_summary = f"# Course Practical Cheat-Sheet & Summary\n\n[Failed to generate cheat-sheet using LLM: {str(e)}]\n"
                
            practical_path = os.path.join(output_dir, "Course_Practical_Notes.md")
            with open(practical_path, "w", encoding="utf-8") as f:
                f.write(practical_summary)
            log_message(f"Practical notes saved to: {practical_path}")
            
            log_message("=== PIPELINE COMPLETED SUCCESSFULLY ===")
            root.after(0, lambda: messagebox.showinfo("Success", f"Processing completed successfully!\nNotes generated in:\n{output_dir}"))
            
        except Exception as e:
            log_message(f"CRITICAL ERROR in pipeline: {str(e)}")
            root.after(0, lambda: messagebox.showerror("Pipeline Error", f"An error occurred during processing:\n{str(e)}"))
            
        finally:
            root.after(0, lambda: start_btn.configure(state="normal", text="Start Processing Pipeline"))
            
    threading.Thread(target=process, daemon=True).start()

# PDF Tooling handlers
def install_pdf_library():
    pip_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "Scripts", "pip")
    if os.path.exists(pip_path + ".exe"):
        pip_path += ".exe"
        
    def run_install():
        log_message("Running pip install markdown-pdf in virtual environment...")
        try:
            process = subprocess.Popen(
                [pip_path, "install", "markdown-pdf"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                shell=True
            )
            for line in process.stdout:
                log_message(line.strip())
            process.wait()
            if process.returncode == 0:
                log_message("SUCCESS: markdown-pdf installed successfully!")
                root.after(0, lambda: messagebox.showinfo("Success", "markdown-pdf installed successfully!"))
            else:
                log_message(f"ERROR: Installation failed with exit code {process.returncode}")
                root.after(0, lambda: messagebox.showerror("Error", f"Installation failed with exit code {process.returncode}"))
        except Exception as e:
            log_message(f"ERROR running pip: {str(e)}")
            root.after(0, lambda: messagebox.showerror("Error", f"Failed to invoke pip: {str(e)}"))

    threading.Thread(target=run_install, daemon=True).start()

def convert_and_save_pdf():
    md_file = filedialog.askopenfilename(
        title="Select Markdown File to Convert",
        filetypes=[("Markdown Files", "*.md"), ("All Files", "*.*")]
    )
    if not md_file:
        return
        
    pdf_file = filedialog.asksaveasfilename(
        title="Save PDF As",
        defaultextension=".pdf",
        filetypes=[("PDF Files", "*.pdf")]
    )
    if not pdf_file:
        return
        
    log_message(f"Converting '{os.path.basename(md_file)}' to PDF...")
    
    def run_conversion():
        try:
            # Dynamically append venv site-packages if present
            venv_site = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "Lib", "site-packages")
            if os.path.exists(venv_site) and venv_site not in sys.path:
                sys.path.append(venv_site)
                
            try:
                from markdown_pdf import MarkdownPdf, Section
            except ImportError:
                raise Exception("The 'markdown-pdf' library is not available. Please click 'Install PDF Library' first.")
                
            with open(md_file, "r", encoding="utf-8", errors="replace") as f:
                md_content = f.read()
                
            pdf = MarkdownPdf(toc_level=2, optimize=True)
            pdf.add_section(Section(md_content, toc=True))
            pdf.save(pdf_file)
            
            log_message(f"SUCCESS: Saved PDF to {pdf_file}")
            root.after(0, lambda: messagebox.showinfo("Success", f"PDF saved successfully to:\n{pdf_file}"))
        except Exception as e:
            log_message(f"ERROR converting PDF: {str(e)}")
            root.after(0, lambda: messagebox.showerror("Error", f"Failed to convert PDF: {str(e)}"))

    threading.Thread(target=run_conversion, daemon=True).start()

# Load file path configuration on startup
load_config()

# Check .env and show help if needed
check_env_and_show_help()

# ----------------- UI Layout Setup -----------------

# Configure main window grid
root.grid_columnconfigure(0, weight=4) # Left column (Configuration)
root.grid_columnconfigure(1, weight=5) # Right column (Console log)
root.grid_rowconfigure(0, weight=0)    # Header
root.grid_rowconfigure(1, weight=1)    # Content area
root.grid_rowconfigure(2, weight=0)    # Bottom PDF utility

# Header Row
header_frame = ctk.CTkFrame(root, fg_color="transparent")
header_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=20, pady=(15, 5))

header_title = ctk.CTkLabel(
    header_frame,
    text="YouTube Transcript to Revision Notes Pipeline",
    font=("Segoe UI", 20, "bold"),
    text_color="#f4f4f5"
)
header_title.pack(anchor="w")

header_subtitle = ctk.CTkLabel(
    header_frame,
    text="Segment transcripts by chapter timestamps and leverage AI to build structured markdown and PDF study materials.",
    font=("Segoe UI", 11),
    text_color="#a1a1aa"
)
header_subtitle.pack(anchor="w", pady=(2, 0))

# Left Side Panel (Configuration and File selection)
left_container = ctk.CTkFrame(root, fg_color="transparent")
left_container.grid(row=1, column=0, sticky="nsew", padx=(20, 10), pady=10)

# Files card
files_card = ctk.CTkFrame(left_container, corner_radius=12, border_width=1, border_color="#3f3f46")
files_card.pack(fill="x", pady=(0, 10), ipady=5)

files_title = ctk.CTkLabel(files_card, text="Files & Output Selection", font=("Segoe UI", 14, "bold"), text_color="#3b82f6")
files_title.pack(anchor="w", padx=15, pady=(12, 8))

files_grid = ctk.CTkFrame(files_card, fg_color="transparent")
files_grid.pack(fill="x", padx=15, pady=5)
files_grid.grid_columnconfigure(1, weight=1)

# Transcript path
lbl_transcript = ctk.CTkLabel(files_grid, text="Transcript File:", font=("Segoe UI", 11, "bold"))
lbl_transcript.grid(row=0, column=0, sticky="w", pady=6, padx=(0, 10))
entry_transcript = ctk.CTkEntry(files_grid, textvariable=transcript_path_var, font=("Segoe UI", 10), placeholder_text="Select transcript file...")
entry_transcript.grid(row=0, column=1, sticky="we", pady=6, padx=5)
btn_browse_trans = ctk.CTkButton(files_grid, text="Browse", width=80, font=("Segoe UI", 10, "bold"), command=browse_transcript)
btn_browse_trans.grid(row=0, column=2, sticky="e", pady=6, padx=(5, 0))

# Timestamps path
lbl_timestamps = ctk.CTkLabel(files_grid, text="Timestamps File:", font=("Segoe UI", 11, "bold"))
lbl_timestamps.grid(row=1, column=0, sticky="w", pady=6, padx=(0, 10))
entry_timestamps = ctk.CTkEntry(files_grid, textvariable=timestamps_path_var, font=("Segoe UI", 10), placeholder_text="Select timestamps file...")
entry_timestamps.grid(row=1, column=1, sticky="we", pady=6, padx=5)
btn_browse_times = ctk.CTkButton(files_grid, text="Browse", width=80, font=("Segoe UI", 10, "bold"), command=browse_timestamps)
btn_browse_times.grid(row=1, column=2, sticky="e", pady=6, padx=(5, 0))

# Output directory
lbl_output = ctk.CTkLabel(files_grid, text="Output Directory:", font=("Segoe UI", 11, "bold"))
lbl_output.grid(row=2, column=0, sticky="w", pady=6, padx=(0, 10))
entry_output = ctk.CTkEntry(files_grid, textvariable=output_dir_var, font=("Segoe UI", 10), placeholder_text="Select output directory...")
entry_output.grid(row=2, column=1, sticky="we", pady=6, padx=5)
btn_browse_out = ctk.CTkButton(files_grid, text="Browse", width=80, font=("Segoe UI", 10, "bold"), command=browse_output_dir)
btn_browse_out.grid(row=2, column=2, sticky="e", pady=6, padx=(5, 0))

# LLM Status indicator card (read-only, shows what .env contains)
llm_card = ctk.CTkFrame(left_container, corner_radius=12, border_width=1, border_color="#3f3f46")
llm_card.pack(fill="x", pady=10, ipady=5)

llm_header = ctk.CTkFrame(llm_card, fg_color="transparent")
llm_header.pack(fill="x", padx=15, pady=(12, 4))

llm_title = ctk.CTkLabel(llm_header, text="LLM Provider", font=("Segoe UI", 14, "bold"), text_color="#3b82f6")
llm_title.pack(side="left")

btn_edit_env = ctk.CTkButton(
    llm_header, text="Edit .env", width=80, height=26,
    font=("Segoe UI", 10, "bold"), fg_color="#3f3f46", hover_color="#52525b",
    command=lambda: _open_env_in_editor()
)
btn_edit_env.pack(side="right")

btn_show_help = ctk.CTkButton(
    llm_header, text="Setup Help", width=90, height=26,
    font=("Segoe UI", 10, "bold"), fg_color="#3f3f46", hover_color="#52525b",
    command=lambda: _show_env_help_popup()
)
btn_show_help.pack(side="right", padx=(0, 5))

def _open_env_in_editor():
    """Open .env file in system default text editor."""
    if not os.path.exists(env_path):
        # Create from example if missing
        if os.path.exists(env_example_path):
            try:
                import shutil
                shutil.copy2(env_example_path, env_path)
            except Exception:
                pass
    try:
        os.startfile(env_path)
    except Exception:
        log_message(f"Could not auto-open .env. Open manually: {env_path}")

# Show current .env status
env_status_frame = ctk.CTkFrame(llm_card, fg_color="#18181b", corner_radius=8)
env_status_frame.pack(fill="x", padx=15, pady=(4, 12))

def _refresh_env_status():
    """Refresh the displayed LLM config status from .env."""
    provider, endpoint, api_key, model = get_llm_config()
    masked_key = "••••" + api_key[-4:] if len(api_key) > 4 else ("(none)" if not api_key else "••••")
    status_lines = (
        f"  Provider:  {provider}\n"
        f"  Endpoint:  {endpoint}\n"
        f"  API Key:   {masked_key}\n"
        f"  Model:     {model}"
    )
    env_status_text.configure(state="normal")
    env_status_text.delete("1.0", tk.END)
    env_status_text.insert("1.0", status_lines)
    env_status_text.configure(state="disabled")

env_status_text = ctk.CTkTextbox(
    env_status_frame, font=("Consolas", 11), fg_color="#18181b",
    text_color="#a1a1aa", height=80, corner_radius=6, border_width=0
)
env_status_text.pack(fill="x", padx=8, pady=8)
env_status_text.configure(state="disabled")

# Refresh status on startup
root.after(100, _refresh_env_status)

# Large prominent Start Button
start_btn = ctk.CTkButton(
    left_container,
    text="Start Processing Pipeline",
    font=("Segoe UI", 13, "bold"),
    fg_color="#10b981",
    hover_color="#059669",
    text_color="#ffffff",
    height=45,
    command=start_pipeline_thread
)
start_btn.pack(fill="x", pady=(15, 5))

# Refresh .env status button under start
btn_refresh_env = ctk.CTkButton(
    left_container,
    text="Refresh LLM Config",
    font=("Segoe UI", 10),
    fg_color="transparent",
    hover_color="#27272a",
    text_color="#71717a",
    border_width=1,
    border_color="#3f3f46",
    height=30,
    command=_refresh_env_status
)
btn_refresh_env.pack(fill="x", pady=(5, 0))

# Right Side Panel (Console logging pane)
right_container = ctk.CTkFrame(root, fg_color="transparent")
right_container.grid(row=1, column=1, sticky="nsew", padx=(10, 20), pady=10)

console_card = ctk.CTkFrame(right_container, corner_radius=12, border_width=1, border_color="#3f3f46")
console_card.pack(fill="both", expand=True)

console_title = ctk.CTkLabel(console_card, text="Console Output", font=("Segoe UI", 14, "bold"), text_color="#3b82f6")
console_title.pack(anchor="w", padx=15, pady=(12, 8))

console_text = ctk.CTkTextbox(
    console_card,
    fg_color="#09090b",
    text_color="#10b981",
    font=("Consolas", 11),
    border_width=0,
    corner_radius=8
)
console_text.pack(fill="both", expand=True, padx=15, pady=(0, 15))
console_text.configure(state="disabled")

# Bottom Panel (Markdown-to-PDF utility)
pdf_card = ctk.CTkFrame(root, corner_radius=12, border_width=1, border_color="#3f3f46")
pdf_card.grid(row=2, column=0, columnspan=2, sticky="ew", padx=20, pady=(10, 20), ipady=5)

pdf_card.grid_columnconfigure(0, weight=1)
pdf_card.grid_columnconfigure(1, weight=0)

pdf_info_frame = ctk.CTkFrame(pdf_card, fg_color="transparent")
pdf_info_frame.grid(row=0, column=0, sticky="w", padx=20, pady=10)

pdf_title = ctk.CTkLabel(pdf_info_frame, text="Markdown-to-PDF Utility", font=("Segoe UI", 13, "bold"), text_color="#3b82f6")
pdf_title.pack(anchor="w")

pdf_desc = ctk.CTkLabel(
    pdf_info_frame,
    text="Convert the generated Markdown study guides to premium styled PDF documents. Make sure the library is installed.",
    font=("Segoe UI", 10),
    text_color="#a1a1aa"
)
pdf_desc.pack(anchor="w", pady=(2, 0))

pdf_btn_frame = ctk.CTkFrame(pdf_card, fg_color="transparent")
pdf_btn_frame.grid(row=0, column=1, sticky="e", padx=20, pady=10)

btn_install_pdf = ctk.CTkButton(
    pdf_btn_frame,
    text="Install PDF Library",
    font=("Segoe UI", 11, "bold"),
    fg_color="#3f3f46",
    hover_color="#52525b",
    text_color="#f4f4f5",
    command=install_pdf_library
)
btn_install_pdf.pack(side="left", padx=5)

btn_convert_pdf = ctk.CTkButton(
    pdf_btn_frame,
    text="Convert & Save PDF",
    font=("Segoe UI", 11, "bold"),
    fg_color="#3b82f6",
    hover_color="#2563eb",
    text_color="#ffffff",
    command=convert_and_save_pdf
)
btn_convert_pdf.pack(side="left", padx=5)

# Startup friendly log message
provider, endpoint, _, model = get_llm_config()
log_message("System initialized.")
log_message(f"LLM Config loaded from .env: {provider} / {model} @ {endpoint}")
log_message("Select your files and click 'Start Processing Pipeline' to begin.")

if __name__ == "__main__":
    root.mainloop()
