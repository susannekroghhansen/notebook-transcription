# Notebook Transcription — Web App

A local web app that converts scanned notebook PDFs into searchable Markdown using Claude Vision, then lets you chat with and repurpose your notes in the browser.

---

## What it does

| Tab | What it does |
|-----|-------------|
| **Process** | Upload a PDF scan of your notebook → splits into pages → transcribes each page via Claude Vision → download the combined `.md` file |
| **Chat** | Load any notebook `.md` and ask questions about your notes using Claude |
| **Write** | Turn a notebook `.md` into a full article, bullet points, or article angles |

Processing runs in the background with a live progress list that updates as each page completes.

---

## Prerequisites

- Python 3.11+
- pip3
- An Anthropic API key (`sk-ant-...`) — get one at console.anthropic.com

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

**To make it permanent** (so you don't have to re-export every session), add that line to `~/.zshrc`:

```bash
echo 'export ANTHROPIC_API_KEY="sk-ant-..."' >> ~/.zshrc
source ~/.zshrc
```

---

## How to run

```bash
cd notebook-webapp
python3 -m uvicorn main:app --reload --port 8000
```

Then open **http://localhost:8000** in your browser.

---

## How to use each tab

### Process
1. Click **Choose File** and select a PDF scan of your notebook.
2. Click **Upload & Process** — the app splits the PDF into pages and sends each one to Claude Vision.
3. Watch the progress list update as pages complete. When all pages are done, a **Download** button appears.
4. Click Download to save the combined `.md` transcription file.

### Chat
1. Click **Load File** and select a previously transcribed `.md` file.
2. Type a question in the message box (e.g. "What did I write about project X?" or "List all tasks I mentioned").
3. Claude answers based on your notebook content. The full conversation history is preserved during the session.

### Write
1. Click **Load File** and select a `.md` file.
2. Choose an output format: **Full Article**, **Bullet Points**, or **Article Angles**.
3. Click **Generate** — Claude rewrites your notes into the chosen format.
4. Copy or save the output.

---

## Troubleshooting

### "Wrong folder" / module not found error
Make sure you run the command from *inside* the `notebook-webapp` directory, not from the parent folder:

```bash
# Correct:
cd notebook-webapp
python3 -m uvicorn main:app --reload --port 8000

# Wrong (will fail):
python3 -m uvicorn notebook-webapp/main:app --reload --port 8000
```

### Port already in use
If you see `[Errno 48] Address already in use`, another process is on port 8000. Either kill it or use a different port:

```bash
# Use a different port:
python3 -m uvicorn main:app --reload --port 8001
```

To find and kill whatever is using port 8000:

```bash
lsof -ti :8000 | xargs kill
```

### Auth token vs API key conflict
The app uses the standard `ANTHROPIC_API_KEY` environment variable. If you previously set `ANTHROPIC_AUTH_TOKEN` instead, the app will fail silently or return auth errors. Make sure you export the correct variable:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
# Do NOT use ANTHROPIC_AUTH_TOKEN — that variable is not read by this app
```

If both are set in your `~/.zshrc`, remove `ANTHROPIC_AUTH_TOKEN` to avoid confusion.

---

## Folder structure

```
notebook-webapp/
├── main.py            # FastAPI backend
├── requirements.txt
├── README.md
├── static/            # Frontend (HTML / CSS / JS)
│   ├── index.html
│   ├── style.css
│   └── app.js
└── data/              # Created automatically at first run
    ├── uploads/       # .md files uploaded via Chat / Write tabs
    └── jobs/          # One sub-folder per processing job
        └── <job-id>/
            ├── high-res/    # Full-resolution page JPEGs
            ├── low-res/     # Resized images sent to the API
            ├── notes/       # Per-page .md transcriptions
            └── *_complete.md
```

> The `data/` folder is excluded from git.

---

## Notes

- Rate-limit errors are handled automatically with a 60-second retry.
- Uploaded files and job outputs persist until you delete them from `data/`.
- The app uses `claude-sonnet-4-6` by default (defined as `DEFAULT_MODEL` in `main.py`).
