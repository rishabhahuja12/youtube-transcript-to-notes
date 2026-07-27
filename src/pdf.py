"""
PDF conversion module for markdown documents.

Provides Playwright HTML-to-PDF rendering and CSS styling themes.
"""

import os
import re
import sys
import tempfile
from typing import Optional

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_shared_pdf_css(theme: str = "Textbook") -> str:
    """Get CSS rules for Markdown to PDF conversion.

    Args:
        theme: Visual theme name ("Textbook", "ChatGPT Dark", or "Minimal Mono").

    Returns:
        str: Custom CSS styling block string.
    """
    base_css = """
    body {
        font-family: 'Segoe UI', Helvetica, sans-serif;
        line-height: 1.5;
    }
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


def convert_md_to_pdf(md_path: str, theme: str = "Textbook", pdf_path: Optional[str] = None) -> str:
    """Convert a markdown file to a PDF using Playwright rendering.

    Args:
        md_path: Absolute path to the source markdown file.
        theme: CSS theme name ("Textbook", "ChatGPT Dark", "Minimal Mono").
        pdf_path: Optional destination PDF file path. Defaults to replacing .md extension with .pdf.

    Returns:
        str: Path to the generated PDF file.
    """
    if pdf_path is None:
        pdf_path = md_path.rsplit(".", 1)[0] + ".pdf"

    import asyncio
    asyncio.set_event_loop(asyncio.new_event_loop())

    venv_site = os.path.join(SCRIPT_DIR, ".venv", "Lib", "site-packages")
    if os.path.exists(venv_site) and venv_site not in sys.path:
        sys.path.append(venv_site)

    import markdown
    from playwright.sync_api import sync_playwright

    with open(md_path, "r", encoding="utf-8", errors="replace") as f:
        md_content = f.read()

    # Sanitize markdown: escape any raw script/iframe tags to prevent XSS before rendering
    md_content = re.sub(r'<(/?(?:script|iframe|object|embed|applet|style)[^>]*)>', r'&lt;\1&gt;', md_content, flags=re.IGNORECASE)

    html_body = markdown.markdown(md_content, extensions=["fenced_code", "tables"])
    custom_css = get_shared_pdf_css(theme)

    html_content = (
        "<!DOCTYPE html>"
        "<html>"
        "<head>"
        "<meta charset=\"utf-8\">"
        "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'; img-src data: file:; script-src 'none'\">"
        f"<style>{custom_css}</style>"
        "</head>"
        "<body>"
        f"{html_body}"
        "</body>"
        "</html>"
    )

    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".html", encoding="utf-8") as f:
        f.write(html_content)
        temp_html = f.name

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"file://{temp_html}", wait_until="networkidle")
            page.pdf(path=pdf_path, format="A4", print_background=True, prefer_css_page_size=True)
            browser.close()
    finally:
        if os.path.exists(temp_html):
            os.remove(temp_html)

    return pdf_path
