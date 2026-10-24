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

## File map

```
demo-video/
├── brand.yaml                  ← user edits this
├── mascot.json                 ← optional: custom mascot (or copied from mascots/ by build.sh)
├── mascots/                    ← roster characters copied from assets/mascots/ at init
│   └── octopus.json            ← built-in octopus character
├── scripts/                    ← copied from skill
│   ├── apply-brand.py          ← compiles brand.yaml → .build/
│   ├── make-vo.py
│   ├── make-captions.py
│   ├── make-music.sh           ← music bed fitted to the video (library / procedural / file / none)
│   ├── fetch-music.py          ← CC0 track fetch + sha256 cache (music/manifest.yaml)
│   ├── verify-final.py         ← post-mux gate: duration, audio, white flash, captions per scene
│   ├── plan-scenes.py          ← resolves scene sequence
│   ├── build-scenes.sh
│   ├── assemble.sh
│   ├── mix-final.sh
│   ├── burn-captions.sh
│   ├── timing_util.py          ← shared VO/video alignment math (unit-tested)
│   ├── check-timing.py         ← P0-1 truncation gate (run by mix-final.sh)
│   ├── dry-run-plan.py         ← P3-1 dry run (run by build.sh --plan)
│   ├── normalize-clip.py       ← P0-3 pin a scene to exact duration
│   ├── scene_cache.py          ← P0-2 skip re-capturing unchanged scenes
│   ├── prereqs.py              ← P1-2 arc-aware VHS/Docker gate
│   ├── autofit.py              ← P0-1 opt-in: fit speedup to voiceover length
│   ├── mascot_data.py          ← parse mascot.json sprite grid
│   ├── render-mascot.py        → render mascot sprite frames from mascot.json
│   ├── resolve-mascot-timeline.py ← map scene timeline to mascot emotion segments
│   ├── overlay-mascot.py       ← composite mascot frames onto scene video
│   ├── mascot_brand.py         ← remap mascot palette to brand colors
│   ├── make-auth.mjs           ← P2-1 log in once → auth.json (storageState)
│   ├── record-frame.mjs
│   ├── record-endcards.mjs
│   ├── record-graph.mjs
│   ├── record-browser.mjs      ← real-app / html_mockup capture (glow/highlight selectors must match one node)
│   ├── glow_check.mjs          ← selector validation shared with tests
│   ├── display.sh
│   └── build.sh                ← orchestrator (build | --plan)
├── templates/
│   ├── frame.html              ← terminal-on-desk composite
│   ├── endcards.html           ← branded end cards
│   ├── graph.html              ← knowledge graph
│   └── tape/                   ← VHS scene tapes
├── assets/
│   └── backdrop.jpg            ← Unsplash workspace photo (or user-supplied)
└── videos/                     ← pipeline outputs
    └── final-framed.mp4        ← the deliverable
```
