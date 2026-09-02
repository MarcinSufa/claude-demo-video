# Tests

Unit tests for the pure logic behind the timing-safety and scene-duration features.
No extra dependencies — Python stdlib `unittest` only (Python is already a skill prereq).

```bash
python -m unittest discover -s tests
```

| Test file | Covers |
|---|---|
| `test_timing_util.py` | `speech_end_seconds`, `check_alignment` (P0-1 gate), `predict_video_seconds` (validated Σraw/speedup−crossfade model), `estimate_vo_seconds` (P3-1 dry run) |
| `test_normalize.py` | `decide_normalization` — trim/pad/none decision for `duration:` (P0-3) |
| `test_fetch_music.py` | `fetch-music.py`: manifest lookup, per-user cache, sha256 rejection, alternate fallback (file:// fixtures, no network) |
| `test_make_music.py` | `make-music.sh`: bed length follows the video in every mode, library failure falls back with a WARNING (needs ffmpeg + bash) |
| `test_glow_check.py` | `glow_check.mjs`: glow/highlight selector must match exactly one node (needs node) |
| `test_dry_run_plan_measured.py` | `dry-run-plan.measured_vo`: `--plan` prefers a current `vo-words.json` over the word-count estimate |
| `test_verify_final.py` | `verify-final.py`: duration, audio, white-flash and caption checks (real clips need ffmpeg) |

These cover the decision logic; the ffmpeg/Playwright/TTS glue around them is smoke-tested
manually (see the spec's verification plan). Run the suite before committing changes to
`timing_util.py`, `check-timing.py`, `dry-run-plan.py`, or `normalize-clip.py`.
