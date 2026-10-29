---
name: demo-video
description: Record a real web app as video, or turn it into a polished ~50s narrated feature film. Quick capture drives a running app (localhost or live) with Playwright from a small scene.json and writes an mp4 with no voiceover or music, to verify a UI change or record a click-through. The full film adds real-UI, HTML-mockup or terminal scenes, free AI voiceover (Edge TTS), karaoke captions, a music bed and brand framing. Use when the user says "record a click-through", "verify UI with video", "make a feature video", "demo video of my app", "record my app with narration", "product launch film", or in Polish "nagraj demo", "nagraj przeklikanie", "zrób film z aplikacji".
argument-hint: "[capture <scene.json> | init | plan | build | preview]"
---

# /demo-video — record an app: a quick capture or a ~50s narrated film

Two ways to use it:

- **Quick capture** (most common): drive the running app through a few clicks and get an mp4. No voiceover, music or brand setup. Use it to verify a UI change or to hand someone a click-through.
- **Full film**: a scaffolded `demo-video/` project with `brand.yaml` → `videos/final-framed.mp4` with voiceover, captions, music and framing.

## Quick capture (verify a UI change, no voiceover, no music)

Needs only **node + Playwright + ffmpeg** (no Python, no brand.yaml).
Node resolves `playwright` from the script's own folder, so run the recorder from a folder
where Playwright is installed: copy the three scripts next to a `node_modules` that has it.

```bash
mkdir -p /tmp/demo-capture && cd /tmp/demo-capture
cp "${CLAUDE_SKILL_DIR}"/assets/scripts/{record-browser,glow_check,paint_guard,chromium_launch}.mjs .
ln -s /path/to/app/node_modules node_modules       # reuse the app's Playwright, or:
# npm init -y && npm install playwright && npx playwright install chromium   (pnpm works too)
node record-browser.mjs scene.json
```

Minimal `scene.json` (paths are relative to the current folder):

```json
{
  "url": "http://localhost:3000/todos",
  "output": "videos/add-item.mp4",
  "viewport": { "width": 1280, "height": 720 },
  "actions": [
    { "fill": { "selector": "input[name=title]", "text": "Buy milk" } },
    { "click": "button.add", "glow": true },
    { "waitToast": "Saved" },
    { "highlight": "#list li" }
  ]
}
```

- Actions: `hover`, `click`, `fill`, `type`, `press`, `scroll`, `scroll_into_view`, `wait`, `waitToast`, `highlight`; `glow: true` pulses the target. Options: `clip` (crop to one element), `settle_ms`, `tail_ms`, `cursor`, `initScript`. Full list: `references/scene-config.md` → `browser_capture`.
- A `glow`/`highlight` selector (CSS or Playwright: `button:has-text("Save")`, `role=button[name="Save"]`) must match exactly one element, or the recording stops and names the action, selector and count.
- Output: the mp4 at `output` (default `videos/scene_browser.mp4`) plus `<output>.events.json`. Per-action `speed`/`zoom` are applied only by `python3 cut-clip.py <output>` (copy it too).
- Wrong browser build ("Executable doesn't exist", `chromium_headless_shell-12xx`): set `DEMO_CHROMIUM_PATH` to an installed Chromium/Chrome binary (`ls ~/.cache/ms-playwright/`). Do not patch `executablePath` in the scripts. More: `references/troubleshooting.md`.

**Verify the result yourself** before reporting: check the length, then look at frames.

```bash
ffprobe -v error -show_entries format=duration -of csv=p=0 videos/add-item.mp4
ffmpeg -v error -y -i videos/add-item.mp4 -vf "fps=1,scale=640:-1,tile=3x2" -frames:v 1 sheet.png   # 6 frames in one image
ffmpeg -v error -y -sseof -1 -i videos/add-item.mp4 -frames:v 1 last.png                            # final state
```

Open `sheet.png` / `last.png` with the Read tool and confirm the change is on screen. Text drawn as boxes means the machine has no fonts (troubleshooting).

## Full film: what it makes

A single `final-framed.mp4` (~50s, 1920×1080) showing **how an application works**:
your scenes in your order (`browser_capture` of the real app, `html_mockup` for an unbuilt
feature, `before_after` bug→fix, `screen_recording`, `terminal` via VHS, `diorama`, built-in
`graph`/`endcards`), free Edge TTS voiceover, karaoke captions readable on light and dark UI,
a music bed ducked under the voice (CC0 library / procedural / your file / none) and brand
framing. All free tools (ffmpeg, Playwright, VHS, Edge TTS); only the optional PixelLab
mascot art is paid. The bundled `memory-product-default` arc (7 terminal scenes) is just an
example; usually you compose scenes around the real app.

Not for 5-minute tutorials (it targets ~50s) or pure motion graphics with no UI, terminal or mockup.

## Workflow (full film)

`/demo-video init` (scaffold `demo-video/`) → user edits `brand.yaml` (palette, voice, VO script,
scenes) → `/demo-video plan` (~1s dry run, PASS/WARN) → `/demo-video build` → `/demo-video preview`
(local server + tunnel for phone review).

`bash scripts/build.sh` compiles `brand.yaml` into `.build/`, records scenes, voiceover, captions
and music, mixes, verifies and frames the video. `check-timing.py` **fails the build** if narration
overruns the video (override: `DEMO_ALLOW_TRUNCATE=1`), and `verify-final.py` blocks on duration
drift, silent audio or a white flash. Step list and internals: `references/workflow.md`.

## Prerequisites

ffmpeg and Node/Playwright are needed for all captures. Full films need Python 3.10+ and pyyaml;
voice needs edge-tts. VHS is only for terminal scenes. `build.sh` checks prerequisites and prints
install commands. Full table and venv recipe: `references/setup.md`.

## Configuration — `brand.yaml`

`init` copies `assets/brand.example.yaml` (fully commented). Top-level keys: `project`,
`palette`, `logo`, `typography`, `voice`, `music`, `backdrop`, `scenes`, `voiceover`,
`end_cards`, optional `mascot`, `auth`, `verify`. The two that matter most:

```yaml
scenes:
  speedup: 1.20                # 1.0 = realtime
  sequence:                    # any order, any count
    - { type: browser_capture, url: "http://localhost:3000", actions: [ { click: "button.new", glow: true } ] }
    - { type: html_mockup, source: "mockups/example.html", duration: 6 }
    - endcards
voiceover:
  - { text: "Every session starts the same way.", pause_after: 1.1 }
  - { text: "You explain your stack.",            pause_after: 0.3 }
  # ... 12-15 lines targeting ~45s of speech for a 50s video
```

Full schema, voice options and VO writing principles: `references/brand-config.md`.
Scene types and options: `references/scene-config.md`.

## What the agent (Claude) does

1. **Detect intent**. "record / capture / verify this UI" with no narration → Quick capture (above). "init demo-video" → scaffold mode. "build" → pipeline mode. "plan" / "dry run" / "how long will it be" → plan mode (`bash scripts/build.sh --plan`). If unclear, ask which.

2. **For `init`** — scaffold `<project>/demo-video/` (the layout `build.sh` expects):
   ```bash
   D=<project>/demo-video; A="${CLAUDE_SKILL_DIR}/assets"
   mkdir -p "$D"/{scripts,templates,mascots,music,mockups}
   cp "$A"/scripts/* "$D/scripts/"; cp -r "$A"/templates/* "$D/templates/"
   cp "$A"/mascots/*.json "$D/mascots/"; cp -r "$A"/music/* "$D/music/"     # roster + CC0 manifest
   cp "$A/brand.example.yaml" "$D/brand.yaml"; cp "$A/mockup.example.html" "$D/mockups/example.html"
   cp "$A/package.example.json" "$D/package.json"   # Playwright installs HERE, not in a parent
   ```
   - Mascot wanted: pick the best-fit roster character, `mascot_brand.remap_palette` it to the brand colors, write `mascot.json` next to `brand.yaml` (`references/mascot.md`).
   - Interview (3-5 questions: product name, URL, voice gender/tone, what each scene shows) and fill in `brand.yaml`.
   - Tell the user: "Run `npm install && npx playwright install chromium` in demo-video/, then `/demo-video plan` and `/demo-video build`."

3. **For `build`** — `bash scripts/build.sh` from `demo-video/`. Never run the steps by hand.
   It gates prerequisites arc-aware and STOPs with the install command for anything missing.
   Re-runs reuse unchanged scene clips: `--only <id>` re-records one scene, `--no-cache` all.
   Relay its progress lines; on an error show the ffmpeg/Playwright stderr; most are missing fonts or bad palette syntax (`references/troubleshooting.md`).

3b. **For `plan`** — `bash scripts/build.sh --plan` (~1s, no render; needs only ffmpeg + python3 + pyyaml).
   Prints each scene's length, the voiceover length (measured from `.build/vo-words.json` when it
   matches the script, else estimated) and the predicted video length with **PASS/WARN**;
   WARN exits non-zero (narration would be cut). Use it to tune `voiceover`, `duration`, `speedup`.

4. **For `preview`** — check for a `cloudflared` binary in the project (offer to download it from
   https://github.com/cloudflare/cloudflared/releases/latest, ~50 MB), write a simple `index.html` with a
   `<video>` per output, run `./cloudflared tunnel --url http://localhost:8765` and print the trycloudflare URL.

## Demo content for features that don't exist yet

**Do NOT add a view to the real codebase just for the recording** — that leaves cruft in
production code. Use an **`html_mockup` scene**: a standalone HTML file in `mockups/` (brand
palette/fonts), captured by the same Playwright engine. Reserve `browser_capture` for routes
that genuinely exist.

## Special scenes, pronunciation, gotchas

- **`before_after`**: the bug, then the fix, as two labeled clips (sequential or side by side). Read `references/before-after.md` when a scene uses it or the user asks for a bug→fix demo.
- **`diorama`**: several windows on one canvas, a moving camera, the mascot hopping between them. Read `references/diorama.md` when a scene uses it.
- **Mascot**: optional animated pixel mascot (`mascot:` in brand.yaml; grid, sprite sheet or paid PixelLab art). Read `references/mascot.md` when the user wants one or a build prints a mascot warning.
- **Brand names**: a non-English voice reads an English name phonetically (Polish says "Asistel" as "A-śi-stel"). Add a `voice.pronounce` map in brand.yaml (respelling for the voice; captions keep the original).
- **Gotchas**: the bundled scripts already handle white flashes, audio truncation, WordBoundary timing and caption contrast. Read `references/gotchas.md` before editing any script or template by hand.

## Output

After `build` completes, the user has:
- `videos/final-framed.mp4` — share this on Twitter / LinkedIn / landing page
- `videos/final-with-captions.mp4` — same but full-screen (no terminal frame)
- `videos/captions.srt` — upload to YouTube for accessibility / SEO
- `.build/vo.mp3` — standalone voice track if they want to re-edit in another tool

## Testing & maintenance

Re-copy all of `assets/scripts/*` and `assets/music/` after every skill update. `build.sh` warns on
drift; `DEMO_STRICT_SCRIPTS=1` makes it fatal.

## References (read on demand)

- `references/scene-config.md` — every scene type and option (`browser_capture` actions, auth, `duration`, `clip`, autofit). Read when writing `scenes:` or a quick-capture scene.json beyond the minimal example.
- `references/brand-config.md` — full `brand.yaml` schema, voices, music, and VO writing principles (short sentences, ~115 wpm). Read when filling in `brand.yaml` or writing the voiceover.
- `references/setup.md`: install table, PEP 668 venv recipe, and Python resolution. Read when setting up or troubleshooting prerequisites.
- `references/workflow.md` — what each pipeline step does, caching, file map, vendored scripts. Read when a step fails or before editing a script.
- `references/troubleshooting.md` — white flashes, sync drift, audio truncation, browser build/library errors. Read when a build or capture misbehaves.
- `references/gotchas.md`, `references/before-after.md`, `references/diorama.md`, `references/mascot.md` — see *Special scenes* above for when.
