#!/usr/bin/env python3
"""
Notebook App — macOS menu bar controller
Requires: pip install rumps
"""

import os
import re
import shlex
import subprocess
import time
import urllib.request
import webbrowser
from typing import Optional

import rumps

APP_URL = "http://localhost:8000"
PORT = 8000


# ── Helpers ────────────────────────────────────────────────────────────────────

def load_api_key_from_zshrc() -> Optional[str]:
    """Parse ANTHROPIC_API_KEY from ~/.zshrc if not already in environment."""
    zshrc = os.path.expanduser("~/.zshrc")
    try:
        text = open(zshrc).read()
        match = re.search(
            r'export\s+ANTHROPIC_API_KEY\s*=\s*["\']?([^"\'\s]+)["\']?', text
        )
        if match:
            return match.group(1)
    except FileNotFoundError:
        pass
    return None


def get_server_pid() -> Optional[int]:
    """Return PID of the process listening on PORT, or None."""
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{PORT}"],
            capture_output=True, text=True
        )
        pid_str = result.stdout.strip()
        if pid_str:
            return int(pid_str.split()[0])
    except (ValueError, IndexError):
        pass
    return None


def server_running() -> bool:
    return get_server_pid() is not None


def start_server(api_key: Optional[str]):
    env = os.environ.copy()
    if api_key:
        env["ANTHROPIC_API_KEY"] = api_key

    # Determine the directory this script lives in
    app_dir = os.path.dirname(os.path.abspath(__file__))

    subprocess.Popen(
        ["/usr/bin/python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", str(PORT)],
        cwd=app_dir,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def stop_server():
    pid = get_server_pid()
    if pid:
        subprocess.run(["kill", str(pid)])


# ── Menu bar app ───────────────────────────────────────────────────────────────

class NotebookMenuBar(rumps.App):
    def __init__(self):
        # Load API key once at startup
        self.api_key = os.environ.get("ANTHROPIC_API_KEY") or load_api_key_from_zshrc()

        super().__init__(
            name="Notebook App",
            title=self.get_icon(),
            quit_button=None,       # We manage Quit ourselves
        )

        self.menu = [
            rumps.MenuItem("Open Notebook App", callback=self.open_app),
            rumps.MenuItem("Stop Server",        callback=self.stop_app),
            None,                               # separator
            rumps.MenuItem("Quit",               callback=self.quit_app),
        ]

        # Poll server state every 5 seconds
        self._timer = rumps.Timer(self._refresh, 5)
        self._timer.start()
        self._refresh(None)

    # ── Icon / status ──────────────────────────────────────────────────────────

    def get_icon(self) -> str:
        """Return a title string with a coloured dot + notebook emoji."""
        dot = "🟢" if server_running() else "⚫"
        return f"{dot} 📓"

    def _refresh(self, _):
        self.title = self.get_icon()
        running = server_running()
        self.menu["Stop Server"].set_callback(self.stop_app if running else None)

    # ── Menu callbacks ─────────────────────────────────────────────────────────

    @rumps.clicked("Open Notebook App")
    def open_app(self, _):
        if not server_running():
            rumps.notification(
                title="Notebook App",
                subtitle="Starting server…",
                message="Opening browser in a moment.",
            )
            start_server(self.api_key)

        # Poll HTTP until server responds (max 15 s)
        for _ in range(30):
            try:
                urllib.request.urlopen(APP_URL, timeout=1)
                break
            except Exception:
                time.sleep(0.5)

        print("Opening browser...", flush=True)
        subprocess.run(["open", APP_URL])
        webbrowser.open(APP_URL)
        self._refresh(None)

    @rumps.clicked("Stop Server")
    def stop_app(self, _):
        stop_server()
        self._refresh(None)
        rumps.notification(
            title="Notebook App",
            subtitle="Server stopped",
            message="",
        )

    @rumps.clicked("Quit")
    def quit_app(self, _):
        stop_server()
        rumps.quit_application()


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    NotebookMenuBar().run()
