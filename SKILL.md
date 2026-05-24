---
name: demo-video
description: Use when the user wants to produce a 50-second product demo video for their project — including voiceover, captions, terminal scenes, knowledge-graph visualisation, and a real-photo backdrop. Triggers on "create demo video", "make product video", "launch film", "show this as a video", "video for landing page", "screen recording with narration", "ExoVault-style demo".
---

# /demo-video — produce a 50s product demo film

## What it makes

A single `final-framed.mp4` (~50s, 1920×1080, ~3 MB) that contains:

- **7 scene story arc** (hero → typing → amnesia → graph → recall → multi-agent → end cards)
- **AI voiceover** (Edge TTS, free, no API key)
- **Karaoke word-highlight captions** (synced to voice via WordBoundary events)
- **Ambient music bed** (ducked under voice)
- **Terminal-on-desk treatment** — the demo plays inside a styled terminal window composited on a real workspace photo

Built entirely with **free tools** — ffmpeg, Playwright headless Chromium, VHS (Charm), Edge TTS. Zero paid services.

## When to use

- User says they want a product demo video, launch film, or social-media demo
- User has a CLI/terminal product they want to showcase
- User wants something in the style of Anthropic's "agent view in Claude Code" feature drops
- User mentions tools that won't help: "After Effects is too much", "Screen Studio is Mac-only", "Loom is just screen recording"

## When NOT to use

- User wants live screen recording of an actual session → use /qa or /browse instead
- User wants a 5-minute tutorial → this targets 50s product films, not long-form content
- User wants pure motion graphics with no terminal/CLI element → use a real design tool

## Workflow (single command per project)

```
1. /demo-video init                  → scaffolds demo-video/ in current project
2. user edits brand.yaml             → palette, voice, VO script, scenes
3. /demo-video build                 → runs pipeline, produces final-framed.mp4
4. /demo-video preview               → starts local server + tunnel for mobile review
```

Inside Claude Code, the skill orchestrates these by reading config and invoking bundled scripts.

## Pipeline (what `build` runs)

```
make-vo.py        → Edge TTS streams vo.mp3 + vo-words.json (word-level timing)
make-captions.py  → captions.ass (karaoke) + captions.srt
make-music.sh     → procedural ambient pad music.mp3 (placeholder; swap with real track)
assemble.sh       → 7 normalized scenes crossfaded → final-rough.mp4
mix-final.sh      → voice + music sidechain-ducked → final-with-audio.mp4
burn-captions.sh  → ffmpeg subtitles filter → final-with-captions.mp4
record-frame.mjs  → Playwright snapshot + ffmpeg overlay → final-framed.mp4
```

Each step caches outputs. Re-running only re-processes what changed.

## Prerequisites

| Tool | Install | Why |
|---|---|---|
| **ffmpeg** | `winget install Gyan.FFmpeg` / `brew install ffmpeg` | All video/audio operations |
| **Python 3.10+** | system | VO + caption scripts |
| **Node 18+ + pnpm** | system | Playwright recorder |
| **edge-tts** | `pip install --user edge-tts` | Free Microsoft TTS, no API key |
| **playwright** | `cd demo-video && pnpm add playwright && pnpm exec playwright install chromium` | Headless Chrome for HTML scene capture |
| **VHS** (Charm) | `winget install charmbracelet.vhs` / `brew install vhs` | Terminal scene recording |
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

1. **Detect intent**. If user says "init demo-video" → scaffold mode. If says "build" → pipeline mode. If neither, ask which.

2. **For `init`**:
   - `mkdir <project>/demo-video/`
   - Copy `assets/scripts/*` and `assets/templates/*` to that folder
   - Copy `assets/brand.example.yaml` → `brand.yaml`
   - Run a quick interactive interview (3-5 questions): product name, URL, voice gender/tone, what each scene should show
   - Fill in `brand.yaml` based on answers
   - Print: "Edit `brand.yaml` to refine, then run `/demo-video build`"

3. **For `build`**:
   - Read `brand.yaml`
   - Verify prerequisites (`ffmpeg --version`, `python -c "import edge_tts"`, `node -v`, `vhs --version` or docker available)
   - If any missing → tell user the install command and STOP
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

4. **For `preview`**:
   - Verify cloudflared binary exists in project (offer to download from https://github.com/cloudflare/cloudflared/releases/latest if missing — ~50 MB)
   - Start tunnel: `./cloudflared tunnel --url http://localhost:8765`
   - Generate a simple `index.html` with embedded `<video>` players for each output
   - Print the trycloudflare URL — user opens on phone to review

## Critical gotchas (must apply, do not skip)

These were discovered the hard way building the reference implementation. The bundled scripts already encode them but if the agent regenerates from scratch, re-apply:

| Gotcha | Fix |
|---|---|
| **HTML pages record as WHITE flashes** at start because Playwright captures pre-CSS frames | (a) Inline `style="background:#0a0705"` on `<html>`. (b) `-ss 0.5` trim in ffmpeg conversion. Both required. |
| **Audio truncates video** to voice length (~45s) instead of full 50s, causing white tail | `apad` on voice + `duration=first` on amix in `mix-final.sh`. Never use `-shortest` for the final mux. |
| **record-graph.mjs picks endcards.webm alphabetically** when both exist | Delete `graph.webm` and `graph.mp4` at start of script. Filter webm list by mtime, not name. |
| **VHS terminal pre-CSS shows white** during VHS startup | Use bash here-doc to print Vellum theme + clear screen before any content prints |
| **Embedded `<video>` in Playwright headless plays at ~20% speed** due to throttling | Don't embed video in Playwright. Use ffmpeg `overlay` filter to composite source video onto a Playwright-captured PNG of the frame chrome. |
| **Edge TTS WordBoundary events don't fire by default** | Pass `boundary="WordBoundary"` to `edge_tts.Communicate(...)` |
| **Scene crossfade offsets drift** when scene durations change | `assemble.sh` reads actual normalized durations via ffprobe before computing xfade offsets, never hardcodes |
| **VO timing drifts from scenes** | After every scene-duration change, re-run alignment check: `python -c "..."` script that maps each VO line to its scene. If any line ends up in the wrong scene, adjust `pause_after` values in `brand.yaml` and regenerate VO. |

## File map

```
demo-video/
├── brand.yaml                  ← user edits this
├── scripts/                    ← copied from skill
│   ├── make-vo.py
│   ├── make-captions.py
│   ├── make-music.sh
│   ├── assemble.sh
│   ├── mix-final.sh
│   ├── burn-captions.sh
│   ├── record-frame.mjs
│   ├── record-endcards.mjs
│   ├── record-graph.mjs
│   ├── display.sh
│   └── build.sh                ← orchestrator
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
