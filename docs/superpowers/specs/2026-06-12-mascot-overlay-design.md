# Mascot — brand pixel character overlay for /demo-video

Date: 2026-06-12
Status: approved design intent (brainstorm with user); amended after spec review
— see "Implementation constraints" for binding pipeline decisions.

## Summary

A pixel-art mascot (in the style of the Claude Code octopus) composited over
demo videos produced by the /demo-video skill. It never speaks — it reacts in
pantomime: idles, types along, panics at errors, celebrates successes, sleeps
through slow parts. It is generated from the user's brand (logo + palette) at
init time, works on every scene type, and is fully configurable per scene.

## Decisions made (with user)

| Question | Decision |
|---|---|
| How does it deliver humor? | **Reactions only** — no speech bubbles, no narration changes. Pure animation; humor through body language. |
| How is the character created? | **Hybrid** — skill ships a curated roster of pixel characters with complete animation sets; at init Claude picks the best-fit base for the brand, remaps colors to the brand palette, and may edit the pixel grid to add a brand accessory. |
| How does it know what to react to? | **Auto + override** — pipeline infers a default emotion timeline from scene metadata; `brand.yaml` can override per scene. |
| Where does it live on screen? | **Corner home + scripted moments** — anchored in a corner by default; big beats trigger bounded excursions (jump on AFTER reveal, recoil at an error toast, hide during dense UI). Auto-flips corner away from the scene's action region. |
| Which scenes? | **All scene types** (browser_capture, terminal, before_after, html_mockup, screen_recording, graph). Off by default on endcards. Global and per-scene toggles. |
| Pipeline placement? | **Per-scene overlay** inside `build-scenes.sh`, before normalization/assembly, participating in the scene cache. |

## Components

### 1. Character roster (shipped assets)

- 5–8 pixel characters: octopus, fox, owl, cat, robot, turtle (+ optionally more).
- Each character is a **pixel-grid data file** (JSON): named palette slots
  (`body`, `belly`, `eyes`, `accent`, `accessory`) plus per-animation frame
  grids (~16×16 to 24×24 cells, each cell a palette-slot name or transparent).
- Required animation set per character: `idle`, `type`, `panic`, `celebrate`,
  `sleep`, `point`, `enter`, `exit`. Frame counts are per-animation; playback
  fps declared in the file (e.g. 6–8 fps for the pixel feel).
- A JSON schema (`assets/mascots/schema.json`) defines the format; CI validates
  every roster file against it. Acceptance for accessory edits: edited frames
  still validate, stay within the declared grid, and only touch
  `accessory`-slot cells.
- Delivery is phased: **octopus ships first** as the reference character; the
  rest of the roster lands after the pipeline works end-to-end (see Phasing).
- Location: `assets/mascots/<name>.json` in the skill; copied on init. New
  scripts must be added to the `cp` list in `build.sh`.

### 2. Brand personalization (init-time, agent-driven)

At `/demo-video init` (or a new `/demo-video mascot` subcommand for existing
projects), Claude:

1. Reads `brand.yaml` palette + logo SVG.
2. Picks the best-fit roster character (or honors `mascot.character`).
3. Remaps palette slots to brand colors (body ← accent or a derived tint).
   Contrast guard: `body` and `eyes` must hit ≥ 3:1 WCAG contrast against
   `palette.bg`; if a mapped color fails, fall back to a lightened/darkened
   tint of the same hue that passes.
4. Optionally edits grids to add a brand accessory (hat, badge, item derived
   from the logo motif). Edits stay within the existing frame dimensions.
5. Writes the result to `mascot.json` **next to `brand.yaml`** (the demo
   project root) — user-editable, reproducible, committed with the project.
   `apply-brand.py` resolves this path and passes the `mascot` config through
   into `.build/config.json`.

### 3. `render-mascot.py` (new script)

- Input: `mascot.json` + `.build/config.json` (for palette resolution).
- Output: transparent PNG frame sequences per animation in
  `.build/mascot/<anim>/frame-%03d.png`, nearest-neighbor upscaled to the
  on-screen size (default ~140 px tall at 1080p; configurable via
  `mascot.scale`).
- No new heavy dependencies: frames are written by piping raw RGBA to ffmpeg
  (reuses the existing hard dependency; no stdlib PNG encoder to maintain).
- Default upscale and scale factor are pinned in `mascot.json` (`cell_px`,
  `scale`) so golden-frame tests are deterministic across platforms.

### 4. Emotion resolver (two-stage)

Accurate reaction timing depends on post-capture data (`.events.json` from
`record-browser.mjs`, real clip durations), so resolution is split:

**Stage 1 — plan time (`plan-scenes.py`):** defaults from scene type, user
overrides, enabled/disabled, enter/exit flags → writes a `mascot_plan` stub
into each scene-plan entry. Emotions here are best-effort.

**Stage 2 — build time (new `resolve-mascot-timeline.py`, called from
`build-scenes.sh` after capture + `cut-clip.py` + `normalize-clip.py`):**
merges the stub with `<output>.events.json` (waitToast/speed windows), ffprobe
duration of the **final normalized clip**, `half_duration`, and pinned
`duration` → exact timeline `[{at, until, emotion, moment?}]`.

Default rules from metadata the pipeline already has:

- scene type `terminal` → `type` for the body of the scene (no event sidecar;
  this is a whole-scene heuristic, not output-synced)
- `graph` → `idle`; `multi_agent` → `type`
- `before_after`, `layout: sequential`: BEFORE half → `panic` (after a brief
  `idle`), AFTER half → `celebrate` on reveal. `layout: side_by_side`: a single
  emotion for the scene — `point` (overridable); no half-split.
- `waitToast` action → `panic` if the toast text matches
  `/error|fail|invalid|denied/i`, else `point`; timed to the toast window from
  `.events.json`
- per-action `speed` ramps (slow segments) → `sleep`
- default fill → `idle`
- scene boundaries → `enter` at scene start where the mascot was absent, `exit`
  when the next scene disables it. Enter/exit are **suppressed** when the
  adjacent scene also has the mascot enabled (the crossfade carries it), and
  are kept within the first/last 0.3s of the scene otherwise.

Stage-1 stubs live in `scene-plan.json`; stage-2 final timelines are written as
sidecars next to each scene clip (`<output>.mascot.json`).

### 5. `overlay-mascot.py` (new script, called by `build-scenes.sh`)

- Runs **after** `cut-clip.py` and `normalize-clip.py` — always on the final,
  duration-pinned clip, so timelines never drift against trim/pad and the
  resolver targets the real final duration.
- Composites the PNG sequences via ffmpeg `overlay` with
  `enable='between(t,..)'` windows per timeline segment; "moments" are short
  scripted position offsets implemented as time-windowed overlay x/y
  expressions. v1 moments vocabulary: `peek` (errors), `jump` (celebrate),
  `hide` (dense-UI scenes), `recoil` (panic); per-scene `moments: off` disables
  all of them.
- Position: corner home (default `bottom-right`) with an explicit
  `caption_clearance_px` (default **200**) lifting the mascot above the burned
  caption band (captions sit ~160–200px from the bottom: bottom-center,
  `MarginV: 120`, ~40px font). Flips to bottom-left when the scene's
  `clip`/`zoom` action region overlaps the home corner. The mascot lives inside
  the screen rect only — `record-frame.mjs` terminal chrome is unaffected.
- Speedup interaction: `assemble.sh` `setpts` scales mascot playback too. The
  stage-2 resolver compensates by declaring timelines in capture-time seconds
  and bumping animation fps by the scene's effective speedup, so on-screen
  animation speed stays constant.

### 5b. Cache layering (`scene_cache.py`)

The current cache-hit path skips the whole loop body in `build-scenes.sh`, so a
single key would either re-record on mascot changes or never re-overlay. Split
into two layers:

| Phase | Cache key includes | Skipped when |
|---|---|---|
| Capture | plan entry + tape/html deps (today's key) | unchanged |
| Overlay | capture output hash + `mascot.json` + resolved timeline | both fresh |

On a capture cache hit, `build-scenes.sh` still runs the overlay phase if its
sidecar is stale (mascot config or timeline changed) — re-overlaying an
existing capture without re-recording. Capture output stays on disk as the
pristine pre-overlay clip; overlay writes a separate `<output>.mascot.mp4`
consumed by `assemble.sh`. Bump `scene_cache.VERSION` when this ships.

### 6. Configuration (`brand.yaml`)

```yaml
mascot:
  character: fox        # roster name | "auto" (Claude picks) | path to mascot.json
  enabled: true         # global toggle (default true once mascot.json exists)
  scale: 1.0            # relative to default ~140px height
  position: bottom-right

scenes:
  sequence:
    - hero
    - type: before_after
      mascot: { before: panic, after: celebrate }   # emotion overrides
    - type: browser_capture
      mascot: { position: bottom-left, moments: off }
    - type: graph
      mascot: { enabled: false }
```

Per-scene `mascot:` accepts: `enabled`, `position`, `moments` (on/off),
emotion override(s) — a single emotion for the scene or `before`/`after` for
before_after halves.

## Error handling

- Missing or invalid `mascot.json` → warn and build mascot-less; never block.
- Unknown emotion in an override → warn, fall back to `idle`.
- Character grid larger than expected or bad palette slot → validation error at
  `render-mascot.py` with the offending frame named.
- Endcards and the framed composite (`record-frame.mjs`) are untouched — the
  mascot is baked into scene clips before assembly, so captions burn on top and
  crossfades carry it naturally.

## Testing

- Unit tests (`tests/`): emotion resolver (scene metadata → timeline),
  palette remapping (slots → brand colors, contrast guard), cache-key
  composition.
- Golden-frame test: render the octopus `idle` frame 0 at the pinned
  `cell_px`/`scale` and compare pixels.
- Dry run: extend the existing `dry-run-plan.py` (no new flag) to report mascot
  status per scene (character, stage-1 emotions) with zero rendering.

## Implementation phasing

1. **Schema + octopus only** — `schema.json`, one roster character,
   `render-mascot.py`, static `idle` overlay in a corner, no resolver.
2. **Build-stage timeline** — `resolve-mascot-timeline.py`, `.events.json`
   integration, before_after + browser_capture rules.
3. **Cache + init** — layered capture/overlay cache, brand remap,
   `/demo-video mascot` subcommand.
4. **Moments + corner flip** — `peek`/`jump`/`hide`/`recoil`, overlap detection
   from existing `clip`/`zoom` rects.
5. **Full roster** — remaining characters.

## Out of scope (YAGNI)

- Speech bubbles / text from the mascot (explicitly rejected).
- Free-roaming pathfinding movement (bounded "moments" only).
- Image-AI sprite generation; sprites are deterministic data files.
- Sound effects tied to mascot actions.

## Phase 4 addendum (approved 2026-06-12, after v1 feedback)

v1 shipped a corner sidekick with one emotion per scene — too static in practice
(html_mockup scenes produce no events). Phase 4 adds motion:

- **Keyframes (user choreography).** Per-scene
  `mascot: { keyframes: [{at: 0, emotion: idle}, {at: 3, emotion: point, position: bottom-left}] }`.
  Keyframes win over auto-resolution for that scene; `at` is seconds into the
  final clip, clamped to duration; each segment may carry its own `position`.
  This revisits the brainstorm decision ("auto + override" over keyframes) —
  keyframes are now an additional, optional layer, not a replacement.
- **Movement.** When consecutive segments have different positions, the mascot
  WALKS between anchors: an inserted move segment (~0.8s) lerps overlay x/y via
  ffmpeg time expressions and plays the `type` animation as the walk cycle.
- **Emotion motion modifiers.** `celebrate` → bouncing y offset; `panic` →
  small x shake; `hide` (new pseudo-emotion) → slides below the bottom edge.
  Implemented as overlay x/y expressions, no new sprite frames required.
- **Corner auto-flip** (from the original phase 4 list) remains optional —
  delivered only if trivial after the above.
- **Art v2 (user feedback: "it doesn't look good").** The octopus is redrawn on
  a larger canvas (~24×20 cells) with two new palette slots — `outline` (dark
  silhouette edge, the single biggest readability win at small sizes) and
  `shade` (body shading) — and richer animation: 3–4 frames per emotion, a
  dedicated 4-frame `walk` cycle (used by move segments), clearly readable eye
  states (open / wide / closed), and expressive poses (panic arms up, celebrate
  jump pose, point with an actually extended arm). Format unchanged — only the
  data file and its golden hash change.

## Future work (v2 — not in this spec)

Inspired by Anthropic's "Introducing agent view in Claude Code" film
(music-only, Clawd in a cowboy hat walking across and lassoing floating
terminal windows on a pastel canvas):

- **`diorama` scene type** — N sub-captures (terminal/browser) composited at
  offsets on a large canvas with an ffmpeg pan/zoom camera path between them.
- **Prop interactions** — extend the moments system with scene-geometry
  awareness so the mascot can stand on / walk along / drag window edges
  (window rects are already known to the compositor).
- **Per-video props** — one-off accessories (hat, lasso) for a story gag; same
  pixel-grid accessory mechanism as brand personalization.
