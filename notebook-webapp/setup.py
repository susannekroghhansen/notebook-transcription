"""
py2app build script for Notebook App.

Build the .app bundle:
    python3 setup.py py2app

The finished app lands in dist/Notebook App.app
Drag it to /Applications or keep it anywhere — double-click to launch.
"""

import glob
import os
from collections import defaultdict

from setuptools import setup

# ── Entry point ────────────────────────────────────────────────────────────────

APP = ["launcher.py"]

# ── Data files ─────────────────────────────────────────────────────────────────
# Include main.py (the FastAPI app) and the entire static/ tree.
# py2app places these into Contents/Resources/ at the given sub-path.
# main.py's Path(__file__).parent will resolve to Contents/Resources/,
# so static/ and data/ (created at runtime) land right next to it.

def collect_tree(src_dir: str) -> list[tuple[str, list[str]]]:
    """Return [(dest_dir, [files]), ...] for every file under src_dir."""
    groups: dict[str, list[str]] = defaultdict(list)
    for path in glob.glob(f"{src_dir}/**/*", recursive=True):
        if os.path.isfile(path):
            groups[os.path.dirname(path)].append(path)
    return list(groups.items())


DATA_FILES = [
    ("", ["main.py"]),          # → Contents/Resources/main.py
    *collect_tree("static"),    # → Contents/Resources/static/…
]

# ── py2app options ─────────────────────────────────────────────────────────────

OPTIONS = {
    # Don't emulate argv / Apple Events — not needed for a web-server launcher.
    "argv_emulation": False,

    # Don't auto-chdir; launcher.py handles that itself.
    "no_chdir": True,

    # Packages that main.py imports (py2app can't scan it automatically
    # because it's included as a data file, not as the entry-point module).
    "packages": [
        "fastapi",
        "uvicorn",
        "starlette",
        "anthropic",
        "fitz",          # PyMuPDF
        "PIL",           # Pillow
        "multipart",     # python-multipart
        "anyio",
        "httpx",
        "httpcore",
        "h11",
        "pydantic",
        "pydantic_core",
        "sniffio",
        "certifi",
        "charset_normalizer",
        "idna",
        "click",
        "typing_extensions",
    ],

    # Explicit modules that py2app's static analyser might miss.
    "includes": [
        "uvicorn.main",
        "uvicorn.config",
        "uvicorn.server",
        "uvicorn.lifespan.on",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websockets.websockets_impl",
        "email.mime.text",
        "email.mime.multipart",
    ],

    # macOS app metadata.
    "plist": {
        "CFBundleName": "Notebook App",
        "CFBundleDisplayName": "Notebook App",
        "CFBundleIdentifier": "com.notebook.app",
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "10.15.0",
        # Show in Dock while running (no tray icon needed).
        "LSUIElement": False,
    },
}

# ── Setup call ─────────────────────────────────────────────────────────────────

setup(
    name="Notebook App",
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
