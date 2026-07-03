#!/usr/bin/env python3
"""
YouTube Transcript to Notes Pipeline — Desktop UI
==================================================
This file contains ONLY the GUI layer. All business logic lives in the
``src/`` package:

  - ``src.parser``     — transcript/outline parsing and segmentation
  - ``src.config``     — .env and config.json management
  - ``src.llm_client`` — HTTP calls to LLM providers
  - ``src.pipeline``   — end-to-end pipeline orchestration
"""
import os
import sys
import json
import shutil
import threading
import subprocess
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox

import customtkinter as ctk

from src.config import parse_env_file, get_llm_config
from src.llm_client import APP_VERSION
from src.pipeline import run_pipeline, run_pipeline_from_data

# ─────────────────────────── Path Resolution ───────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(SCRIPT_DIR, ".env")
ENV_EXAMPLE_PATH = os.path.join(SCRIPT_DIR, ".env.example")
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")

# ─────────────────────────── Helper Functions ──────────────────────────


def _open_path(path):
    """Open a file or directory with the OS default handler (Windows)."""
    try:
        os.startfile(path)
    except Exception:
        pass


# ─────────────────────── Configuration Persistence ─────────────────────


def load_config(transcript_var, timestamps_var, output_var):
    """Load saved file paths from config.json."""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            transcript_var.set(data.get("transcript_path", ""))
            timestamps_var.set(data.get("timestamps_path", ""))
            output_var.set(data.get("output_dir", ""))
        except Exception:
            pass


def save_config(transcript_var, timestamps_var, output_var):
    """Persist file paths to config.json (no credentials stored here)."""
    data = {
        "transcript_path": transcript_var.get().strip(),
        "timestamps_path": timestamps_var.get().strip(),
        "output_dir": output_var.get().strip(),
    }
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception:
        pass


# ──────────────────────────── First-Run Help ───────────────────────────


def check_env_and_show_help(root):
    """On first run, check if credentials exist. If not, show setup dialog."""
    from src.credentials import has_stored_credentials
    
    if has_stored_credentials():
        return
        
    env = parse_env_file(ENV_PATH)
    if not env or not env.get("MODEL_NAME"):
        root.after(500, lambda: _show_env_help_popup(root))


def _show_env_help_popup(root):
    """Display an interactive dialog for secure API credential setup."""
    from src.credentials import store_all_credentials
    
    help_win = ctk.CTkToplevel(root)
    help_win.title("API Configuration Setup")
    help_win.geometry("500x550")
    help_win.resizable(False, False)
    help_win.transient(root)
    help_win.grab_set()

    ctk.CTkLabel(
        help_win, text="Welcome! Let's set up your LLM provider.",
        font=("Segoe UI", 16, "bold"), text_color="#3b82f6"
    ).pack(pady=(20, 5), padx=20, anchor="w")

    ctk.CTkLabel(
        help_win,
        text="This app needs an LLM endpoint to generate notes.\n"
             "Your credentials will be securely stored in the Windows\n"
             "Credential Manager.",
        font=("Segoe UI", 11), text_color="#a1a1aa", justify="left"
    ).pack(padx=20, anchor="w", pady=(0, 20))

    form_frame = ctk.CTkFrame(help_win, fg_color="transparent")
    form_frame.pack(fill="x", padx=20)

    # Variables
    provider_var = tk.StringVar(value="Groq")
    endpoint_var = tk.StringVar(value="https://api.groq.com/openai/v1/chat/completions")
    api_key_var = tk.StringVar()
    model_var = tk.StringVar(value="llama-3.3-70b-versatile")

    def on_provider_change(*args):
        prov = provider_var.get()
        if prov == "Groq":
            endpoint_var.set("https://api.groq.com/openai/v1/chat/completions")
            model_var.set("llama-3.3-70b-versatile")
        elif prov == "OpenRouter":
            endpoint_var.set("https://openrouter.ai/api/v1/chat/completions")
            model_var.set("anthropic/claude-3.5-sonnet")
        elif prov == "Gemini":
            endpoint_var.set("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions")
            model_var.set("gemini-1.5-flash")
        elif prov == "Ollama":
            endpoint_var.set("http://localhost:11434")
            model_var.set("llama3")
            api_key_var.set("")

    provider_var.trace_add("write", on_provider_change)

    # Form Fields
    ctk.CTkLabel(form_frame, text="Provider:", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w", pady=8)
    provider_dropdown = ctk.CTkOptionMenu(form_frame, variable=provider_var, values=["Groq", "OpenRouter", "Gemini", "Ollama", "Other"])
    provider_dropdown.grid(row=0, column=1, sticky="we", pady=8, padx=(10, 0))

    ctk.CTkLabel(form_frame, text="Endpoint URL:", font=("Segoe UI", 11, "bold")).grid(row=1, column=0, sticky="w", pady=8)
    ctk.CTkEntry(form_frame, textvariable=endpoint_var, width=300).grid(row=1, column=1, sticky="we", pady=8, padx=(10, 0))

    ctk.CTkLabel(form_frame, text="Model Name:", font=("Segoe UI", 11, "bold")).grid(row=2, column=0, sticky="w", pady=8)
    ctk.CTkEntry(form_frame, textvariable=model_var, width=300).grid(row=2, column=1, sticky="we", pady=8, padx=(10, 0))

    ctk.CTkLabel(form_frame, text="API Key:", font=("Segoe UI", 11, "bold")).grid(row=3, column=0, sticky="w", pady=8)
    ctk.CTkEntry(form_frame, textvariable=api_key_var, show="*", width=300).grid(row=3, column=1, sticky="we", pady=8, padx=(10, 0))

    def save_and_close():
        p = provider_var.get().strip()
        e = endpoint_var.get().strip()
        k = api_key_var.get().strip()
        m = model_var.get().strip()

        if not e or not m:
            messagebox.showerror("Error", "Endpoint and Model Name are required.", parent=help_win)
            return

        success = store_all_credentials(p, e, k, m)
        if success:
            messagebox.showinfo("Success", "Credentials saved securely!", parent=help_win)
            help_win.destroy()
            
            # Since config might have changed, restart is technically safest, but we can just let them click start.
            root.after(0, lambda: messagebox.showinfo("Ready", "Configuration saved. You can now use the pipeline."))
        else:
            messagebox.showerror("Error", "Failed to save to system keyring.", parent=help_win)

    btn_frame = ctk.CTkFrame(help_win, fg_color="transparent")
    btn_frame.pack(pady=30, padx=20, fill="x")

    ctk.CTkButton(
        btn_frame, text="Save Credentials", font=("Segoe UI", 13, "bold"),
        fg_color="#10b981", hover_color="#059669", height=40,
        command=save_and_close
    ).pack(fill="x")


# ───────────────────────── PDF Tooling Handlers ────────────────────────


def install_pdf_library(log_fn, root):
    """Install markdown-pdf into the local .venv."""
    pip_path = os.path.join(SCRIPT_DIR, ".venv", "Scripts", "pip")
    if os.path.exists(pip_path + ".exe"):
        pip_path += ".exe"

    def run_install():
        log_fn("Running pip install markdown-pdf in virtual environment...")
        try:
            process = subprocess.Popen(
                [pip_path, "install", "markdown-pdf"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                shell=False,
            )
            for line in process.stdout:
                log_fn(line.strip())
            process.wait()
            if process.returncode == 0:
                log_fn("SUCCESS: markdown-pdf installed successfully!")
                root.after(0, lambda: messagebox.showinfo("Success", "markdown-pdf installed successfully!"))
            else:
                log_fn(f"ERROR: Installation failed with exit code {process.returncode}")
                root.after(0, lambda: messagebox.showerror("Error", f"Installation failed with exit code {process.returncode}"))
        except Exception as e:
            log_fn(f"ERROR running pip: {str(e)}")
            root.after(0, lambda: messagebox.showerror("Error", f"Failed to invoke pip: {str(e)}"))

    threading.Thread(target=run_install, daemon=True).start()


def convert_and_save_pdf(log_fn, root):
    """Let the user pick a Markdown file and export it as PDF."""
    md_file = filedialog.askopenfilename(
        title="Select Markdown File to Convert",
        filetypes=[("Markdown Files", "*.md"), ("All Files", "*.*")],
    )
    if not md_file:
        return

    pdf_file = filedialog.asksaveasfilename(
        title="Save PDF As",
        defaultextension=".pdf",
        filetypes=[("PDF Files", "*.pdf")],
    )
    if not pdf_file:
        return

    log_fn(f"Converting '{os.path.basename(md_file)}' to PDF...")

    def run_conversion():
        try:
            venv_site = os.path.join(SCRIPT_DIR, ".venv", "Lib", "site-packages")
            if os.path.exists(venv_site) and venv_site not in sys.path:
                sys.path.append(venv_site)
            try:
                from markdown_pdf import MarkdownPdf, Section
            except ImportError:
                raise Exception("The 'markdown-pdf' library is not available. Please click 'Install PDF Library' first.")
            with open(md_file, "r", encoding="utf-8", errors="replace") as f:
                md_content = f.read()

            custom_css = """
            body { font-family: 'Segoe UI', Helvetica, sans-serif; line-height: 1.5; color: #1f2937; }
            h1 {
                color: #1e3a8a;
                font-size: 28pt;
                border-bottom: 3px solid #3b82f6;
                padding-bottom: 6px;
                margin-top: 0;
            }
            h2 { 
                color: #2563eb; 
                font-size: 20pt; 
                border-bottom: 1px solid #d1d5db;
                padding-bottom: 4px;
                margin-top: 0; 
            }
            h3 { color: #047857; font-size: 16pt; margin-top: 1.2em; }
            h4 { color: #6d28d9; font-size: 14pt; }
            p { margin-bottom: 1em; }
            li { margin-bottom: 0.5em; }
            pre { 
                background-color: #f8fafc; 
                padding: 12px; 
                border-left: 4px solid #94a3b8;
                font-family: 'Courier New', Courier, monospace;
                font-size: 10pt;
                white-space: pre-wrap;
            }
            code { 
                background-color: #f1f5f9; 
                color: #be123c; 
                padding: 2px 5px; 
                font-family: 'Courier New', Courier, monospace;
            }
            blockquote { 
                border-left: 4px solid #3b82f6; 
                background-color: #eff6ff;
                padding: 10px 15px; 
                color: #4b5563; 
                font-style: italic; 
            }
            table { width: 100%; border-collapse: collapse; margin: 1em 0; }
            th { background-color: #e2e8f0; font-weight: bold; padding: 10px; border: 1px solid #cbd5e1; color: #0f172a; text-align: left; }
            td { padding: 10px; border: 1px solid #cbd5e1; }
            tr:nth-child(even) { background-color: #f8fafc; }
            a { color: #2563eb; text-decoration: none; }
            """

            pdf = MarkdownPdf(toc_level=2, optimize=True)
            
            # Split markdown by H1/H2 headings to force true page breaks
            lines = md_content.split('\n')
            chunks = []
            current_chunk = []
            
            for line in lines:
                if line.startswith('# ') or line.startswith('## '):
                    if current_chunk:
                        chunks.append('\n'.join(current_chunk))
                        current_chunk = []
                current_chunk.append(line)
            
            if current_chunk:
                chunks.append('\n'.join(current_chunk))
                
            for chunk in chunks:
                if chunk.strip():
                    pdf.add_section(Section(chunk, toc=True), user_css=custom_css)
                    
            pdf.save(pdf_file)
            log_fn(f"SUCCESS: Saved PDF to {pdf_file}")
            root.after(0, lambda: messagebox.showinfo("Success", f"PDF saved successfully to:\n{pdf_file}"))
        except Exception as e:
            log_fn(f"ERROR converting PDF: {str(e)}")
            root.after(0, lambda: messagebox.showerror("Error", f"Failed to convert PDF: {str(e)}"))

    threading.Thread(target=run_conversion, daemon=True).start()


# ═══════════════════════════════════════════════════════════════════════
#  MAIN APPLICATION (only runs when executed directly)
# ═══════════════════════════════════════════════════════════════════════

def main():
    # ── Theme ──
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    root.title(f"YouTube Transcript to Notes Pipeline v{APP_VERSION}")
    root.geometry("1200x800")
    root.minsize(1050, 750)

    # ── Global state ──
    cancel_event = threading.Event()
    transcript_path_var = tk.StringVar()
    timestamps_path_var = tk.StringVar()
    output_dir_var = tk.StringVar()
    youtube_url_var = tk.StringVar()

    # ── Console log helper with file mirroring ──
    def log_message(msg):
        timestamp = datetime.now().strftime("%H:%M:%S")
        stamped = f"[{timestamp}] {msg}"
        def _append():
            console_text.configure(state="normal")
            console_text.insert(tk.END, stamped + "\n")
            console_text.see(tk.END)
            console_text.configure(state="disabled")
        root.after(0, _append)
        # Mirror to log file
        try:
            out_dir = output_dir_var.get().strip()
            if out_dir and os.path.isdir(out_dir):
                log_path = os.path.join(out_dir, "pipeline.log")
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(stamped + "\n")
        except Exception:
            pass

    # ── Browse handlers ──
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

    # ── Pipeline launcher ──
    def start_pipeline_thread():
        save_config(transcript_path_var, timestamps_path_var, output_dir_var)

        transcript_path = transcript_path_var.get().strip()
        timestamps_path = timestamps_path_var.get().strip()
        output_dir = output_dir_var.get().strip()
        provider, endpoint_url, api_key, model_name = get_llm_config(ENV_PATH)

        # Validation
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

        cancel_event.clear()
        start_btn.pack_forget()
        cancel_btn.configure(state="normal", text="Cancel Pipeline")
        cancel_btn.pack(fill="x", side="bottom")
        status_label.configure(text="Status: Running...", text_color="#fbbf24")

        def on_progress(current, total):
            progress_bar.set(current / total if total else 0)

        def process():
            result = None
            try:
                result = run_pipeline(
                    transcript_path=transcript_path,
                    timestamps_path=timestamps_path,
                    output_dir=output_dir,
                    provider=provider,
                    endpoint_url=endpoint_url,
                    api_key=api_key,
                    model_name=model_name,
                    cancel_event=cancel_event,
                    on_log=log_message,
                    on_progress=on_progress,
                )
                if result["success"]:
                    root.after(0, lambda: progress_bar.set(1.0))
                    root.after(0, lambda: messagebox.showinfo(
                        "Success",
                        f"Processing completed successfully!\nNotes generated in:\n{output_dir}"
                    ))
                elif result.get("error"):
                    root.after(0, lambda: messagebox.showerror("Pipeline Error", result["error"]))
            except Exception as e:
                log_message(f"CRITICAL ERROR in pipeline: {str(e)}")
                root.after(0, lambda: messagebox.showerror("Pipeline Error", str(e)))
            finally:
                def restore_ui():
                    cancel_btn.pack_forget()
                    start_btn.pack(fill="x", side="bottom")
                    progress_bar.set(0)
                    if cancel_event.is_set():
                        status_label.configure(text="Status: Cancelled", text_color="#ef4444")
                    elif result and result.get("success"):
                        status_label.configure(text="Status: Completed ✅", text_color="#10b981")
                    else:
                        status_label.configure(text="Status: Error", text_color="#ef4444")
                root.after(0, restore_ui)

        threading.Thread(target=process, daemon=True).start()

    # ── YouTube URL Pipeline launcher ──
    def start_youtube_pipeline_thread():
        url = youtube_url_var.get().strip()
        output_dir = output_dir_var.get().strip()
        provider, endpoint_url, api_key, model_name = get_llm_config(ENV_PATH)

        if not url:
            messagebox.showerror("Validation Error", "Please paste a YouTube URL.")
            return
        if not output_dir or not os.path.isdir(output_dir):
            messagebox.showerror("Validation Error", "Please select a valid output directory.")
            return
        if not endpoint_url:
            messagebox.showerror("Validation Error", "No ENDPOINT_URL found in .env file. Please configure it.")
            return
        if not model_name:
            messagebox.showerror("Validation Error", "No MODEL_NAME found in .env file. Please configure it.")
            return

        cancel_event.clear()
        start_btn.pack_forget()
        cancel_btn.configure(state="normal", text="Cancel Pipeline")
        cancel_btn.pack(fill="x", side="bottom")
        status_label.configure(text="Status: Running...", text_color="#fbbf24")

        def on_progress(current, total):
            progress_bar.set(current / total if total else 0)

        def process():
            result = None
            try:
                from src.youtube import extract_from_url
                log_message("=== YOUTUBE EXTRACTION ===")
                log_message(f"Extracting data from: {url}")

                data = extract_from_url(url, on_log=log_message)

                if not data['transcript_blocks']:
                    log_message("ERROR: No transcript could be extracted.")
                    root.after(0, lambda: messagebox.showerror("Error", "No transcript found for this video."))
                    return
                if not data['chapters']:
                    log_message("ERROR: No chapters could be determined.")
                    root.after(0, lambda: messagebox.showerror("Error", "No chapters found for this video."))
                    return

                log_message(f"Extraction complete. Starting LLM pipeline...")

                result = run_pipeline_from_data(
                    transcript_blocks=data['transcript_blocks'],
                    chapters=data['chapters'],
                    output_dir=output_dir,
                    provider=provider,
                    endpoint_url=endpoint_url,
                    api_key=api_key,
                    model_name=model_name,
                    cancel_event=cancel_event,
                    on_log=log_message,
                    on_progress=on_progress,
                )
                if result["success"]:
                    root.after(0, lambda: progress_bar.set(1.0))
                    root.after(0, lambda: messagebox.showinfo(
                        "Success",
                        f"Processing completed successfully!\nNotes generated in:\n{output_dir}"
                    ))
                elif result.get("error"):
                    root.after(0, lambda: messagebox.showerror("Pipeline Error", result["error"]))
            except ImportError:
                log_message("ERROR: youtube-transcript-api or yt-dlp not installed.")
                log_message("Run: .venv\\Scripts\\pip install youtube-transcript-api yt-dlp")
                root.after(0, lambda: messagebox.showerror(
                    "Missing Libraries",
                    "youtube-transcript-api and yt-dlp are required.\n\n"
                    "Run in terminal:\n.venv\\Scripts\\pip install youtube-transcript-api yt-dlp"
                ))
            except Exception as e:
                log_message(f"CRITICAL ERROR: {str(e)}")
                root.after(0, lambda: messagebox.showerror("Pipeline Error", str(e)))
            finally:
                def restore_ui():
                    cancel_btn.pack_forget()
                    start_btn.pack(fill="x", side="bottom")
                    progress_bar.set(0)
                    if cancel_event.is_set():
                        status_label.configure(text="Status: Cancelled", text_color="#ef4444")
                    elif result and result.get("success"):
                        status_label.configure(text="Status: Completed ✅", text_color="#10b981")
                    else:
                        status_label.configure(text="Status: Error", text_color="#ef4444")
                root.after(0, restore_ui)

        threading.Thread(target=process, daemon=True).start()

    def cancel_pipeline():
        if messagebox.askyesno("Confirm Cancel", "Are you sure you want to cancel the pipeline?"):
            log_message("Cancel requested. Waiting for current chapter to finish...")
            cancel_btn.configure(state="disabled", text="Cancelling...")
            cancel_event.set()

    # ─────────────────────── UI LAYOUT ───────────────────────

    root.grid_columnconfigure(0, weight=1)
    root.grid_rowconfigure(0, weight=0)    # Header
    root.grid_rowconfigure(1, weight=0)    # Top panel (Files & Actions)
    root.grid_rowconfigure(2, weight=0)    # Progress bar
    root.grid_rowconfigure(3, weight=1)    # Console area (expanding)
    root.grid_rowconfigure(4, weight=0)    # Bottom PDF utility

    # ── Header ──
    header_frame = ctk.CTkFrame(root, fg_color="transparent")
    header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(15, 5))

    ctk.CTkLabel(
        header_frame, text="YouTube Transcript to Revision Notes Pipeline",
        font=("Segoe UI", 20, "bold"), text_color="#f4f4f5"
    ).pack(anchor="w")

    ctk.CTkLabel(
        header_frame,
        text="Segment transcripts by chapter timestamps and leverage AI to build structured markdown and PDF study materials.",
        font=("Segoe UI", 11), text_color="#a1a1aa"
    ).pack(anchor="w", pady=(2, 0))

    # ── Top Panel (Files + Actions) ──
    top_container = ctk.CTkFrame(root, fg_color="transparent")
    top_container.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 5))
    top_container.grid_columnconfigure(0, weight=3)
    top_container.grid_columnconfigure(1, weight=1)

    # Input card with tabs
    input_card = ctk.CTkFrame(top_container, corner_radius=12, border_width=1, border_color="#3f3f46")
    input_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

    input_tabs = ctk.CTkTabview(input_card, corner_radius=10, height=180,
                                 segmented_button_fg_color="#27272a",
                                 segmented_button_selected_color="#3b82f6",
                                 segmented_button_selected_hover_color="#2563eb")
    input_tabs.pack(fill="both", expand=True, padx=10, pady=(5, 10))

    # ── YouTube URL Tab (Default) ──
    yt_tab = input_tabs.add("YouTube URL")
    yt_tab.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(yt_tab, text="Paste a YouTube video link below and select an output directory.",
                 font=("Segoe UI", 10), text_color="#a1a1aa").grid(row=0, column=0, columnspan=2, sticky="w", padx=5, pady=(5, 8))

    ctk.CTkLabel(yt_tab, text="YouTube URL:", font=("Segoe UI", 11, "bold")).grid(row=1, column=0, sticky="w", padx=5, pady=4)
    ctk.CTkEntry(yt_tab, textvariable=youtube_url_var, font=("Segoe UI", 10),
                 placeholder_text="https://www.youtube.com/watch?v=...").grid(row=2, column=0, columnspan=2, sticky="we", padx=5, pady=4)

    ctk.CTkLabel(yt_tab, text="Output Directory:", font=("Segoe UI", 11, "bold")).grid(row=3, column=0, sticky="w", padx=5, pady=4)
    yt_output_frame = ctk.CTkFrame(yt_tab, fg_color="transparent")
    yt_output_frame.grid(row=4, column=0, columnspan=2, sticky="we", padx=5, pady=4)
    yt_output_frame.grid_columnconfigure(0, weight=1)
    ctk.CTkEntry(yt_output_frame, textvariable=output_dir_var, font=("Segoe UI", 10),
                 placeholder_text="Select output directory...").grid(row=0, column=0, sticky="we", padx=(0, 5))
    ctk.CTkButton(yt_output_frame, text="Browse", width=80, font=("Segoe UI", 10, "bold"),
                  command=browse_output_dir).grid(row=0, column=1, sticky="e")

    # ── Manual Files Tab ──
    files_tab = input_tabs.add("Manual Files")
    files_tab.grid_columnconfigure(1, weight=1)

    for row_idx, (label_text, var, browse_fn) in enumerate([
        ("Transcript File:", transcript_path_var, browse_transcript),
        ("Timestamps File:", timestamps_path_var, browse_timestamps),
        ("Output Directory:", output_dir_var, browse_output_dir),
    ]):
        ctk.CTkLabel(files_tab, text=label_text, font=("Segoe UI", 11, "bold")).grid(row=row_idx, column=0, sticky="w", pady=6, padx=(5, 10))
        ctk.CTkEntry(files_tab, textvariable=var, font=("Segoe UI", 10), placeholder_text=f"Select {label_text.lower().replace(':', '...')}").grid(row=row_idx, column=1, sticky="we", pady=6, padx=5)
        ctk.CTkButton(files_tab, text="Browse", width=80, font=("Segoe UI", 10, "bold"), command=browse_fn).grid(row=row_idx, column=2, sticky="e", pady=6, padx=(5, 5))

    input_tabs.set("YouTube URL")  # Default to YouTube tab

    # Actions card
    actions_card = ctk.CTkFrame(top_container, corner_radius=12, border_width=1, border_color="#3f3f46")
    actions_card.grid(row=0, column=1, sticky="nsew")

    ctk.CTkLabel(actions_card, text="Pipeline Controls", font=("Segoe UI", 14, "bold"), text_color="#10b981").pack(anchor="w", padx=15, pady=(12, 8))

    actions_inner = ctk.CTkFrame(actions_card, fg_color="transparent")
    actions_inner.pack(fill="both", expand=True, padx=15, pady=(0, 15))

    # Status indicator
    status_label = ctk.CTkLabel(
        actions_inner, text="Status: Ready",
        font=("Segoe UI", 10), text_color="#a1a1aa"
    )
    status_label.pack(anchor="w", pady=(5, 5))

    ctk.CTkButton(
        actions_inner, text="API Setup / Credentials",
        font=("Segoe UI", 11, "bold"), fg_color="#3f3f46", hover_color="#52525b", height=35,
        command=lambda: _show_env_help_popup(root)
    ).pack(fill="x", pady=(5, 5))

    open_output_btn = ctk.CTkButton(
        actions_inner, text="Open Output Folder",
        font=("Segoe UI", 11, "bold"), fg_color="#3f3f46", hover_color="#52525b", height=35,
        command=lambda: _open_path(output_dir_var.get().strip()) if output_dir_var.get().strip() else None
    )
    open_output_btn.pack(fill="x", pady=(0, 5))

    def get_active_start_command():
        """Route to the correct pipeline based on active tab."""
        active = input_tabs.get()
        if active == "YouTube URL":
            start_youtube_pipeline_thread()
        else:
            start_pipeline_thread()

    start_btn = ctk.CTkButton(
        actions_inner, text="Start Pipeline",
        font=("Segoe UI", 13, "bold"), fg_color="#10b981", hover_color="#059669",
        text_color="#ffffff", height=45, command=get_active_start_command
    )
    start_btn.pack(fill="x", side="bottom")

    cancel_btn = ctk.CTkButton(
        actions_inner, text="Cancel Pipeline",
        font=("Segoe UI", 13, "bold"), fg_color="#ef4444", hover_color="#dc2626",
        text_color="#ffffff", height=45, command=cancel_pipeline
    )

    # ── Progress Bar ──
    progress_bar = ctk.CTkProgressBar(root, height=6, corner_radius=3, progress_color="#10b981")
    progress_bar.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 5))
    progress_bar.set(0)

    # ── Console ──
    console_card = ctk.CTkFrame(root, corner_radius=12, border_width=1, border_color="#3f3f46")
    console_card.grid(row=3, column=0, sticky="nsew", padx=20, pady=5)

    console_header = ctk.CTkFrame(console_card, fg_color="transparent")
    console_header.pack(fill="x", padx=15, pady=(12, 8))

    ctk.CTkLabel(console_header, text="Console Output", font=("Segoe UI", 14, "bold"), text_color="#3b82f6").pack(side="left")

    def clear_console():
        console_text.configure(state="normal")
        console_text.delete("1.0", tk.END)
        console_text.configure(state="disabled")

    ctk.CTkButton(
        console_header, text="Clear", width=60, height=26,
        font=("Segoe UI", 10, "bold"), fg_color="#3f3f46", hover_color="#52525b",
        command=clear_console
    ).pack(side="right")

    console_text = ctk.CTkTextbox(
        console_card, fg_color="#09090b", text_color="#10b981",
        font=("Consolas", 11), border_width=0, corner_radius=8
    )
    console_text.pack(fill="both", expand=True, padx=15, pady=(0, 15))
    console_text.configure(state="disabled")

    # ── PDF Utility ──
    pdf_card = ctk.CTkFrame(root, corner_radius=12, border_width=1, border_color="#3f3f46")
    pdf_card.grid(row=4, column=0, sticky="ew", padx=20, pady=(5, 20), ipady=5)
    pdf_card.grid_columnconfigure(0, weight=1)
    pdf_card.grid_columnconfigure(1, weight=0)

    pdf_info = ctk.CTkFrame(pdf_card, fg_color="transparent")
    pdf_info.grid(row=0, column=0, sticky="w", padx=20, pady=10)
    ctk.CTkLabel(pdf_info, text="Markdown-to-PDF Utility", font=("Segoe UI", 13, "bold"), text_color="#3b82f6").pack(anchor="w")
    ctk.CTkLabel(pdf_info, text="Convert the generated Markdown study guides to premium styled PDF documents.", font=("Segoe UI", 10), text_color="#a1a1aa").pack(anchor="w", pady=(2, 0))

    pdf_btns = ctk.CTkFrame(pdf_card, fg_color="transparent")
    pdf_btns.grid(row=0, column=1, sticky="e", padx=20, pady=10)
    ctk.CTkButton(pdf_btns, text="Install PDF Library", font=("Segoe UI", 11, "bold"), fg_color="#3f3f46", hover_color="#52525b", text_color="#f4f4f5", command=lambda: install_pdf_library(log_message, root)).pack(side="left", padx=5)
    ctk.CTkButton(pdf_btns, text="Convert & Save PDF", font=("Segoe UI", 11, "bold"), fg_color="#3b82f6", hover_color="#2563eb", text_color="#ffffff", command=lambda: convert_and_save_pdf(log_message, root)).pack(side="left", padx=5)

    # ── Startup ──
    load_config(transcript_path_var, timestamps_path_var, output_dir_var)
    check_env_and_show_help(root)

    provider, endpoint, _, model = get_llm_config(ENV_PATH)
    log_message("System initialized.")
    log_message(f"LLM Config loaded from .env: {provider} / {model} @ {endpoint}")
    log_message("Select your files and click 'Start Pipeline' to begin.")

    root.mainloop()


if __name__ == "__main__":
    main()
