# Mascot

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

## Art sources (`mascot.source`)

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
