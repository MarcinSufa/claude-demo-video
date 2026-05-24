# Troubleshooting

## Symptoms → Causes

### White flash mid-video

**Most likely:** Playwright captured a white pre-CSS frame in `endcards.mp4` or `graph.mp4`.

**Fix:**
1. Verify HTML has inline bg: `<html lang="en" style="background:#0a0705">`
2. Verify recorder script trims first 500ms: `-ss 0.5` before `-i webm` in ffmpeg conversion
3. Rebuild that scene: `rm videos/endcards.mp4 && node scripts/record-endcards.mjs`

### Video ends abruptly / cut off at ~45s

**Most likely:** audio mix used `-shortest` or `duration=longest` is broken by sidechain.

**Fix in `mix-final.sh`:**
- Voice filter must have `apad` AFTER volume: `[1:a]adelay=200|200,volume=1.0,apad,asplit=...`
- amix must use `duration=first` (music = 60s, so output = 60s)
- Output `-t` flag must equal VIDEO duration, not auto

Verify:
```bash
ffprobe -v error -show_entries stream=codec_type,duration -of default=noprint_wrappers=1 videos/final-with-captions.mp4
# Both video AND audio should be ~50s. If audio is 45s, the mix is broken.
```

### Voice plays during wrong scene

**Most likely:** scene durations changed but VO pauses still target old timing.

**Diagnostic:**
```bash
python -c "
import json, subprocess
data = json.load(open('vo-words.json'))
durs = []
for s in ['s1','s2','s3','s4','s5','s6','s7']:
    d = subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',f'.normalized/{s}.mp4']).decode().strip()
    durs.append(float(d))
XF = 0.6
starts = [0.0]
for d in durs[:-1]:
    starts.append(starts[-1] + d - XF)
ends = [starts[i] + durs[i] for i in range(7)]
labels = ['hero','typing','amnesia','GRAPH','recall','multi','endcards']
scenes = list(zip(starts, ends, labels))
def scn(t):
    matches = [n for s,e,n in scenes if s <= t < e]
    return matches[-1] if matches else 'OUT'
for line in data['lines']:
    print(f\"{line['line_start']:5.1f}s [{scn(line['line_start']):11}] {line['text']}\")
"
```

If any line lands in wrong scene, adjust `pause_after` in `brand.yaml` for the line BEFORE it, then rebuild.

### Graph scene shows endcards (or vice versa)

**Most likely:** `record-graph.mjs` picked the wrong `.webm` because endcards.webm exists alphabetically first.

**Fix:** The recorder must DELETE its own output files at start, then mtime-sort the leftover webm. Confirm with:
```bash
grep "unlinkSync" scripts/record-graph.mjs    # must exist
grep "mtimeMs" scripts/record-graph.mjs       # must exist
```

If missing, the script was a buggy older version. Re-copy from the skill `assets/scripts/`.

### Embedded video plays in slow motion in frame.html

**Most likely:** You're using the OLD `record-frame.mjs` that embeds `<video>` in the page and lets Playwright record the playback.

**Fix:** Use the NEW version that captures `frame.html?bg=1` (empty rectangle) as ONE static PNG, then ffmpeg-overlays the actual video onto the rectangle. Zero throttling.

Verify:
```bash
grep "scale=.*overlay" scripts/record-frame.mjs    # ffmpeg overlay approach — correct
grep "recordVideo" scripts/record-frame.mjs        # if present → OLD approach, WRONG
```

### Music inaudible

**Most likely:** music volume set too low, or sidechain ratio too aggressive.

**Fix in `mix-final.sh`:**
- Music volume: `[2:a]volume=0.45` (not 0.10 or 0.20 — too quiet)
- Sidechain: `ratio=4` (not 8, that crushes too hard)
- Skip `loudnorm`, use `alimiter=limit=0.95` for cleaner output

### "Why you chose Postgres" includes "Again" / wrong word

**Most likely:** old `voiceover` in brand.yaml.

**Fix:** Edit `brand.yaml`, find the line, remove the unwanted word, run `bash build.sh --force-vo`.

### Captions appear with wrong timing

**Most likely:** `vo.mp3` was regenerated but `captions.ass` wasn't.

**Fix:** `rm captions.ass && python scripts/make-captions.py && bash scripts/burn-captions.sh`

### "Multi-agent" displayed instead of "MULTI-AGENT" in spec line

**Most likely:** spec_line in `brand.yaml` is mixed case. Spec line is auto-uppercased by CSS — values are stored as-is.

Just edit `brand.yaml`:
```yaml
end_cards:
  spec_line: "encrypted · multi-agent · mcp-native"   # always lowercase here
```
CSS handles uppercasing for display.

### Backdrop doesn't show in final video

**Most likely:** terminal element is 100% opaque or too large, covering the backdrop entirely.

**Fix in `frame.html`:**
- Terminal `background: rgba(10, 7, 5, 0.86)` — 86% opaque, lets backdrop bleed
- Terminal width 1400px (out of 1920 viewport) — leaves 260px breathing room on sides
- `mask-image: radial-gradient(...)` fades terminal edges into backdrop

If still no backdrop, check that `videos/backdrop.jpg` exists and is readable by the python http server (test: `curl -I http://localhost:8765/videos/backdrop.jpg`).

### `vhs` command not found on Windows

VHS doesn't have native Windows binary. Use Docker fallback:
```bash
MSYS_NO_PATHCONV=1 docker run --rm -v "$(pwd):/vhs" -w /vhs ghcr.io/charmbracelet/vhs tape/01_hero_blank.tape
```

Or install via WSL: `sudo apt install vhs`.

### `edge-tts` command not found

Edge TTS installed via `pip install --user edge-tts` may not be on PATH. Use module form:
```bash
python -m edge_tts --voice en-US-AndrewNeural --text "hello" --write-media test.mp3
```

The skill's `make-vo.py` uses the Python module directly, so PATH doesn't matter.

### Playwright "Executable doesn't exist"

```bash
cd demo-video
pnpm exec playwright install chromium
```

### Final video larger than 10 MB

Re-encode with higher CRF (lower quality):
```bash
ffmpeg -i videos/final-framed.mp4 -c:v libx264 -crf 24 -preset slower -c:a copy videos/final-small.mp4
```

CRF 18 = visually lossless, CRF 23 = default, CRF 28 = noticeably compressed.

## Still stuck?

Open the videos in this order and find where it breaks:
1. `videos/final-rough.mp4` — video only, no audio. Are scenes correct?
2. `videos/final-with-audio.mp4` — adds audio. Is voice synced?
3. `videos/final-with-captions.mp4` — adds captions. Are they aligned with voice?
4. `videos/final-framed.mp4` — adds frame. Is composite right?

The first step where you see the issue tells you which script to debug.
