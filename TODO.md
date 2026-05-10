# Longhand — to do

Outstanding work and ideas, kept here so nothing gets lost between sessions.

Updated: 10 May 2026

---

## In flight — `add-voice-transcription` branch

The voice transcription pipeline is built, tested, and works at quality. One step left before the branch can be merged into `main`.

- [ ] **Rebuild the .app with py2app** so "Longhand" appears in the dock with both pipelines bundled inside it. Slow step (5–15 minutes) and occasionally fiddly with the new Whisper dependency. Test the rebuilt .app end-to-end before merging.
- [ ] **Merge `add-voice-transcription` into `main`** once the rebuilt .app is verified.
- [ ] **Delete the `add-voice-transcription` branch** locally and on GitHub after merge — branches are temporary, history stays in `main`.

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

Add a manual language selector (Auto / Danish / English) on the Voice tab for situations where auto-detect picks wrong on short or mixed-language recordings. Decided to defer until real use shows whether it's actually a problem — small problem for v1, potentially worth solving in a small follow-up branch.

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

## Sunset condition (from brief v2.0)

Retire Longhand when *both* halves can be replaced:

- macOS adds native local audio transcription that handles Whisper-quality Danish, AND
- Something off-the-shelf handles the notebook + diagram side at the quality the current Claude vision pipeline produces

Until then — Longhand earns its place.
