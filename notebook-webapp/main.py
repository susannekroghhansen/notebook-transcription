#!/usr/bin/env python3
"""
Notebook Transcription Web App — FastAPI backend

Run with:
    cd notebook-webapp
    uvicorn main:app --reload --port 8000
"""

import asyncio
import base64
import json
import os
import re
import traceback
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

import anthropic
import fitz  # PyMuPDF
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

try:
    import torch
    from diffusers import StableDiffusionPipeline
    _HAS_SD = True
except ImportError:
    _HAS_SD = False

# ── Configuration ──────────────────────────────────────────────────────────────

HIGH_RES_DPI = 200
MAX_DIMENSION = 1024
DEFAULT_MODEL = "claude-sonnet-4-6"

BASE_DIR          = Path(__file__).parent
DATA_DIR          = BASE_DIR / "data"
STATIC_DIR        = BASE_DIR / "static"
ILLUSTRATIONS_DIR = DATA_DIR / "illustrations"
MODELS_DIR        = DATA_DIR / "models"

SD_MODEL_ID = "runwayml/stable-diffusion-v1-5"

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
Image.MAX_IMAGE_PIXELS = None

SYSTEM_PROMPT = """You are an expert visual analyst specialising in sketchnotes, visual thinking,
and hand-drawn notebook documentation. Your task is to produce rich, structured markdown
descriptions of notebook pages that can fully substitute for the original image when a future
reader or LLM cannot see the image itself.

You document every page using this exact four-part structure:

1. TRANSCRIPTION — Accurate, verbatim capture of all text, organised spatially (e.g. by page
   side, section, or visual region). Use blockquotes for transcribed text.

2. ILLUSTRATION DESCRIPTIONS — Accurate, detailed descriptions of every hand-drawn visual:
   what it depicts, its position on the page, and any labels or annotations attached to it.

3. MEANING & INTERPRETATION — The meaning conveyed through the relationship between text,
   illustrations, and layout. What argument or idea does the page communicate as a whole?
   How do the visual and textual elements reinforce each other?

4. VISUAL STYLE — Colours used, medium (e.g. pen, marker, highlighter), composition,
   typography style, and overall aesthetic character.

Be thorough and specific. Richness of description is the priority."""

USER_PROMPT = """Please document this notebook page as a rich markdown file using the four-part
structure: Full Text Transcription, Illustration Descriptions, Meaning & Interpretation,
and Visual Style & Composition.

Start the document with a title heading derived from the main subject of the page,
followed by key metadata (source filename, page numbers if visible, visual format).

The output must be detailed enough that a reader who cannot see the image can fully
understand both the content and the visual design of the page."""

# ── App setup ──────────────────────────────────────────────────────────────────

app = FastAPI(title="Notebook Transcription")

client = anthropic.AsyncAnthropic(
    api_key=os.environ.get("ANTHROPIC_API_KEY")
)

# In-memory job store: job_id -> job dict
jobs: dict[str, dict] = {}

# Ensure data directories exist at startup
for d in [DATA_DIR, DATA_DIR / "uploads", DATA_DIR / "jobs",
          ILLUSTRATIONS_DIR, MODELS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── Stable Diffusion pipeline (lazy-loaded on first request) ───────────────────

_sd_pipeline = None
_sd_load_lock  = asyncio.Lock()   # prevents concurrent model loads
_sd_infer_lock = asyncio.Lock()   # prevents concurrent inference (OOM guard)


async def _get_sd_pipeline():
    """Return the loaded SD pipeline, loading it on first call."""
    global _sd_pipeline
    if _sd_pipeline is not None:
        return _sd_pipeline

    async with _sd_load_lock:
        if _sd_pipeline is not None:          # double-check after acquiring lock
            return _sd_pipeline

        def _load():
            if torch.backends.mps.is_available():
                device, dtype = "mps", torch.float16
            elif torch.cuda.is_available():
                device, dtype = "cuda", torch.float16
            else:
                device, dtype = "cpu", torch.float32

            print(f"[SD] Loading {SD_MODEL_ID} → {device} ({dtype}) …")
            pipe = StableDiffusionPipeline.from_pretrained(
                SD_MODEL_ID,
                torch_dtype=dtype,
                cache_dir=str(MODELS_DIR),
                safety_checker=None,
                requires_safety_checker=False,
            )
            pipe = pipe.to(device)
            pipe.enable_attention_slicing()
            print(f"[SD] Pipeline ready on {device}")
            return pipe

        _sd_pipeline = await asyncio.to_thread(_load)
        return _sd_pipeline


# ── Helper functions ───────────────────────────────────────────────────────────

def split_pdf_sync(
    pdf_path: Path, output_dir: Path, notebook: str, date: str, topic: str
) -> list[Path]:
    """Split PDF into per-page JPEG files. Runs in a thread."""
    output_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(pdf_path))
    pages: list[Path] = []
    for i, page in enumerate(doc, 1):
        filename = f"{notebook}_{date}_p{i:02d}_{topic}.jpg"
        pix = page.get_pixmap(dpi=HIGH_RES_DPI)
        out_path = output_dir / filename
        pix.save(str(out_path))
        pages.append(out_path)
    doc.close()
    return pages


def create_low_res_sync(image_path: Path, output_dir: Path) -> Path:
    """Resize an image to MAX_DIMENSION. Runs in a thread."""
    output_dir.mkdir(parents=True, exist_ok=True)
    img = Image.open(image_path).convert("RGB")
    img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.LANCZOS)
    out_path = output_dir / image_path.name
    img.save(str(out_path), format="JPEG", quality=85)
    return out_path


async def transcribe_image(image_path: Path) -> str:
    """Send a single image to Claude and return the markdown transcription."""
    with open(image_path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")
    message = await client.messages.create(
        model=DEFAULT_MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_data,
                        },
                    },
                    {"type": "text", "text": USER_PROMPT},
                ],
            }
        ],
    )
    return message.content[0].text


# ── Background job runner ──────────────────────────────────────────────────────

async def run_job(job_id: str, pdf_path: Path, notebook: str, date: str, topic: str):
    job = jobs[job_id]
    queue: asyncio.Queue = job["queue"]
    job_dir = DATA_DIR / "jobs" / job_id
    high_res_dir = job_dir / "high-res"
    low_res_dir  = job_dir / "low-res"
    notes_dir    = job_dir / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)

    async def emit(event: dict):
        await queue.put(event)

    try:
        # 1. Split PDF
        await emit({"type": "status", "message": "Splitting PDF into page images…"})
        high_res_pages = await asyncio.to_thread(
            split_pdf_sync, pdf_path, high_res_dir, notebook, date, topic
        )

        # 2. Initialise page state
        page_states = [
            {"index": i + 1, "filename": p.name, "status": "waiting"}
            for i, p in enumerate(high_res_pages)
        ]
        job["pages"] = page_states
        await emit({"type": "pages_init", "pages": page_states})

        # 3. Transcribe each page
        saved_notes: list[Path] = []

        for i, high_res_path in enumerate(high_res_pages):
            page_num = i + 1
            job["pages"][i]["status"] = "processing"
            await emit({"type": "page_update", "index": page_num, "status": "processing"})

            low_res_path: Path | None = None
            try:
                low_res_path = await asyncio.to_thread(
                    create_low_res_sync, high_res_path, low_res_dir
                )
                markdown = await transcribe_image(low_res_path)
                out_name = f"{high_res_path.stem}_notebook.md"
                out_path = notes_dir / out_name
                header = f"<!-- source: {high_res_path.name} -->\n\n"
                out_path.write_text(header + markdown, encoding="utf-8")
                job["pages"][i]["status"] = "done"
                saved_notes.append(out_path)
                await emit({"type": "page_update", "index": page_num, "status": "done"})

            except anthropic.RateLimitError:
                job["pages"][i]["status"] = "retrying"
                await emit({
                    "type": "page_update",
                    "index": page_num,
                    "status": "retrying",
                    "message": "Rate limited — waiting 60 s…",
                })
                await asyncio.sleep(60)
                try:
                    if low_res_path is None:
                        low_res_path = await asyncio.to_thread(
                            create_low_res_sync, high_res_path, low_res_dir
                        )
                    markdown = await transcribe_image(low_res_path)
                    out_name = f"{high_res_path.stem}_notebook.md"
                    out_path = notes_dir / out_name
                    out_path.write_text(
                        f"<!-- source: {high_res_path.name} -->\n\n" + markdown,
                        encoding="utf-8",
                    )
                    job["pages"][i]["status"] = "done"
                    saved_notes.append(out_path)
                    await emit({"type": "page_update", "index": page_num, "status": "done"})
                except Exception as e2:
                    job["pages"][i]["status"] = "error"
                    job["pages"][i]["error"] = str(e2)
                    await emit({
                        "type": "page_update",
                        "index": page_num,
                        "status": "error",
                        "error": str(e2),
                    })

            except Exception as e:
                job["pages"][i]["status"] = "error"
                job["pages"][i]["error"] = str(e)
                await emit({
                    "type": "page_update",
                    "index": page_num,
                    "status": "error",
                    "error": str(e),
                })

            # Brief delay between pages to respect rate limits
            if i < len(high_res_pages) - 1:
                await asyncio.sleep(2)

        # 4. Combine all notes
        if saved_notes:
            await emit({"type": "status", "message": "Combining pages into one file…"})
            parts = [p.read_text(encoding="utf-8") for p in sorted(saved_notes)]
            combined = "\n\n---\n\n".join(parts)
            combined_path = job_dir / f"{notebook}_{date}_complete.md"
            combined_path.write_text(combined, encoding="utf-8")
            job["combined_path"] = str(combined_path)
            job["combined_name"] = combined_path.name
            job["combined_content"] = combined

        job["status"] = "done"
        await emit({
            "type": "done",
            "combined_name": job.get("combined_name"),
            "pages_done": len(saved_notes),
            "pages_total": len(high_res_pages),
        })

    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
        await emit({"type": "error", "message": str(e)})


# ── Process routes ─────────────────────────────────────────────────────────────

@app.post("/api/process/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    notebook: str = Form(default="NB"),
    date: str = Form(default="UnknownDate"),
    topic: str = Form(default="notebook"),
):
    try:
        print("Upload endpoint hit")
        print("file:", file)
        print("file.filename:", file.filename)
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(400, "Only PDF files are supported")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        job_id = f"{notebook}_{date}_{timestamp}"
        job_dir = DATA_DIR / "jobs" / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        pdf_path = job_dir / file.filename
        content = await file.read()
        pdf_path.write_bytes(content)

        meta = {"notebook": notebook, "date": date, "topic": topic, "job_id": job_id}
        (job_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

        jobs[job_id] = {
            "id": job_id,
            "status": "pending",
            "filename": file.filename,
            "pages": [],
            "combined_path": None,
            "combined_name": None,
            "combined_content": None,
            "error": None,
            "queue": asyncio.Queue(),
        }

        asyncio.create_task(run_job(job_id, pdf_path, notebook, date, topic))
        return {"job_id": job_id}

    except HTTPException:
        raise
    except Exception as e:
        print("UPLOAD ERROR:", str(e))
        traceback.print_exc()
        raise HTTPException(500, f"Upload failed: {e}") from e


@app.get("/api/process/stream/{job_id}")
async def stream_progress(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")

    job = jobs[job_id]
    queue: asyncio.Queue = job["queue"]

    async def generate() -> AsyncGenerator[str, None]:
        # Send a snapshot of current state immediately so late-connecting clients
        # can reconstruct progress without missing any events.
        snapshot = {k: v for k, v in job.items() if k not in ("queue", "combined_content")}
        yield f"data: {json.dumps({'type': 'snapshot', 'job': snapshot})}\n\n"

        # If job already finished, send a terminal event and close.
        if job["status"] in ("done", "error"):
            terminal = {"type": job["status"]}
            if job["status"] == "done":
                terminal["combined_name"] = job.get("combined_name")
            else:
                terminal["message"] = job.get("error", "Unknown error")
            yield f"data: {json.dumps(terminal)}\n\n"
            return

        # Stream live events from the queue.
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") in ("done", "error"):
                    break
            except asyncio.TimeoutError:
                # Keep-alive heartbeat
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
                if job["status"] in ("done", "error"):
                    break

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/process/download/{job_id}")
async def download_combined(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    job = jobs[job_id]
    path = job.get("combined_path")
    if not path or not Path(path).exists():
        raise HTTPException(400, "No combined file available yet")
    return FileResponse(Path(path), filename=job["combined_name"], media_type="text/markdown")


@app.get("/api/process/content/{job_id}")
async def get_job_content(job_id: str):
    """Return combined .md content for a finished job (used by Chat / Write tabs)."""
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    job = jobs[job_id]
    if not job.get("combined_content"):
        raise HTTPException(400, "No content available yet")
    return {"content": job["combined_content"], "name": job.get("combined_name", "notebook.md")}


# ── Chat route ─────────────────────────────────────────────────────────────────

@app.post("/api/chat")
async def chat(request: dict):
    context: str = request.get("context", "")
    messages: list = request.get("messages", [])
    if not messages:
        raise HTTPException(400, "No messages provided")

    system = (
        "You are a helpful assistant answering questions about a handwritten notebook.\n"
        "The following is the full transcription of the notebook in markdown format:\n\n"
        f"<notebook>\n{context}\n</notebook>\n\n"
        "Answer accurately based on the notebook content. "
        "Reference specific pages or sections when relevant."
    )

    response = await client.messages.create(
        model=DEFAULT_MODEL,
        max_tokens=2048,
        system=system,
        messages=messages,
    )
    return {"reply": response.content[0].text}


# ── Write route ────────────────────────────────────────────────────────────────

@app.post("/api/write")
async def write_content(request: dict):
    context: str     = request.get("context", "")
    topic: str       = request.get("topic", "")
    output_type: str = request.get("output_type", "full article")
    tone: str        = request.get("tone", "professional")

    type_map = {
        "full article": (
            "Write a complete, well-structured article with an engaging introduction, "
            "developed body sections, and a memorable conclusion."
        ),
        "bullet points": (
            "Write a concise, well-organised bullet-point summary. "
            "Group key takeaways by theme with clear section headings."
        ),
        "article angles": (
            "Generate 5 distinct article angles or pitch ideas. "
            "For each: a compelling headline and a 2-3 sentence pitch explaining the angle."
        ),
    }
    tone_map = {
        "professional": (
            "Use a professional, authoritative tone suited for a business or thought-leadership audience."
        ),
        "conversational": (
            "Use a warm, conversational tone — as if explaining to a curious, intelligent friend."
        ),
        "inspirational": (
            "Use an energising, motivational tone that uplifts and moves the reader to action."
        ),
    }

    system = (
        "You are a skilled writer who transforms raw notebook ideas into polished written content.\n"
        "Here is the notebook to draw from:\n\n"
        f"<notebook>\n{context}\n</notebook>\n\n"
        f"{type_map.get(output_type, type_map['full article'])} "
        f"{tone_map.get(tone, tone_map['professional'])}"
    )
    user_msg = (
        f"Write about this topic/focus: {topic}"
        if topic
        else "Write about the main themes and key insights from this notebook."
    )

    response = await client.messages.create(
        model=DEFAULT_MODEL,
        max_tokens=3000,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )
    return {"content": response.content[0].text}


# ── File management routes ─────────────────────────────────────────────────────

@app.post("/api/files/upload")
async def upload_md_file(file: UploadFile = File(...)):
    if not file.filename or not file.filename.endswith(".md"):
        raise HTTPException(400, "Only .md files are supported")
    save_path = DATA_DIR / "uploads" / file.filename
    raw = await file.read()
    save_path.write_bytes(raw)
    return {
        "filename": file.filename,
        "path": str(save_path),
        "content": raw.decode("utf-8"),
    }


@app.get("/api/files/list")
async def list_md_files():
    files = []
    uploads_dir = DATA_DIR / "uploads"
    if uploads_dir.exists():
        for f in sorted(uploads_dir.glob("*.md")):
            files.append({"name": f.name, "path": str(f), "source": "upload"})
    jobs_dir = DATA_DIR / "jobs"
    if jobs_dir.exists():
        for job_dir in sorted(jobs_dir.iterdir(), reverse=True):
            if job_dir.is_dir():
                for f in job_dir.glob("*_complete.md"):
                    files.append({"name": f.name, "path": str(f), "source": "processed"})
    return {"files": files}


@app.get("/api/files/content")
async def get_file_content(path: str):
    file_path = Path(path)
    if not file_path.exists():
        raise HTTPException(404, "File not found")
    if file_path.suffix != ".md":
        raise HTTPException(400, "Not a markdown file")
    # Security: must be inside the data directory
    try:
        file_path.resolve().relative_to(DATA_DIR.resolve())
    except ValueError:
        raise HTTPException(403, "Access denied")
    return {"content": file_path.read_text(encoding="utf-8"), "name": file_path.name}


# ── Library routes ─────────────────────────────────────────────────────────────

def _resolve_job_dir(job_id: str) -> Path:
    """Safely resolve a job directory, blocking path traversal."""
    jobs_base = (DATA_DIR / "jobs").resolve()
    job_dir = jobs_base / job_id
    try:
        job_dir.resolve().relative_to(jobs_base)
    except ValueError:
        raise HTTPException(403, "Access denied")
    if not job_dir.exists() or not job_dir.is_dir():
        raise HTTPException(404, "Job not found")
    return job_dir


async def _generate_tags(job_dir: Path, combined_path: Path) -> list[str]:
    """Return cached tags or generate + cache them via Claude."""
    tags_path = job_dir / "tags.json"
    if tags_path.exists():
        return json.loads(tags_path.read_text(encoding="utf-8"))

    content = combined_path.read_text(encoding="utf-8")[:6000]
    response = await client.messages.create(
        model=DEFAULT_MODEL,
        max_tokens=256,
        messages=[{
            "role": "user",
            "content": (
                "Extract exactly 10 short topic tags from this notebook transcription. "
                "Return only a JSON array of 10 strings, each 1-3 words. No other text.\n\n"
                + content
            ),
        }],
    )
    raw = response.content[0].text.strip()
    try:
        tags = json.loads(raw)
        if not isinstance(tags, list):
            raise ValueError
        tags = [str(t) for t in tags[:10]]
    except (json.JSONDecodeError, ValueError):
        m = re.search(r"\[.*?\]", raw, re.DOTALL)
        tags = json.loads(m.group()) if m else []

    tags_path.write_text(json.dumps(tags), encoding="utf-8")
    return tags


@app.get("/api/library")
async def list_library():
    jobs_dir = DATA_DIR / "jobs"
    entries = []
    needs_tags: list[tuple[int, Path, Path]] = []  # (entry index, job_dir, combined_path)

    if not jobs_dir.exists():
        return {"notebooks": []}

    for job_dir in sorted(jobs_dir.iterdir(), reverse=True):
        if not job_dir.is_dir():
            continue
        try:
            combined_files = list(job_dir.glob("*_complete.md"))
            if not combined_files:
                continue
            combined_path = combined_files[0]

            meta_path = job_dir / "meta.json"
            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                notebook_name = meta.get("notebook", job_dir.name)
                date_str = meta.get("date", "")
                topic_str = meta.get("topic", "")
            else:
                stem = combined_path.stem.removesuffix("_complete")
                notebook_name = stem
                date_str = ""
                topic_str = ""

            notes_dir = job_dir / "notes"
            page_count = len(list(notes_dir.glob("*.md"))) if notes_dir.exists() else 0

            tags_path = job_dir / "tags.json"
            if tags_path.exists():
                tags: list[str] | None = json.loads(tags_path.read_text(encoding="utf-8"))
            else:
                tags = None
                needs_tags.append((len(entries), job_dir, combined_path))

            entries.append({
                "job_id": job_dir.name,
                "notebook": notebook_name,
                "date": date_str,
                "topic": topic_str,
                "pages": page_count,
                "combined_md": combined_path.name,
                "tags": tags,
            })
        except Exception as e:
            print(f"[library] skipping {job_dir.name}: {e}")

    # Generate tags concurrently for all entries that need them
    if needs_tags:
        async def _gen(idx: int, jd: Path, cp: Path) -> None:
            try:
                entries[idx]["tags"] = await _generate_tags(jd, cp)
            except Exception as e:
                print(f"[library] tag gen failed for {jd.name}: {e}")
                entries[idx]["tags"] = []

        await asyncio.gather(*[_gen(i, jd, cp) for i, jd, cp in needs_tags])

    return {"notebooks": entries}


@app.get("/api/library/{job_id}/tags")
async def get_or_generate_tags(job_id: str):
    job_dir = _resolve_job_dir(job_id)
    combined_files = list(job_dir.glob("*_complete.md"))
    if not combined_files:
        raise HTTPException(400, "No combined file found")
    tags = await _generate_tags(job_dir, combined_files[0])
    return {"tags": tags}


@app.get("/api/library/{job_id}/content")
async def library_content(job_id: str):
    job_dir = _resolve_job_dir(job_id)
    combined_files = list(job_dir.glob("*_complete.md"))
    if not combined_files:
        raise HTTPException(400, "No combined file found")
    path = combined_files[0]
    return {"content": path.read_text(encoding="utf-8"), "name": path.name}


@app.get("/api/library/{job_id}/download")
async def library_download(job_id: str):
    job_dir = _resolve_job_dir(job_id)
    combined_files = list(job_dir.glob("*_complete.md"))
    if not combined_files:
        raise HTTPException(400, "No combined file found")
    path = combined_files[0]
    return FileResponse(path, filename=path.name, media_type="text/markdown")


# ── Illustrate routes ──────────────────────────────────────────────────────────

@app.post("/api/illustrate")
async def illustrate(request: dict):
    if not _HAS_SD:
        raise HTTPException(
            503,
            "Stable Diffusion dependencies not installed. "
            "Run: pip install torch torchvision diffusers transformers accelerate",
        )

    style_notebook_id: str | None = request.get("style_notebook_id")
    user_prompt: str = request.get("user_prompt", "").strip()
    if not user_prompt:
        raise HTTPException(400, "user_prompt is required")

    # 1. Load style context from notebook (first 3 000 chars is plenty for style)
    style_context = ""
    if style_notebook_id:
        try:
            job_dir = _resolve_job_dir(style_notebook_id)
            combined_files = list(job_dir.glob("*_complete.md"))
            if combined_files:
                style_context = combined_files[0].read_text(encoding="utf-8")[:3000]
        except HTTPException:
            pass  # invalid job_id — proceed without style

    # 2. Build an enriched SD prompt via Claude
    if style_context:
        enrichment_msg = (
            "Based on this visual style description, create a Stable Diffusion prompt "
            "that captures: hand-drawn, sketchnote style, the specific colours, line quality, "
            f"and illustration approach. Apply this style to: {user_prompt}. "
            "Return only the prompt, no explanation.\n\n"
            f"<style>\n{style_context}\n</style>"
        )
        response = await client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=256,
            messages=[{"role": "user", "content": enrichment_msg}],
        )
        sd_prompt = response.content[0].text.strip()
    else:
        sd_prompt = (
            f"hand-drawn sketchnote illustration, {user_prompt}, "
            "pen and ink, bold marker strokes, warm off-white paper, clean lines, "
            "visual thinking style, minimal colour palette"
        )

    # 3. Run Stable Diffusion (blocks in a thread so the event loop stays free)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename  = f"illustration_{timestamp}.png"
    out_path  = ILLUSTRATIONS_DIR / filename

    async with _sd_infer_lock:
        pipe = await _get_sd_pipeline()

        def _infer():
            if torch.backends.mps.is_available():
                torch.mps.empty_cache()
            result = pipe(
                sd_prompt,
                num_inference_steps=25,
                guidance_scale=7.5,
                width=512,
                height=512,
            )
            result.images[0].save(str(out_path), format="PNG")

        await asyncio.to_thread(_infer)

    return {
        "url":      f"/illustrations/{filename}",
        "filename": filename,
        "prompt":   sd_prompt,
    }


@app.get("/api/illustrate/history")
async def illustrate_history():
    if not ILLUSTRATIONS_DIR.exists():
        return {"images": []}
    files = sorted(
        ILLUSTRATIONS_DIR.glob("*.png"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )[:5]
    return {
        "images": [
            {"url": f"/illustrations/{f.name}", "filename": f.name}
            for f in files
        ]
    }


# ── Static files (must be last) ────────────────────────────────────────────────

app.mount("/illustrations", StaticFiles(directory=str(ILLUSTRATIONS_DIR)), name="illustrations")
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
