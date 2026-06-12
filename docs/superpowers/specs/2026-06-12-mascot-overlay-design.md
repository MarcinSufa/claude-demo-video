# Mascot — brand pixel character overlay for /demo-video

Date: 2026-06-12
Status: approved (brainstorm with user)

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
- Location: `assets/mascots/<name>.json` in the skill; copied on init.

### 2. Brand personalization (init-time, agent-driven)

At `/demo-video init` (or a new `/demo-video mascot` subcommand for existing
projects), Claude:

1. Reads `brand.yaml` palette + logo SVG.
2. Picks the best-fit roster character (or honors `mascot.character`).
3. Remaps palette slots to brand colors (body ← accent or a derived tint,
   ensuring contrast against `palette.bg`).
4. Optionally edits grids to add a brand accessory (hat, badge, item derived
   from the logo motif). Edits stay within the existing frame dimensions.
5. Writes the result to `demo-video/mascot.json` — user-editable, reproducible,
   committed with the project.

### 3. `render-mascot.py` (new script)

- Input: `mascot.json` + `.build/config.json` (for palette resolution).
- Output: transparent PNG frame sequences per animation in
  `.build/mascot/<anim>/frame-%03d.png`, nearest-neighbor upscaled to the
  on-screen size (default ~140 px tall at 1080p; configurable via
  `mascot.scale`).
- No new heavy dependencies: write PNGs via a minimal stdlib PNG encoder or by
  piping raw RGBA to ffmpeg.

### 4. Emotion resolver (extends `plan-scenes.py`)

Builds a per-scene reaction timeline `[{at, until, emotion}]` from metadata the
pipeline already has:

- scene type `terminal` → `type` while output is printing
- `before_after`: BEFORE half → `panic` (after a brief `idle`), AFTER half →
  `celebrate` on reveal
- `waitToast` action → `point`/`panic` (error-styled toast) timed to the toast window
- per-action `speed` ramps (slow segments) → `sleep`
- default fill → `idle`
- scene boundaries → `enter` at scene start where the mascot was absent, `exit`
  when the next scene disables it

Resolved timeline is written into `scene-plan.json` per scene.

### 5. `overlay-mascot.py` (new script, called by `build-scenes.sh`)

- Runs after a scene clip is rendered, before `normalize-clip.py`.
- Composites the PNG sequences via ffmpeg `overlay` with
  `enable='between(t,..)'` windows per timeline segment; "moments" are short
  scripted position offsets (peek, jump, hide) implemented as time-windowed
  overlay x/y expressions.
- Position: corner home (default bottom-right) with margins that clear the
  caption band; flips to bottom-left when the scene's `clip`/`zoom` action
  region overlaps the home corner.
- Cache: mascot config + timeline hash joins the `scene_cache.py` key, so
  unchanged scenes skip re-compositing.

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
- Golden-frame test: render the octopus `idle` frame 0 and compare pixels.
- `--plan` dry run reports mascot status per scene (character, emotions) with
  zero rendering.

## Out of scope (YAGNI)

- Speech bubbles / text from the mascot (explicitly rejected).
- Free-roaming pathfinding movement (bounded "moments" only).
- Image-AI sprite generation; sprites are deterministic data files.
- Sound effects tied to mascot actions.
