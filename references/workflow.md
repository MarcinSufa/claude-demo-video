# Pipeline workflow — internals

The /demo-video build runs 7 sequential steps. Each step has a cache check and skips if up-to-date.

## Dependency graph

```
brand.yaml
   │
   ├──> [1] make-vo.py        → vo.mp3, vo-words.json
   │      └──> [2] make-captions.py → captions.ass, captions.srt
   │
   ├──> [3] make-music.sh     → music.mp3  (procedural; replace with real track)
   │
   ├──> assets/templates/*    → [4] assemble.sh → final-rough.mp4
   │                                 (also uses normalized scenes in .normalized/)
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

### 3. `make-music.sh` — Procedural ambient

- Generates 60s warm pad via ffmpeg sine waves + reverb + lowpass
- Placeholder only — replace `music.mp3` with real CC0 track from Pixabay/FMA for production

### 4. `assemble.sh` — Scene normalization + crossfade

- For each scene mp4, ffmpeg-normalizes to 1920×1080@30fps with `setpts=PTS/SPEEDUP`
- Reads ACTUAL durations via ffprobe (don't hardcode!)
- Computes xfade offsets cumulatively
- Chains 6 xfade transitions
- Output: `videos/final-rough.mp4` (no audio)

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

Each step checks if its output is newer than its inputs. To force re-run:
```bash
bash build.sh --force-vo                    # Re-run from VO down
rm -rf .normalized .vo && bash build.sh     # Nuclear: re-run everything
rm music.mp3 && bash build.sh               # Re-generate music
```

## Where time is spent

On a typical run (clean cache):
- `make-vo.py` ~12s (Edge TTS streaming, network-bound)
- `make-captions.py` ~0.1s
- `make-music.sh` ~3s
- `assemble.sh` ~25s (7 normalize + xfade chain encoding)
- `mix-final.sh` ~8s
- `burn-captions.sh` ~12s (re-encode video with libass)
- `record-frame.mjs` ~15s (Playwright launch + ffmpeg overlay)
- **Total: ~75s** for a 50s output video.

Cached re-run: ~30s (Playwright + final encode dominate).
