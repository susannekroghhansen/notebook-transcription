#!/usr/bin/env python3
"""
Notebook App — py2app entry point.
Double-clicking the .app bundle starts the uvicorn server and opens the browser.
No terminal window required.
"""

import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

APP_URL = "http://localhost:8000"
PORT = 8000


def resources_dir() -> str:
    """
    Return the Resources directory for this process.
    When frozen by py2app: Contents/MacOS/<exe>  →  ../Resources
    When running from source: same directory as this file.
    """
    if getattr(sys, "frozen", False):
        return os.path.normpath(
            os.path.join(os.path.dirname(sys.executable), "..", "Resources")
        )
    return os.path.dirname(os.path.abspath(__file__))


def load_api_key() -> None:
    """Inject ANTHROPIC_API_KEY from ~/.zshrc if not already set."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    zshrc = os.path.expanduser("~/.zshrc")
    try:
        text = open(zshrc).read()
        m = re.search(
            r'export\s+ANTHROPIC_API_KEY\s*=\s*["\']?([^"\'\s]+)["\']?', text
        )
        if m:
            os.environ["ANTHROPIC_API_KEY"] = m.group(1)
    except FileNotFoundError:
        pass


def wait_and_open() -> None:
    """Poll until the server responds (max 15 s), then open the browser."""
    for _ in range(30):
        try:
            urllib.request.urlopen(APP_URL, timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    subprocess.run(["open", APP_URL])
    webbrowser.open(APP_URL)


def main() -> None:
    res = resources_dir()

    # Make bundled modules (main.py, etc.) importable and set the working
    # directory so that main.py's Path(__file__).parent resolves correctly.
    os.chdir(res)
    sys.path.insert(0, res)

    load_api_key()

    # Open the browser in the background while the server starts.
    threading.Thread(target=wait_and_open, daemon=True).start()

    # Run uvicorn in-process (blocks until the server exits / app is quit).
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)


if __name__ == "__main__":
    main()
