# Diorama scene — design

Date: 2026-06-13
Status: design for approval

## Summary

A new `diorama` scene type: several terminal/browser windows arranged on a big
canvas, an eased camera that pans/zooms between them, and the brand mascot moving
across the windows (standing on a window's edge, hopping to another, pointing at
the focused one). The "Introducing agent view in Claude Code" look — wrangling
many agent sessions in one shot.

## The key idea (what makes it tractable)

**Composite everything onto the big canvas first, then move a camera over it.**

```
1. CANVAS (e.g. 3840×2160) = brand backdrop
2.   + each window's clip composited at its canvas (x,y), optional window chrome
3.   + the MASCOT overlaid at CANVAS coordinates (window-relative keyframes)
4. CAMERA = an animated 1920×1080 viewport cropped from the canvas (pan + zoom),
   eased between focus targets, then scaled to 1920×1080 → the final scene clip
```

Because the mascot is drawn onto the canvas **before** the camera crop, it moves
with the camera naturally and can be placed relative to windows — no separate
"project mascot into screen space" math. The mascot's own eased/arced hop (just
shipped) carries it between windows in canvas space.

## Components

### 1. Window capture + canvas composite (`make-diorama.py`, new)
- Each window is a clip: a `{ source }` path, or a `browser_capture` spec
  (`url`/`actions`/`auth`) recorded by the existing `record-browser.mjs`, or a
  `terminal` tape. Reuses the capture machinery build-scenes already has.
- Optional **window chrome**: reuse the `frame.html`/terminal-title styling so a
  window reads as an app window (title bar, traffic lights). Off → raw clip.
- Composite: ffmpeg overlays each (optionally chrome-wrapped, scaled) window clip
  onto the backdrop at its `(x,y)` → the **canvas video** (canvas_w × canvas_h,
  duration = scene `duration`). Windows are static in position; their content plays.

### 2. Mascot on the canvas (reuse `overlay-mascot.py` in canvas space)
- The diorama's `mascot.keyframes` use **window-relative anchors**:
  `{ at, emotion, at_window: <id>, anchor: top|beside|on }` resolves to a canvas
  (x,y) from that window's rect (e.g. `top` = centered on the window's top edge).
- `resolve-mascot-timeline.py` already turns keyframes → positioned segments with
  walk-moves; here positions are canvas coords. `overlay-mascot.py` composites
  onto the canvas video at those coords (its anchors generalise from screen dims
  to canvas dims). The eased/arced hop moves it window-to-window.
- Caption-clearance/corner logic is bypassed in canvas space (the mascot is placed
  explicitly), so a small `space: "canvas"` flag tells overlay-mascot to use the
  given coords verbatim.

### 3. Camera (eased pan/zoom tour)
- `camera:` is a list of focus stops: `{ focus: <window id> | all | mascot, zoom, hold, transition }`.
- Each stop → a target viewport rect on the canvas (centered on the window/mascot,
  width = 1920/zoom, 16:9). Between stops the viewport eases (smoothstep) cx/cy/zoom.
- Implemented with `crop=w=W(t):h=H(t):x=X(t):y=Y(t):eval=frame, scale=1920:1080`
  — the same animated-crop technique `cut-clip.py` already uses for Ken-Burns zoom,
  generalised to a multi-target path. Produces the 1920×1080 scene clip.

### 4. Pipeline integration
- `plan-scenes.py`: resolve a `diorama` scene → a plan entry with windows/camera/
  mascot/canvas + the scene `mp4`.
- `build-scenes.sh`: new `diorama` case → capture each window, then `make-diorama.py`
  composites canvas + mascot + camera → `$mp4`. Pinned to `duration` like other scenes.
- Caches per the existing two-layer scheme (capture hash + composite inputs).

## Config

```yaml
- type: diorama
  duration: 14
  canvas: { width: 3840, height: 2160, backdrop: assets/desk.jpg }
  windows:
    - { id: worker, source: footage/worker.mp4, x: 200,  y: 200,  w: 1280, chrome: true, title: "worker — claude" }
    - { id: review, url: "http://localhost:3000", actions: [...], x: 2300, y: 760, w: 1280, chrome: true, title: "review" }
    - { id: board,  source: footage/board.mp4,  x: 1100, y: 1300, w: 1500 }
  camera:
    - { focus: worker, zoom: 1.5, hold: 3 }
    - { focus: review, zoom: 1.5, hold: 4, transition: 1.0 }
    - { focus: all,    zoom: 1.0, hold: 3, transition: 1.2 }   # pull back to the whole board
  mascot:
    keyframes:
      - { at: 0,  emotion: idle,  at_window: worker, anchor: top }    # perched on the worker window
      - { at: 4,  emotion: point, at_window: review, anchor: beside } # hops over, points at review
      - { at: 9,  emotion: celebrate, at_window: board, anchor: top }
```

## v1 boundaries (YAGNI)

- **Static window positions** — windows don't move/animate their placement (only
  the camera moves). Moving/rearranging windows is future work.
- **Mascot is *placed* at window-relative anchors**, not physically standing with
  collision/edge-walking — it hops to an anchor point near each window. Reads as
  "on the window" without a physics system.
- **One backdrop, one canvas.** No multi-canvas / parallax layers.
- Reuses existing capture (browser/terminal/source) — no new capture types.

## Risks / cost
- Large canvas video + per-frame crop is heavier to render than a flat scene
  (mitigate: cap canvas at 2× frame by default; cache aggressively).
- Camera easing math (multi-target path, 16:9-locked zoom) is the trickiest part —
  unit-test the pure viewport-at-time function hard.
- Window chrome reuse may need a small canvas-coordinate variant of `frame.html`.

## Testing
- Pure: viewport-at-time (focus stops → eased cx/cy/zoom, clamped to canvas),
  window-relative anchor resolution (window rect + anchor → canvas xy), camera
  rect 16:9 + within-canvas invariants.
- Integration: a 2-window diorama smoke (sources = generated clips) → assert a
  non-blank 1920×1080 clip of the right duration, mascot present.
