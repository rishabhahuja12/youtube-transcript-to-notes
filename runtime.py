"""Resolve and manage runtimes shipped with, or used by, StudySuite."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

POT_HOST = "127.0.0.1"
POT_PORT = 4416
POT_BASE_URL = f"http://{POT_HOST}:{POT_PORT}"


class RuntimeSetupError(RuntimeError):
    """Raised when a required packaged/developer runtime is unavailable."""


def application_root() -> Path:
    """Resolve the root directory of the application environment."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root)
    return Path(__file__).resolve().parent


def runtime_root() -> Path:
    """Resolve the root path of packaged runtime binaries."""
    return application_root() / "runtime"


def resolve_node() -> str:
    """Resolve bundled Node first, then a system Node for developer mode."""
    node_name = "node.exe" if os.name == "nt" else "node"
    bundled = runtime_root() / "node" / node_name
    if bundled.is_file():
        return str(bundled)
    system = shutil.which("node")
    if system:
        return system
    raise RuntimeSetupError(
        "Node.js runtime is missing. Reinstall the StudySuite release bundle, "
        "or install the pinned developer Node runtime and run scripts/setup.ps1."
    )


def resolve_pot_server() -> Path:
    """Resolve the filesystem path to the PO Token server entry script."""
    server = runtime_root() / "bgutil-ytdlp-pot-provider" / "server" / "build" / "main.js"
    if not server.is_file():
        raise RuntimeSetupError(
            "The bundled PO Token provider is missing. Reinstall StudySuite; "
            "transcript extraction cannot start without it."
        )
    return server


def start_pot_server(*, node: Optional[str] = None, server: Optional[Path] = None,
                     timeout: float = 10.0) -> subprocess.Popen:
    """Start the local PO Token server and wait until its /ping endpoint is ready."""
    server_path = server or resolve_pot_server()
    process = subprocess.Popen(
        [node or resolve_node(), str(server_path)],
        cwd=str(server_path.parent.parent),
        stdout=None,
        stderr=None,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        wait_for_pot_server(process, timeout=timeout)
    except Exception:
        terminate_process(process)
        raise
    return process


def wait_for_pot_server(process: subprocess.Popen, *, timeout: float = 10.0) -> None:
    """Poll the PO Token server endpoint until it reports ready or times out."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeSetupError("The bundled PO Token provider exited before becoming ready.")
        try:
            with urllib.request.urlopen(f"{POT_BASE_URL}/ping", timeout=0.5) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.1)
    raise RuntimeSetupError("The PO Token provider did not respond to /ping within 10 seconds.")


def terminate_process(process: Optional[subprocess.Popen]) -> None:
    """Safely terminate a background subprocess with graceful SIGTERM and fallback SIGKILL."""
    if not process or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)

