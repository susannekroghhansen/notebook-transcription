# Longhand — to do

Outstanding work and ideas, kept here so nothing gets lost between sessions.

Updated: 10 May 2026

---

## In flight — `add-voice-transcription` branch

The voice transcription pipeline is built, tested, and works at quality in dev mode. The bundled `.app` build is most of the way there but isn't ready to use yet.

### Pick up here next session: finish the .app bundle

The .app builds successfully but crashes on launch with:

```
Error: bad local file header: '/Applications/Longhand.app/Contents/Resources/lib/python314.zip'
```

This is a py2app issue where the zipped Python runtime inside the bundle gets corrupted during builds with heavy AI dependencies (faster-whisper, torch, ctranslate2, onnxruntime, Stable Diffusion all together).

**Likely fixes to try, in order:**

1. **Completely fresh build from scratch.** Sometimes the cached state across multiple rebuilds causes corruption. Run:
   ```bash
   rm -rf build/ dist/ .eggs/
   python setup.py py2app
   ```
2. **Try the `semi-standalone` or `--no-strip` build flag.** py2app strips debug symbols by default; for big builds this sometimes corrupts the zip. Add to setup.py options or pass on the command line.
3. **Add `argv_emulation=False` to py2app options** if it isn't already — known to interact badly with some packaged apps.
4. **As a last resort: add `"site_packages": True, "strip": False` to py2app options** to disable the aggressive packaging that's causing the corruption.

Once the bundled app launches and the voice tab transcribes successfully:
- [ ] Drag the working `Longhand.app` to Applications, confirm dock icon
- [ ] Test voice transcription end-to-end in the bundled version
- [ ] Test notebook transcription still works in the bundled version (regression check)
- [ ] Commit the working setup.py
- [ ] Merge `add-voice-transcription` into `main`
- [ ] Delete the `add-voice-transcription` branch (locally and on GitHub)

### Known bug to fix alongside bundling: app opens two browser tabs

When the bundled `Longhand.app` is launched from the dock, two browser tabs open with the Longhand UI instead of one. Likely cause: both the rumps menu bar app and the launcher script independently call something like `open http://localhost:8000` on startup.

To fix: read `menubar.py` and `launcher.py` to find the two browser-open calls, then either remove one, or make one check first whether the page is already open.

### How to use Longhand in dev mode meanwhile

The voice pipeline works perfectly via uvicorn — you don't have to wait for the bundled .app to use it.

```bash
cd ~/Documents/claude-projects/notebook-transcription/notebook-webapp
source venv/bin/activate
uvicorn main:app --port 8000
```

Then open `http://localhost:8000` in the browser. Stop the server with Ctrl+C in that Terminal window.

---

## Parking lot — next session candidates

Work that's been discussed and is worth doing, but isn't started yet. Each one warrants its own brief update and its own branch.

### Speaker diarization (v2.1)

Distinguish multiple voices in a recording so transcripts read as "Speaker A: ..." / "Speaker B: ...". Most relevant for work session recordings (one of the three scenarios in the v2.0 brief); less relevant for solo voice memos and notebook scans.

- Library: `pyannote.audio` (runs locally, preserves privacy)
- HuggingFace account already created and model licences already accepted (March 2026); token may need regenerating
- Quality is audio-dependent — phone-on-table in a noisy room is the hard case
- Integration work: align Whisper segments with pyannote speaker turns by timestamp, then format markdown with speaker labels
- Frontend: live transcript needs to show speaker labels as it builds

### Language override dropdown (v2.2)

Add a manual language selector (Auto / Danish / English) on the Voice tab for situations where auto-detect picks wrong on short or mixed-language recordings. Decided to defer until real use shows whether it's actually a problem.

### Voice transcript library / tagging (v2.3)

Voice transcripts currently produce markdown but don't appear in any persistent library — each transcription is a one-off. Once everything works end-to-end, build a way to keep them and find them later.

Open product question to think through before building:

- **Same library as notebooks, with tags?** Notebooks and voice transcripts live together in one Library tab, distinguished by a type tag (e.g. "📓 notebook" / "🎙 voice") and visually different — different card style, icon, accent colour — so they can be filtered or scanned at a glance.
- **Separate Voice Library tab?** Keeps the two pipelines fully separate. Cleaner, but means switching tabs to find related material across both.

The first option matches how the raw material actually lives in your head (it's all *captured thinking*, just from different sources) and supports the Unruled Play workflow where a notebook page and a voice memo on the same topic might both feed one Substack post. The second is simpler to build but more rigid in use.

Either way, the design needs:
- A way to list saved transcripts (date, title, type, language, length)
- A way to filter or search
- A way to delete or archive
- Visual distinction so notebooks and voice transcripts are never confusable at a glance — different shape, different texture, different accent colour, not just different icon

### The stashed Stable Diffusion experiment

The `git stash` from 10 May contains an unfinished SD device/dtype refactor from March. Intent unknown. Either revisit and finish, or discard.

- Inspect with: `git stash show -p stash@{0}`
- Either apply with `git stash pop` and finish the work, or drop with `git stash drop stash@{0}`

---

## Known limitations to live with (for now)

These are real, but not worth fixing right now.

- **Mid-recording language switching.** Whisper locks onto a language in the first ~30 seconds and transcribes everything as that language. Recordings that switch between Danish and English will produce garbled output for the secondary language. No fix in scope; workaround is to split mixed recordings before uploading.
- **CPU-only Whisper on Apple Silicon.** `faster-whisper` uses CTranslate2, which doesn't support Apple Metal/MPS. Runs natively on CPU via Accelerate framework — fast, but not GPU-accelerated. ~16–25 minutes for a 30-minute recording on `large-v3`.
- **`large-v3` quality on Danish.** Better than `medium`, but still expects manual cleanup. Names, technical terms, regional pronunciations need fixing by hand.

---

## Setup.py changes made this session (for reference)

Three changes to `notebook-webapp/setup.py` during the bundling attempt — keep in case they need reverting or revisiting:

1. **Removed `setup_requires=["py2app"]`** — this was causing setuptools to fetch a fresh isolated py2app egg that couldn't see modulegraph.
2. **Added `import sys; sys.setrecursionlimit(10000)`** at the top — needed because py2app's AST analyser was hitting Python's default recursion limit when analysing ctranslate2 and onnxruntime.
3. **Added these packages to the py2app `packages` list:** `faster_whisper`, `ctranslate2`, `av`, `onnxruntime`. Required because faster-whisper is imported lazily inside a function and py2app's static analysis missed it.

---

## Sunset condition (from brief v2.0)

Retire Longhand when *both* halves can be replaced:

- macOS adds native local audio transcription that handles Whisper-quality Danish, AND
- Something off-the-shelf handles the notebook + diagram side at the quality the current Claude vision pipeline produces

Until then — Longhand earns its place.
