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
from tkinter import filedialog, messagebox

import customtkinter as ctk

from src.config import parse_env_file, get_llm_config
from src.llm_client import APP_VERSION
from src.pipeline import run_pipeline

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
    """On first run, if .env is missing or empty, copy .env.example and show help."""
    env = parse_env_file(ENV_PATH)
    if not env or not env.get("MODEL_NAME"):
        if not os.path.exists(ENV_PATH) and os.path.exists(ENV_EXAMPLE_PATH):
            try:
                shutil.copy2(ENV_EXAMPLE_PATH, ENV_PATH)
            except Exception:
                pass
        root.after(500, lambda: _show_env_help_popup(root))


def _show_env_help_popup(root):
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
        help_win, text="Config file location:",
        font=("Segoe UI", 11, "bold"), text_color="#f4f4f5"
    ).pack(padx=20, anchor="w")

    path_entry = ctk.CTkEntry(help_win, font=("Consolas", 10), width=560, state="normal")
    path_entry.pack(padx=20, pady=(2, 10), anchor="w")
    path_entry.insert(0, ENV_PATH)
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

    btn_frame = ctk.CTkFrame(help_win, fg_color="transparent")
    btn_frame.pack(pady=15, padx=20, fill="x")

    ctk.CTkButton(
        btn_frame, text="Open .env File", font=("Segoe UI", 11, "bold"),
        fg_color="#3f3f46", hover_color="#52525b",
        command=lambda: _open_path(ENV_PATH)
    ).pack(side="left", padx=(0, 10))

    ctk.CTkButton(
        btn_frame, text="Got it, close", font=("Segoe UI", 11, "bold"),
        fg_color="#3b82f6", hover_color="#2563eb", command=help_win.destroy
    ).pack(side="right")


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
            pdf = MarkdownPdf(toc_level=2, optimize=True)
            pdf.add_section(Section(md_content, toc=True))
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

    # ── Console log helper ──
    def log_message(msg):
        def _append():
            console_text.configure(state="normal")
            console_text.insert(tk.END, msg + "\n")
            console_text.see(tk.END)
            console_text.configure(state="disabled")
        root.after(0, _append)

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

        def on_progress(current, total):
            progress_bar.set(current / total if total else 0)

        def process():
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

    # Files card
    files_card = ctk.CTkFrame(top_container, corner_radius=12, border_width=1, border_color="#3f3f46")
    files_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

    ctk.CTkLabel(files_card, text="Files & Output Selection", font=("Segoe UI", 14, "bold"), text_color="#3b82f6").pack(anchor="w", padx=15, pady=(12, 8))

    files_grid = ctk.CTkFrame(files_card, fg_color="transparent")
    files_grid.pack(fill="x", padx=15, pady=5)
    files_grid.grid_columnconfigure(1, weight=1)

    for row_idx, (label_text, var, browse_fn) in enumerate([
        ("Transcript File:", transcript_path_var, browse_transcript),
        ("Timestamps File:", timestamps_path_var, browse_timestamps),
        ("Output Directory:", output_dir_var, browse_output_dir),
    ]):
        ctk.CTkLabel(files_grid, text=label_text, font=("Segoe UI", 11, "bold")).grid(row=row_idx, column=0, sticky="w", pady=6, padx=(0, 10))
        ctk.CTkEntry(files_grid, textvariable=var, font=("Segoe UI", 10), placeholder_text=f"Select {label_text.lower().replace(':', '...')}").grid(row=row_idx, column=1, sticky="we", pady=6, padx=5)
        ctk.CTkButton(files_grid, text="Browse", width=80, font=("Segoe UI", 10, "bold"), command=browse_fn).grid(row=row_idx, column=2, sticky="e", pady=6, padx=(5, 0))

    # Actions card
    actions_card = ctk.CTkFrame(top_container, corner_radius=12, border_width=1, border_color="#3f3f46")
    actions_card.grid(row=0, column=1, sticky="nsew")

    ctk.CTkLabel(actions_card, text="Pipeline Controls", font=("Segoe UI", 14, "bold"), text_color="#10b981").pack(anchor="w", padx=15, pady=(12, 8))

    actions_inner = ctk.CTkFrame(actions_card, fg_color="transparent")
    actions_inner.pack(fill="both", expand=True, padx=15, pady=(0, 15))

    ctk.CTkButton(
        actions_inner, text="Edit LLM Config (.env)",
        font=("Segoe UI", 11, "bold"), fg_color="#3f3f46", hover_color="#52525b", height=35,
        command=lambda: _open_path(ENV_PATH) if os.path.exists(ENV_PATH) else None
    ).pack(fill="x", pady=(10, 15))

    start_btn = ctk.CTkButton(
        actions_inner, text="Start Pipeline",
        font=("Segoe UI", 13, "bold"), fg_color="#10b981", hover_color="#059669",
        text_color="#ffffff", height=45, command=start_pipeline_thread
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
