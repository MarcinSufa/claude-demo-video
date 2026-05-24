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

These cover the decision logic; the ffmpeg/Playwright/TTS glue around them is smoke-tested
manually (see the spec's verification plan). Run the suite before committing changes to
`timing_util.py`, `check-timing.py`, `dry-run-plan.py`, or `normalize-clip.py`.
