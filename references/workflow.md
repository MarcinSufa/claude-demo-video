# Pipeline workflow — internals

`bash scripts/build.sh` runs everything inside `.build/`, in this order:
`apply-brand.py` (brand.yaml → config + templates) → `plan-scenes.py` (scene-plan.json;
`--plan` stops here after `dry-run-plan.py`) → mascot frames (if enabled) → the 7 media steps
below, with `build-scenes.sh` (records every scene by type), the optional auth login and
`autofit.py` before step 3, and `verify-final.py` before step 7.
Only scene clips are cached (see "Cache behavior"); the other steps re-run on every build.

## Dependency graph

```
brand.yaml
   │
   ├──> [1] make-vo.py        → vo.mp3, vo-words.json
   │      └──> [2] make-captions.py → captions.ass, captions.srt
   │
   ├──> assets/templates/*    → [3] assemble.sh → final-rough.mp4
   │                                 (also uses normalized scenes in .normalized/)
   │
   ├──> (3)                   → [4] make-music.sh → music.mp3  (library CC0 track / procedural / file, fitted to [3])
   │
   └──> (1) + (3) + (4)       → [5] mix-final.sh → final-with-audio.mp4
            (2) + (5)         → [6] burn-captions.sh → final-with-captions.mp4
            (6) + frame.html  → [7] record-frame.mjs → final-framed.mp4
```

## Step-by-step

### 1. `make-vo.py` — Voiceover via Edge TTS

- Reads `brand.yaml` `voice` and `voiceover` sections
- For each line, streams Edge TTS with `boundary="WordBoundary"` (critical — without this no word timing)
- Saves per-segment mp3 in `.vo/seg_NN.mp3`
- Concatenates with `pause_after` silence padding
- Outputs:
  - `vo.mp3` — final concatenated audio
  - `vo-words.json` — every word with absolute start time + duration

### 2. `make-captions.py` — Karaoke ASS + standard SRT

- Reads `vo-words.json`
- Generates `captions.ass` with per-word `\k` highlight codes (centiseconds)
- Style: word being spoken = brass, before = bone, after = bone
- Also generates `captions.srt` (line-level) for YouTube upload

### 3. `assemble.sh`: Scene normalization + crossfade

- For each scene mp4, ffmpeg-normalizes to 1920×1080@30fps with `setpts=PTS/SPEEDUP`
- Reads ACTUAL durations via ffprobe (don't hardcode!)
- Computes xfade offsets cumulatively
- Chains N-1 xfade transitions for N scenes (offset math in embedded Python, any N)
- Output: `videos/final-rough.mp4` (no audio)

### 4. `make-music.sh`: Music bed

- Runs after assemble (step 3) so the bed length equals `final-rough.mp4` (looped or trimmed, faded out);
  before the video exists it predicts the length from `scene-plan.json`
- `mode: library`: `fetch-music.py` downloads the mood's CC0 track from `music/manifest.yaml`
  into the per-user cache and verifies its sha256; on any failure it prints a WARNING and
  falls back to the procedural preset of the same mood
- `mode: procedural`: per-mood chord table, detuned pad plus plucked arpeggio, ffmpeg only

### 5. `mix-final.sh` — Audio mix

- Loads voice + music
- Voice: `adelay=200|200,volume=1.0,apad` — `apad` is critical to prevent truncation
- Music: `volume=0.45`
- Sidechain compress music with voice as trigger (music ducks when voice plays)
- amix with `duration=first` (NOT `longest`, NOT `-shortest` flag — those truncate)
- Final loudnorm to -16 LUFS
- Output: `videos/final-with-audio.mp4`

### 6. `burn-captions.sh` — Burn ASS into video

- `ffmpeg -vf "subtitles=captions.ass"` — burns karaoke into video pixels
- Output: `videos/final-with-captions.mp4` (51s, ~3 MB)

### 7. `record-frame.mjs` — Terminal-on-desk composite

- Playwright captures `frame.html?bg=1` as ONE static PNG (no embedded video — that throttles)
- ffmpeg overlays `final-with-captions.mp4` onto exact rectangle in PNG
- Output: `videos/final-framed.mp4` (the deliverable)

## Cache behavior

Voiceover, captions, assemble, music, mix and the frame re-run on every build.
Recorded scene clips are cached per scene (`scene_cache.py`) and reused when the scene spec is unchanged:
```bash
bash scripts/build.sh                       # reuse cached scene clips
bash scripts/build.sh --only c2             # re-record scene c2, reuse the rest
bash scripts/build.sh --no-cache            # re-record every scene
rm -rf .build && bash scripts/build.sh      # nuclear: start from scratch
```

## Where time is spent

On a typical run (clean cache):
- `make-vo.py` ~12s (Edge TTS streaming, network-bound)
- `make-captions.py` ~0.1s
- `make-music.sh` ~3s
- `assemble.sh` ~25s for 7 scenes (normalize each + xfade chain encoding)
- `mix-final.sh` ~8s
- `burn-captions.sh` ~12s (re-encode video with libass)
- `record-frame.mjs` ~15s (Playwright launch + ffmpeg overlay)
- **Total: ~75s** for a 50s output video.

Cached re-run: ~30s (Playwright + final encode dominate).
