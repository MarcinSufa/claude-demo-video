---
name: demo-video
description: Use when the user wants to turn their app, UI, or product into a polished ~50s feature/demo video showing how it works — capturing the real running app (or an HTML mockup, or a terminal), narrated with AI voiceover, synced karaoke captions, a music bed, and brand framing. Triggers on "make a feature video", "demo video of my app", "show how my app works as a video", "UI walkthrough video", "product launch film", "video for landing page", "record my app with narration", "screen recording with voiceover and captions", "ExoVault-style demo".
---

# /demo-video — turn an app/UI into a ~50s narrated feature film

## What it makes

A single `final-framed.mp4` (~50s, 1920×1080) that shows **how an application works**, in a polished product-film aesthetic:

- **Your scenes, your order** — `scenes.sequence` composes any mix of: `browser_capture` (drive + record the REAL running app), `before_after` (a labeled BEFORE/AFTER comparison of two clips — bug→fix task demos), `html_mockup` (a designed screen for an unbuilt feature), `screen_recording` (an existing clip), `terminal` (CLI via VHS), plus built-in `graph` and `endcards`.
- **AI voiceover** narrating the feature (Edge TTS, free, no API key, many languages/voices)
- **Karaoke word-highlight captions** synced via WordBoundary events, readable on light AND dark UI
- **Music bed**: CC0 library track per mood / procedural / your own file / none, fitted to the video, auto-ducked under the voice
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
render-mascot.py  → mascot sprite frames (if mascot: configured) — overlaid inside build-scenes.sh per row/step
make-vo.py        → Edge TTS streams vo.mp3 + vo-words.json (word-level timing)
make-captions.py  → captions.ass (karaoke) + captions.srt
plan-scenes.py    → resolve the scene sequence → scene-plan.json
make-auth.mjs     → (if `auth:` set) log in once → auth.json (authed scenes reuse it).
                    mode: scripted (creds) | manual (headed, you log in — SSO/OIDC/2FA)
build-scenes.sh   → render each scene by type; pin to `duration:` (normalize-clip.py) if set; cached
autofit.py        → (if `scenes.autofit`) adjust speedup so video holds the voiceover
assemble.sh       → normalize + speedup + crossfade N scenes → final-rough.mp4
make-music.sh     → music.mp3 fitted to final-rough.mp4 (library CC0 track via fetch-music.py, procedural, file or none)
mix-final.sh      → ⚠ timing gate (check-timing.py) → voice + music sidechain-ducked → final-with-audio.mp4
burn-captions.sh  → ffmpeg subtitles filter → final-with-captions.mp4
verify-final.py   → ⚠ blocks on duration drift, missing/silent audio, white flash; prints captions per scene
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
   - Copy `assets/mascots/` → `<project>/demo-video/mascots/` (the roster JSON files — needed so the build can find roster characters at `demo-video/mascots/$CHAR.json` when running from a scaffolded project)
   - Copy `assets/music/` → `<project>/demo-video/music/` (the CC0 track manifest read by `music.mode: library`; without it the build warns and uses procedural music)
   - Copy `assets/brand.example.yaml` → `brand.yaml`
   - Copy `assets/package.example.json` → `package.json` (so `pnpm install` lands
     Playwright in *this* folder, not a parent — without a local manifest pnpm walks
     up and installs into the wrong `node_modules`). Optionally set `name` to `<project>-demo-video`.
   - Copy `assets/mockup.example.html` → `mockups/example.html` (starter for `html_mockup`
     scenes — demo unbuilt features without touching the real codebase)
   - If the user wants the mascot: read the logo/brand colors, pick the best-fit roster character, call `mascot_brand.remap_palette` with brand colors, optionally edit accessory cells in the grid, write `mascot.json` next to `brand.yaml`.
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
     bash assemble.sh
     bash make-music.sh
     bash mix-final.sh
     bash burn-captions.sh
     python verify-final.py videos/final-with-captions.mp4 --rough videos/final-rough.mp4
     node record-frame.mjs
     ```
   - On each step, report progress to user
   - On any error, stop and show ffmpeg/playwright stderr — most issues are missing fonts or wrong palette syntax

3b. **For `plan`** (dry run, ~1s, no render):
   - `bash scripts/build.sh --plan`
   - Reports each scene's pinned `duration` (and on-screen length after speedup), the
     voiceover length (measured from `.build/vo-words.json` when a build of the current
     script exists, otherwise estimated from word count; the output names which), and the
     predicted video length with a **PASS/WARN** verdict. WARN exits non-zero: narration would be cut.
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

## Before / after task demos (`before_after` scene)

To show a task's outcome — the bug, then the fix — use a **`before_after`** scene.
It takes two clips, burns a colored banner on each (red = before, green = after by
default), and joins them — `layout: sequential` (before then after) or
`side_by_side` (the two clips next to each other).

```yaml
sequence:
  - hero
  - type: before_after
    before: { source: "footage/before.mp4", label: "BEFORE — the bug" }
    after:  { source: "footage/after.mp4",  label: "AFTER — the fix" }
    layout: sequential        # or "side_by_side"
    half_duration: 8          # optional: trim each half to N seconds
  - endcards
```

Each half is a **clip path / `{ source }`**, or a **`browser_capture` spec**
(`{ url, actions, auth, ... }`) that the pipeline records for you — so you can
point `before` at the deployed/no-fix URL and `after` at the fixed branch and let
it capture both. A `source` path is taken **relative to your demo project
directory** (where `brand.yaml` lives, e.g. `footage/before.mp4`), or absolute.
How to produce the two clips for a *code* change:

1. Record the **before** against the no-fix state (deployed URL, or the base
   branch's dev server), e.g. via a Playwright/e2e run with `video: 'on'`, or a
   `before_after` half with `before: { url: <staging>, actions: [...] }`.
2. Record the **after** against the fixed branch the same way (a second dev server
   on another port + re-auth, or `after: { url: <local-fix>, ... }`).
3. Drive the *same* interaction in both so the comparison is honest; trim with
   `half_duration` and label each side.

**Focus the capture on what changed.** A `before_after` capture half is a
`browser_capture` spec, so its `actions` take focus controls: `glow`/`highlight`
to pulse the touched element (the selector must match exactly one DOM node, or the
recording stops naming the action, selector and count), `waitToast` to guarantee an error/success
notification is on screen, and per-action `speed` (ramp out a slow load) + `zoom`
(Ken Burns onto the toast/field). Off-screen targets are auto-scrolled into view
before interaction. So a bug→fix demo reads clearly — the viewer sees the toast in
BEFORE and its absence in AFTER, full-frame, without watching spinners. See
`references/scene-config.md` → *Focus & pacing*. (`clip` frames one region for the
whole half; `speed`/`zoom` are time-windowed and composable with it.)

Banner labels render through ffmpeg `drawtext`, which is not reliably UTF-8 on
Windows — labels are auto-sanitized to ASCII (an em-dash becomes `-`), so keep
them short and plain.

## Diorama scene (`diorama`)

A **`diorama`** lays out N terminal/browser windows on one big canvas, then moves
an eased camera that pans and zooms between them while the mascot hops from window
to window — the "agent view" of several sessions working at once. Each window is a
recorded clip (a `source` mp4 or a live `url` capture) placed at a canvas
`(x, y)` with a width `w`; the camera visits `focus` targets; the mascot is
keyed per window.

```yaml
sequence:
  - hero
  - type: diorama
    duration: 14                 # optional — defaults to the camera tour's length
    canvas: { width: 2560, height: 1440, backdrop: "color=c=0x0a0705" }  # 16:9; backdrop: lavfi color= or an image path
    windows:                     # id + top-left (x,y) + width (w); height follows the clip aspect
      - { id: worker,   source: "footage/worker.mp4",        x: 120,  y: 300, w: 1000, chrome: true }
      - { id: reviewer, url: "http://localhost:3000/review", x: 1440, y: 600, w: 1000, actions: [{ wait: 1.0 }] }
    camera:                      # focus: a window id | "all" (bbox of all windows); zoom>1 tightens
      - { focus: all,      zoom: 1.0, hold: 1.5 }
      - { focus: worker,   zoom: 1.8, hold: 3.0, transition: 1.2 }   # transition eases INTO this stop
      - { focus: reviewer, zoom: 1.8, hold: 3.0, transition: 1.2 }
    mascot:                      # window-relative keyframes: at_window + anchor (top | beside | on)
      keyframes:
        - { at: 0,  emotion: idle,      at_window: worker,   anchor: top }
        - { at: 5,  emotion: point,     at_window: reviewer, anchor: beside }   # auto-walks worker -> reviewer
        - { at: 10, emotion: celebrate, at_window: reviewer, anchor: top }
```

How it builds: every window clip is composited onto the canvas at its `(x, y)`,
the mascot is drawn at its window-relative anchor (in canvas space), then a single
`zoompan` camera renders the 1920×1080 scene by panning/zooming over the canvas.
Camera coordinates are eased with smoothstep; the mascot auto-walks between windows
when consecutive keyframes target different ones.

**v1 boundaries:**
- **Windows are static** — they don't move or animate position; only the camera moves.
- **The mascot is placed at anchors**, not physics/collision-walked — `top` perches
  on a window's top edge, `beside` sits to its right, `on` centers inside it.
- **The canvas must be 16:9** (the camera frames a 16:9 region; a non-16:9 canvas
  would distort). 2560×1440 is the natural choice.
- **Heavier to render** than a flat scene — it composites the canvas and runs a
  second camera pass, so expect a diorama to cost more than an equivalent single clip.
- **Window chrome (`chrome: true`).** A window may set `chrome: true` (and an optional `title:`, default = the window id) to draw a macOS-style title bar — three traffic-light dots + the title — framing it. Use it for raw `source`/`url` clips that don't bring their own window frame (the Fractal mockups draw their own chrome in HTML). The bar adds a fixed height above the clip, and the camera frames the whole window including its chrome. Long titles may clip.

The global mascot's corner overlay is **auto-suppressed** on diorama scenes (the
scene composites its own mascot on the canvas), so a diorama and ordinary overlaid
scenes coexist in one video without a double mascot.

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
| **VO timing drifts from scenes** | `check-timing.py` now checks this automatically on every build (Problem B): it maps each VO line to the scene it starts in and warns (never fails the build) if the line overruns that scene's window, including the internal BEFORE/AFTER cut inside a composite `before_after` scene. No hand-run script needed -- if a warning prints, adjust `pause_after` values in `brand.yaml` and regenerate VO. |
| **Karaoke captions wash out on light app UI** (`browser_capture` / `html_mockup` scenes) | Use `BorderStyle=3` opaque box. The box colour goes in the **`OutlineColour` slot** (libass draws the BorderStyle=3 box from OutlineColour, NOT BackColour) and **must be fully opaque (alpha `00`)** — a semi-transparent box overlaps at the per-word `\k` seams and doubles up into ugly darker vertical bands. Set box colour = `palette_bg` so it blends invisibly on dark terminal scenes but reads as a solid bar over light UI. |

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

## Output

After `build` completes, the user has:
- `videos/final-framed.mp4` — share this on Twitter / LinkedIn / landing page
- `videos/final-with-captions.mp4` — same but full-screen (no terminal frame)
- `captions.srt` — upload to YouTube for accessibility / SEO
- `vo.mp3` — standalone voice track if they want to re-edit in another tool

## Mascot

An animated mascot character can be overlaid on any scene. Configure globally in `brand.yaml`:

```yaml
mascot:
  character: octopus      # roster character (or ship your own mascot.json next to brand.yaml)
  enabled: true
  position: bottom-right  # bottom-left | top-right | top-left
  scale: 1.0
  shade: true             # CHOICE: true = painted depth · false/omit = flat (default). See below.
```

**Shaded or flat — your choice.** The `shade` flag is the single switch between
the two looks: leave it off (or `false`) for the original flat fills, set `true`
for procedural depth. Default is flat, so existing builds are unchanged; flipping
one line lets you compare.

**Procedural shading (`shade: true`).** A flat character gets dimensionality at
build time with no art rework: `shade_sprite.py` (shader v2) adds a *hue-shifted
ramp* the way pixel artists do it — light reads warm, shadow reads cool, so flat
fills look painted rather than just dimmed. On the top of the silhouette it places
a `hi` rim that's lighter **and** hue-rotated toward yellow (slightly
desaturated); along the bottom a `shade` rim that's darker **and** hue-rotated
toward blue/purple (slightly more saturated). A second, deeper `shade2` lands on
the silhouette floor and under overhangs (chin, pouch) for a two-step shadow
gradient instead of one flat band, and a subtle 1-cell checkerboard *dither*
softens the body→shadow boundary into texture rather than a hard line. Each eye
still gets a near-white catch-light. It's deterministic, derives every new colour
from the character's own body colour (near-greys ramp by value only, no tint), and
works on any character that has `body` and `eyes` palette slots. The dither is on
by default (pass `--no-dither` to `shade_sprite.py` to disable). Off by default
(flat fills); opt in per project.

### Art sources (`mascot.source`)

The mascot art can come from three places — all converge on the same rendered
frame contract (`<dir>/<emotion>/f_%03d.png` + `mascot-meta.json`), so the
overlay, keyframes, caching, and motion work identically whatever the source:

- **`grid`** (default) — a hand-authored pixel-grid `mascot.json` (a roster
  character or your own), optionally `shade`d, rendered by `render-mascot.py`.
  Fully free, deterministic, editable, brand-remappable.
- **`sheet`** — import an external sprite sheet + Aseprite-style frames JSON
  (the format libresprite, Aseprite, and pixel-art plugins export). Lets a human
  artist or another tool author the sprites; `import-spritesheet.py` slices the
  sheet by its `frameTags` into per-emotion frames. Tag your animations with the
  emotion names (`idle`, `walk`, `panic`, …).

  ```yaml
  mascot:
    source: sheet
    sheet: mascot-sheet.png    # next to brand.yaml
    tags: mascot-sheet.json    # Aseprite frames+frameTags export
  ```

- **`pixellab`** — generate the character and its cycles with the PixelLab API
  (AI pixel-art, **paid**). The API key is read from the `PIXELLAB_API_KEY`
  environment variable, or from `~/.pixellab/credentials.json`
  (`{"api_key": "..."}`); without a key the build warns and proceeds mascot-less.
  `gen-pixellab.py` creates a base character from the prompt, animates it per
  emotion, and writes the frames.

  ```yaml
  mascot:
    source: pixellab
    prompt: "a coral kangaroo with a cream pouch, friendly"
    n_frames: 6
  ```

  Run `python gen-pixellab.py <out> --prompt "…" --dry-run` to exercise the
  plumbing without a key or spend.

Whichever source you use, ideally cover the full emotion set
(idle/type/walk/panic/celebrate/sleep/point/enter/exit). Any emotion a sheet or
PixelLab run doesn't provide is **filled from `idle`** at build time (with a
warning) so the overlay never hard-fails — that emotion simply renders as idle.
`idle` itself must be present.

The mascot's emotion is inferred from the scene type by default (e.g. `type` for terminal, `idle` for browser captures). Override per scene using the dict form in `scenes.sequence`:

```yaml
scenes:
  sequence:
    - hero
    - type: before_after
      before: { source: footage/before.mp4 }
      after:  { source: footage/after.mp4 }
      mascot: { before: panic, after: celebrate }   # emotion per half
    - type: browser_capture
      url: http://localhost:3000
      mascot: { emotion: celebrate }                # single emotion override
    - type: terminal
      scene: recall
      mascot: { enabled: false }                    # suppress for this scene
    - endcards
```

**Built-in string scene names** (e.g. `"hero"`, `"graph"`) do not support per-scene `mascot:` overrides — use the dict form `{ type: ..., mascot: {...} }` for that. The global `mascot:` block in `brand.yaml` still applies to all scenes.

**Keyframe choreography.** Within a single scene you can time-stamp emotions and positions using `keyframes`. Each keyframe has an `at` (seconds from scene start), an `emotion`, and an optional `position`. Keyframes replace event-based resolution for that scene; the mascot holds the default emotion/position before the first keyframe if its `at` > 0.

```yaml
- type: html_mockup
  source: mockups/board.html
  duration: 15
  mascot:
    keyframes:
      - { at: 0,  emotion: idle }
      - { at: 4,  emotion: type }
      - { at: 9,  emotion: point, position: bottom-left }
      - { at: 13, emotion: celebrate }
```

**Walk between positions.** When consecutive keyframes (or segments) have different `position` values, the pipeline automatically inserts a 0.8 s `walk` move-segment at the start of the later segment. The mascot slides from the old anchor to the new one using a lerped ffmpeg expression — no manual walk step required.

**Motion modifiers.** Two emotions add physical motion on top of position:
- `celebrate` — bounces the mascot vertically (`18 * abs(sin((t-AT)*4))` px) while playing the celebrate animation frames.
- `panic` — shakes the mascot horizontally (`4 * sin((t-AT)*18)` px) while playing the panic animation frames.

**Roster.** Built-in characters: `octopus`, `tessel`, `kangaroo`. Specify one with `mascot.character` in `brand.yaml`. You can also ship a custom `mascot.json` next to `brand.yaml` (any character name).

**Never blocks the build.** If `render-mascot.py` fails (missing font, bad JSON), the pipeline warns and continues mascot-less — the video still renders.

**Two-layer cache.** Mascot frames are cached separately from scene recordings. Changing `mascot:` config (emotion, position, scale, keyframes) re-overlays without re-recording, so iteration is fast.

## Testing & maintenance

- **Unit tests** — `python -m unittest discover -s tests` (timing/duration, scene
  cache, mascot data/shading/timeline/sources; run before changing those scripts).
- **Integration smoke** — `bash tests/smoke_build.sh` scaffolds a throwaway project
  and exercises the real pipeline. It always runs a light `--plan` tier (config +
  scene-plan + drift guard); with `node` + `edge-tts` + a Playwright `node_modules`
  present (or `DEMO_SMOKE_NODE_MODULES=/path`) it also does a FULL render and asserts
  a non-blank video. Catches integration breaks unit tests can't (mockups not copied
  into `.build`, mascot-less arg skew, white-flash).
- **Vendored-script drift guard** — each project keeps a COPY of these scripts in
  `demo-video/scripts/`. A partial re-sync (some files refreshed, others stale) used
  to fail silently (e.g. a new `build.sh` passing `--scale` to an old
  `render-mascot.py`). `build.sh` now fingerprints its scripts against the committed
  `assets/scripts/VERSION` and **warns** if they're inconsistent — re-copy ALL of
  `assets/scripts/*` to fix. `DEMO_STRICT_SCRIPTS=1` makes drift a hard error
  instead of a warning. After changing any runtime script, refresh the stamp:
  `python assets/scripts/scripts_fingerprint.py --write assets/scripts` (a unit test
  enforces it's current). **Migration:** projects scaffolded before this guard
  existed lack `scripts_fingerprint.py`/`VERSION` and silently skip the check until
  you re-copy the full `assets/scripts/*` set once.
- **CI** — `.github/workflows/test.yml` runs the unit tests, shell syntax checks, and
  the `--plan` smoke tier on every push/PR.

## See also

- `references/workflow.md` — pipeline internals, what each step does
- `references/brand-config.md` — full `brand.yaml` schema with all options
- `references/troubleshooting.md` — debugging white flashes, sync drift, audio truncation
- `references/persuasion-pacing.md` — VO writing principles (Anthropic-style narration, 115 wpm, short sentences)
