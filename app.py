#!/usr/bin/env python3
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

# Modern Styling Constants
BG_DARK = "#18181b"      # Sleek dark gray
BG_PANEL = "#27272a"     # Slightly lighter panel background
FG_LIGHT = "#f4f4f5"     # Clear off-white text
FG_MUTED = "#a1a1aa"     # Gray muted text
ACCENT_BLUE = "#3b82f6"  # Premium accent blue
ACCENT_GREEN = "#10b981" # Success green
BORDER_COLOR = "#3f3f46" # Panel border

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
        with urllib.request.urlopen(req, timeout=120) as response:
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

# ----------------- UI Application Structure -----------------

root = tk.Tk()
root.title("YouTube Transcript to Notes Pipeline")
root.geometry("1100x700")
root.configure(bg=BG_DARK)

# Global variables for entries
transcript_path_var = tk.StringVar()
timestamps_path_var = tk.StringVar()
output_dir_var = tk.StringVar()

provider_var = tk.StringVar(value="Ollama")
endpoint_url_var = tk.StringVar(value="http://localhost:11434")
api_key_var = tk.StringVar()
model_name_var = tk.StringVar(value="llama3")

# Thread-safe console log
def log_message(msg):
    def append_log():
        console_text.config(state="normal")
        console_text.insert(tk.END, msg + "\n")
        console_text.see(tk.END)
        console_text.config(state="disabled")
    root.after(0, append_log)

# UI Elements Creation Helpers
def create_entry(parent, textvariable, width=40, show=""):
    return tk.Entry(
        parent, textvariable=textvariable, width=width, show=show,
        bg="#18181b", fg=FG_LIGHT, insertbackground=FG_LIGHT,
        bd=1, relief="solid", highlightthickness=1,
        highlightbackground="#3f3f46", highlightcolor=ACCENT_BLUE,
        font=("Segoe UI", 10)
    )

def create_button(parent, text, command, bg="#3f3f46", fg=FG_LIGHT, hover_bg="#52525b", font=("Segoe UI", 9, "bold")):
    btn = tk.Button(
        parent, text=text, command=command, bg=bg, fg=fg,
        activebackground=hover_bg, activeforeground=fg,
        bd=0, relief="flat", padx=10, pady=5, font=font, cursor="hand2"
    )
    def on_enter(e):
        if btn["state"] != "disabled":
            btn.config(bg=hover_bg)
    def on_leave(e):
        if btn["state"] != "disabled":
            btn.config(bg=bg)
    btn.bind("<Enter>", on_enter)
    btn.bind("<Leave>", on_leave)
    return btn

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
    transcript_path = transcript_path_var.get().strip()
    timestamps_path = timestamps_path_var.get().strip()
    output_dir = output_dir_var.get().strip()
    
    provider = provider_var.get()
    endpoint_url = endpoint_url_var.get().strip()
    api_key = api_key_var.get().strip()
    model_name = model_name_var.get().strip()
    
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
        messagebox.showerror("Validation Error", "Please provide an LLM endpoint URL.")
        return
    if not model_name:
        messagebox.showerror("Validation Error", "Please provide an LLM model name.")
        return

    start_btn.config(state="disabled", text="Running...")
    
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
            root.after(0, lambda: start_btn.config(state="normal", text="Start Processing"))
            
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

# ----------------- UI Layout Setup -----------------

# Set layout structure
root.grid_columnconfigure(0, weight=0, minsize=450)
root.grid_columnconfigure(1, weight=1)
root.grid_rowconfigure(1, weight=1)

# Title Header
header_label = tk.Label(
    root, text="YouTube Transcript to Revision Notes Generator",
    font=("Segoe UI", 16, "bold"), bg=BG_DARK, fg=FG_LIGHT, anchor="w", padx=15, pady=10
)
header_label.grid(row=0, column=0, columnspan=2, sticky="we")

# Left Column (Configuration Panels)
left_frame = tk.Frame(root, bg=BG_DARK, padx=10, pady=5)
left_frame.grid(row=1, column=0, sticky="nsew")

# Right Column (Console Logs)
right_frame = tk.Frame(root, bg=BG_DARK, padx=10, pady=5)
right_frame.grid(row=1, column=1, sticky="nsew")

# ---- Panel 1: Files Selection ----
files_lf = tk.LabelFrame(
    left_frame, text=" Files Selection ", bg=BG_PANEL, fg=ACCENT_BLUE,
    font=("Segoe UI", 11, "bold"), bd=1, relief="solid", padx=10, pady=10
)
files_lf.pack(fill="x", pady=5)

# Transcript path row
tk.Label(files_lf, text="Transcript Path:", bg=BG_PANEL, fg=FG_LIGHT, font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", pady=5)
transcript_entry = create_entry(files_lf, transcript_path_var, width=30)
transcript_entry.grid(row=0, column=1, padx=5, pady=5, sticky="we")
create_button(files_lf, "Browse", browse_transcript).grid(row=0, column=2, padx=5, pady=5)

# Timestamps path row
tk.Label(files_lf, text="Timestamps Path:", bg=BG_PANEL, fg=FG_LIGHT, font=("Segoe UI", 9, "bold")).grid(row=1, column=0, sticky="w", pady=5)
timestamps_entry = create_entry(files_lf, timestamps_path_var, width=30)
timestamps_entry.grid(row=1, column=1, padx=5, pady=5, sticky="we")
create_button(files_lf, "Browse", browse_timestamps).grid(row=1, column=2, padx=5, pady=5)

# Output directory row
tk.Label(files_lf, text="Output Directory:", bg=BG_PANEL, fg=FG_LIGHT, font=("Segoe UI", 9, "bold")).grid(row=2, column=0, sticky="w", pady=5)
output_entry = create_entry(files_lf, output_dir_var, width=30)
output_entry.grid(row=2, column=1, padx=5, pady=5, sticky="we")
create_button(files_lf, "Browse", browse_output_dir).grid(row=2, column=2, padx=5, pady=5)

files_lf.grid_columnconfigure(1, weight=1)

# ---- Panel 2: LLM Configuration ----
llm_lf = tk.LabelFrame(
    left_frame, text=" LLM Configuration ", bg=BG_PANEL, fg=ACCENT_BLUE,
    font=("Segoe UI", 11, "bold"), bd=1, relief="solid", padx=10, pady=10
)
llm_lf.pack(fill="x", pady=5)

# Provider
tk.Label(llm_lf, text="Provider:", bg=BG_PANEL, fg=FG_LIGHT, font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", pady=5)
provider_menu = tk.OptionMenu(llm_lf, provider_var, "Ollama", "OpenAI Compatible")
provider_menu.config(
    bg="#18181b", fg=FG_LIGHT, activebackground="#27272a", activeforeground=FG_LIGHT,
    bd=1, relief="solid", font=("Segoe UI", 9), highlightthickness=0
)
provider_menu["menu"].config(bg="#18181b", fg=FG_LIGHT, activebackground=ACCENT_BLUE)
provider_menu.grid(row=0, column=1, padx=5, pady=5, sticky="w")

# Endpoint URL
tk.Label(llm_lf, text="Endpoint URL:", bg=BG_PANEL, fg=FG_LIGHT, font=("Segoe UI", 9, "bold")).grid(row=1, column=0, sticky="w", pady=5)
endpoint_entry = create_entry(llm_lf, endpoint_url_var, width=40)
endpoint_entry.grid(row=1, column=1, padx=5, pady=5, sticky="we")

# API Key
tk.Label(llm_lf, text="API Key (if req):", bg=BG_PANEL, fg=FG_LIGHT, font=("Segoe UI", 9, "bold")).grid(row=2, column=0, sticky="w", pady=5)
api_key_entry = create_entry(llm_lf, api_key_var, width=40, show="*")
api_key_entry.grid(row=2, column=1, padx=5, pady=5, sticky="we")

# Model Name
tk.Label(llm_lf, text="Model Name:", bg=BG_PANEL, fg=FG_LIGHT, font=("Segoe UI", 9, "bold")).grid(row=3, column=0, sticky="w", pady=5)
model_entry = create_entry(llm_lf, model_name_var, width=40)
model_entry.grid(row=3, column=1, padx=5, pady=5, sticky="we")

llm_lf.grid_columnconfigure(1, weight=1)

# ---- Panel 3: MD-to-PDF Conversion ----
pdf_lf = tk.LabelFrame(
    left_frame, text=" MD-to-PDF Conversion ", bg=BG_PANEL, fg=ACCENT_BLUE,
    font=("Segoe UI", 11, "bold"), bd=1, relief="solid", padx=10, pady=10
)
pdf_lf.pack(fill="x", pady=5)

btn_install_pdf = create_button(pdf_lf, "Install PDF Library", install_pdf_library, bg="#3f3f46", hover_bg="#52525b")
btn_install_pdf.grid(row=0, column=0, padx=5, pady=5, sticky="we")

btn_convert_pdf = create_button(pdf_lf, "Convert & Save PDF", convert_and_save_pdf, bg="#3f3f46", hover_bg="#52525b")
btn_convert_pdf.grid(row=0, column=1, padx=5, pady=5, sticky="we")

pdf_lf.grid_columnconfigure(0, weight=1)
pdf_lf.grid_columnconfigure(1, weight=1)

# Start Execution Button
start_btn = create_button(
    left_frame, "Start Processing Pipeline", start_pipeline_thread,
    bg=ACCENT_BLUE, hover_bg="#2563eb", font=("Segoe UI", 11, "bold")
)
start_btn.pack(fill="x", pady=15, ipady=5)

# ---- Panel 4: Console Logs ----
console_lf = tk.LabelFrame(
    right_frame, text=" Console Logs ", bg=BG_PANEL, fg=ACCENT_BLUE,
    font=("Segoe UI", 11, "bold"), bd=1, relief="solid", padx=10, pady=10
)
console_lf.pack(fill="both", expand=True)

console_text = tk.Text(
    console_lf, bg="#09090b", fg=ACCENT_GREEN, insertbackground=ACCENT_GREEN,
    font=("Consolas", 10), bd=0, wrap="word", state="disabled"
)
console_text.pack(side="left", fill="both", expand=True)

scrollbar = tk.Scrollbar(console_lf, command=console_text.yview)
scrollbar.pack(side="right", fill="y")
console_text.config(yscrollcommand=scrollbar.set)

# Startup friendly log message
log_message("System initialized. Fill in the paths and parameters, and press Start.")

if __name__ == "__main__":
    root.mainloop()
