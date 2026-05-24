# Scene types & custom arcs

The default `arc: memory-product-default` builds a fixed 7-scene terminal narrative.
For **real UI / feature demos**, set `arc: custom` and define `scenes.custom_scenes`.

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
Same engine as the built-in `graph`/`endcards` scenes.

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

- `browser_capture` — ✅ working (record-browser.mjs)
- `screen_recording` / `html_mockup` — engine exists (assemble normalizes any mp4;
  Playwright renders any HTML); custom-arc dispatcher in assemble.sh is the remaining
  wiring (v0.2). Until then, run `record-browser.mjs` standalone and drop outputs into
  `videos/`, then point assemble at them.
