# Scene types, count & custom arcs

## Choosing how many scenes (and which)

Three ways, most-explicit wins:

**1. `scenes.sequence`** — pick the EXACT scenes and count (recommended). Mix
built-in names with custom scene objects, any count ≥ 2:

```yaml
scenes:
  sequence: [hero, graph, endcards]          # tight 3-scene cut
```
```yaml
scenes:
  sequence:
    - hero
    - { type: browser_capture, url: "http://localhost:3000", actions: [{ scroll: 400 }] }
    - endcards                                # built-in + real UI
```
Built-in names: `hero`, `typing`, `amnesia`, `graph`, `recall`, `multi-agent`, `endcards`.

**2. `arc` preset** — named shortcut that expands to a sequence:
- `memory-product-default` → 7 scenes (hero·typing·amnesia·graph·recall·multi-agent·endcards)
- `short` → 3 (hero·graph·endcards)
- `problem-solution` → 5 (hero·amnesia·graph·recall·endcards)

**3. `arc: custom` + `custom_scenes`** — legacy all-custom list (same as sequence of objects).

## Music

```yaml
music:
  mode: "procedural"   # procedural | file | none
  volume: 0.45         # bed level, auto-ducked under voice
  # file: "assets/track.mp3"   # for mode: file
```
- **procedural** — generated warm ambient pad (default, placeholder quality)
- **file** — your own track. Free/CC0 sources: Pixabay Music, Free Music Archive, YouTube Audio Library
- **none** — voice only, no bed

---

## Scene types (for custom scenes / sequence objects)

For **real UI / feature demos**, use scene objects in `sequence` (or `custom_scenes`).

## Scene types

### `browser_capture` — record a real running app

Drives a real URL with Playwright (click/type/scroll/hover), records video with a
smooth fake cursor, trims the pre-paint frame. This is how you demo **actual UI**.

```yaml
- type: browser_capture
  url: "http://localhost:3000/dashboard"   # real app OR https://live-site.com
  cursor: true              # show a soft cursor that glides between targets
  settle_ms: 1200           # wait after page load before acting
  tail_ms: 1500             # hold at the end
  viewport: { width: 1920, height: 1080 }
  duration: 6               # optional — pin the clip to EXACTLY 6s (see below)
  clip: ".schedules-dialog" # optional — crop+zoom to the element you're changing
  actions:
    - { wait: 1.0 }                                          # pause N seconds
    - { hover: ".sidebar .new-vault" }                       # glide + hover selector
    - { click: "button.new-vault", glow: true }             # glide + click (glow: pulse it)
    - { fill: { selector: "input[name=title]", text: "..." }}# fill an input
    - { type: "typed character by character" }               # type into focused el
    - { press: "Enter" }                                     # keyboard key
    - { scroll: 400 }                                        # wheel down (negative = up)
    - { scroll_into_view: ".load-row" }                      # bring an off-screen el into view
    - { highlight: ".total-row" }                            # pulse an element (no click)
    - { waitToast: "Error" }                                 # wait until a toast/alert shows
    - { wait: 1.5, speed: 4 }                                # speed: ramp this span (hide loading)
```

**Focus & pacing (per-action `speed` / `zoom`).** Any action takes an optional
`speed` (playback rate for its span — `speed: 4` over a `wait` makes a slow load
read as a blink) and `zoom` (a Ken Burns push onto the region that changed). These
are written to a `<clip>.events.json` sidecar and applied by `cut-clip.py` after
capture — a no-op when unused, so existing scenes are unaffected.

```yaml
actions:
  - { click: "button.save", glow: true }
  - { wait: 2.0, speed: 5 }                                  # the save spinner flies by
  - { waitToast: "Saved", zoom: { fx: 0.85, fy: 0.12, z: 1.3 } }  # zoom the toast corner
```

`zoom` focal points are normalized: `fx`/`fy` are 0–1 (0,0 = top-left), `z` > 1 is
the zoom factor. `speed`/`zoom` are **time-windowed** (they affect only that
action's span); `clip` (below) is a **static** crop applied to the whole scene. Use
`zoom` to push in on a toast then pull back; use `clip` to frame one dialog for the
entire scene. `waitToast` matches any `[class*=toast]` / `[role=alert]` node, so an
error/success notification is guaranteed on screen rather than scrolling past.

**`clip` — frame the change, not the whole page.** When a demo is about one
control/dialog/row, record the full page but crop+zoom the output to that element so
viewers actually see what changed:

```yaml
clip: ".schedules-dialog"               # selector (default 32px padding)
clip: { selector: ".load-row", pad: 48 }  # selector + custom padding
clip: { x: 600, y: 300, width: 720, height: 480 }   # explicit rect
```

The element is measured at the **end** of the scene (so a dialog opened mid-scene is on
screen), then the clip is cropped to it and upscaled back to the scene size — so every
scene keeps identical dimensions for crossfades. Use `scroll_into_view` first if the
target is below the fold. Works in `before_after` capture halves too. Don't begin a
real-app scene on the loading screen — `browser_capture` already auto-trims the boot/auth
splash (`trim_start_ms` to override).

**Runs standalone too:**
```bash
node scripts/record-browser.mjs scene.json
```
where `scene.json` has `{ url, output, actions, ... }`.

**Tips:**
- For authenticated pages, capture against a logged-in localhost session, or add a
  login action sequence at the start.
- `cursor: true` injects a CSS dot that follows Playwright's mouse — clicks ripple.
- Keep each capture 4-8s. Longer = the assembled film drags.

### `screen_recording` — import an existing clip

```yaml
- type: screen_recording
  source: "assets/feature-clip.mp4"   # from Screen Studio, OBS, QuickTime, etc.
```
ffmpeg normalizes it (1920×1080, 30fps, speedup) and folds it into the crossfade chain.

### `html_mockup` — render a designed screen

```yaml
- type: html_mockup
  source: "mockups/new-pricing.html"   # any local HTML (uses your fonts/palette)
  duration: 6
  actions: [ { scroll: 300 } ]         # optional Playwright actions
```
Same engine as the built-in `graph`/`endcards` scenes. Use this to demo a feature the
real app doesn't have yet **without adding a throwaway view to your codebase**. Start
from `mockups/example.html` (scaffolded by `init`). The recorder injects your
`palette.bg` before first paint, so a mockup that forgets an inline background won't
record as a white flash.

### Warming up real routes (`browser_capture`)

Dev servers (Next etc.) compile a route on first hit, so a cold capture can catch a
"Rendering…" overlay. `browser_capture` warms the route in a separate (non-recording)
pass first — default **on** for `localhost`/`127.0.0.1`, **off** for public sites.
Override per scene with `warmup: true|false`.

### Authenticated apps (`auth:` + `auth: true`)

Each `browser_capture` runs in its own browser context, so an authenticated app would
otherwise need to log in inside every scene. Define a top-level `auth:` block — the build
logs in **once** (via `make-auth.mjs`), saves the session (Playwright `storageState`), and
any scene with `auth: true` starts already logged in with no login UI on camera.

**Scripted** (default) — replay credentials headlessly:

```yaml
auth:
  login_url: "http://localhost:3000/login"
  actions:
    - { fill: { selector: "#email", text: "demo@yourapp.com" } }
    - { fill: { selector: "#password", text: "demo-password" } }
    - { click: "button[type=submit]" }
  wait_for: "**/dashboard"        # URL glob OR a selector confirming login landed

scenes:
  sequence:
    - { type: browser_capture, url: "http://localhost:3000/orders", auth: true }
```

**Manual** (`mode: manual`) — for SSO / OIDC / 2FA flows that can't be scripted, and to keep
**zero credentials in the file**. The build opens a **headed** browser; you log in by hand,
and the session is saved + reused on later builds (delete `.build/auth.json` to re-login):

```yaml
auth:
  mode: manual
  login_url: "https://app.example.com/"
  wait_for: 'role=link[name="Dashboard"]'   # a post-login signal — a SELECTOR is most robust
                                             # (a URL glob can match a transient pre-login hop)
```

If login doesn't complete, `make-auth.mjs` fails loudly (prints the final URL + page text,
saves `auth-fail.png`, exits non-zero) instead of recording a login screen. Tip: target the
multi-select options that portal to `<body>` with an UNscoped `role=option[name="…"]`
(scoping to the dialog misses them).

### Auto-fitting length to the voiceover (`scenes.autofit`)

Set `scenes.autofit: true` and the build adjusts `speedup` after capture so the video just
holds the narration (`video ≥ last-spoken-word + 1s`), clamped to 0.8–1.4×. If the VO is too
long to fit even at the slowest allowed speed, it warns and leaves `speedup` alone — the
mix step still **fails** rather than silently truncating. Off by default; pin scene
`duration`s for fully deterministic timing instead.

### Pinning scene length (`duration:`) — deterministic alignment

`browser_capture` and VHS clip lengths jitter run-to-run, which makes voiceover↔video
timing a guessing game. Add `duration:` to **any generated scene** (browser_capture,
html_mockup, terminal, graph, endcards) and the clip is normalized to exactly that —
trimmed if long, freeze-frame padded if short:

```yaml
- { type: browser_capture, url: "...", duration: 6 }   # always 6.00s, every run
```

**`duration` is the RAW clip length (before `scenes.speedup`).** assemble.sh then
applies speedup to every scene, so the on-screen length ≈ `duration / speedup`, and the
final film length follows the validated model:

```
video = Σ(duration) / speedup − (N−1) × crossfade_seconds
```

Pin every scene's `duration` and the film length is known before you render — run
`/demo-video plan` (dry run) to see the predicted length and a PASS/WARN against your
voiceover estimate. Not applied to `screen_recording` (won't mutate your source file).

### Built-in scenes (reusable in custom arc)

```yaml
- type: terminal
  scene: hero          # hero | input | amnesia | recall | agent:0
- type: graph          # knowledge-graph animation (uses palette + memory colors)
- type: endcards       # branded end cards (logo + wordmark + tagline + url)
```

## Example: feature-launch arc for a SaaS

```yaml
scenes:
  arc: custom
  speedup: 1.15
  crossfade_seconds: 0.5
  custom_scenes:
    - type: browser_capture            # the problem: empty state
      url: "http://localhost:3000/projects"
      actions: [ { wait: 1.5 } ]
    - type: browser_capture            # the feature in action
      url: "http://localhost:3000/projects/new"
      actions:
        - { click: "button.ai-suggest" }
        - { wait: 2.0 }
        - { scroll: 300 }
    - type: browser_capture            # the result
      url: "http://localhost:3000/projects/123"
      actions: [ { hover: ".ai-badge" }, { wait: 1.5 } ]
    - type: endcards

voiceover:
  - { text: "Starting a project used to mean a blank page.", pause_after: 1.2 }
  - { text: "Now, just describe it.", pause_after: 1.0 }
  - { text: "AI scaffolds the structure.", pause_after: 1.5 }
  - { text: "You refine. It remembers.", pause_after: 1.0 }
  - { text: "yourapp dot com.", pause_after: 0.5 }
```

The VO + captions + music + terminal-on-desk frame all apply identically — you get a
polished launch film of your **real product UI**, not a terminal mockup.

## Status

- `browser_capture` — ✅ working (record-browser.mjs), `duration:` honored
- `html_mockup` — ✅ working (same Playwright engine), `duration:` honored
- `screen_recording` — ✅ working (assemble normalizes any mp4); `duration:` ignored
  (won't mutate your source file)
- Custom-arc / `sequence` dispatcher — ✅ wired in build-scenes.sh (any scene count/order)
