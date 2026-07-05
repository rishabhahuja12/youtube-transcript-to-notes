#!/usr/bin/env python3
"""YouTube Transcript to Notes Pipeline — Desktop GUI Layer.

This module implements the CustomTkinter desktop GUI featuring a left sidebar
navigation shell (Library, New Pipeline, Settings), a course workspace view
with 5 sub-tabs (Notes, Chat, Graph, PDF, Keyframes), persistent status/dock,
and full integration with backend pipeline modules.
"""

import json
import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from tkinter import filedialog, messagebox

import customtkinter as ctk

from src.chat import ChatSession
from src.config import get_llm_config, parse_env_file
from src.credentials import (
    get_llm_config_from_keyring,
    get_provider_pool_or_legacy,
    has_stored_credentials,
    store_provider_pool,
)
from src.llm_client import APP_VERSION
from src.pipeline import run_pipeline, run_pipeline_from_data
from src.provider_pool import ProviderConfig, ProviderPool

# ─────────────────────────── Design Tokens ───────────────────────────

BG_COLOR = "#0b0f19"
CARD_BG = "#161e2e"
SIDEBAR_BG = "#0f172a"
BORDER_COLOR = "#1f293d"
ACCENT_COLOR = "#6366f1"
ACCENT_HOVER = "#4f46e5"
TEXT_COLOR = "#f4f4f5"
TEXT_MUTED = "#9ca3af"
SUCCESS_COLOR = "#10b981"
WARNING_COLOR = "#fbbf24"
ERROR_COLOR = "#ef4444"
CARD_RADIUS = 12

# ─────────────────────────── Path Resolution ───────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(SCRIPT_DIR, ".env")
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")


def _open_path(path: str) -> None:
    """Open a file or directory with the OS default handler.

    Args:
        path (str): File or directory path to open.
    """
    try:
        os.startfile(path)
    except Exception:
        pass


def check_ollama_status() -> bool:
    """Check if the local Ollama server is running on localhost:11434.

    Returns:
        bool: True if Ollama responds, False otherwise.
    """
    try:
        req = urllib.request.urlopen("http://localhost:11434", timeout=2)
        return req.getcode() == 200
    except Exception:
        return False


# ─────────────────────── Configuration Persistence ─────────────────────


def load_recent_outputs() -> List[str]:
    """Load the list of recently used output directories from config.json.

    Returns:
        List[str]: List of directory paths.
    """
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("recent_outputs", [])
        except Exception:
            return []
    return []


def add_recent_output(path: str) -> None:
    """Add an output directory path to the recent list in config.json.

    Args:
        path (str): The directory path to store.
    """
    if not path or not os.path.isdir(path):
        return
    data: Dict[str, Any] = {}
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
    except Exception:
        data = {}

    recents = data.get("recent_outputs", [])
    if path in recents:
        recents.remove(path)
    recents.insert(0, path)
    recents = recents[:10]
    data["recent_outputs"] = recents

    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception:
        pass


def get_powerup_time_hint(feature: str, video_duration_sec: int = 600) -> str:
    """Calculate dynamic estimated time addition for power-up engines.

    Args:
        feature (str): Feature identifier ("vision", "kag", or "pdf").
        video_duration_sec (int, optional): Video duration in seconds. Defaults to 600.

    Returns:
        str: Formatted time estimate hint string (e.g. "+ ~35s").
    """
    if feature == "vision":
        est = max(15, int(35 * (video_duration_sec / 600)))
        return f"+ ~{est}s"
    elif feature == "kag":
        est = max(10, int(15 * (video_duration_sec / 600)))
        return f"+ ~{est}s"
    elif feature == "pdf":
        return "+ ~5s"
    return "+ 0s"



# ──────────────────────────── Setup Popup ───────────────────────────


def check_env_and_show_help(root: ctk.CTk) -> None:
    """Check credentials on launch; prompt setup dialog if missing.

    Args:
        root (ctk.CTk): Main application root window.
    """
    if not has_stored_credentials():
        root.after(500, lambda: _show_env_help_popup(root))


def _show_env_help_popup(root: ctk.CTk) -> None:
    """Display an interactive dialog for API credential management.

    Args:
        root (ctk.CTk): Parent root window.
    """
    help_win = ctk.CTkToplevel(root)
    help_win.title("API Configuration Vault")
    help_win.geometry("680x760")
    help_win.resizable(False, False)
    help_win.transient(root)
    help_win.grab_set()
    help_win.attributes("-topmost", True)

    ctk.CTkLabel(
        help_win,
        text="🔑 API Configuration Vault",
        font=("Segoe UI", 16, "bold"),
        text_color=ACCENT_COLOR,
    ).pack(pady=(20, 5), padx=20, anchor="w")

    pool = get_provider_pool_or_legacy()
    configs = pool.configs.copy()

    tabview = ctk.CTkTabview(help_win, height=220)
    tabview.pack(fill="x", padx=20, pady=(0, 15))

    text_tab = tabview.add("Text Models")
    vision_tab = tabview.add("Vision Models")

    pool_frame_text = ctk.CTkScrollableFrame(text_tab, height=140)
    pool_frame_text.pack(fill="both", expand=True, padx=5, pady=5)

    pool_frame_vision = ctk.CTkScrollableFrame(vision_tab, height=140)
    pool_frame_vision.pack(fill="both", expand=True, padx=5, pady=5)

    def refresh_pool_display() -> None:
        for widget in pool_frame_text.winfo_children():
            widget.destroy()
        for widget in pool_frame_vision.winfo_children():
            widget.destroy()

        for idx, config in enumerate(configs):
            is_vision = getattr(config, "capability", "text") == "vision"
            parent_frame = pool_frame_vision if is_vision else pool_frame_text
            row = ctk.CTkFrame(parent_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)

            k = config.api_key
            masked_key = (k[:8] + "...") if len(k) > 8 else ("*" * len(k)) if k else "None"
            lbl_text = f"#{idx+1} {config.provider} | {config.model_name} | Key: {masked_key}"

            ctk.CTkLabel(row, text=lbl_text, font=("Segoe UI", 12)).pack(
                side="left", padx=5
            )

            def remove_item(i: int = idx) -> None:
                configs.pop(i)
                refresh_pool_display()

            ctk.CTkButton(
                row,
                text="Remove",
                width=60,
                height=24,
                fg_color=ERROR_COLOR,
                hover_color="#dc2626",
                command=remove_item,
            ).pack(side="right", padx=5)

    refresh_pool_display()

    ctk.CTkLabel(
        help_win, text="── Add Provider Config ──", font=("Segoe UI", 13, "bold")
    ).pack(pady=(5, 5), padx=20, anchor="w")

    form_frame = ctk.CTkFrame(help_win, fg_color="transparent")
    form_frame.pack(fill="x", padx=20)

    provider_var = tk.StringVar(value="Gemini")
    endpoint_var = tk.StringVar(
        value="https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    )
    api_key_var = tk.StringVar()
    model_var = tk.StringVar(value="gemini-1.5-flash")

    def on_provider_change(*args: Any) -> None:
        prov = provider_var.get()
        if prov == "Groq":
            endpoint_var.set("https://api.groq.com/openai/v1/chat/completions")
            model_var.set("llama-3.3-70b-versatile")
        elif prov == "OpenRouter":
            endpoint_var.set("https://openrouter.ai/api/v1/chat/completions")
            model_var.set("anthropic/claude-3.5-sonnet")
        elif prov == "Gemini":
            endpoint_var.set(
                "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
            )
            model_var.set("gemini-1.5-flash")
        elif prov in ("Ollama", "Ollama (Local)"):
            endpoint_var.set("http://localhost:11434")
            model_var.set("llama3")
            api_key_var.set("")
        elif prov == "Custom":
            endpoint_var.set("")
            model_var.set("")
            api_key_var.set("")

    provider_var.trace_add("write", on_provider_change)

    fields = [
        ("Provider:", provider_var, ["Gemini", "Groq", "OpenRouter", "Ollama (Local)", "Custom"]),
        ("Endpoint URL:", endpoint_var, None),
        ("Model Name:", model_var, None),
        ("API Key:", api_key_var, None),
    ]

    for r, (label, var, options) in enumerate(fields):
        ctk.CTkLabel(form_frame, text=label, font=("Segoe UI", 11, "bold")).grid(
            row=r, column=0, sticky="w", pady=6
        )
        if options:
            ctk.CTkOptionMenu(form_frame, variable=var, values=options).grid(
                row=r, column=1, sticky="we", pady=6, padx=(10, 0)
            )
        else:
            ctk.CTkEntry(form_frame, textvariable=var, width=320).grid(
                row=r, column=1, sticky="we", pady=6, padx=(10, 0)
            )

    def add_to_pool() -> None:
        p = provider_var.get().strip()
        e = endpoint_var.get().strip()
        k = api_key_var.get().strip()
        m = model_var.get().strip()

        if not e or not m:
            messagebox.showerror(
                "Validation Error", "Endpoint and Model Name are required.", parent=help_win
            )
            return
        if not k and "Ollama" not in p:
            messagebox.showerror(
                "Validation Error", "API Key is required for remote providers.", parent=help_win
            )
            return

        current_tab = tabview.get()
        cap = "vision" if current_tab == "Vision Models" else "text"
        configs.append(
            ProviderConfig(
                provider=p, endpoint_url=e, api_key=k, model_name=m, capability=cap
            )
        )
        refresh_pool_display()
        api_key_var.set("")

    ctk.CTkButton(
        form_frame,
        text="+ Add Config to Pool",
        font=("Segoe UI", 11, "bold"),
        fg_color=ACCENT_COLOR,
        hover_color=ACCENT_HOVER,
        command=add_to_pool,
    ).grid(row=4, column=1, sticky="e", pady=10)

    def save_and_close() -> None:
        new_pool = ProviderPool(configs)
        success = store_provider_pool(new_pool.to_json())
        if success:
            messagebox.showinfo("Success", "Provider pool saved securely!", parent=help_win)
            help_win.destroy()
        else:
            messagebox.showerror("Error", "Failed to save to system keyring.", parent=help_win)

    ctk.CTkButton(
        help_win,
        text="💾 Save Provider Pool",
        font=("Segoe UI", 12, "bold"),
        fg_color=SUCCESS_COLOR,
        hover_color="#059669",
        height=38,
        command=save_and_close,
    ).pack(pady=15, padx=20, fill="x")


# ───────────────────────── PDF Tooling Handlers ────────────────────────


def install_pdf_library(log_fn: Any, root: ctk.CTk) -> None:
    """Install playwright, markdown, and pygments into local .venv.

    Args:
        log_fn (Callable[[str], None]): Function to log output messages.
        root (ctk.CTk): Application root window.
    """
    pip_path = os.path.join(SCRIPT_DIR, ".venv", "Scripts", "pip")
    python_path = os.path.join(SCRIPT_DIR, ".venv", "Scripts", "python")
    if os.path.exists(pip_path + ".exe"):
        pip_path += ".exe"
    if os.path.exists(python_path + ".exe"):
        python_path += ".exe"

    def run_install() -> None:
        log_fn("Installing PDF engine dependencies (playwright, markdown, pygments)...")
        try:
            p1 = subprocess.Popen(
                [pip_path, "install", "playwright", "markdown", "pygments"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            for line in p1.stdout:  # type: ignore
                log_fn(line.strip())
            p1.wait()
            if p1.returncode != 0:
                log_fn(f"ERROR: Pip install failed code {p1.returncode}")
                root.after(
                    0,
                    lambda: messagebox.showerror(
                        "Error", f"Pip install failed code {p1.returncode}"
                    ),
                )
                return

            log_fn("Installing Chromium browser via Playwright...")
            p2 = subprocess.Popen(
                [python_path, "-m", "playwright", "install", "chromium"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            for line in p2.stdout:  # type: ignore
                log_fn(line.strip())
            p2.wait()

            if p2.returncode == 0:
                log_fn("SUCCESS: Playwright Chromium installed!")
                root.after(
                    0,
                    lambda: messagebox.showinfo(
                        "Success", "Playwright PDF engine installed successfully!"
                    ),
                )
            else:
                log_fn(f"ERROR: Chromium install failed code {p2.returncode}")
                root.after(
                    0,
                    lambda: messagebox.showerror(
                        "Error", f"Chromium install failed code {p2.returncode}"
                    ),
                )
        except Exception as e:
            log_fn(f"ERROR running install: {e}")
            root.after(
                0, lambda: messagebox.showerror("Error", f"Failed install: {e}")
            )

    threading.Thread(target=run_install, daemon=True).start()


def _is_playwright_ready() -> bool:
    """Check if Playwright Chromium executable is available.

    Returns:
        bool: True if Playwright chromium browser exists, False otherwise.
    """
    try:
        venv_site = os.path.join(SCRIPT_DIR, ".venv", "Lib", "site-packages")
        if os.path.exists(venv_site) and venv_site not in sys.path:
            sys.path.append(venv_site)
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            return os.path.exists(p.chromium.executable_path)
    except Exception:
        return False


def _ensure_playwright_ready(log_fn: Any, root: ctk.CTk) -> bool:
    """Ensure Playwright is installed; prompt install dialog if missing.

    Args:
        log_fn (Callable[[str], None]): Logger function.
        root (ctk.CTk): Parent window.

    Returns:
        bool: True if ready, False otherwise.
    """
    if _is_playwright_ready():
        return True
    ans = messagebox.askyesno(
        "PDF Engine Required",
        "The PDF engine (Playwright + Chromium) is not installed yet.\n\n"
        "Would you like to install it now (~150MB)?",
        parent=root,
    )
    if ans:
        install_pdf_library(log_fn, root)
    return False


def _get_shared_pdf_css(theme: str = "Textbook") -> str:
    """Get CSS rules for Markdown to PDF conversion.

    Args:
        theme (str): Visual theme ("Textbook", "ChatGPT Dark", "Minimal Mono").

    Returns:
        str: Custom CSS styling block.
    """
    base_css = """
    body { font-family: 'Segoe UI', Helvetica, sans-serif; line-height: 1.5; }
    h1 { break-before: page; margin-top: 0; }
    h1:first-of-type { break-before: auto; }
    h1, h2, h3, h4 { break-after: avoid; }
    pre, blockquote, table, tr { break-inside: avoid; }
    table { width: 100%; border-collapse: collapse; margin: 1em 0; }
    @page { margin: 20mm; }
    """
    if theme == "Textbook":
        return base_css + """
        body { color: #1f2937; }
        h1 { color: #1e3a8a; font-size: 24pt; border-bottom: 3px solid #3b82f6; }
        h2 { color: #2563eb; font-size: 18pt; border-bottom: 1px solid #d1d5db; }
        pre { background-color: #f8fafc; padding: 12px; border-left: 4px solid #94a3b8; }
        blockquote { border-left: 4px solid #3b82f6; background-color: #eff6ff; padding: 10px; }
        th { background-color: #e2e8f0; padding: 8px; border: 1px solid #cbd5e1; }
        td { padding: 8px; border: 1px solid #cbd5e1; }
        """
    elif theme == "ChatGPT Dark":
        return base_css + """
        @page { margin: 0; }
        body { color: #ececf1; background-color: #212121; padding: 20mm; }
        h1 { color: #ffffff; font-size: 24pt; border-bottom: 1px solid #4d4d4d; }
        h2 { color: #f9f9f9; font-size: 18pt; border-bottom: 1px solid #3d3d3d; }
        pre { background-color: #0d0d0d; padding: 12px; border-left: 4px solid #10a37f; }
        blockquote { border-left: 4px solid #10a37f; background-color: #2f2f2f; padding: 10px; }
        th { background-color: #2f2f2f; padding: 8px; border: 1px solid #4d4d4d; color: #fff; }
        td { padding: 8px; border: 1px solid #4d4d4d; }
        """
    else:  # Minimal Mono
        return base_css + """
        body { font-family: 'Courier New', Courier, monospace; color: #000; }
        h1, h2, h3 { color: #000; text-transform: uppercase; border-bottom: 1px solid #000; }
        pre { background-color: #fff; padding: 12px; border: 1px solid #000; }
        blockquote { border-left: 4px solid #000; padding: 10px; }
        th, td { border: 1px solid #000; padding: 8px; }
        """


def convert_file_to_pdf(
    md_file: str, pdf_file: str, theme: str, log_fn: Any, root: ctk.CTk
) -> None:
    """Convert a markdown file to PDF using Playwright sync engine.

    Args:
        md_file (str): Path to input markdown file.
        pdf_file (str): Destination PDF file path.
        theme (str): Selected visual theme.
        log_fn (Callable[[str], None]): Logging handler.
        root (ctk.CTk): Parent window.
    """
    log_fn(f"Exporting '{os.path.basename(md_file)}' to PDF...")

    def run_conv() -> None:
        try:
            import asyncio

            asyncio.set_event_loop(asyncio.new_event_loop())
            venv_site = os.path.join(SCRIPT_DIR, ".venv", "Lib", "site-packages")
            if os.path.exists(venv_site) and venv_site not in sys.path:
                sys.path.append(venv_site)
            import markdown
            from playwright.sync_api import sync_playwright

            with open(md_file, "r", encoding="utf-8", errors="replace") as f:
                md_content = f.read()

            html_body = markdown.markdown(md_content, extensions=["fenced_code", "tables"])
            custom_css = _get_shared_pdf_css(theme)
            mermaid_script = """
            <script>
                document.querySelectorAll('code.language-mermaid').forEach(function(c) {
                    var pre = c.parentNode;
                    var div = document.createElement('div');
                    div.className = 'mermaid';
                    div.textContent = c.textContent;
                    pre.parentNode.replaceChild(div, pre);
                });
                mermaid.initialize({startOnLoad:true});
            </script>
            """
            full_html = (
                f"<html><head><style>{custom_css}</style>"
                f'<script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>'
                f"</head><body>{html_body}{mermaid_script}</body></html>"
            )

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.set_content(full_html)
                page.pdf(path=pdf_file, format="A4", print_background=True)
                browser.close()

            log_fn(f"SUCCESS: Saved PDF to {pdf_file}")
            root.after(
                0,
                lambda: messagebox.showinfo(
                    "Success", f"PDF saved successfully:\n{pdf_file}"
                ),
            )
        except Exception as e:
            log_fn(f"ERROR exporting PDF: {e}")
            root.after(
                0, lambda: messagebox.showerror("Error", f"Failed PDF export: {e}")
            )

    threading.Thread(target=run_conv, daemon=True).start()


def convert_and_save_pdf(log_fn: Any, root: ctk.CTk, theme: str = "Textbook") -> None:
    """Prompt file dialogs and trigger Markdown to PDF conversion.

    Args:
        log_fn (Callable[[str], None]): Log function.
        root (ctk.CTk): Root window.
        theme (str): PDF theme name.
    """
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
    convert_file_to_pdf(md_file, pdf_file, theme, log_fn, root)


def preview_pdf(log_fn: Any, root: ctk.CTk, theme: str = "Textbook") -> None:
    """Render PDF preview to a temp file and open with system default viewer.

    Args:
        log_fn (Callable[[str], None]): Logging handler.
        root (ctk.CTk): Parent root window.
        theme (str): Theme name.
    """
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

    def run_prev() -> None:
        try:
            import asyncio

            asyncio.set_event_loop(asyncio.new_event_loop())
            venv_site = os.path.join(SCRIPT_DIR, ".venv", "Lib", "site-packages")
            if os.path.exists(venv_site) and venv_site not in sys.path:
                sys.path.append(venv_site)
            import markdown
            from playwright.sync_api import sync_playwright

            with open(md_file, "r", encoding="utf-8", errors="replace") as f:
                md_content = f.read()

            html_body = markdown.markdown(md_content, extensions=["fenced_code", "tables"])
            custom_css = _get_shared_pdf_css(theme)
            temp_pdf = os.path.join(tempfile.gettempdir(), "transcriptor_preview.pdf")
            full_html = (
                f"<html><head><style>{custom_css}</style></head>"
                f"<body>{html_body}</body></html>"
            )

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.set_content(full_html)
                page.pdf(path=temp_pdf, format="A4", print_background=True)
                browser.close()

            log_fn("SUCCESS: Opening PDF preview...")
            _open_path(temp_pdf)
        except Exception as e:
            log_fn(f"ERROR generating preview: {e}")
            root.after(
                0, lambda: messagebox.showerror("Error", f"Preview failed: {e}")
            )

    threading.Thread(target=run_prev, daemon=True).start()


# ═══════════════════════════════════════════════════════════════════════
#  MAIN APPLICATION CLASS
# ═══════════════════════════════════════════════════════════════════════


class StudySuiteApp(ctk.CTk):
    """Main CustomTkinter desktop application for YouTube Study Suite."""

    def __init__(self) -> None:
        """Initialize main application shell, UI state, and navigation."""
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title(f"YouTube Transcript to Notes AI Study Suite v{APP_VERSION}")
        self.geometry("1240x880")
        self.minsize(1050, 780)
        self.configure(fg_color=BG_COLOR)

        # State Variables
        self.cancel_event = threading.Event()
        self.current_screen = "library"
        self.current_course_dir: Optional[str] = None

        # Pipeline Form Vars
        self.youtube_url_var = tk.StringVar()
        self.output_dir_var = tk.StringVar()
        self.transcript_path_var = tk.StringVar()
        self.timestamps_path_var = tk.StringVar()
        self.topic_title_var = tk.StringVar()
        self.pdf_theme_var = tk.StringVar(value="Textbook")
        self.multimodal_var = tk.BooleanVar(value=False)
        self.kag_var = tk.BooleanVar(value=False)
        self.auto_pdf_var = tk.BooleanVar(value=True)
        self.input_mode_var = tk.StringVar(value="YouTube URL")

        # Chat session reference and chat history state retention
        self.active_chat_session: Optional[ChatSession] = None
        self.chat_histories: Dict[str, List[Tuple[str, str]]] = {}


        # Build UI Shell
        self._build_layout_grid()
        self._build_sidebar()
        self._build_footer_dock()
        self._build_main_container()

        # Load Startup Screen
        check_env_and_show_help(self)
        self.show_screen("library")
        self._check_ollama_async()

    # ────────────────────────── Layout Shell ──────────────────────────

    def _build_layout_grid(self) -> None:
        """Configure main root grid columns and rows."""
        self.grid_columnconfigure(0, weight=0, minsize=230)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)  # Main Content View
        self.grid_rowconfigure(1, weight=0)  # Footer Dock

    def _build_sidebar(self) -> None:
        """Construct left navigation sidebar."""
        self.sidebar = ctk.CTkFrame(
            self,
            fg_color=SIDEBAR_BG,
            corner_radius=0,
            border_width=1,
            border_color=BORDER_COLOR,
        )
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(5, weight=1)  # Spacer

        # Header Title
        title_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        title_frame.pack(fill="x", padx=18, pady=(20, 25))

        ctk.CTkLabel(
            title_frame,
            text="🎓 AI Study Suite",
            font=("Segoe UI", 18, "bold"),
            text_color=TEXT_COLOR,
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_frame,
            text="Transcript to Notes Pipeline",
            font=("Segoe UI", 10),
            text_color=TEXT_MUTED,
        ).pack(anchor="w", pady=(2, 0))

        # Nav Buttons
        self.nav_buttons: Dict[str, ctk.CTkButton] = {}
        nav_items = [
            ("library", "📚 Library"),
            ("new_pipeline", "🚀 New pipeline"),
            ("settings", "⚙️ Settings"),
        ]

        for name, label in nav_items:
            btn = ctk.CTkButton(
                self.sidebar,
                text=label,
                anchor="w",
                font=("Segoe UI", 13, "bold"),
                height=42,
                corner_radius=8,
                fg_color="transparent",
                text_color=TEXT_MUTED,
                hover_color="#1e293b",
                command=lambda n=name: self.show_screen(n),
            )
            btn.pack(fill="x", padx=12, pady=4)
            self.nav_buttons[name] = btn

        # Spacer
        ctk.CTkFrame(self.sidebar, fg_color="transparent").pack(
            fill="both", expand=True
        )

        # Bottom Ollama Connection Status Card
        ollama_card = ctk.CTkFrame(
            self.sidebar,
            fg_color=CARD_BG,
            corner_radius=8,
            border_width=1,
            border_color=BORDER_COLOR,
        )
        ollama_card.pack(fill="x", padx=12, pady=(0, 15))

        self.ollama_status_lbl = ctk.CTkLabel(
            ollama_card,
            text="🔴 Checking Ollama...",
            font=("Segoe UI", 11, "bold"),
            text_color=TEXT_MUTED,
        )
        self.ollama_status_lbl.pack(pady=10, padx=10)

    def _build_footer_dock(self) -> None:
        """Construct persistent bottom dock containing progress bar and logs drawer."""
        self.footer_container = ctk.CTkFrame(
            self, fg_color=SIDEBAR_BG, corner_radius=0, border_width=1, border_color=BORDER_COLOR
        )
        self.footer_container.grid(row=1, column=0, columnspan=2, sticky="ew")

        # Collapsible Logs Drawer Frame
        self.logs_drawer = ctk.CTkFrame(
            self.footer_container, fg_color=CARD_BG, corner_radius=0
        )
        self.console_text = ctk.CTkTextbox(
            self.logs_drawer,
            fg_color="#09090b",
            text_color=SUCCESS_COLOR,
            font=("Consolas", 10),
            height=140,
        )
        self.console_text.pack(fill="both", expand=True, padx=10, pady=8)
        self.console_text.configure(state="disabled")

        # Dock Control Bar
        self.dock_bar = ctk.CTkFrame(self.footer_container, fg_color="transparent", height=45)
        self.dock_bar.pack(fill="x", padx=15, pady=8)

        # Left Status Indicator Pill
        self.status_pill = ctk.CTkFrame(
            self.dock_bar, width=10, height=10, corner_radius=5, fg_color=TEXT_MUTED
        )
        self.status_pill.pack(side="left", padx=(0, 8))

        self.dock_status_lbl = ctk.CTkLabel(
            self.dock_bar,
            text="Status: Ready",
            font=("Segoe UI", 11, "bold"),
            text_color=TEXT_MUTED,
        )

        self.dock_status_lbl.pack(side="left", padx=(0, 15))

        self.dock_step_lbl = ctk.CTkLabel(
            self.dock_bar, text="", font=("Segoe UI", 10), text_color=TEXT_MUTED
        )
        self.dock_step_lbl.pack(side="left", padx=(0, 15))

        # Progress bar
        self.dock_progress = ctk.CTkProgressBar(
            self.dock_bar, height=8, corner_radius=4, progress_color=ACCENT_COLOR
        )
        self.dock_progress.pack(side="left", fill="x", expand=True, padx=(0, 15))
        self.dock_progress.set(0)

        # Logs Toggle Button
        self.logs_btn = ctk.CTkButton(
            self.dock_bar,
            text="📜 Logs",
            width=80,
            height=30,
            font=("Segoe UI", 11, "bold"),
            fg_color=CARD_BG,
            hover_color="#1f293d",
            command=self.toggle_logs_drawer,
        )
        self.logs_btn.pack(side="right", padx=(5, 0))

        # Cancel Pipeline Button (Hidden by default)
        self.dock_cancel_btn = ctk.CTkButton(
            self.dock_bar,
            text="Cancel Pipeline",
            width=110,
            height=30,
            font=("Segoe UI", 11, "bold"),
            fg_color=ERROR_COLOR,
            hover_color="#dc2626",
            command=self.cancel_pipeline,
        )

    def _build_main_container(self) -> None:
        """Construct center view container frame."""
        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.grid(row=0, column=1, sticky="nsew", padx=20, pady=15)
        self.main_container.grid_columnconfigure(0, weight=1)
        self.main_container.grid_rowconfigure(0, weight=1)

    # ────────────────────────── Logging & Logs ──────────────────────────

    def log_message(self, msg: str) -> None:
        """Append log message to console widget and mirror to pipeline.log file.

        Args:
            msg (str): Message to log.
        """
        stamped = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"

        def _append() -> None:
            self.console_text.configure(state="normal")
            self.console_text.insert(tk.END, stamped + "\n")
            self.console_text.see(tk.END)
            self.console_text.configure(state="disabled")

        self.after(0, _append)

        try:
            out_dir = self.output_dir_var.get().strip()
            if out_dir and os.path.isdir(out_dir):
                log_path = os.path.join(out_dir, "pipeline.log")
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(stamped + "\n")
        except Exception:
            pass

    def toggle_logs_drawer(self) -> None:
        """Toggle visibility of the bottom collapsible logs drawer."""
        if self.logs_drawer.winfo_ismapped():
            self.logs_drawer.pack_forget()
            self.logs_btn.configure(fg_color=CARD_BG)
        else:
            self.logs_drawer.pack(fill="x", side="top", before=self.dock_bar)
            self.logs_btn.configure(fg_color=ACCENT_COLOR)

    def _check_ollama_async(self) -> None:
        """Check Ollama status in background thread and update sidebar indicator."""

        def worker() -> None:
            online = check_ollama_status()
            def update() -> None:
                if online:
                    self.ollama_status_lbl.configure(
                        text="🟢 Ollama Connected", text_color=SUCCESS_COLOR
                    )
                else:
                    self.ollama_status_lbl.configure(
                        text="🔴 Ollama Offline", text_color=ERROR_COLOR
                    )
            self.after(0, update)

        threading.Thread(target=worker, daemon=True).start()

    # ──────────────────────── Navigation Controller ──────────────────────

    def show_screen(self, screen_name: str, **kwargs: Any) -> None:
        """Switch current main container view frame.

        Args:
            screen_name (str): Screen identifier ("library", "new_pipeline",
                "course_workspace", "settings").
            **kwargs: Extra arguments (e.g. course_dir for course_workspace).
        """
        self.current_screen = screen_name

        # Highlight sidebar active button
        for name, btn in self.nav_buttons.items():
            if name == screen_name:
                btn.configure(fg_color=ACCENT_COLOR, text_color="#ffffff")
            else:
                btn.configure(fg_color="transparent", text_color=TEXT_MUTED)

        # Clear existing screen widgets
        for child in self.main_container.winfo_children():
            child.destroy()

        if screen_name == "library":
            self._render_library_screen()
        elif screen_name == "new_pipeline":
            self._render_new_pipeline_screen()
        elif screen_name == "course_workspace":
            course_dir = kwargs.get("course_dir", self.current_course_dir)
            self.current_course_dir = course_dir
            self._render_course_workspace_screen(course_dir)
        elif screen_name == "settings":
            self._render_settings_screen()

    # ═════════════════════════════════════════════════════════════════════
    #  SCREEN 1: 📚 LIBRARY
    # ═════════════════════════════════════════════════════════════════════

    def _render_library_screen(self) -> None:
        """Render Screen 1: Library overview of saved courses."""
        view_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        view_frame.pack(fill="both", expand=True)

        # Header Title
        header_frame = ctk.CTkFrame(view_frame, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(
            header_frame,
            text="📚 Course Library",
            font=("Segoe UI", 22, "bold"),
            text_color=TEXT_COLOR,
        ).pack(side="left")

        ctk.CTkButton(
            header_frame,
            text="🔄 Refresh",
            width=90,
            height=32,
            font=("Segoe UI", 11, "bold"),
            fg_color=CARD_BG,
            border_width=1,
            border_color=BORDER_COLOR,
            command=self._render_library_screen,
        ).pack(side="right")

        # Scrollable Cards Grid Container
        scroll_frame = ctk.CTkScrollableFrame(
            view_frame, fg_color="transparent", corner_radius=0
        )
        scroll_frame.pack(fill="both", expand=True)

        recent_paths = load_recent_outputs()
        valid_paths = [p for p in recent_paths if os.path.isdir(p)]

        if not valid_paths:
            # Empty State Card
            empty_card = ctk.CTkFrame(
                scroll_frame,
                fg_color=CARD_BG,
                corner_radius=CARD_RADIUS,
                border_width=1,
                border_color=BORDER_COLOR,
            )
            empty_card.pack(fill="both", expand=True, padx=40, pady=60)

            ctk.CTkLabel(
                empty_card,
                text="🎓 Welcome to YouTube Study Suite!",
                font=("Segoe UI", 18, "bold"),
                text_color=TEXT_COLOR,
            ).pack(pady=(40, 8))
            ctk.CTkLabel(
                empty_card,
                text="No study courses found yet. Start your first YouTube study pipeline.",
                font=("Segoe UI", 12),
                text_color=TEXT_MUTED,
            ).pack(pady=(0, 20))

            ctk.CTkButton(
                empty_card,
                text="🚀 Start Your First Course",
                font=("Segoe UI", 13, "bold"),
                fg_color=ACCENT_COLOR,
                hover_color=ACCENT_HOVER,
                height=45,
                width=220,
                command=lambda: self.show_screen("new_pipeline"),
            ).pack(pady=(0, 40))
            return

        # Render Course Cards
        for path in valid_paths:
            title = os.path.basename(os.path.normpath(path))
            mtime = datetime.fromtimestamp(os.path.getmtime(path)).strftime(
                "%b %d, %Y • %H:%M"
            )

            # Check Badges
            has_vision = os.path.exists(os.path.join(path, "keyframes"))
            has_kag = os.path.exists(
                os.path.join(path, "knowledge_graph.html")
            ) or os.path.exists(os.path.join(path, "knowledge_graph.json"))
            pdf_files = [f for f in os.listdir(path) if f.endswith(".pdf")]
            has_pdf = len(pdf_files) > 0

            card = ctk.CTkFrame(
                scroll_frame,
                fg_color=CARD_BG,
                corner_radius=CARD_RADIUS,
                border_width=1,
                border_color=BORDER_COLOR,
            )
            card.pack(fill="x", pady=6, padx=4)

            # Left Info
            info_frame = ctk.CTkFrame(card, fg_color="transparent")
            info_frame.pack(side="left", fill="both", expand=True, padx=18, pady=14)

            ctk.CTkLabel(
                info_frame,
                text=title,
                font=("Segoe UI", 15, "bold"),
                text_color=TEXT_COLOR,
                anchor="w",
            ).pack(anchor="w")

            ctk.CTkLabel(
                info_frame,
                text=f"📂 {path}  |  🕒 {mtime}",
                font=("Segoe UI", 10),
                text_color=TEXT_MUTED,
                anchor="w",
            ).pack(anchor="w", pady=(3, 8))

            # Badges Row
            badges_frame = ctk.CTkFrame(info_frame, fg_color="transparent")
            badges_frame.pack(anchor="w")

            if has_vision:
                ctk.CTkLabel(
                    badges_frame,
                    text="📸 Vision",
                    font=("Segoe UI", 9, "bold"),
                    fg_color="#312e81",
                    text_color="#c7d2fe",
                    corner_radius=4,
                    padx=6,
                    pady=2,
                ).pack(side="left", padx=(0, 6))
            if has_kag:
                ctk.CTkLabel(
                    badges_frame,
                    text="🕸️ KAG",
                    font=("Segoe UI", 9, "bold"),
                    fg_color="#065f46",
                    text_color="#a7f3d0",
                    corner_radius=4,
                    padx=6,
                    pady=2,
                ).pack(side="left", padx=(0, 6))
            if has_pdf:
                ctk.CTkLabel(
                    badges_frame,
                    text="📄 PDF",
                    font=("Segoe UI", 9, "bold"),
                    fg_color="#831843",
                    text_color="#fbcfe8",
                    corner_radius=4,
                    padx=6,
                    pady=2,
                ).pack(side="left", padx=(0, 6))

            # Open Button
            ctk.CTkButton(
                card,
                text="Open Workspace →",
                font=("Segoe UI", 11, "bold"),
                fg_color=ACCENT_COLOR,
                hover_color=ACCENT_HOVER,
                height=36,
                width=140,
                command=lambda p=path: self.show_screen(
                    "course_workspace", course_dir=p
                ),
            ).pack(side="right", padx=18, pady=14)

    # ═════════════════════════════════════════════════════════════════════
    #  SCREEN 2: 🚀 NEW PIPELINE
    # ═════════════════════════════════════════════════════════════════════

    def _render_new_pipeline_screen(self) -> None:
        """Render Screen 2: New Pipeline form and power-up toggle cards."""
        view_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        view_frame.pack(fill="both", expand=True)

        ctk.CTkLabel(
            view_frame,
            text="🚀 Create New Study Pipeline",
            font=("Segoe UI", 22, "bold"),
            text_color=TEXT_COLOR,
        ).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(
            view_frame,
            text=(
                "Extract YouTube transcripts, extract vision keyframes, "
                "build Knowledge Graphs, and generate notes."
            ),
            font=("Segoe UI", 11),
            text_color=TEXT_MUTED,
        ).pack(anchor="w", pady=(0, 15))

        # Main Input Card
        input_card = ctk.CTkFrame(
            view_frame,
            fg_color=CARD_BG,
            corner_radius=CARD_RADIUS,
            border_width=1,
            border_color=BORDER_COLOR,
        )
        input_card.pack(fill="x", pady=(0, 15))

        input_tabs = ctk.CTkTabview(
            input_card,
            corner_radius=8,
            height=200,
            segmented_button_fg_color="#0f172a",
            segmented_button_selected_color=ACCENT_COLOR,
        )
        input_tabs.pack(fill="both", expand=True, padx=12, pady=10)

        # Tab 1: YouTube URL
        yt_tab = input_tabs.add("YouTube URL")
        yt_tab.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            yt_tab, text="YouTube Video Link:", font=("Segoe UI", 11, "bold")
        ).grid(row=0, column=0, sticky="w", pady=(5, 4))
        ctk.CTkEntry(
            yt_tab,
            textvariable=self.youtube_url_var,
            placeholder_text="https://www.youtube.com/watch?v=...",
            font=("Segoe UI", 11),
        ).grid(row=1, column=0, sticky="we", pady=(0, 10))

        ctk.CTkLabel(
            yt_tab, text="Output Directory:", font=("Segoe UI", 11, "bold")
        ).grid(row=2, column=0, sticky="w", pady=(5, 4))

        yt_out_frame = ctk.CTkFrame(yt_tab, fg_color="transparent")
        yt_out_frame.grid(row=3, column=0, sticky="we")
        yt_out_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkEntry(
            yt_out_frame,
            textvariable=self.output_dir_var,
            placeholder_text="Select directory to save notes...",
            font=("Segoe UI", 11),
        ).grid(row=0, column=0, sticky="we", padx=(0, 8))

        ctk.CTkButton(
            yt_out_frame,
            text="Browse",
            width=90,
            font=("Segoe UI", 11, "bold"),
            command=self._browse_output_dir,
        ).grid(row=0, column=1)

        # Tab 2: Local Files
        files_tab = input_tabs.add("Local Text Files")
        files_tab.grid_columnconfigure(1, weight=1)

        fields = [
            ("Course Topic / Title:", self.topic_title_var, None),
            ("Transcript File (.txt):", self.transcript_path_var, self._browse_transcript),
            ("Timestamps File (.txt):", self.timestamps_path_var, self._browse_timestamps),
            ("Output Directory:", self.output_dir_var, self._browse_output_dir),
        ]

        for idx, (label_text, var, browse_fn) in enumerate(fields):
            ctk.CTkLabel(
                files_tab, text=label_text, font=("Segoe UI", 11, "bold")
            ).grid(row=idx, column=0, sticky="w", pady=4, padx=(0, 10))
            ctk.CTkEntry(files_tab, textvariable=var, font=("Segoe UI", 10)).grid(
                row=idx, column=1, sticky="we", pady=4
            )
            if browse_fn:
                ctk.CTkButton(
                    files_tab,
                    text="Browse",
                    width=75,
                    font=("Segoe UI", 10, "bold"),
                    command=browse_fn,
                ).grid(row=idx, column=2, sticky="e", pady=4, padx=(6, 0))

        # Power-Up Toggle Cards Frame
        ctk.CTkLabel(
            view_frame, text="⚡ Power-Up Engines", font=("Segoe UI", 14, "bold")
        ).pack(anchor="w", pady=(5, 8))

        powerups_frame = ctk.CTkFrame(view_frame, fg_color="transparent")
        powerups_frame.pack(fill="x", pady=(0, 20))
        powerups_frame.grid_columnconfigure((0, 1, 2), weight=1)

        # PowerUp 1: Vision
        p1 = ctk.CTkFrame(
            powerups_frame,
            fg_color=CARD_BG,
            corner_radius=CARD_RADIUS,
            border_width=1,
            border_color=BORDER_COLOR,
        )
        p1.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        ctk.CTkLabel(p1, text="📸 Vision Engine", font=("Segoe UI", 13, "bold")).pack(
            anchor="w", padx=12, pady=(12, 2)
        )
        hint_v = get_powerup_time_hint("vision")
        ctk.CTkLabel(
            p1,
            text=f"Extracts visual keyframes ({hint_v})",
            font=("Segoe UI", 10),
            text_color=TEXT_MUTED,
        ).pack(anchor="w", padx=12, pady=(0, 10))
        ctk.CTkSwitch(
            p1, text="Enabled", variable=self.multimodal_var, font=("Segoe UI", 11)
        ).pack(anchor="w", padx=12, pady=(0, 12))

        # PowerUp 2: KAG
        p2 = ctk.CTkFrame(
            powerups_frame,
            fg_color=CARD_BG,
            corner_radius=CARD_RADIUS,
            border_width=1,
            border_color=BORDER_COLOR,
        )
        p2.grid(row=0, column=1, sticky="nsew", padx=3)
        ctk.CTkLabel(
            p2, text="🕸️ Knowledge Graph", font=("Segoe UI", 13, "bold")
        ).pack(anchor="w", padx=12, pady=(12, 2))
        hint_k = get_powerup_time_hint("kag")
        ctk.CTkLabel(
            p2,
            text=f"Mermaid HTML Graph ({hint_k})",
            font=("Segoe UI", 10),
            text_color=TEXT_MUTED,
        ).pack(anchor="w", padx=12, pady=(0, 10))
        ctk.CTkSwitch(
            p2, text="Enabled", variable=self.kag_var, font=("Segoe UI", 11)
        ).pack(anchor="w", padx=12, pady=(0, 12))

        # PowerUp 3: Auto PDF
        p3 = ctk.CTkFrame(
            powerups_frame,
            fg_color=CARD_BG,
            corner_radius=CARD_RADIUS,
            border_width=1,
            border_color=BORDER_COLOR,
        )
        p3.grid(row=0, column=2, sticky="nsew", padx=(6, 0))
        ctk.CTkLabel(
            p3, text="📄 Auto PDF Export", font=("Segoe UI", 13, "bold")
        ).pack(anchor="w", padx=12, pady=(12, 2))
        hint_p = get_powerup_time_hint("pdf")
        ctk.CTkLabel(
            p3,
            text=f"Exports PDF on finish ({hint_p})",
            font=("Segoe UI", 10),
            text_color=TEXT_MUTED,
        ).pack(anchor="w", padx=12, pady=(0, 10))
        ctk.CTkSwitch(
            p3, text="Enabled", variable=self.auto_pdf_var, font=("Segoe UI", 11)
        ).pack(anchor="w", padx=12, pady=(0, 12))

        # Start Button
        self.start_pipeline_btn = ctk.CTkButton(
            view_frame,
            text="🚀 Start Pipeline Processing",
            font=("Segoe UI", 14, "bold"),
            fg_color=ACCENT_COLOR,
            hover_color=ACCENT_HOVER,
            height=48,
            command=lambda: self.start_pipeline_job(input_tabs.get()),
        )
        self.start_pipeline_btn.pack(fill="x")

    def _browse_transcript(self) -> None:
        """Open file dialog for transcript txt file."""
        p = filedialog.askopenfilename(filetypes=[("Text files", "*.txt")])
        if p:
            self.transcript_path_var.set(p)

    def _browse_timestamps(self) -> None:
        """Open file dialog for timestamps txt file."""
        p = filedialog.askopenfilename(filetypes=[("Text files", "*.txt")])
        if p:
            self.timestamps_path_var.set(p)

    def _browse_output_dir(self) -> None:
        """Open directory dialog for output folder."""
        p = filedialog.askdirectory()
        if p:
            self.output_dir_var.set(p)

    # ────────────────────── Pipeline Runner Logic ─────────────────────

    def start_pipeline_job(self, active_tab: str) -> None:
        """Validate input parameters and launch background pipeline execution.

        Args:
            active_tab (str): Active input mode ("YouTube URL" or "Local Text Files").
        """
        output_dir = self.output_dir_var.get().strip()

        # Validate credentials pool
        try:
            pool = get_provider_pool_or_legacy()
            if pool.total == 0:
                raise ValueError("No credentials")
        except Exception:
            messagebox.showerror(
                "Missing Credentials",
                "No API configuration pool found. Please configure API credentials.",
                parent=self,
            )
            _show_env_help_popup(self)
            return

        if not output_dir or not os.path.isdir(output_dir):
            messagebox.showerror(
                "Validation Error", "Please specify a valid output directory.", parent=self
            )
            return

        if active_tab == "YouTube URL":
            url = self.youtube_url_var.get().strip()
            if not url:
                messagebox.showerror(
                    "Validation Error", "Please paste a YouTube video URL.", parent=self
                )
                return
            if self.multimodal_var.get():
                ans = messagebox.askyesno(
                    "Bandwidth Warning",
                    "Extracting video frames requires downloading video (~50-200MB).\nProceed?",
                    parent=self,
                )
                if not ans:
                    return
        else:
            tr = self.transcript_path_var.get().strip()
            ts = self.timestamps_path_var.get().strip()
            title = self.topic_title_var.get().strip()
            if not tr or not os.path.exists(tr):
                messagebox.showerror("Error", "Valid transcript file path required.", parent=self)
                return
            if not ts or not os.path.exists(ts):
                messagebox.showerror("Error", "Valid timestamps file path required.", parent=self)
                return
            if not title:
                messagebox.showerror("Error", "Topic/Title required.", parent=self)
                return

        # Reset cancel state and UI status
        self.cancel_event.clear()
        self.dock_cancel_btn.pack(side="right", padx=(0, 8))
        self.start_pipeline_btn.configure(state="disabled", text="Pipeline Running...")
        self.dock_status_lbl.configure(text="Status: Running...", text_color=WARNING_COLOR)
        self.status_pill.configure(fg_color=WARNING_COLOR)
        self.dock_progress.configure(mode="indeterminate")
        self.dock_progress.start()
        self.dock_step_lbl.configure(text="Initializing pipeline...")

        def on_progress(current: int, total: int) -> None:
            def _update() -> None:
                self.dock_progress.stop()
                self.dock_progress.configure(mode="determinate")
                self.dock_progress.set(current / total if total else 0)
                if total > 0:
                    self.dock_step_lbl.configure(text=f"Step {current} of {total}...")
            self.after(0, _update)

        def worker() -> None:
            self.log_message(f"Starting pipeline using {pool.total} provider config(s).")
            result: Optional[Dict[str, Any]] = None
            try:
                if active_tab == "YouTube URL":
                    from src.youtube import extract_from_url

                    self.log_message("=== YOUTUBE DATA EXTRACTION ===")
                    data = extract_from_url(url, on_log=self.log_message)

                    if not data.get("transcript_blocks"):
                        self.after(
                            0, lambda: messagebox.showerror("Error", "No transcript found.")
                        )
                        return
                    if not data.get("chapters"):
                        self.after(
                            0, lambda: messagebox.showerror("Error", "No chapters found.")
                        )
                        return

                    result = run_pipeline_from_data(
                        transcript_blocks=data["transcript_blocks"],
                        chapters=data["chapters"],
                        output_dir=output_dir,
                        pool=pool,
                        cancel_event=self.cancel_event,
                        on_log=self.log_message,
                        on_progress=on_progress,
                        video_title=data.get("metadata", {}).get("title"),
                        enable_multimodal=self.multimodal_var.get(),
                        youtube_url=url,
                        enable_kag=self.kag_var.get(),
                    )
                else:
                    result = run_pipeline(
                        transcript_path=tr,
                        timestamps_path=ts,
                        output_dir=output_dir,
                        pool=pool,
                        cancel_event=self.cancel_event,
                        on_log=self.log_message,
                        on_progress=on_progress,
                        video_title=title,
                        enable_kag=self.kag_var.get(),
                    )

                if result and result.get("success"):
                    add_recent_output(output_dir)
                    if self.auto_pdf_var.get():
                        out_files = os.listdir(output_dir)
                        detailed = [
                            f for f in out_files if f.endswith("_Detailed_Notes.md")
                        ]
                        if detailed:
                            detailed_notes = os.path.join(output_dir, detailed[0])
                            pdf_out = os.path.splitext(detailed_notes)[0] + ".pdf"
                            convert_file_to_pdf(
                                detailed_notes,
                                pdf_out,
                                self.pdf_theme_var.get(),
                                self.log_message,
                                self,
                            )
            except Exception as e:
                self.log_message(f"CRITICAL ERROR: {e}")
                self.after(0, lambda: messagebox.showerror("Pipeline Error", str(e)))
            finally:
                def restore_ui() -> None:
                    self.dock_progress.stop()
                    self.dock_progress.configure(mode="determinate")
                    self.dock_cancel_btn.pack_forget()
                    try:
                        self.start_pipeline_btn.configure(
                            state="normal", text="🚀 Start Pipeline Processing"
                        )
                    except Exception:
                        pass

                    if self.cancel_event.is_set():
                        self.dock_status_lbl.configure(
                            text="Status: Cancelled", text_color=ERROR_COLOR
                        )
                        self.status_pill.configure(fg_color=ERROR_COLOR)
                        self.dock_progress.set(0)
                        self.dock_step_lbl.configure(text="")
                    elif result and result.get("success"):
                        self.dock_status_lbl.configure(
                            text="Status: Completed ✅", text_color=SUCCESS_COLOR
                        )
                        self.status_pill.configure(fg_color=SUCCESS_COLOR)
                        self.dock_progress.set(1.0)
                        self.dock_step_lbl.configure(text="Done.")
                        # Auto navigate into Course Workspace!
                        self.show_screen("course_workspace", course_dir=output_dir)
                    else:
                        self.dock_status_lbl.configure(
                            text="Status: Error", text_color=ERROR_COLOR
                        )
                        self.status_pill.configure(fg_color=ERROR_COLOR)
                        self.dock_progress.set(0)
                        self.dock_step_lbl.configure(text="Error occurred.")

                self.after(0, restore_ui)

        threading.Thread(target=worker, daemon=True).start()

    def cancel_pipeline(self) -> None:
        """Cancel ongoing pipeline thread."""
        if messagebox.askyesno(
            "Confirm Cancel", "Cancel running pipeline operation?", parent=self
        ):
            self.log_message("Cancel requested. Waiting for current chapter to stop...")
            self.dock_cancel_btn.configure(state="disabled", text="Cancelling...")
            self.cancel_event.set()

    # ═════════════════════════════════════════════════════════════════════
    #  SCREEN 3: 🎓 COURSE WORKSPACE
    # ═════════════════════════════════════════════════════════════════════

    def _render_course_workspace_screen(self, course_dir: Optional[str]) -> None:
        """Render Screen 3: Course Workspace with 5 sub-tabs.

        Args:
            course_dir (Optional[str]): Course directory path.
        """
        view_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        view_frame.pack(fill="both", expand=True)

        if not course_dir or not os.path.isdir(course_dir):
            ctk.CTkLabel(
                view_frame,
                text="⚠️ No valid course directory selected.",
                font=("Segoe UI", 16, "bold"),
                text_color=ERROR_COLOR,
            ).pack(pady=40)
            ctk.CTkButton(
                view_frame,
                text="← Back to Library",
                command=lambda: self.show_screen("library"),
            ).pack()
            return

        title = os.path.basename(os.path.normpath(course_dir))

        # Workspace Header
        header = ctk.CTkFrame(view_frame, fg_color="transparent")
        header.pack(fill="x", pady=(0, 10))

        ctk.CTkButton(
            header,
            text="← Back to Library",
            width=120,
            height=32,
            font=("Segoe UI", 11, "bold"),
            fg_color=CARD_BG,
            border_width=1,
            border_color=BORDER_COLOR,
            command=lambda: self.show_screen("library"),
        ).pack(side="left", padx=(0, 12))

        ctk.CTkLabel(
            header,
            text=f"🎓 {title}",
            font=("Segoe UI", 18, "bold"),
            text_color=TEXT_COLOR,
        ).pack(side="left")

        ctk.CTkButton(
            header,
            text="📂 Open Output Folder",
            width=140,
            height=32,
            font=("Segoe UI", 11, "bold"),
            fg_color=CARD_BG,
            border_width=1,
            border_color=BORDER_COLOR,
            command=lambda: _open_path(course_dir),
        ).pack(side="right")

        # 5 Sub-Tabs View
        tabview = ctk.CTkTabview(
            view_frame,
            corner_radius=CARD_RADIUS,
            segmented_button_fg_color="#0f172a",
            segmented_button_selected_color=ACCENT_COLOR,
        )
        tabview.pack(fill="both", expand=True)

        notes_tab = tabview.add("📝 Notes")
        chat_tab = tabview.add("💬 Chat")
        graph_tab = tabview.add("🕸️ Graph")
        pdf_tab = tabview.add("📄 PDF")
        keyframes_tab = tabview.add("🖼️ Keyframes")

        # ── 1. NOTES TAB ──
        md_files = [f for f in os.listdir(course_dir) if f.endswith(".md")]
        if not md_files:
            ctk.CTkLabel(
                notes_tab, text="No Markdown notes found in folder.", font=("Segoe UI", 12)
            ).pack(pady=20)
        else:
            note_var = tk.StringVar(value=md_files[0])
            top_bar = ctk.CTkFrame(notes_tab, fg_color="transparent")
            top_bar.pack(fill="x", padx=10, pady=6)

            ctk.CTkLabel(
                top_bar, text="Select Note File:", font=("Segoe UI", 11, "bold")
            ).pack(side="left", padx=(0, 8))

            notes_textbox = ctk.CTkTextbox(
                notes_tab, fg_color="#09090b", text_color=TEXT_COLOR, font=("Segoe UI", 11)
            )
            notes_textbox.pack(fill="both", expand=True, padx=10, pady=(0, 10))

            def display_note(*args: Any) -> None:
                selected_file = os.path.join(course_dir, note_var.get())
                if os.path.exists(selected_file):
                    with open(selected_file, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    notes_textbox.configure(state="normal")
                    notes_textbox.delete("1.0", tk.END)
                    notes_textbox.insert(tk.END, content)
                    notes_textbox.configure(state="disabled")

            ctk.CTkOptionMenu(
                top_bar, variable=note_var, values=md_files, command=display_note
            ).pack(side="left")

            display_note()

        # ── 2. CHAT TAB ──
        chat_tab.grid_columnconfigure(1, weight=1)
        chat_tab.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            chat_tab,
            text="Local CAG Chat (Ollama) scoped to this course.",
            font=("Segoe UI", 11),
            text_color=TEXT_MUTED,
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=6)

        chat_log = ctk.CTkTextbox(
            chat_tab,
            fg_color="#09090b",
            text_color=TEXT_COLOR,
            font=("Segoe UI", 11),
            wrap="word",
        )
        chat_log.grid(row=1, column=0, columnspan=3, sticky="nsew", padx=10, pady=6)

        # Restore retained chat history for course_dir
        saved_history = self.chat_histories.setdefault(course_dir, [])
        chat_log.configure(state="normal")
        chat_log.delete("1.0", tk.END)
        for sender, msg in saved_history:
            if sender == "AI":
                chat_log.insert(tk.END, f"AI: {msg}\n\n")
            else:
                chat_log.insert(tk.END, f"You: {msg}\n")
        chat_log.see(tk.END)
        chat_log.configure(state="disabled")

        chat_input = ctk.CTkEntry(
            chat_tab, placeholder_text="Ask a question about this course...", font=("Segoe UI", 11)
        )
        chat_input.grid(row=2, column=0, columnspan=2, sticky="we", padx=(10, 5), pady=6)

        chat_model_var = tk.StringVar(value="llama3")
        model_dropdown = ctk.CTkOptionMenu(
            chat_tab,
            variable=chat_model_var,
            values=["llama3", "phi3", "qwen2.5:3b", "gemma"],
            width=110,
        )
        model_dropdown.grid(row=0, column=2, sticky="e", padx=10, pady=6)

        chat_btn_frame = ctk.CTkFrame(chat_tab, fg_color="transparent")
        chat_btn_frame.grid(row=2, column=2, sticky="e", padx=(0, 10), pady=6)

        def send_course_chat(*args: Any) -> None:
            user_msg = chat_input.get().strip()
            if not user_msg:
                return

            chat_input.delete(0, tk.END)
            self.chat_histories[course_dir].append(("You", user_msg))
            chat_log.configure(state="normal")
            chat_log.insert(tk.END, f"You: {user_msg}\n")
            chat_log.see(tk.END)
            chat_log.configure(state="disabled")

            def run_chat_worker() -> None:
                try:
                    if (
                        self.active_chat_session is None
                        or self.active_chat_session.notes_dir != course_dir
                        or self.active_chat_session.ollama_model != chat_model_var.get()
                    ):
                        self.active_chat_session = ChatSession(
                            course_dir, chat_model_var.get()
                        )
                    ans = self.active_chat_session.send(user_msg)
                    self.chat_histories[course_dir].append(("AI", ans))

                    def update() -> None:
                        chat_log.configure(state="normal")
                        chat_log.insert(tk.END, f"AI: {ans}\n\n")
                        chat_log.see(tk.END)
                        chat_log.configure(state="disabled")

                    self.after(0, update)
                except Exception as e:
                    def err() -> None:
                        chat_log.configure(state="normal")
                        chat_log.insert(tk.END, f"Error: {e}\n\n")
                        chat_log.see(tk.END)
                        chat_log.configure(state="disabled")

                    self.after(0, err)

            threading.Thread(target=run_chat_worker, daemon=True).start()

        def clear_chat() -> None:
            self.active_chat_session = None
            self.chat_histories[course_dir] = []
            chat_log.configure(state="normal")
            chat_log.delete("1.0", tk.END)
            chat_log.configure(state="disabled")

        ctk.CTkButton(
            chat_btn_frame,
            text="Clear",
            width=60,
            fg_color=ERROR_COLOR,
            hover_color="#dc2626",
            command=clear_chat,
        ).pack(side="left", padx=(0, 5))

        send_btn = ctk.CTkButton(
            chat_btn_frame,
            text="Send",
            width=65,
            fg_color=ACCENT_COLOR,
            hover_color=ACCENT_HOVER,
            command=send_course_chat,
        )
        send_btn.pack(side="left")
        chat_input.bind("<Return>", send_course_chat)

        # ── 3. GRAPH TAB ──
        html_graph = os.path.join(course_dir, "knowledge_graph.html")
        if os.path.exists(html_graph):
            ctk.CTkLabel(
                graph_tab,
                text="🕸️ Interactive Mermaid Knowledge Graph",
                font=("Segoe UI", 16, "bold"),
            ).pack(pady=(30, 8))
            ctk.CTkLabel(
                graph_tab,
                text=f"Graph File: {html_graph}",
                font=("Segoe UI", 11),
                text_color=TEXT_MUTED,
            ).pack(pady=(0, 20))
            ctk.CTkButton(
                graph_tab,
                text="🌐 Open Interactive Graph in Browser",
                font=("Segoe UI", 13, "bold"),
                fg_color=ACCENT_COLOR,
                hover_color=ACCENT_HOVER,
                height=45,
                width=260,
                command=lambda: _open_path(html_graph),
            ).pack()
        else:
            ctk.CTkLabel(
                graph_tab,
                text="Knowledge Graph was not generated for this course run.",
                font=("Segoe UI", 12),
                text_color=TEXT_MUTED,
            ).pack(pady=40)

        # ── 4. PDF TAB ──
        pdf_form = ctk.CTkFrame(pdf_tab, fg_color="transparent")
        pdf_form.pack(fill="x", padx=20, pady=20)

        ctk.CTkLabel(
            pdf_form, text="PDF Theme:", font=("Segoe UI", 12, "bold")
        ).pack(side="left", padx=(0, 10))

        pdf_theme_opt = ctk.CTkOptionMenu(
            pdf_form,
            variable=self.pdf_theme_var,
            values=["Textbook", "ChatGPT Dark", "Minimal Mono"],
        )
        pdf_theme_opt.pack(side="left", padx=(0, 20))

        if md_files:
            target_md_var = tk.StringVar(value=md_files[0])
            ctk.CTkLabel(
                pdf_form, text="Target Markdown File:", font=("Segoe UI", 12, "bold")
            ).pack(side="left", padx=(0, 10))
            ctk.CTkOptionMenu(
                pdf_form, variable=target_md_var, values=md_files
            ).pack(side="left")

        pdf_actions = ctk.CTkFrame(pdf_tab, fg_color="transparent")
        pdf_actions.pack(pady=20)

        def do_preview() -> None:
            if md_files:
                f_path = os.path.join(course_dir, target_md_var.get())
                preview_pdf(self.log_message, self, theme=self.pdf_theme_var.get())

        def do_export() -> None:
            if md_files:
                f_path = os.path.join(course_dir, target_md_var.get())
                pdf_file = filedialog.asksaveasfilename(
                    title="Export PDF As",
                    defaultextension=".pdf",
                    filetypes=[("PDF Files", "*.pdf")],
                )
                if pdf_file:
                    convert_file_to_pdf(
                        f_path, pdf_file, self.pdf_theme_var.get(), self.log_message, self
                    )

        ctk.CTkButton(
            pdf_actions,
            text="👁️ Preview PDF",
            font=("Segoe UI", 12, "bold"),
            fg_color=CARD_BG,
            border_width=1,
            border_color=BORDER_COLOR,
            height=40,
            width=140,
            command=do_preview,
        ).pack(side="left", padx=10)

        ctk.CTkButton(
            pdf_actions,
            text="📥 Export PDF",
            font=("Segoe UI", 12, "bold"),
            fg_color=ACCENT_COLOR,
            hover_color=ACCENT_HOVER,
            height=40,
            width=140,
            command=do_export,
        ).pack(side="left", padx=10)

        # ── 5. KEYFRAMES TAB ──
        keyframes_dir = os.path.join(course_dir, "keyframes")
        if os.path.exists(keyframes_dir):
            imgs = [
                os.path.join(keyframes_dir, f)
                for f in os.listdir(keyframes_dir)
                if f.lower().endswith((".png", ".jpg", ".jpeg"))
            ]
            if imgs:
                kf_scroll = ctk.CTkScrollableFrame(
                    keyframes_tab, fg_color="transparent"
                )
                kf_scroll.pack(fill="both", expand=True, padx=10, pady=10)

                for img_p in imgs:
                    fname = os.path.basename(img_p)
                    row_f = ctk.CTkFrame(
                        kf_scroll,
                        fg_color=CARD_BG,
                        corner_radius=8,
                        border_width=1,
                        border_color=BORDER_COLOR,
                    )
                    row_f.pack(fill="x", pady=4, padx=5)

                    thumb_rendered = False
                    try:
                        from PIL import Image

                        pil_img = Image.open(img_p)
                        pil_img.thumbnail((160, 90))
                        ctk_img = ctk.CTkImage(
                            light_image=pil_img, dark_image=pil_img, size=(160, 90)
                        )
                        img_lbl = ctk.CTkLabel(row_f, image=ctk_img, text="")
                        img_lbl.image = ctk_img  # Store reference
                        img_lbl.pack(side="left", padx=12, pady=8)
                        thumb_rendered = True
                    except Exception:
                        pass

                    if not thumb_rendered:
                        ctk.CTkLabel(
                            row_f,
                            text=f"🖼️ {fname}",
                            font=("Segoe UI", 11, "bold"),
                        ).pack(side="left", padx=12, pady=10)
                    else:
                        ctk.CTkLabel(
                            row_f,
                            text=fname,
                            font=("Segoe UI", 11, "bold"),
                        ).pack(side="left", padx=12, pady=10)

                    ctk.CTkButton(
                        row_f,
                        text="View Image",
                        width=90,
                        height=28,
                        font=("Segoe UI", 10, "bold"),
                        command=lambda p=img_p: _open_path(p),
                    ).pack(side="right", padx=12, pady=10)
            else:
                ctk.CTkLabel(
                    keyframes_tab, text="No keyframe image files found.", font=("Segoe UI", 12)
                ).pack(pady=40)
        else:
            ctk.CTkLabel(
                keyframes_tab,
                text="No keyframes extracted for this course (Vision Engine was off).",
                font=("Segoe UI", 12),
                text_color=TEXT_MUTED,
            ).pack(pady=40)

    # ═════════════════════════════════════════════════════════════════════
    #  SCREEN 4: ⚙️ SETTINGS
    # ═════════════════════════════════════════════════════════════════════

    def _render_settings_screen(self) -> None:
        """Render Screen 4: Settings & System Health."""
        view_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        view_frame.pack(fill="both", expand=True)

        ctk.CTkLabel(
            view_frame,
            text="⚙️ Settings & System Health",
            font=("Segoe UI", 22, "bold"),
            text_color=TEXT_COLOR,
        ).pack(anchor="w", pady=(0, 15))

        tabview = ctk.CTkTabview(
            view_frame,
            corner_radius=CARD_RADIUS,
            segmented_button_fg_color="#0f172a",
            segmented_button_selected_color=ACCENT_COLOR,
        )
        tabview.pack(fill="both", expand=True)

        text_tab = tabview.add("Text Models")
        vision_tab = tabview.add("Vision Models")
        health_tab = tabview.add("System Health")
        tools_tab = tabview.add("Utilities")

        # Provider Pool Info
        pool = get_provider_pool_or_legacy()

        # ── Text Models Tab ──
        text_configs = [
            c for c in pool.configs if getattr(c, "capability", "text") == "text"
        ]
        ctk.CTkLabel(
            text_tab,
            text=f"Configured Text Reasoning Models ({len(text_configs)})",
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w", padx=15, pady=(15, 8))

        text_scroll = ctk.CTkScrollableFrame(text_tab, fg_color="transparent")
        text_scroll.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        for cfg in text_configs:
            k = cfg.api_key
            masked = (k[:8] + "...") if len(k) > 8 else ("*" * len(k)) if k else "None"
            f = ctk.CTkFrame(
                text_scroll,
                fg_color=CARD_BG,
                corner_radius=8,
                border_width=1,
                border_color=BORDER_COLOR,
            )
            f.pack(fill="x", pady=4)
            ctk.CTkLabel(
                f,
                text=f"{cfg.provider}  •  {cfg.model_name}  •  Key: {masked}",
                font=("Segoe UI", 11),
            ).pack(padx=12, pady=10, anchor="w")

        ctk.CTkButton(
            text_tab,
            text="Manage Provider Vault",
            font=("Segoe UI", 11, "bold"),
            fg_color=ACCENT_COLOR,
            hover_color=ACCENT_HOVER,
            command=lambda: _show_env_help_popup(self),
        ).pack(padx=15, pady=12, anchor="w")

        # ── Vision Models Tab ──
        vision_configs = [
            c for c in pool.configs if getattr(c, "capability", "text") == "vision"
        ]
        ctk.CTkLabel(
            vision_tab,
            text=f"Configured Multimodal Vision Models ({len(vision_configs)})",
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w", padx=15, pady=(15, 8))

        vision_scroll = ctk.CTkScrollableFrame(vision_tab, fg_color="transparent")
        vision_scroll.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        for cfg in vision_configs:
            k = cfg.api_key
            masked = (k[:8] + "...") if len(k) > 8 else ("*" * len(k)) if k else "None"
            f = ctk.CTkFrame(
                vision_scroll,
                fg_color=CARD_BG,
                corner_radius=8,
                border_width=1,
                border_color=BORDER_COLOR,
            )
            f.pack(fill="x", pady=4)
            ctk.CTkLabel(
                f,
                text=f"{cfg.provider}  •  {cfg.model_name}  •  Key: {masked}",
                font=("Segoe UI", 11),
            ).pack(padx=12, pady=10, anchor="w")

        ctk.CTkButton(
            vision_tab,
            text="Manage Provider Vault",
            font=("Segoe UI", 11, "bold"),
            fg_color=ACCENT_COLOR,
            hover_color=ACCENT_HOVER,
            command=lambda: _show_env_help_popup(self),
        ).pack(padx=15, pady=12, anchor="w")

        # ── System Health Tab ──
        health_frame = ctk.CTkFrame(health_tab, fg_color="transparent")
        health_frame.pack(fill="both", expand=True, padx=15, pady=15)

        # Card 1: Keyring
        h1 = ctk.CTkFrame(
            health_frame,
            fg_color=CARD_BG,
            corner_radius=CARD_RADIUS,
            border_width=1,
            border_color=BORDER_COLOR,
        )
        h1.pack(fill="x", pady=6)
        has_keys = has_stored_credentials()
        ctk.CTkLabel(
            h1,
            text=f"🔐 Windows Keyring Storage: {'🟢 Active' if has_keys else '🔴 Not Configured'}",
            font=("Segoe UI", 12, "bold"),
        ).pack(side="left", padx=15, pady=12)

        # Card 2: Playwright
        h2 = ctk.CTkFrame(
            health_frame,
            fg_color=CARD_BG,
            corner_radius=CARD_RADIUS,
            border_width=1,
            border_color=BORDER_COLOR,
        )
        h2.pack(fill="x", pady=6)
        pw_status = "🟢 Ready" if pw_ready else "🔴 Not Installed"
        ctk.CTkLabel(
            h2,
            text=f"📄 Playwright PDF Engine: {pw_status}",
            font=("Segoe UI", 12, "bold"),
        ).pack(side="left", padx=15, pady=12)
        if not pw_ready:
            ctk.CTkButton(
                h2,
                text="Install Now",
                width=100,
                font=("Segoe UI", 10, "bold"),
                command=lambda: install_pdf_library(self.log_message, self),
            ).pack(side="right", padx=15, pady=12)

        # Card 3: Ollama
        h3 = ctk.CTkFrame(
            health_frame,
            fg_color=CARD_BG,
            corner_radius=CARD_RADIUS,
            border_width=1,
            border_color=BORDER_COLOR,
        )
        h3.pack(fill="x", pady=6)
        ollama_ready = check_ollama_status()
        ollama_status = "🟢 Connected" if ollama_ready else "🔴 Offline"
        ctk.CTkLabel(
            h3,
            text=f"🦙 Local Ollama Service (11434): {ollama_status}",
            font=("Segoe UI", 12, "bold"),
        ).pack(side="left", padx=15, pady=12)

        # ── Utilities Tab ──
        util_card = ctk.CTkFrame(
            tools_tab,
            fg_color=CARD_BG,
            corner_radius=CARD_RADIUS,
            border_width=1,
            border_color=BORDER_COLOR,
        )
        util_card.pack(fill="x", padx=15, pady=15)

        ctk.CTkLabel(
            util_card,
            text="📄 Convert External Markdown (.md) to PDF",
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w", padx=15, pady=(15, 4))
        ctk.CTkLabel(
            util_card,
            text="Select any standalone Markdown file to convert to print-ready PDF.",
            font=("Segoe UI", 11),
            text_color=TEXT_MUTED,
        ).pack(anchor="w", padx=15, pady=(0, 15))

        btn_row = ctk.CTkFrame(util_card, fg_color="transparent")
        btn_row.pack(anchor="w", padx=15, pady=(0, 15))

        ctk.CTkButton(
            btn_row,
            text="👁️ Preview PDF",
            font=("Segoe UI", 11, "bold"),
            fg_color=CARD_BG,
            border_width=1,
            border_color=BORDER_COLOR,
            command=lambda: preview_pdf(
                self.log_message, self, theme=self.pdf_theme_var.get()
            ),
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_row,
            text="📥 Export PDF",
            font=("Segoe UI", 11, "bold"),
            fg_color=ACCENT_COLOR,
            hover_color=ACCENT_HOVER,
            command=lambda: convert_and_save_pdf(
                self.log_message, self, theme=self.pdf_theme_var.get()
            ),
        ).pack(side="left")


# ═══════════════════════════════════════════════════════════════════════
#  APPLICATION ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════


def main() -> None:
    """Launch YouTube Transcript to Notes desktop application."""
    app = StudySuiteApp()
    app.mainloop()


if __name__ == "__main__":
    main()
