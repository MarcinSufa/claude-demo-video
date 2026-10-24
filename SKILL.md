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
   - Run `bash scripts/build.sh` from the `demo-video/` folder (where `brand.yaml` lives).
     It compiles `brand.yaml` into `.build/`, resolves the scene plan, gates prerequisites
     **arc-aware** (ffmpeg/python3/node/edge-tts/Playwright always; VHS/Docker only if the
     plan has a terminal or multi-agent scene), starts the local http server and runs every
     step listed under *Pipeline*. Never run the steps by hand.
   - If a prerequisite is missing it prints the install command and STOPs.
   - Re-runs reuse unchanged scene clips: `--only <id>` re-records one scene, `--no-cache` all.
   - Report its progress lines to the user. On an error, show the ffmpeg/Playwright stderr;
     most issues are missing fonts or wrong palette syntax (`references/troubleshooting.md`).

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

Shows a task's outcome: the bug, then the fix, as two labeled clips (sequential or side by side).
Read `references/before-after.md` when a scene uses `type: before_after` or the user asks for a bug→fix demo.

## Diorama scene (`diorama`)

Several windows on one canvas with a moving camera and the mascot hopping between them.
Read `references/diorama.md` when a scene uses `type: diorama`.

## Pronouncing brand names

TTS reads brand names phonetically in its own language — a Polish voice says
"Asistel" as "A-śi-stel" (like the name *Asia*). When using a non-English `voice_id`
with an English product name, sanity-check pronunciation and add a `voice.pronounce`
map in brand.yaml (respell for the voice; captions keep the original spelling).

## Critical gotchas

The bundled scripts already handle white flashes, audio truncation, WordBoundary timing, caption contrast and more.
Read `references/gotchas.md` before regenerating or editing any script or template by hand.

## Output

After `build` completes, the user has:
- `videos/final-framed.mp4` — share this on Twitter / LinkedIn / landing page
- `videos/final-with-captions.mp4` — same but full-screen (no terminal frame)
- `captions.srt` — upload to YouTube for accessibility / SEO
- `vo.mp3` — standalone voice track if they want to re-edit in another tool

## Mascot

An optional animated pixel mascot (`mascot:` in brand.yaml; grid, sprite sheet or paid PixelLab art).
Read `references/mascot.md` when the user wants a mascot or a build prints a mascot warning.

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
