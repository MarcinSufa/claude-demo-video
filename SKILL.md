---
name: demo-video
description: Use when the user wants to turn their app, UI, or product into a polished ~50s feature/demo video showing how it works — capturing the real running app (or an HTML mockup, or a terminal), narrated with AI voiceover, synced karaoke captions, a music bed, and brand framing. Triggers on "make a feature video", "demo video of my app", "show how my app works as a video", "UI walkthrough video", "product launch film", "video for landing page", "record my app with narration", "screen recording with voiceover and captions", "ExoVault-style demo".
---

# /demo-video — turn an app/UI into a ~50s narrated feature film

## What it makes

A single `final-framed.mp4` (~50s, 1920×1080) that shows **how an application works**, in a polished product-film aesthetic:

- **Your scenes, your order** — `scenes.sequence` composes any mix of: `browser_capture` (drive + record the REAL running app), `html_mockup` (a designed screen for an unbuilt feature), `screen_recording` (an existing clip), `terminal` (CLI via VHS), plus built-in `graph` and `endcards`.
- **AI voiceover** narrating the feature (Edge TTS, free, no API key, many languages/voices)
- **Karaoke word-highlight captions** synced via WordBoundary events, readable on light AND dark UI
- **Music bed** — procedural / your own file / none — auto-ducked under the voice
- **Brand framing** — palette, fonts, logo, end cards; optional styled-window-on-desk composite

Built entirely with **free tools** — ffmpeg, Playwright headless Chromium, VHS (Charm), Edge TTS. Zero paid services.

The bundled default (`memory-product-default`) is a 7-scene terminal narrative, but that's just one example arc — the common case is composing your own scenes around your real app's UI.

## When to use

- User wants a feature/demo/launch video of their **app or UI** — showing how it works, narrated and captioned
- User wants to capture their **real running app** (localhost or live site) as a polished film
- User wants to demo a **feature that isn't built yet** (use an `html_mockup` scene — no throwaway code in the real app)
- User has a CLI/terminal product to showcase
- User wants the aesthetic of Anthropic/Linear-style product films without an After Effects / Synthesia / HeyGen subscription

## When NOT to use

- User wants a raw, unedited live screen recording of a working session → use /qa or /browse instead
- User wants a 5-minute tutorial → this targets ~50s feature films, not long-form content
- User wants pure motion graphics / explainer animation with no real UI, terminal, or mockup → use a design tool

## Workflow (single command per project)

```
1. /demo-video init                  → scaffolds demo-video/ in current project
2. user edits brand.yaml             → palette, voice, VO script, scenes
3. /demo-video plan                  → dry run (~1s): VO + video length estimate, PASS/WARN — no render
4. /demo-video build                 → runs pipeline, produces final-framed.mp4
5. /demo-video preview               → starts local server + tunnel for mobile review
```

Inside Claude Code, the skill orchestrates these by reading config and invoking bundled scripts.

## Pipeline (what `build` runs)

```
apply-brand.py    → compile brand.yaml → .build/ (rendered templates + config.json)
make-vo.py        → Edge TTS streams vo.mp3 + vo-words.json (word-level timing)
make-captions.py  → captions.ass (karaoke) + captions.srt
make-music.sh     → procedural ambient pad music.mp3 (or mode: file / none)
plan-scenes.py    → resolve the scene sequence → scene-plan.json
build-scenes.sh   → render each scene by type; pin to `duration:` (normalize-clip.py) if set
assemble.sh       → normalize + speedup + crossfade N scenes → final-rough.mp4
mix-final.sh      → ⚠ timing gate (check-timing.py) → voice + music sidechain-ducked → final-with-audio.mp4
burn-captions.sh  → ffmpeg subtitles filter → final-with-captions.mp4
record-frame.mjs  → Playwright snapshot + ffmpeg overlay → final-framed.mp4
```

Each step caches outputs. Re-running only re-processes what changed.

**Timing safety net (P0-1).** `mix-final.sh` cuts the voice track to the video length,
so a voiceover longer than the assembled video would silently lose its closing line.
Before muxing, `check-timing.py` compares the real speech-end (from `vo-words.json`)
against the video and **fails the build** with an actionable message if narration
overruns. Override with `DEMO_ALLOW_TRUNCATE=1`. Catch it earlier with `/demo-video plan`.

## Prerequisites

| Tool | Install | Why |
|---|---|---|
| **ffmpeg** | `winget install Gyan.FFmpeg` / `brew install ffmpeg` | All video/audio operations |
| **Python 3.10+** | system | VO + caption scripts |
| **Node 18+ + pnpm** | system | Playwright recorder |
| **edge-tts** | `pip install --user edge-tts` | Free Microsoft TTS, no API key |
| **playwright** | `cd demo-video && pnpm install && pnpm exec playwright install chromium` | Headless Chrome for HTML/graph/end-card capture + frame composite (always needed) |
| **VHS** (Charm) | `winget install charmbracelet.vhs` / `brew install vhs` | Terminal scene recording — **only if** the arc has terminal/multi-agent scenes |
| **Docker** (alt) | system | VHS via container (Windows fallback) |

The skill verifies these before running `build` and asks the user to install missing ones.

## Configuration — `brand.yaml`

The skill scaffolds a `brand.yaml` with these top-level keys:

```yaml
project:
  name: "MyProduct"
  url: "myproduct.com"
  version_tag: "v0.1"          # shown in terminal title bar

palette:
  bg: "#0a0705"                # deep terminal bg
  fg: "#dcd7cf"                # text foreground
  accent: "#dbaf71"            # brass/orange highlight (cursor, links)
  rule: "#29231f"              # subtle dividers
  end_card_bg: "#1e1714"       # end-card background (can differ)
  memory_type_colors: { ... }  # optional per-type colors for graph

logo:
  svg_inline: |                # paste full SVG markup (orbital, monogram, etc.)
    <svg ...>...</svg>
  wordmark_italic: "MyPro"     # part rendered italic
  wordmark_roman: "duct"       # part rendered roman

typography:
  display: "Newsreader"        # end-card serif
  body: "Inter"
  mono: "JetBrains Mono"

voice:
  provider: "edge-tts"
  voice_id: "en-US-AndrewNeural"
  rate: "+0%"                  # -10% slower, +10% faster

backdrop:
  type: "image"                # or "color"
  source: "assets/backdrop.jpg"   # local file OR Unsplash URL
  blur: 4                      # 0 = sharp, 8 = strong DOF

scenes:
  speedup: 1.20                # global 1.0 = realtime, 1.30 = faster
  crossfade_seconds: 0.6
  # 7 scenes auto-mapped; override per-scene config in advanced/
  # See references/scene-config.md for per-scene options

voiceover:
  - { text: "Every session starts the same way.", pause_after: 1.1 }
  - { text: "You explain your stack.",            pause_after: 0.3 }
  - { text: "And we forget.",                     pause_after: 2.0 }
  # ... 12-15 lines targeting ~45s of speech for a 50s video
```

See `references/brand-config.md` for the full schema and tuning guide.

## What the agent (Claude) does

When invoked, follow this sequence:

1. **Detect intent**. "init demo-video" → scaffold mode. "build" → pipeline mode. "plan" / "dry run" / "how long will it be" → plan mode (`bash scripts/build.sh --plan`). If neither, ask which.

2. **For `init`**:
   - `mkdir <project>/demo-video/`
   - Copy `assets/scripts/*` and `assets/templates/*` to that folder
   - Copy `assets/brand.example.yaml` → `brand.yaml`
   - Copy `assets/package.example.json` → `package.json` (so `pnpm install` lands
     Playwright in *this* folder, not a parent — without a local manifest pnpm walks
     up and installs into the wrong `node_modules`). Optionally set `name` to `<project>-demo-video`.
   - Copy `assets/mockup.example.html` → `mockups/example.html` (starter for `html_mockup`
     scenes — demo unbuilt features without touching the real codebase)
   - Run a quick interactive interview (3-5 questions): product name, URL, voice gender/tone, what each scene should show
   - Fill in `brand.yaml` based on answers
   - Print: "Run `pnpm install && pnpm exec playwright install chromium`, edit `brand.yaml`, then `/demo-video plan` and `/demo-video build`."

3. **For `build`**:
   - Read `brand.yaml`
   - `build.sh` resolves the scene plan first, then gates prerequisites **arc-aware**:
     ffmpeg/python/node/edge-tts/Playwright always; VHS/Docker only if the plan has a
     terminal or multi-agent scene. Caching (`--no-cache`, `--only <id>`) reuses
     unchanged scene clips between runs.
   - If any missing → it prints the exact install command and STOPs
   - Template the scripts: substitute `{{project.name}}`, `{{palette.bg}}`, etc. into the bundled scripts/HTML/tape files
   - Start local http server: `python -m http.server 8765` (background)
   - Run pipeline in sequence:
     ```bash
     python make-vo.py
     python make-captions.py
     bash make-music.sh
     bash assemble.sh
     bash mix-final.sh
     bash burn-captions.sh
     node record-frame.mjs
     ```
   - On each step, report progress to user
   - On any error, stop and show ffmpeg/playwright stderr — most issues are missing fonts or wrong palette syntax

3b. **For `plan`** (dry run, ~1s, no render):
   - `bash scripts/build.sh --plan`
   - Reports each scene's pinned `duration` (and on-screen length after speedup), the
     voiceover length estimated from word count (no TTS), and the predicted video length
     with a **PASS/WARN** verdict. WARN exits non-zero — narration would be cut.
   - Needs only ffmpeg + python + pyyaml (no VHS/Playwright/edge-tts), so it runs anywhere.
   - Use it before `build` to tune `voiceover` / scene `duration` / `speedup` cheaply.

4. **For `preview`**:
   - Verify cloudflared binary exists in project (offer to download from https://github.com/cloudflare/cloudflared/releases/latest if missing — ~50 MB)
   - Start tunnel: `./cloudflared tunnel --url http://localhost:8765`
   - Generate a simple `index.html` with embedded `<video>` players for each output
   - Print the trycloudflare URL — user opens on phone to review

## Demo content for features that don't exist yet

If a scene needs UI the real app doesn't have yet (an unbuilt feature, an empty
route), **do NOT add a view to the real codebase just for the recording** — that
leaves throwaway cruft in production code. Instead use an **`html_mockup` scene**:
build a standalone HTML file in `mockups/` (brand palette/fonts), capture that via
the same Playwright engine as graph/endcards. It never touches the real app and is
easy to discard. Reserve `browser_capture` for routes that genuinely exist.

## Pronouncing brand names

TTS reads brand names phonetically in its own language — a Polish voice says
"Asistel" as "A-śi-stel" (like the name *Asia*). When using a non-English `voice_id`
with an English product name, sanity-check pronunciation and add a `voice.pronounce`
map in brand.yaml (respell for the voice; captions keep the original spelling).

## Critical gotchas (must apply, do not skip)

These were discovered the hard way building the reference implementation. The bundled scripts already encode them but if the agent regenerates from scratch, re-apply:

| Gotcha | Fix |
|---|---|
| **HTML pages record as WHITE flashes** at start because Playwright captures pre-CSS frames | (a) Inline `style="background:#0a0705"` on `<html>`. (b) `-ss` trim in ffmpeg conversion. For `html_mockup` scenes the recorder now ALSO injects the palette bg before first paint automatically (P2-3), so a mockup that forgets the inline bg won't flash. |
| **First capture of a cold dev-server route shows "Rendering…"** (Next compiles on first hit) | `browser_capture` warms the route in a separate non-recording context before recording (P2-2). Default on for `localhost`, off for public sites; override per-scene with `warmup: true|false`. |
| **Brand fonts don't load / wrong font on end card** | The Google Fonts `<link>` is generated from `typography.{display,body,mono,tagline}` (P1-3). Google `css2` is strict — an unsupported axis 400s the whole request — so `apply-brand.py` keeps a per-family axis table (`FONT_SPECS`); unknown families load regular-only and print a warning. Add new families there. |
| **Audio truncates video** to voice length (~45s) instead of full 50s, causing white tail | `apad` on voice + `duration=first` on amix in `mix-final.sh`. Never use `-shortest` for the final mux. |
| **record-graph.mjs picks endcards.webm alphabetically** when both exist | Delete `graph.webm` and `graph.mp4` at start of script. Filter webm list by mtime, not name. |
| **VHS terminal pre-CSS shows white** during VHS startup | Use bash here-doc to print Vellum theme + clear screen before any content prints |
| **Embedded `<video>` in Playwright headless plays at ~20% speed** due to throttling | Don't embed video in Playwright. Use ffmpeg `overlay` filter to composite source video onto a Playwright-captured PNG of the frame chrome. |
| **Edge TTS WordBoundary events don't fire by default** | Pass `boundary="WordBoundary"` to `edge_tts.Communicate(...)` |
| **Scene crossfade offsets drift** when scene durations change | `assemble.sh` reads actual normalized durations via ffprobe before computing xfade offsets, never hardcodes |
| **VO timing drifts from scenes** | After every scene-duration change, re-run alignment check: `python -c "..."` script that maps each VO line to its scene. If any line ends up in the wrong scene, adjust `pause_after` values in `brand.yaml` and regenerate VO. |
| **Karaoke captions wash out on light app UI** (`browser_capture` / `html_mockup` scenes) | Use `BorderStyle=3` opaque box. The box colour goes in the **`OutlineColour` slot** (libass draws the BorderStyle=3 box from OutlineColour, NOT BackColour) and **must be fully opaque (alpha `00`)** — a semi-transparent box overlaps at the per-word `\k` seams and doubles up into ugly darker vertical bands. Set box colour = `palette_bg` so it blends invisibly on dark terminal scenes but reads as a solid bar over light UI. |

## File map

```
demo-video/
├── brand.yaml                  ← user edits this
├── scripts/                    ← copied from skill
│   ├── apply-brand.py          ← compiles brand.yaml → .build/
│   ├── make-vo.py
│   ├── make-captions.py
│   ├── make-music.sh
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
│   ├── record-frame.mjs
│   ├── record-endcards.mjs
│   ├── record-graph.mjs
│   ├── record-browser.mjs      ← real-app / html_mockup capture
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

## Output

After `build` completes, the user has:
- `videos/final-framed.mp4` — share this on Twitter / LinkedIn / landing page
- `videos/final-with-captions.mp4` — same but full-screen (no terminal frame)
- `captions.srt` — upload to YouTube for accessibility / SEO
- `vo.mp3` — standalone voice track if they want to re-edit in another tool

## See also

- `references/workflow.md` — pipeline internals, what each step does
- `references/brand-config.md` — full `brand.yaml` schema with all options
- `references/troubleshooting.md` — debugging white flashes, sync drift, audio truncation
- `references/persuasion-pacing.md` — VO writing principles (Anthropic-style narration, 115 wpm, short sentences)
- `tests/` — `python -m unittest discover -s tests` (timing/duration logic; run before changing those scripts)
