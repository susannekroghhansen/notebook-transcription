# Notebook — Web App

A local macOS app that converts scanned notebook PDFs into searchable Markdown using Claude Vision, then lets you chat with and repurpose your notes in the browser.

---

## What it does

| Tab | What it does |
|-----|-------------|
| **Library** | Browse all transcribed notebooks in a card grid — with AI-generated topic tags, page counts, and quick actions to open in Chat, Write, or download |
| **Process** | Upload a PDF scan → splits into pages → transcribes each page via Claude Vision → saves a combined `.md` file |
| **Chat** | Select one or more notebooks from a multi-notebook picker and ask questions about your notes using Claude |
| **Write** | Select one or more notebooks and generate a full article, bullet points, or article angles from the combined content |

Processing runs in the background with a live per-page progress list. Tags are generated automatically on first library load and cached alongside each notebook.

---

## Prerequisites

- Python 3.11+
- An Anthropic API key (`sk-ant-...`) — get one at [console.anthropic.com](https://console.anthropic.com)

---

## Installation

From inside the `notebook-webapp` folder:

```bash
pip3 install -r requirements.txt
```

---

## Configuration

Export your Anthropic API key before running the app:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

**To make it permanent**, add that line to `~/.zshrc`:

```bash
echo 'export ANTHROPIC_API_KEY="sk-ant-..."' >> ~/.zshrc
source ~/.zshrc
```

The macOS app bundle reads the key directly from `~/.zshrc` automatically, so you only need to set it once.

---

## How to launch

There are three ways to run the app:

### Option 1 — Dock / Finder app (recommended)

Double-click **`Notebook App.app`** in the `notebook-webapp` folder (or drag it to your Dock). It starts the server silently and opens `http://localhost:8000` in your browser. No terminal window required.

To build or rebuild the `.app` bundle after code changes:

```bash
cd notebook-webapp
python3 setup.py py2app
```

### Option 2 — .command launcher

Double-click **`Launch Notebook App.command`** in the `notebook-webapp` folder. A terminal window opens, starts the server, and launches the browser. Close the terminal window to stop.

### Option 3 — Terminal

```bash
cd notebook-webapp
uvicorn main:app --reload --port 8000
```

Then open **http://localhost:8000** in your browser.

---

## Menu bar app

**`Start Menu Bar App.command`** launches a lightweight menu bar controller (requires `pip install rumps`). It adds a notebook icon to the macOS menu bar with options to open the app, start/stop the server, and quit. Useful if you want the app always available without a terminal window.

---

## How to use each tab

### Library

The Library loads automatically when you switch to it and shows all completed notebooks as cards. Each card displays:

- **Notebook name** and metadata (page count, date)
- **10 AI-generated topic tags** as muted-pink pill badges — generated once via Claude and cached in `tags.json` per notebook
- **Action buttons** — Open in Chat, Open in Write, Download `.md`

Tags are generated the first time the Library loads after a notebook is processed. Subsequent loads are instant from the cache.

### Process

1. Drag and drop a PDF (or click to browse) into the upload area.
2. Fill in the Notebook ID, Date, and Topic fields.
3. Click **Transcribe notebook** — the app splits the PDF into pages and transcribes each one via Claude Vision.
4. Watch the per-page progress list. When complete, use the action buttons to download the `.md`, open it in Chat, or open it in Write.

### Chat

1. Click the **Select notebooks…** dropdown.
2. Check one or more notebooks (or tick **Select all**).
3. Click **Load into chat** — the selected notebooks' content is combined and sent as context to Claude.
4. Selected notebooks appear as **removable pink pills** above the chat. Click × on any pill to remove that notebook from the context.
5. Ask anything: "What did I write about X?", "Summarise the key ideas", "Are there any diagrams?" etc.

When you switch to Chat via **Open in Chat** from the Library or Process tab, that notebook loads directly and appears as a pill.

### Write

1. Click the **Select notebooks…** dropdown and select one or more notebooks.
2. Click **Load for writing** — the selected notebooks appear as pink pills.
3. Optionally enter a **Topic / Focus**.
4. Choose an **Output type** (Full Article, Bullet Points, Article Angles) and **Tone**.
5. Click **Generate** — Claude synthesises content from all selected notebooks.
6. Copy or download the output.

---

## Folder structure

```
notebook-webapp/
├── main.py                      # FastAPI backend
├── launcher.py                  # py2app entry point (runs uvicorn in-process)
├── menubar.py                   # Menu bar controller (requires rumps)
├── setup.py                     # py2app build config
├── requirements.txt
├── README.md
├── Notebook App.app             # macOS app bundle (double-click to launch)
├── Launch Notebook App.command  # Terminal-based launcher
├── Start Menu Bar App.command   # Menu bar app launcher
├── Stop Notebook App.command    # Kills the server process
├── static/                      # Frontend (HTML / CSS / JS)
│   ├── index.html
│   ├── style.css
│   └── app.js
└── data/                        # Created automatically at first run
    ├── uploads/                 # .md files uploaded manually
    └── jobs/                    # One sub-folder per processing job
        └── <job-id>/
            ├── meta.json        # Notebook ID, date, topic
            ├── tags.json        # Cached AI-generated topic tags
            ├── high-res/        # Full-resolution page JPEGs
            ├── low-res/         # Resized images sent to Claude
            ├── notes/           # Per-page .md transcriptions
            └── *_complete.md    # Combined transcription
```

> The `data/` folder is excluded from git.

---

## Troubleshooting

### "Wrong folder" / module not found

Run the command from *inside* the `notebook-webapp` directory:

```bash
cd notebook-webapp
uvicorn main:app --reload --port 8000
```

### Port already in use

```bash
# Kill whatever is on port 8000:
lsof -ti :8000 | xargs kill

# Or use a different port:
uvicorn main:app --reload --port 8001
```

### API key not found

The app reads `ANTHROPIC_API_KEY` from the environment. If the key is set in `~/.zshrc` but not picked up by the terminal, run:

```bash
source ~/.zshrc
```

The `.app` bundle reads `~/.zshrc` directly, so the key is always available without a manual export.

### Rate limit errors

Rate-limit errors (HTTP 429) are handled automatically with a 60-second retry per page. If you have many pages and hit limits frequently, consider processing smaller PDFs.

---

## Notes

- The app uses `claude-sonnet-4-6` by default (defined as `DEFAULT_MODEL` in `main.py`).
- Uploaded files and job outputs persist in `data/` until you delete them.
- Tags are generated with `max_tokens=256` and cached in `tags.json` — delete `tags.json` from a job folder to force regeneration.
