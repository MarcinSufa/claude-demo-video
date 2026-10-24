# Diorama scene (`diorama`)

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
