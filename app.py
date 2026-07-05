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


def load_recent_outputs() -> list[str]:
    """Load the list of recently used output directories from config.json.
    
    Returns:
        list[str]: A list of recent directory paths.
    """
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("recent_outputs", [])
    except Exception:
        return []

def add_recent_output(path: str) -> None:
    """Add a new output directory path to the recent list in config.json.
    
    Args:
        path (str): The directory path to add.
    """
    if not path or not os.path.isdir(path):
        return
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    
    recents = data.get("recent_outputs", [])
    if path in recents:
        recents.remove(path)
    recents.insert(0, path)
    recents = recents[:5]
    data["recent_outputs"] = recents
    
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception:
        pass


def save_config(transcript_var, timestamps_var, output_var):
    """Persist file paths to config.json (no credentials stored here)."""
    data = {}
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
    except Exception:
        pass

    data["transcript_path"] = transcript_var.get().strip()
    data["timestamps_path"] = timestamps_var.get().strip()
    data["output_dir"] = output_var.get().strip()

    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception:
        pass


# ──────────────────────────── First-Run Help ───────────────────────────


def check_env_and_show_help(root):
    """On first run, check if credentials exist. If not, show setup dialog."""
    from src.credentials import has_stored_credentials
    
    if not has_stored_credentials():
        root.after(500, lambda: _show_env_help_popup(root))


def _show_env_help_popup(root):
    """Display an interactive dialog for secure API credential setup."""
    from src.credentials import store_provider_pool, get_provider_pool_or_legacy
    from src.provider_pool import ProviderConfig, ProviderPool

    help_win = ctk.CTkToplevel(root)
    help_win.title("API Configuration Setup")
    help_win.geometry("600x650")
    help_win.resizable(False, False)
    help_win.transient(root)
    help_win.grab_set()
    help_win.attributes("-topmost", True)

    ctk.CTkLabel(
        help_win, text="🔑 API Configuration Pool",
        font=("Segoe UI", 16, "bold"), text_color="#3b82f6"
    ).pack(pady=(20, 5), padx=20, anchor="w")

    pool = get_provider_pool_or_legacy()
    configs = pool.configs.copy()

    # Top Section: Pool Display
    pool_frame = ctk.CTkScrollableFrame(help_win, height=150)
    pool_frame.pack(fill="x", padx=20, pady=(0, 20))

    def refresh_pool_display():
        for widget in pool_frame.winfo_children():
            widget.destroy()
        
        for idx, config in enumerate(configs):
            row = ctk.CTkFrame(pool_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)
            
            k = config.api_key
            masked_key = (k[:8] + "...") if len(k) > 8 else ("*" * len(k)) if k else ""
            lbl_text = f"#{idx+1} {config.provider} | {config.model_name} | {masked_key}"
            
            ctk.CTkLabel(row, text=lbl_text, font=("Segoe UI", 12)).pack(side="left", padx=5)
            
            def remove_item(i=idx):
                configs.pop(i)
                refresh_pool_display()
                
            btn = ctk.CTkButton(
                row, text="Remove", width=60, height=24, fg_color="#ef4444",
                hover_color="#dc2626", command=remove_item
            )
            btn.pack(side="right", padx=5)

    refresh_pool_display()

    ctk.CTkLabel(
        help_win, text="── Add New Configuration ──",
        font=("Segoe UI", 14, "bold")
    ).pack(pady=(10, 10), padx=20, anchor="w")

    form_frame = ctk.CTkFrame(help_win, fg_color="transparent")
    form_frame.pack(fill="x", padx=20)

    # Variables
    provider_var = tk.StringVar(value="Gemini")
    endpoint_var = tk.StringVar(
        value="https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    )
    api_key_var = tk.StringVar()
    model_var = tk.StringVar(value="gemini-1.5-flash")

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
        elif prov == "Ollama (Local)":
            endpoint_var.set("http://localhost:11434")
            model_var.set("llama3")
            api_key_var.set("")
        elif prov == "Custom":
            endpoint_var.set("")
            model_var.set("")
            api_key_var.set("")

    provider_var.trace_add("write", on_provider_change)

    # Form Fields
    ctk.CTkLabel(form_frame, text="Provider:", font=("Segoe UI", 11, "bold")).grid(
        row=0, column=0, sticky="w", pady=8
    )
    provider_dropdown = ctk.CTkOptionMenu(
        form_frame, variable=provider_var, 
        values=["Gemini", "Groq", "OpenRouter", "Ollama (Local)", "Custom"]
    )
    provider_dropdown.grid(row=0, column=1, sticky="we", pady=8, padx=(10, 0))

    ctk.CTkLabel(form_frame, text="Endpoint URL:", font=("Segoe UI", 11, "bold")).grid(
        row=1, column=0, sticky="w", pady=8
    )
    ctk.CTkEntry(form_frame, textvariable=endpoint_var, width=300).grid(
        row=1, column=1, sticky="we", pady=8, padx=(10, 0)
    )

    ctk.CTkLabel(form_frame, text="Model Name:", font=("Segoe UI", 11, "bold")).grid(
        row=2, column=0, sticky="w", pady=8
    )
    ctk.CTkEntry(form_frame, textvariable=model_var, width=300).grid(
        row=2, column=1, sticky="we", pady=8, padx=(10, 0)
    )

    ctk.CTkLabel(form_frame, text="API Key:", font=("Segoe UI", 11, "bold")).grid(
        row=3, column=0, sticky="w", pady=8
    )
    ctk.CTkEntry(form_frame, textvariable=api_key_var, width=300).grid(
        row=3, column=1, sticky="we", pady=8, padx=(10, 0)
    )

    def add_to_pool():
        p = provider_var.get().strip()
        e = endpoint_var.get().strip()
        k = api_key_var.get().strip()
        m = model_var.get().strip()

        if not e or not m:
            messagebox.showerror("Error", "Endpoint and Model Name are required.", parent=help_win)
            return

        if not k and "Ollama" not in p:
            messagebox.showerror("Error", "API Key is required for remote providers.", parent=help_win)
            return

        configs.append(ProviderConfig(provider=p, endpoint_url=e, api_key=k, model_name=m))
        refresh_pool_display()
        
        # clear fields
        api_key_var.set("")

    ctk.CTkButton(
        form_frame, text="+ Add to Pool", font=("Segoe UI", 12, "bold"),
        fg_color="#3b82f6", hover_color="#2563eb",
        command=add_to_pool
    ).grid(row=4, column=1, sticky="e", pady=10)

    def save_and_close():
        new_pool = ProviderPool(configs)
        success = store_provider_pool(new_pool.to_json())
        if success:
            messagebox.showinfo("Success", "Pool saved securely!", parent=help_win)
            help_win.destroy()
        else:
            messagebox.showerror("Error", "Failed to save to system keyring.", parent=help_win)

    btn_frame = ctk.CTkFrame(help_win, fg_color="transparent")
    btn_frame.pack(pady=20, padx=20, fill="x")

    ctk.CTkButton(
        btn_frame, text="Save Pool", font=("Segoe UI", 13, "bold"),
        fg_color="#10b981", hover_color="#059669", height=40,
        command=save_and_close
    ).pack(fill="x")


# ───────────────────────── PDF Tooling Handlers ────────────────────────


def install_pdf_library(log_fn, root):
    """Install playwright, markdown, and pygments into the local .venv."""
    pip_path = os.path.join(SCRIPT_DIR, ".venv", "Scripts", "pip")
    python_path = os.path.join(SCRIPT_DIR, ".venv", "Scripts", "python")
    if os.path.exists(pip_path + ".exe"):
        pip_path += ".exe"
    if os.path.exists(python_path + ".exe"):
        python_path += ".exe"

    def run_install():
        log_fn("Running pip install playwright markdown pygments...")
        try:
            process1 = subprocess.Popen(
                [pip_path, "install", "playwright", "markdown", "pygments"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=False,
            )
            for line in process1.stdout:
                log_fn(line.strip())
            process1.wait()
            
            if process1.returncode != 0:
                log_fn(f"ERROR: Pip installation failed with exit code {process1.returncode}")
                root.after(0, lambda: messagebox.showerror("Error", f"Pip installation failed with exit code {process1.returncode}"))
                return

            log_fn("Installing chromium for playwright...")
            process2 = subprocess.Popen(
                [python_path, "-m", "playwright", "install", "chromium"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=False,
            )
            for line in process2.stdout:
                log_fn(line.strip())
            process2.wait()
            
            if process2.returncode == 0:
                log_fn("SUCCESS: Playwright installed successfully!")
                root.after(0, lambda: messagebox.showinfo("Success", "Playwright and dependencies installed successfully!"))
            else:
                log_fn(f"ERROR: Chromium installation failed with exit code {process2.returncode}")
                root.after(0, lambda: messagebox.showerror("Error", f"Chromium installation failed with exit code {process2.returncode}"))

        except Exception as e:
            log_fn(f"ERROR running install: {str(e)}")
            root.after(0, lambda: messagebox.showerror("Error", f"Failed to invoke install commands: {str(e)}"))

    threading.Thread(target=run_install, daemon=True).start()


def _is_playwright_ready() -> bool:
    """Check if Playwright and Chromium browser are installed and ready."""
    try:
        venv_site = os.path.join(SCRIPT_DIR, ".venv", "Lib", "site-packages")
        if os.path.exists(venv_site) and venv_site not in sys.path:
            sys.path.append(venv_site)
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            path = p.chromium.executable_path
            return os.path.exists(path)
    except Exception:
        return False


def _ensure_playwright_ready(log_fn, root) -> bool:
    """Check if Playwright is ready. If not, offer to auto-install.
    Returns True if ready, False if user declined or install failed."""
    if _is_playwright_ready():
        return True
    
    answer = messagebox.askyesno(
        "PDF Engine Not Installed",
        "The PDF engine (Playwright + Chromium) is not installed yet.\n\n"
        "Would you like to install it now? This is a one-time setup\n"
        "that downloads a small headless browser (~150MB).",
        parent=root,
    )
    if not answer:
        return False
    
    log_fn("Auto-installing Playwright PDF engine...")
    install_pdf_library(log_fn, root)
    return False  # Not ready yet — install is async, user should retry after


def _get_shared_pdf_css(theme="Textbook"):
    """Return the custom CSS used for both preview and export."""
    base_css = """
    body { font-family: 'Segoe UI', Helvetica, sans-serif; line-height: 1.5; }
    h1 { break-before: page; margin-top: 0; }
    h1:first-of-type { break-before: auto; }
    h1, h2, h3, h4, h5, h6 { break-after: avoid; }
    pre, blockquote, table, tr { break-inside: avoid; }
    table { width: 100%; border-collapse: collapse; margin: 1em 0; }
    @page { margin: 20mm; }
    """
    
    if theme == "Textbook":
        theme_css = """
        body { color: #1f2937; }
        h1 { color: #1e3a8a; font-size: 26pt; border-bottom: 3px solid #3b82f6; padding-bottom: 6px; }
        h2 { color: #2563eb; font-size: 18pt; border-bottom: 1px solid #d1d5db; padding-bottom: 4px; }
        h3 { color: #047857; font-size: 14pt; margin-top: 1.2em; }
        pre { background-color: #f8fafc; padding: 12px; border-left: 4px solid #94a3b8; font-family: 'Courier New', Courier, monospace; font-size: 10pt; white-space: pre-wrap; }
        code { background-color: #f1f5f9; color: #be123c; padding: 2px 5px; font-family: 'Courier New', Courier, monospace; }
        blockquote { border-left: 4px solid #3b82f6; background-color: #eff6ff; padding: 10px 15px; color: #4b5563; font-style: italic; }
        th { background-color: #e2e8f0; font-weight: bold; padding: 10px; border: 1px solid #cbd5e1; color: #0f172a; text-align: left; }
        td { padding: 10px; border: 1px solid #cbd5e1; }
        tr:nth-child(even) { background-color: #f8fafc; }
        a { color: #2563eb; text-decoration: none; }
        @media print { body { -webkit-print-color-adjust: exact; print-color-adjust: exact; } }
        """
    elif theme == "ChatGPT Dark":
        theme_css = """
        @page { margin: 0; }
        body { color: #ececf1; background-color: #212121; padding: 20mm; min-height: 100vh; box-sizing: border-box; }
        h1 { color: #ffffff; font-size: 24pt; border-bottom: 1px solid #4d4d4d; padding-bottom: 6px; }
        h2 { color: #f9f9f9; font-size: 18pt; border-bottom: 1px solid #3d3d3d; padding-bottom: 4px; }
        h3 { color: #b0b0b0; font-size: 14pt; margin-top: 1.2em; }
        pre { background-color: #0d0d0d; padding: 12px; border-left: 4px solid #10a37f; font-family: 'Courier New', Courier, monospace; font-size: 10pt; white-space: pre-wrap; color: #ececf1; }
        code { background-color: #2f2f2f; color: #fca5a5; padding: 2px 5px; font-family: 'Courier New', Courier, monospace; }
        blockquote { border-left: 4px solid #10a37f; background-color: #2f2f2f; padding: 10px 15px; color: #d1d1d6; font-style: italic; }
        th { background-color: #2f2f2f; font-weight: bold; padding: 10px; border: 1px solid #4d4d4d; color: #ffffff; text-align: left; }
        td { padding: 10px; border: 1px solid #4d4d4d; }
        tr:nth-child(even) { background-color: #2f2f2f; opacity: 0.8; }
        a { color: #10a37f; text-decoration: none; }
        @media print { 
            body { background-color: #212121 !important; color: #ececf1 !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; } 
            pre { background-color: #0d0d0d !important; color: #ececf1 !important; }
            blockquote { background-color: #2f2f2f !important; }
        }
        """
    else: # Minimal Mono
        theme_css = """
        body { font-family: 'Courier New', Courier, monospace; color: #000000; }
        h1, h2, h3 { color: #000000; text-transform: uppercase; border-bottom: 1px solid #000000; margin-top: 1.2em; }
        pre { background-color: #ffffff; padding: 12px; border: 1px solid #000000; white-space: pre-wrap; }
        code { font-weight: bold; }
        blockquote { border-left: 4px solid #000000; padding: 10px 15px; font-style: italic; }
        th, td { border: 1px solid #000000; padding: 10px; }
        """
        
    return base_css + theme_css

def convert_and_save_pdf(log_fn, root, theme="Textbook"):
    """Let the user pick a Markdown file and export it as PDF."""
    if not _ensure_playwright_ready(log_fn, root):
        return

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
            import asyncio
            asyncio.set_event_loop(asyncio.new_event_loop())
            
            venv_site = os.path.join(SCRIPT_DIR, ".venv", "Lib", "site-packages")
            if os.path.exists(venv_site) and venv_site not in sys.path:
                sys.path.append(venv_site)
            try:
                import markdown
                from playwright.sync_api import sync_playwright
            except ImportError:
                raise Exception("Playwright or Markdown is not available. Please install them by running: pip install playwright markdown pygments && playwright install chromium")

            with open(md_file, "r", encoding="utf-8", errors="replace") as f:
                md_content = f.read()

            html_content = markdown.markdown(md_content, extensions=['fenced_code', 'tables'])
            custom_css = _get_shared_pdf_css(theme)
            
            mermaid_script = """
            <script>
                document.querySelectorAll('code.language-mermaid').forEach(function(codeBlock) {
                    var pre = codeBlock.parentNode;
                    var div = document.createElement('div');
                    div.className = 'mermaid';
                    div.textContent = codeBlock.textContent;
                    pre.parentNode.replaceChild(div, pre);
                });
                mermaid.initialize({startOnLoad:true});
            </script>
            """
            
            full_html = (
                f"<html><head>"
                f"<style>{custom_css}</style>"
                f'<script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>'
                f"</head><body>{html_content}"
                f"{mermaid_script}"
                f"</body></html>"
            )

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.set_content(full_html)
                page.pdf(path=pdf_file, format="A4", print_background=True)
                browser.close()

            log_fn(f"SUCCESS: Saved PDF to {pdf_file}")
            root.after(0, lambda: messagebox.showinfo("Success", f"PDF saved successfully to:\n{pdf_file}"))
        except Exception as e:
            err_msg = str(e)
            log_fn(f"ERROR converting PDF: {err_msg}")
            root.after(0, lambda: messagebox.showerror("Error", f"Failed to convert PDF:\n{err_msg}"))

    threading.Thread(target=run_conversion, daemon=True).start()


def preview_pdf(log_fn, root, theme="Textbook"):
    """Render the PDF to a temporary file and open it for preview."""
    import tempfile
    
    if not _ensure_playwright_ready(log_fn, root):
        return

    md_file = filedialog.askopenfilename(
        title="Select Markdown File to Preview",
        filetypes=[("Markdown Files", "*.md"), ("All Files", "*.*")],
    )
    if not md_file:
        return

    log_fn(f"Generating preview for '{os.path.basename(md_file)}'...")

    def run_preview():
        try:
            import asyncio
            asyncio.set_event_loop(asyncio.new_event_loop())
            
            venv_site = os.path.join(SCRIPT_DIR, ".venv", "Lib", "site-packages")
            if os.path.exists(venv_site) and venv_site not in sys.path:
                sys.path.append(venv_site)
            try:
                import markdown
                from playwright.sync_api import sync_playwright
            except ImportError:
                raise Exception("Playwright or Markdown is not available. Please install them by running: pip install playwright markdown pygments && playwright install chromium")

            with open(md_file, "r", encoding="utf-8", errors="replace") as f:
                md_content = f.read()

            html_content = markdown.markdown(md_content, extensions=['fenced_code', 'tables'])
            custom_css = _get_shared_pdf_css(theme)
            
            mermaid_script = """
            <script>
                document.querySelectorAll('code.language-mermaid').forEach(function(codeBlock) {
                    var pre = codeBlock.parentNode;
                    var div = document.createElement('div');
                    div.className = 'mermaid';
                    div.textContent = codeBlock.textContent;
                    pre.parentNode.replaceChild(div, pre);
                });
                mermaid.initialize({startOnLoad:true});
            </script>
            """
            
            full_html = (
                f"<html><head>"
                f"<style>{custom_css}</style>"
                f'<script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>'
                f"</head><body>{html_content}"
                f"{mermaid_script}"
                f"</body></html>"
            )

            temp_pdf = os.path.join(tempfile.gettempdir(), "yt_transcriptor_preview.pdf")

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.set_content(full_html)
                page.pdf(path=temp_pdf, format="A4", print_background=True)
                browser.close()

            log_fn("SUCCESS: Preview generated. Opening...")
            _open_path(temp_pdf)
        except Exception as e:
            err_msg = str(e)
            log_fn(f"ERROR generating preview: {err_msg}")
            root.after(0, lambda: messagebox.showerror("Error", f"Failed to generate preview:\n{err_msg}"))

    threading.Thread(target=run_preview, daemon=True).start()


# ═══════════════════════════════════════════════════════════════════════
#  MAIN APPLICATION (only runs when executed directly)
# ═══════════════════════════════════════════════════════════════════════

def main():
    # ── Theme ──
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    root.title(f"YouTube Transcript to Notes Pipeline v{APP_VERSION}")
    root.geometry("1200x900")
    root.minsize(1050, 900)

    # ── Global state ──
    cancel_event = threading.Event()
    transcript_path_var = tk.StringVar()
    timestamps_path_var = tk.StringVar()
    output_dir_var = tk.StringVar()
    youtube_url_var = tk.StringVar()
    topic_title_var = tk.StringVar()
    pdf_theme_var = tk.StringVar(value="Textbook")
    multimodal_var = tk.BooleanVar(value=False)
    kag_var = tk.BooleanVar(value=False)

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
    def start_unified_pipeline():
        active = input_tabs.get()
        output_dir = output_dir_var.get().strip()
        
        try:
            from src.credentials import get_provider_pool_or_legacy
            pool = get_provider_pool_or_legacy()
            if pool.total == 0:
                raise ValueError("Incomplete credentials")
        except Exception:
            messagebox.showerror(
                "Missing Credentials",
                "No API configurations found. Please add at least one in API Setup.",
                parent=root,
            )
            _show_env_help_popup(root)
            return
        if not output_dir or not os.path.isdir(output_dir):
            messagebox.showerror("Validation Error", "Please provide a valid output directory.")
            return

        if active == "YouTube URL":
            url = youtube_url_var.get().strip()
            if not url:
                messagebox.showerror("Validation Error", "Please paste a YouTube URL.")
                return
            if multimodal_var.get():
                ans = messagebox.askyesno(
                    "Bandwidth Warning", 
                    "Extracting video frames requires downloading the video.\nThis can use 50-200MB of bandwidth.\n\nDo you want to proceed?",
                    parent=root
                )
                if not ans:
                    return
        else:
            save_config(transcript_path_var, timestamps_path_var, output_dir_var)
            transcript_path = transcript_path_var.get().strip()
            timestamps_path = timestamps_path_var.get().strip()
            if not transcript_path or not os.path.exists(transcript_path):
                messagebox.showerror("Validation Error", "Please provide a valid transcript file path.")
                return
            if not timestamps_path or not os.path.exists(timestamps_path):
                messagebox.showerror("Validation Error", "Please provide a valid timestamps file path.")
                return
            if not topic_title_var.get().strip():
                messagebox.showerror("Validation Error", "Please provide a Topic / Title.")
                return

        cancel_event.clear()
        start_btn.pack_forget()
        cancel_btn.configure(state="normal", text="Cancel Pipeline")
        cancel_btn.pack(fill="x", side="bottom")
        status_label.configure(text="Status: Running...", text_color="#fbbf24")
        status_pill.configure(fg_color="#fbbf24")
        
        export_pdf_btn.pack_forget()
        pdf_theme_menu.pack_forget()

        progress_bar.configure(mode="indeterminate")
        progress_bar.start()
        step_label.configure(text="Initializing pipeline...")

        def on_progress(current, total):
            def _update():
                progress_bar.stop()
                progress_bar.configure(mode="determinate")
                progress_bar.set(current / total if total else 0)
                if total > 0:
                    step_label.configure(text=f"Step {current} of {total}...")
                if current < total:
                    root.after(1000, lambda: (progress_bar.configure(mode="indeterminate"), progress_bar.start()) if status_label.cget("text") == "Status: Running..." else None)
            root.after(0, _update)

        def process():
            log_message(f"Loaded {pool.total} API config(s) from keyring.")
            result = None
            try:
                if active == "YouTube URL":
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

                    log_message("Extraction complete. Starting LLM pipeline...")

                    result = run_pipeline_from_data(
                        transcript_blocks=data['transcript_blocks'],
                        chapters=data['chapters'],
                        output_dir=output_dir,
                        pool=pool,
                        cancel_event=cancel_event,
                        on_log=log_message,
                        on_progress=on_progress,
                        video_title=data.get('metadata', {}).get('title'),
                        enable_multimodal=multimodal_var.get(),
                        youtube_url=url,
                        enable_kag=kag_var.get(),
                    )
                else:
                    result = run_pipeline(
                        transcript_path=transcript_path,
                        timestamps_path=timestamps_path,
                        output_dir=output_dir,
                        pool=pool,
                        cancel_event=cancel_event,
                        on_log=log_message,
                        on_progress=on_progress,
                        video_title=topic_title_var.get().strip(),
                        enable_kag=kag_var.get(),
                    )
                
                if result["success"]:
                    root.after(0, lambda: progress_bar.set(1.0))
                    root.after(0, lambda: messagebox.showinfo(
                        "Success",
                        f"Processing completed successfully!\nNotes generated in:\n{output_dir}"
                    ))
                elif result.get("error"):
                    root.after(0, lambda: messagebox.showerror("Pipeline Error", result["error"]))
            except ImportError as e:
                if active == "YouTube URL" and ("youtube" in str(e) or "yt" in str(e)):
                    log_message("ERROR: youtube-transcript-api or yt-dlp not installed.")
                    log_message("Run: .venv\\Scripts\\pip install youtube-transcript-api yt-dlp")
                    root.after(0, lambda: messagebox.showerror(
                        "Missing Libraries",
                        "youtube-transcript-api and yt-dlp are required.\n\n"
                        "Run in terminal:\n.venv\\Scripts\\pip install youtube-transcript-api yt-dlp"
                    ))
                else:
                    log_message(f"CRITICAL ERROR: {str(e)}")
                    root.after(0, lambda: messagebox.showerror("Pipeline Error", str(e)))
            except Exception as e:
                log_message(f"CRITICAL ERROR: {str(e)}")
                root.after(0, lambda: messagebox.showerror("Pipeline Error", str(e)))
            finally:
                def restore_ui():
                    progress_bar.stop()
                    progress_bar.configure(mode="determinate")
                    cancel_btn.pack_forget()
                    start_btn.pack(fill="x", side="bottom")
                    if cancel_event.is_set():
                        status_label.configure(text="Status: Cancelled", text_color="#ef4444")
                        status_pill.configure(fg_color="#ef4444")
                        progress_bar.set(0)
                        step_label.configure(text="")
                    elif result and result.get("success"):
                        add_recent_output(output_dir)
                        try:
                            refresh_history()
                        except NameError:
                            pass
                        status_label.configure(text="Status: Completed ✅", text_color="#10b981")
                        status_pill.configure(fg_color="#10b981")
                        progress_bar.set(1.0)
                        step_label.configure(text="Done.")
                        pdf_theme_menu.pack(fill="x", pady=(5, 0))
                        export_pdf_btn.pack(fill="x", pady=(5, 0))
                        kag_path = result.get("kag_html_path")
                        if kag_path and os.path.exists(kag_path):
                            open_kag_btn.configure(
                                command=lambda p=kag_path: _open_path(p)
                            )
                            open_kag_btn.pack(fill="x", pady=(5, 0))
                    else:
                        status_label.configure(text="Status: Error", text_color="#ef4444")
                        status_pill.configure(fg_color="#ef4444")
                        progress_bar.set(0)
                        step_label.configure(text="Error occurred.")
                root.after(0, restore_ui)

        threading.Thread(target=process, daemon=True).start()

    def cancel_pipeline():
        if messagebox.askyesno("Confirm Cancel", "Are you sure you want to cancel the pipeline?"):
            log_message("Cancel requested. Waiting for current chapter to finish...")
            cancel_btn.configure(state="disabled", text="Cancelling...")
            cancel_event.set()

    # ─────────────────────── UI LAYOUT ───────────────────────

    CARD_RADIUS = 12
    PAD = 20

    root.grid_columnconfigure(0, weight=1)
    root.grid_rowconfigure(0, weight=0)    # Header
    root.grid_rowconfigure(1, weight=0)    # Top panel (Files & Actions)
    root.grid_rowconfigure(2, weight=0)    # Progress bar
    root.grid_rowconfigure(3, weight=1)    # Console area (expanding)

    # ── Header ──
    header_frame = ctk.CTkFrame(root, fg_color="transparent")
    header_frame.grid(row=0, column=0, sticky="ew", padx=PAD, pady=(15, 5))

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
    top_container.grid(row=1, column=0, sticky="ew", padx=PAD, pady=(0, 5))
    top_container.grid_columnconfigure(0, weight=3)
    top_container.grid_columnconfigure(1, weight=1)
    top_container.grid_rowconfigure(0, weight=1)

    # Input card with tabs
    input_card = ctk.CTkFrame(top_container, corner_radius=CARD_RADIUS, border_width=1, border_color="#3f3f46")
    input_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

    def validate_inputs(*args):
        active = input_tabs.get()
        valid = False
        out = output_dir_var.get().strip()
        if active == "YouTube URL":
            yt = youtube_url_var.get().strip()
            if yt and out:
                valid = True
        else:
            tr = transcript_path_var.get().strip()
            ts = timestamps_path_var.get().strip()
            title = topic_title_var.get().strip()
            if tr and ts and out and title:
                valid = True
        
        try:
            if valid:
                start_btn.configure(state="normal")
            else:
                start_btn.configure(state="disabled")
        except NameError:
            pass

    youtube_url_var.trace_add("write", validate_inputs)
    output_dir_var.trace_add("write", validate_inputs)
    transcript_path_var.trace_add("write", validate_inputs)
    timestamps_path_var.trace_add("write", validate_inputs)
    topic_title_var.trace_add("write", validate_inputs)

    input_tabs = ctk.CTkTabview(input_card, corner_radius=10, height=300,
                                 segmented_button_fg_color="#27272a",
                                 segmented_button_selected_color="#3b82f6",
                                 segmented_button_selected_hover_color="#2563eb",
                                 command=validate_inputs)
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
                  
    ctk.CTkCheckBox(
        yt_tab, text="Extract Video Frames (Multimodal)",
        variable=multimodal_var, font=("Segoe UI", 11)
    ).grid(row=5, column=0, columnspan=2, sticky="w", padx=5, pady=(10, 0))

    ctk.CTkCheckBox(
        yt_tab, text="Generate Knowledge Graph (KAG)",
        variable=kag_var, font=("Segoe UI", 11)
    ).grid(row=6, column=0, columnspan=2, sticky="w", padx=5, pady=(10, 0))

    # ── Manual Files Tab ──
    files_tab = input_tabs.add("Manual Files")
    files_tab.grid_columnconfigure(1, weight=1)

    for row_idx, (label_text, var, browse_fn) in enumerate([
        ("Topic / Title:", topic_title_var, None),
        ("Transcript File:", transcript_path_var, browse_transcript),
        ("Timestamps File:", timestamps_path_var, browse_timestamps),
        ("Output Directory:", output_dir_var, browse_output_dir),
    ]):
        ctk.CTkLabel(files_tab, text=label_text, font=("Segoe UI", 11, "bold")).grid(row=row_idx, column=0, sticky="w", pady=6, padx=(5, 10))
        placeholder = f"Enter {label_text.lower().replace(':', '')}..." if not browse_fn else f"Select {label_text.lower().replace(':', '')}..."
        ctk.CTkEntry(files_tab, textvariable=var, font=("Segoe UI", 10), placeholder_text=placeholder).grid(row=row_idx, column=1, sticky="we", pady=6, padx=5)
        if browse_fn:
            ctk.CTkButton(files_tab, text="Browse", width=80, font=("Segoe UI", 10, "bold"), command=browse_fn).grid(row=row_idx, column=2, sticky="e", pady=6, padx=(5, 5))

    ctk.CTkCheckBox(
        files_tab, text="Generate Knowledge Graph (KAG)",
        variable=kag_var, font=("Segoe UI", 11)
    ).grid(row=4, column=0, columnspan=3, sticky="w", padx=5, pady=(10, 0))

    # ── PDF Tools Tab ──
    pdf_tab = input_tabs.add("PDF Tools")
    pdf_tab.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(pdf_tab, text="Convert any standalone Markdown file to PDF.",
                 font=("Segoe UI", 10), text_color="#a1a1aa").grid(row=0, column=0, columnspan=2, sticky="w", padx=5, pady=(5, 8))

    ctk.CTkLabel(pdf_tab, text="PDF Theme:", font=("Segoe UI", 11, "bold")).grid(row=1, column=0, sticky="w", padx=5, pady=4)
    
    ctk.CTkOptionMenu(
        pdf_tab, variable=pdf_theme_var,
        values=["Textbook", "Minimal Mono", "ChatGPT Dark"],
        font=("Segoe UI", 11)
    ).grid(row=1, column=1, sticky="w", padx=5, pady=4)

    pdf_btns_frame = ctk.CTkFrame(pdf_tab, fg_color="transparent")
    pdf_btns_frame.grid(row=2, column=0, columnspan=2, sticky="we", padx=5, pady=(15, 0))
    pdf_btns_frame.grid_columnconfigure(0, weight=1)
    pdf_btns_frame.grid_columnconfigure(1, weight=1)

    ctk.CTkButton(
        pdf_btns_frame, text="Preview PDF",
        font=("Segoe UI", 11, "bold"), fg_color="#3f3f46", hover_color="#52525b",
        command=lambda: preview_pdf(log_message, root, theme=pdf_theme_var.get())
    ).grid(row=0, column=0, sticky="we", padx=(0, 5))

    ctk.CTkButton(
        pdf_btns_frame, text="Export to PDF",
        font=("Segoe UI", 11, "bold"), fg_color="#3b82f6", hover_color="#2563eb",
        command=lambda: convert_and_save_pdf(log_message, root, theme=pdf_theme_var.get())
    ).grid(row=0, column=1, sticky="we", padx=(5, 0))

    # Add quick install helper link/button directly under PDF buttons
    ctk.CTkButton(
        pdf_tab, text="Click here to Install/Verify PDF Engine (Playwright Chromium)",
        font=("Segoe UI", 9, "underline"), fg_color="transparent", hover_color="#27272a",
        text_color="#a1a1aa", height=20,
        command=lambda: install_pdf_library(log_message, root)
    ).grid(row=3, column=0, columnspan=2, sticky="w", padx=5, pady=(10, 0))

    # ── Local Chat Tab ──
    chat_tab = input_tabs.add("Local Chat")
    chat_tab.grid_columnconfigure(1, weight=1)
    chat_tab.grid_rowconfigure(3, weight=1)
    
    ctk.CTkLabel(
        chat_tab, text="Chat with all generated notes in a folder using Ollama.",
        font=("Segoe UI", 10), text_color="#a1a1aa"
    ).grid(row=0, column=0, columnspan=3, sticky="w", padx=5, pady=(5, 8))
    
    chat_folder_var = tk.StringVar(value="")
    
    def browse_chat_folder():
        d = filedialog.askdirectory(title="Select Generated Notes Folder")
        if d:
            chat_folder_var.set(d)
            
    ctk.CTkButton(
        chat_tab, text="Browse Folder", width=100, font=("Segoe UI", 10, "bold"),
        command=browse_chat_folder
    ).grid(row=1, column=0, sticky="w", padx=(5, 5), pady=4)
    
    ctk.CTkEntry(
        chat_tab, textvariable=chat_folder_var, font=("Segoe UI", 10),
        placeholder_text="Select folder with .md notes..."
    ).grid(row=1, column=1, sticky="we", padx=5, pady=4)
    
    chat_model_var = tk.StringVar(value="llama3")
    chat_model_dropdown = ctk.CTkOptionMenu(
        chat_tab, variable=chat_model_var, values=["llama3", "phi3", "mistral", "gemma"], width=100, font=("Segoe UI", 11)
    )
    chat_model_dropdown.grid(row=1, column=2, sticky="e", padx=(5, 5), pady=4)
    
    chat_log = ctk.CTkTextbox(
        chat_tab, height=80, state="disabled", wrap="word", font=("Segoe UI", 11)
    )
    chat_log.grid(row=3, column=0, columnspan=3, sticky="nsew", padx=5, pady=4)
    
    chat_input = ctk.CTkEntry(
        chat_tab, font=("Segoe UI", 11), placeholder_text="Ask a question..."
    )
    chat_input.grid(row=4, column=0, columnspan=2, sticky="we", padx=(5, 5), pady=4)
    
    chat_state = {"session": None}
    
    def clear_chat(*args):
        chat_state["session"] = None
        chat_log.configure(state="normal")
        chat_log.delete("1.0", "end")
        chat_log.configure(state="disabled")
        
    chat_folder_var.trace_add("write", clear_chat)
    chat_model_var.trace_add("write", clear_chat)

    def send_chat_message(*args):
        user_msg = chat_input.get().strip()
        if not user_msg: return
        
        folder = chat_folder_var.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showerror("Error", "Please select a valid folder.", parent=root)
            return
            
        chat_input.delete(0, 'end')
        chat_log.configure(state="normal")
        chat_log.insert('end', f"You: {user_msg}\n")
        chat_log.see('end')
        chat_log.configure(state="disabled")
        
        chat_btn.configure(state="disabled")
        chat_input.configure(state="disabled")
        clear_btn.configure(state="disabled")
        
        def run_chat():
            from src.chat import ChatSession
            try:
                if chat_state["session"] is None or chat_state["session"].folder_path != folder or chat_state["session"].model_name != chat_model_var.get():
                    chat_state["session"] = ChatSession(folder, chat_model_var.get())
                
                response = chat_state["session"].chat(user_msg)
                
                def update_ui():
                    chat_log.configure(state="normal")
                    chat_log.insert('end', f"AI: {response}\n\n")
                    chat_log.see('end')
                    chat_log.configure(state="disabled")
                    chat_btn.configure(state="normal")
                    chat_input.configure(state="normal")
                    clear_btn.configure(state="normal")
                
                root.after(0, update_ui)
            except Exception as e:
                def show_err():
                    chat_log.configure(state="normal")
                    chat_log.insert('end', f"Error: {str(e)}\n\n")
                    chat_log.see('end')
                    chat_log.configure(state="disabled")
                    chat_btn.configure(state="normal")
                    chat_input.configure(state="normal")
                    clear_btn.configure(state="normal")
                root.after(0, show_err)
                
        threading.Thread(target=run_chat, daemon=True).start()
        
    btn_frame = ctk.CTkFrame(chat_tab, fg_color="transparent")
    btn_frame.grid(row=4, column=2, sticky="e", padx=(0, 5), pady=4)
    
    clear_btn = ctk.CTkButton(
        btn_frame, text="Clear Chat", width=60, fg_color="#ef4444", hover_color="#dc2626",
        font=("Segoe UI", 11, "bold"), command=clear_chat
    )
    clear_btn.pack(side="left", padx=(0, 5))

    chat_btn = ctk.CTkButton(
        btn_frame, text="Send", width=60,
        font=("Segoe UI", 11, "bold"), command=send_chat_message
    )
    chat_btn.pack(side="left")
    
    chat_input.bind("<Return>", send_chat_message)

    input_tabs.set("YouTube URL")  # Default to YouTube tab

    # Actions card
    actions_card = ctk.CTkFrame(top_container, corner_radius=CARD_RADIUS, border_width=1, border_color="#3f3f46")
    actions_card.grid(row=0, column=1, sticky="nsew")

    ctk.CTkLabel(actions_card, text="Pipeline Controls", font=("Segoe UI", 14, "bold"), text_color="#10b981").pack(anchor="w", padx=15, pady=(12, 8))

    actions_inner = ctk.CTkFrame(actions_card, fg_color="transparent")
    actions_inner.pack(fill="both", expand=True, padx=15, pady=(0, 15))

    # Status indicator
    status_frame = ctk.CTkFrame(actions_inner, fg_color="transparent")
    status_frame.pack(anchor="w", pady=(5, 5))
    
    status_pill = ctk.CTkFrame(status_frame, width=10, height=10, corner_radius=5, fg_color="#9ca3af")
    status_pill.pack(side="left", padx=(0, 5))
    
    status_label = ctk.CTkLabel(
        status_frame, text="Status: Ready",
        font=("Segoe UI", 10), text_color="#a1a1aa"
    )
    status_label.pack(side="left")

    ctk.CTkButton(
        actions_inner, text="API Setup / Credentials",
        font=("Segoe UI", 11, "bold"), fg_color="#3f3f46", hover_color="#52525b", height=35,
        command=lambda: _show_env_help_popup(root)
    ).pack(fill="x", pady=(5, 5))

    ctk.CTkButton(
        actions_inner, text="🛠️ Install PDF Engine",
        font=("Segoe UI", 11, "bold"), fg_color="#3f3f46", hover_color="#52525b", height=35,
        command=lambda: install_pdf_library(log_message, root)
    ).pack(fill="x", pady=(0, 5))

    open_output_btn = ctk.CTkButton(
        actions_inner, text="Open Output Folder",
        font=("Segoe UI", 11, "bold"), fg_color="#3f3f46", hover_color="#52525b", height=35,
        command=lambda: _open_path(output_dir_var.get().strip()) if output_dir_var.get().strip() else None
    )
    open_output_btn.pack(fill="x", pady=(0, 5))

    # ── Recents Popup Button ──
    def show_recents_popup():
        recents = load_recent_outputs()
        popup = ctk.CTkToplevel(root)
        popup.title("Recent Generations")
        popup.geometry("450x300")
        popup.transient(root)
        popup.grab_set()
        popup.attributes("-topmost", True)

        ctk.CTkLabel(popup, text="Recent Output Folders", font=("Segoe UI", 14, "bold"),
                     text_color="#3b82f6").pack(anchor="w", padx=15, pady=(15, 10))

        if not recents:
            ctk.CTkLabel(popup, text="No recent outputs yet.", font=("Segoe UI", 11, "italic"),
                         text_color="#71717a").pack(anchor="w", padx=15, pady=10)
        else:
            scroll = ctk.CTkScrollableFrame(popup, fg_color="transparent")
            scroll.pack(fill="both", expand=True, padx=10, pady=(0, 10))
            for path in recents:
                ctk.CTkButton(
                    scroll, text=os.path.basename(path) or path,
                    anchor="w", fg_color="#27272a", hover_color="#3f3f46",
                    text_color="#60a5fa", height=30, font=("Segoe UI", 11),
                    command=lambda p=path: (_open_path(p), popup.destroy())
                ).pack(fill="x", padx=5, pady=3)

        ctk.CTkButton(popup, text="Close", font=("Segoe UI", 11, "bold"),
                      fg_color="#3f3f46", hover_color="#52525b", height=30,
                      command=popup.destroy).pack(pady=(5, 15))

    ctk.CTkButton(
        actions_inner, text="📁 Recent Generations",
        font=("Segoe UI", 11, "bold"), fg_color="#3f3f46", hover_color="#52525b", height=35,
        command=show_recents_popup
    ).pack(fill="x", pady=(0, 5))

    pdf_theme_menu = ctk.CTkOptionMenu(
        actions_inner, variable=pdf_theme_var,
        values=["Textbook", "Minimal Mono", "ChatGPT Dark"],
        font=("Segoe UI", 11)
    )

    export_pdf_btn = ctk.CTkButton(
        actions_inner, text="Export to PDF",
        font=("Segoe UI", 11, "bold"), fg_color="#3b82f6", hover_color="#2563eb", height=35,
        command=lambda: convert_and_save_pdf(log_message, root, theme=pdf_theme_var.get())
    )

    open_kag_btn = ctk.CTkButton(
        actions_inner, text="Open Knowledge Graph",
        font=("Segoe UI", 11, "bold"), fg_color="#8b5cf6", hover_color="#7c3aed", height=35
    )

    start_btn = ctk.CTkButton(
        actions_inner, text="Start Pipeline",
        font=("Segoe UI", 13, "bold"), fg_color="#10b981", hover_color="#059669",
        text_color="#ffffff", height=45, command=start_unified_pipeline, state="disabled"
    )
    start_btn.pack(fill="x", side="bottom")

    cancel_btn = ctk.CTkButton(
        actions_inner, text="Cancel Pipeline",
        font=("Segoe UI", 13, "bold"), fg_color="#ef4444", hover_color="#dc2626",
        text_color="#ffffff", height=45, command=cancel_pipeline
    )

    # ── Progress Bar ──
    progress_frame = ctk.CTkFrame(root, fg_color="transparent")
    progress_frame.grid(row=2, column=0, sticky="ew", padx=PAD, pady=(0, 5))
    progress_frame.grid_columnconfigure(0, weight=1)
    
    step_label = ctk.CTkLabel(progress_frame, text="", font=("Segoe UI", 10), text_color="#a1a1aa")
    step_label.pack(anchor="w")
    
    progress_bar = ctk.CTkProgressBar(progress_frame, height=6, corner_radius=3, progress_color="#10b981")
    progress_bar.pack(fill="x", pady=(2, 0))
    progress_bar.set(0)

    # ── Console ──
    console_card = ctk.CTkFrame(root, corner_radius=CARD_RADIUS, border_width=1, border_color="#3f3f46")
    console_card.grid(row=3, column=0, sticky="nsew", padx=PAD, pady=5)

    console_header = ctk.CTkFrame(console_card, fg_color="transparent")
    console_header.pack(fill="x", padx=15, pady=(12, 8))

    ctk.CTkLabel(console_header, text="Console Output", font=("Segoe UI", 14, "bold"), text_color="#3b82f6").pack(side="left")

    def toggle_console():
        if console_text.winfo_ismapped():
            console_text.pack_forget()
            toggle_btn.configure(text="Show Details")
        else:
            console_text.pack(fill="both", expand=True, padx=15, pady=(0, 15))
            toggle_btn.configure(text="Hide Details")

    toggle_btn = ctk.CTkButton(
        console_header, text="Hide Details", width=80, height=26,
        font=("Segoe UI", 10, "bold"), fg_color="#3f3f46", hover_color="#52525b",
        command=toggle_console
    )
    toggle_btn.pack(side="right", padx=(5, 0))

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

    # ── Startup ──
    load_config(transcript_path_var, timestamps_path_var, output_dir_var)
    check_env_and_show_help(root)

    try:
        from src.credentials import get_llm_config_from_keyring, has_stored_credentials
        if has_stored_credentials():
            provider, endpoint, _, model = get_llm_config_from_keyring()
            config_source = "keyring"
        else:
            raise ValueError("No keyring credentials")
    except Exception:
        provider, endpoint, _, model = get_llm_config(ENV_PATH)
        config_source = ".env"
    log_message("System initialized.")
    log_message(f"LLM Config loaded from {config_source}: {provider} / {model} @ {endpoint}")
    log_message("Select your files and click 'Start Pipeline' to begin.")
    
    validate_inputs()

    root.mainloop()


if __name__ == "__main__":
    main()
