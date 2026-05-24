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
  actions:
    - { wait: 1.0 }                                          # pause N seconds
    - { hover: ".sidebar .new-vault" }                       # glide + hover selector
    - { click: "button.new-vault" }                          # glide + click
    - { fill: { selector: "input[name=title]", text: "..." }}# fill an input
    - { type: "typed character by character" }               # type into focused el
    - { press: "Enter" }                                     # keyboard key
    - { scroll: 400 }                                        # wheel down (negative = up)
```

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
