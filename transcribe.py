#!/usr/bin/env python3
"""
transcribe.py — Full notebook transcription pipeline.

Flow:
  1. Read PDF from  ./original scans/<pdf>
  2. Split into high-res per-page JPEGs → ./photos/<notebook>/high-res/
  3. Create low-res copies for API     → ./photos/<notebook>/low-res/
  4. Transcribe low-res images         → ./notes/<notebook>/<page>_notebook.md
  5. Combine all pages into one file   → ./notes/<notebook>/<notebook>_complete.md

Usage:
    python transcribe.py --pdf scan.pdf --notebook NB03 --date 2026 --topic pink-leuchturm
    python transcribe.py --notebook NB03 --skip-existing   # re-run without re-splitting
"""

import anthropic
import argparse
import base64
import io
import os
import sys
import time
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image

# ── Configuration ─────────────────────────────────────────────────────────────

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
DEFAULT_MODEL        = "anthropic.claude-sonnet-4-6"
HIGH_RES_DPI         = 200    # DPI for archival high-res split
MAX_DIMENSION        = 1024   # longest side for API images (token-optimised)

# Suppress PIL decompression bomb warning — large scans are expected
Image.MAX_IMAGE_PIXELS = None

# Base directories (relative to working directory)
SCANS_DIR  = Path("Original Scans")
PHOTOS_DIR = Path("photos")
NOTES_DIR  = Path("notes")

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


# ── Step 2: Split PDF into high-res pages ─────────────────────────────────────

def split_pdf(pdf_path: Path, high_res_dir: Path, notebook: str, date: str, topic: str) -> int:
    """Split PDF into full-quality per-page JPEGs. Returns page count."""
    high_res_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(pdf_path)
    total = len(doc)
    print(f"\n── Step 2: Split PDF ─────────────────────────────")
    print(f"  {pdf_path.name}  ({total} pages)  →  {high_res_dir}/\n")
    for i, page in enumerate(doc, 1):
        filename = f"{notebook}_{date}_p{i:02d}_{topic}.jpg"
        pix = page.get_pixmap(dpi=HIGH_RES_DPI)
        pix.save(str(high_res_dir / filename))
        print(f"  [{i}/{total}] {filename}")
    doc.close()
    return total


# ── Step 3: Create low-res copies ─────────────────────────────────────────────

def create_low_res_copies(high_res_dir: Path, low_res_dir: Path) -> list[Path]:
    """Resize high-res images to MAX_DIMENSION and save to low_res_dir."""
    low_res_dir.mkdir(parents=True, exist_ok=True)
    images = sorted(
        p for p in high_res_dir.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    print(f"\n── Step 3: Create low-res copies ─────────────────")
    print(f"  Max dimension: {MAX_DIMENSION}px  →  {low_res_dir}/\n")
    low_res_paths = []
    for p in images:
        img = Image.open(p).convert("RGB")
        original_size = img.size
        img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.LANCZOS)
        out_path = low_res_dir / p.name
        img.save(str(out_path), format="JPEG", quality=85)
        low_res_paths.append(out_path)
        print(f"  {p.name}  {original_size[0]}×{original_size[1]}  →  {img.size[0]}×{img.size[1]}")
    return low_res_paths


# ── Step 4: Transcribe images ─────────────────────────────────────────────────

def encode_image(image_path: Path) -> tuple[str, str]:
    """Base64-encode an image for the API."""
    with open(image_path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")
    return data, "image/jpeg"


def transcribe_image(client: anthropic.Anthropic, image_path: Path, model: str) -> str:
    """Send a low-res image to Claude and return the markdown transcription."""
    image_data, media_type = encode_image(image_path)
    message = client.messages.create(
        model=model,
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
                            "media_type": media_type,
                            "data": image_data,
                        },
                    },
                    {"type": "text", "text": USER_PROMPT},
                ],
            }
        ],
    )
    return message.content[0].text


def transcribe_folder(
    low_res_dir: Path,
    notes_dir: Path,
    model: str,
    skip_existing: bool,
    delay: float,
) -> list[Path]:
    """Transcribe all images in low_res_dir. Returns paths of saved notes."""
    notes_dir.mkdir(parents=True, exist_ok=True)
    images = sorted(
        p for p in low_res_dir.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    if not images:
        print(f"No images found in {low_res_dir}")
        sys.exit(1)

    print(f"\n── Step 4: Transcribe ────────────────────────────")
    print(f"  {len(images)} image(s)  →  {notes_dir}/\n")

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_AUTH_TOKEN"))
    success, skipped, failed = 0, 0, 0
    saved_notes = []

    for i, image_path in enumerate(images, 1):
        out_name = f"{image_path.stem}_notebook.md"
        out_path = notes_dir / out_name
        print(f"[{i}/{len(images)}] {image_path.name}")

        if skip_existing and out_path.exists():
            print(f"  ⏭  Skipping — already exists")
            skipped += 1
            saved_notes.append(out_path)
            continue

        try:
            print(f"  Calling Claude API ({model})...")
            markdown = transcribe_image(client, image_path, model)
            header = f"<!-- source: {image_path.name} | model: {model} -->\n\n"
            out_path.write_text(header + markdown, encoding="utf-8")
            print(f"  ✅ Saved → {out_name}")
            success += 1
            saved_notes.append(out_path)

        except anthropic.RateLimitError:
            print(f"  ⚠️  Rate limit — waiting 60s...")
            time.sleep(60)
            try:
                markdown = transcribe_image(client, image_path, model)
                header = f"<!-- source: {image_path.name} | model: {model} -->\n\n"
                out_path.write_text(header + markdown, encoding="utf-8")
                print(f"  ✅ Saved → {out_name}")
                success += 1
                saved_notes.append(out_path)
            except Exception as e:
                print(f"  ❌ Failed after retry: {e}")
                failed += 1

        except Exception as e:
            print(f"  ❌ Error: {e}")
            failed += 1

        if i < len(images) and delay > 0:
            time.sleep(delay)

    print(f"\n  ✅ {success} succeeded  ⏭  {skipped} skipped  ❌ {failed} failed")
    return saved_notes


# ── Step 5: Combine into one file ─────────────────────────────────────────────

def combine_notes(notes: list[Path], notes_dir: Path, notebook: str) -> Path:
    """Concatenate individual page notes into a single complete notebook file."""
    print(f"\n── Step 5: Combine ───────────────────────────────")
    combined_path = notes_dir / f"{notebook}_complete.md"
    parts = []
    for note_path in sorted(notes):
        content = note_path.read_text(encoding="utf-8")
        parts.append(content)

    combined = "\n\n---\n\n".join(parts)
    combined_path.write_text(combined, encoding="utf-8")
    print(f"  ✅ {len(notes)} pages → {combined_path}")
    return combined_path


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Full notebook transcription pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python transcribe.py --pdf scan.pdf --notebook NB03 --date 2026 --topic pink-leuchturm
  python transcribe.py --notebook NB03 --skip-existing
        """,
    )
    parser.add_argument(
        "--pdf",
        type=Path,
        default=None,
        help=f"PDF filename inside '{SCANS_DIR}/' (e.g. scan.pdf)",
    )
    parser.add_argument(
        "--notebook",
        required=True,
        help="Notebook identifier, e.g. NB03",
    )
    parser.add_argument(
        "--date",
        default="UnknownDate",
        help="Date string used in filenames (default: UnknownDate)",
    )
    parser.add_argument(
        "--topic",
        default="UnknownTopic",
        help="Topic string used in filenames (default: UnknownTopic)",
    )
    parser.add_argument(
        "--model", "-m",
        default=DEFAULT_MODEL,
        help=f"Claude model (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip transcription for pages that already have an output file",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Seconds between API calls (default: 2.0)",
    )

    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        print("Error: ANTHROPIC_AUTH_TOKEN is not set.")
        sys.exit(1)

    nb          = args.notebook
    high_res_dir = PHOTOS_DIR / nb / "high-res"
    low_res_dir  = PHOTOS_DIR / nb / "low-res"
    notes_dir    = NOTES_DIR  / nb

    print(f"Notebook: {nb}")
    print(f"Photos:   {PHOTOS_DIR / nb}/")
    print(f"Notes:    {notes_dir}/")

    # Step 2 — split PDF (optional)
    if args.pdf is not None:
        pdf_path = SCANS_DIR / args.pdf
        if not pdf_path.is_file():
            print(f"\nError: PDF not found: {pdf_path}")
            print(f"Place the file in '{SCANS_DIR}/' and try again.")
            sys.exit(1)
        split_pdf(pdf_path, high_res_dir, nb, args.date, args.topic)
        dest = PHOTOS_DIR / nb / pdf_path.name
        pdf_path.rename(dest)
        print(f"\n  Moved {pdf_path.name} → {dest}")

    # Step 3 — create low-res copies
    if not high_res_dir.is_dir():
        print(f"\nError: high-res folder not found: {high_res_dir}")
        print("Run with --pdf to split a PDF first.")
        sys.exit(1)
    create_low_res_copies(high_res_dir, low_res_dir)

    # Step 4 — transcribe
    saved_notes = transcribe_folder(
        low_res_dir=low_res_dir,
        notes_dir=notes_dir,
        model=args.model,
        skip_existing=args.skip_existing,
        delay=args.delay,
    )

    # Step 5 — combine
    if saved_notes:
        combine_notes(saved_notes, notes_dir, nb)

    print(f"\n{'─'*50}")
    print(f"Done. Notes in {notes_dir.resolve()}/")


if __name__ == "__main__":
    main()
