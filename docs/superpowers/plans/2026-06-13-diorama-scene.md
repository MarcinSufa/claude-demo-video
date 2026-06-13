# Diorama Scene Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `diorama` scene type — N terminal/browser windows on a big canvas, the brand mascot moving across them, and an eased camera that pans/zooms between them — producing a normal 1920×1080 scene clip.

**Architecture:** Composite everything onto a large canvas first, then move a camera over it. `make-diorama.py` builds the canvas (backdrop + window clips at canvas positions), overlays the mascot at canvas coordinates (window-relative keyframes, reusing render-mascot + overlay-mascot), then applies an eased multi-target camera (animated ffmpeg crop, like `cut-clip.py`'s zoom) → the scene clip. Pure cores — window-relative anchors and the camera viewport-at-time — are heavily unit-tested; the ffmpeg graph is verified by an integration smoke.

**Tech Stack:** Python 3.10+ stdlib, ffmpeg/ffprobe, bash, unittest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-13-diorama-scene-design.md`.
**Branch:** `feat/diorama-scene` (has the merged eased/arced mascot motion). Tests run from repo root: `python -m unittest discover -s tests` (≈228 green at start). Hyphenated scripts are imported in tests via `importlib.util.spec_from_file_location` — copy `tests/test_cut_clip.py`'s `_load` helper.

## File structure

- **Create `assets/scripts/diorama_layout.py`** — pure geometry: `window_anchor()` (window rect + anchor → canvas xy), `focus_rect()` (a camera stop → target viewport), `camera_timeline()` (stops → eased segments), `viewport_at()` (segments, t → viewport). No I/O, fully unit-tested. (Hyphen-free name so it imports cleanly as a helper module, like `mascot_data.py`/`timing_util.py`.)
- **Create `assets/scripts/make-diorama.py`** — glue + ffmpeg builders: `build_canvas_filter()` (windows → composite filter), `build_camera_filter()` (camera segments → animated-crop+scale+concat filter), `main()` orchestrating capture-outputs → canvas → mascot → camera → scene mp4. Imports `diorama_layout`.
- **Modify `assets/scripts/plan-scenes.py`** — resolve `type: diorama` in `custom_arc()`.
- **Modify `assets/scripts/build-scenes.sh`** — `diorama` case: capture windows, run make-diorama.py.
- **Modify `assets/scripts/build.sh`** — add the two new scripts to the cp list + scripts VERSION.
- **Modify `assets/brand.example.yaml`, `SKILL.md`** — document the scene.
- **Modify `tests/smoke_build.sh`** — a diorama smoke.
- **Create `tests/test_diorama_layout.py`, `tests/test_make_diorama.py`**.

Reused unchanged: `render-mascot.py` (sprite frames), `resolve-mascot-timeline.py` (keyframes → positioned/walk segments), `overlay-mascot.py` (`build_overlay_cmd(capture, out, frames_dir, timeline, positions, fps, speedup)` — already takes an explicit per-segment `positions` list, so it composites onto the canvas at canvas coords with no change).

---

### Task 1: Window-relative anchors (pure)

**Files:** Create `assets/scripts/diorama_layout.py`; Test `tests/test_diorama_layout.py`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_diorama_layout.py
import importlib.util, os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "assets", "scripts"))
from diorama_layout import window_anchor  # noqa: E402

WIN = {"x": 100, "y": 200, "w": 1280, "h": 720}  # a window's canvas rect


class TestWindowAnchor(unittest.TestCase):
    def test_top_perches_centered_on_top_edge(self):
        # sprite 160x140: centered horizontally on the window, sitting ON the top edge
        self.assertEqual(window_anchor(WIN, "top", 160, 140),
                         (100 + (1280 - 160) // 2, 200 - 140))

    def test_beside_is_right_of_window_vertically_centered(self):
        self.assertEqual(window_anchor(WIN, "beside", 160, 140),
                         (100 + 1280 + 8, 200 + (720 - 140) // 2))

    def test_on_is_centered_inside(self):
        self.assertEqual(window_anchor(WIN, "on", 160, 140),
                         (100 + (1280 - 160) // 2, 200 + (720 - 140) // 2))

    def test_unknown_anchor_raises(self):
        with self.assertRaises(ValueError):
            window_anchor(WIN, "sideways", 160, 140)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m unittest discover -s tests -p test_diorama_layout.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'diorama_layout'`

- [ ] **Step 3: Implement `window_anchor` in `diorama_layout.py`**

```python
# assets/scripts/diorama_layout.py
"""diorama_layout.py — pure geometry for the diorama scene.

window_anchor: where the mascot sits relative to a window (canvas coords).
focus_rect / camera_timeline / viewport_at: the eased pan/zoom camera path.
No I/O — make-diorama.py builds ffmpeg around these unit-tested functions.
"""

_ANCHOR_GAP = 8  # px gap for the `beside` anchor


def window_anchor(win, anchor, sprite_w, sprite_h):
    """Canvas (x, y) for the mascot at `anchor` relative to window rect `win`
    ({x, y, w, h}). `top` perches centered on the top edge; `beside` sits to the
    right, vertically centered; `on` centers it inside the window."""
    wx, wy, ww, wh = win["x"], win["y"], win["w"], win["h"]
    if anchor == "top":
        return wx + (ww - sprite_w) // 2, wy - sprite_h
    if anchor == "beside":
        return wx + ww + _ANCHOR_GAP, wy + (wh - sprite_h) // 2
    if anchor == "on":
        return wx + (ww - sprite_w) // 2, wy + (wh - sprite_h) // 2
    raise ValueError(f"unknown mascot anchor '{anchor}' (top|beside|on)")
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m unittest discover -s tests -p test_diorama_layout.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add assets/scripts/diorama_layout.py tests/test_diorama_layout.py
git commit -m "feat(diorama): window-relative mascot anchors (pure)"
```

---

### Task 2: Camera focus rect + timeline + viewport-at (pure)

**Files:** Modify `assets/scripts/diorama_layout.py`; Modify `tests/test_diorama_layout.py`.

Camera model: a viewport is `(x, y, w, h)` = a rect ON the canvas (top-left + size), always `out_aspect` (16:9). `zoom` controls span: `w = canvas_w / zoom` (zoom 1 = whole width, higher = closer). The viewport is centered on the focus, then clamped so it never leaves the canvas. A `focus` is a window id, `"all"` (bounding box of all windows), or `"mascot"` (resolved to a passed-in point).

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/test_diorama_layout.py
from diorama_layout import focus_rect, camera_timeline, viewport_at  # noqa: E402

CANVAS = {"width": 3840, "height": 2160}
WINS = {
    "a": {"x": 200, "y": 200, "w": 1280, "h": 720},
    "b": {"x": 2300, "y": 1100, "w": 1280, "h": 720},
}


class TestFocusRect(unittest.TestCase):
    def test_zoom_one_is_full_width_16x9_centered(self):
        x, y, w, h = focus_rect({"focus": "a", "zoom": 1.0}, WINS, CANVAS)
        self.assertEqual(w, 3840)
        self.assertEqual(h, round(3840 * 9 / 16))   # 2160
        # clamped to canvas (can't center beyond edges)
        self.assertEqual((x, y), (0, 0))

    def test_zoom_in_halves_the_span_and_centers_on_window(self):
        x, y, w, h = focus_rect({"focus": "a", "zoom": 2.0}, WINS, CANVAS)
        self.assertEqual(w, 1920)
        self.assertEqual(h, 1080)
        cx, cy = 200 + 1280 / 2, 200 + 720 / 2          # window centre
        self.assertEqual(x, round(cx - 1920 / 2))
        self.assertEqual(y, round(cy - 1080 / 2))

    def test_all_frames_bounding_box_of_windows(self):
        x, y, w, h = focus_rect({"focus": "all", "zoom": 1.0}, WINS, CANVAS)
        # viewport stays 16:9 and within canvas; centred on the windows' bbox centre
        self.assertEqual((w, h), (3840, 2160))
        self.assertEqual((x, y), (0, 0))

    def test_clamps_within_canvas_when_window_near_edge(self):
        x, y, w, h = focus_rect({"focus": "b", "zoom": 3.0}, WINS, CANVAS)
        self.assertGreaterEqual(x, 0)
        self.assertGreaterEqual(y, 0)
        self.assertLessEqual(x + w, CANVAS["width"])
        self.assertLessEqual(y + h, CANVAS["height"])


class TestCameraTimeline(unittest.TestCase):
    STOPS = [
        {"focus": "a", "zoom": 2.0, "hold": 3},
        {"focus": "b", "zoom": 2.0, "hold": 4, "transition": 1.0},
    ]

    def test_segments_cover_total_duration_contiguously(self):
        segs, total = camera_timeline(self.STOPS, WINS, CANVAS)
        self.assertEqual(segs[0][0], 0.0)
        for (s, e, a, b) in segs:
            self.assertLessEqual(s, e)
        for p, q in zip(segs, segs[1:]):
            self.assertAlmostEqual(p[1], q[0])           # contiguous
        self.assertAlmostEqual(segs[-1][1], total)
        self.assertAlmostEqual(total, 3 + 1 + 4)         # hold + transition + hold

    def test_hold_segment_is_static_transition_eases(self):
        segs, _ = camera_timeline(self.STOPS, WINS, CANVAS)
        holds = [s for s in segs if s[2] == s[3]]
        moves = [s for s in segs if s[2] != s[3]]
        self.assertEqual(len(holds), 2)
        self.assertEqual(len(moves), 1)                  # the 1s transition


class TestViewportAt(unittest.TestCase):
    def test_smoothstep_midpoint_is_halfway(self):
        segs = [(0.0, 1.0, (0, 0, 100, 56), (200, 0, 100, 56))]
        x, y, w, h = viewport_at(segs, 0.5)
        self.assertEqual(x, 100)                          # smoothstep(0.5)=0.5
        self.assertEqual(w, 100)

    def test_endpoints_exact(self):
        segs = [(0.0, 2.0, (0, 0, 100, 56), (200, 0, 100, 56))]
        self.assertEqual(viewport_at(segs, 0.0)[0], 0)
        self.assertEqual(viewport_at(segs, 2.0)[0], 200)

    def test_past_end_holds_last(self):
        segs = [(0.0, 2.0, (0, 0, 100, 56), (200, 0, 100, 56))]
        self.assertEqual(viewport_at(segs, 99)[0], 200)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m unittest discover -s tests -p test_diorama_layout.py -v`
Expected: FAIL — `cannot import name 'focus_rect'`

- [ ] **Step 3: Implement in `diorama_layout.py`**

```python
def _bbox(rects):
    x0 = min(r["x"] for r in rects); y0 = min(r["y"] for r in rects)
    x1 = max(r["x"] + r["w"] for r in rects); y1 = max(r["y"] + r["h"] for r in rects)
    return x0, y0, x1 - x0, y1 - y0


def focus_rect(stop, windows, canvas, out_aspect=16 / 9, mascot_xy=None):
    """A camera stop -> viewport rect (x, y, w, h) on the canvas: out_aspect-locked,
    span = canvas_width/zoom, centred on the focus, clamped within the canvas."""
    cw_canvas, ch_canvas = canvas["width"], canvas["height"]
    focus = stop["focus"]
    if focus == "all":
        bx, by, bw, bh = _bbox(list(windows.values()))
        cx, cy = bx + bw / 2, by + bh / 2
    elif focus == "mascot":
        cx, cy = mascot_xy if mascot_xy else (cw_canvas / 2, ch_canvas / 2)
    else:
        w = windows[focus]
        cx, cy = w["x"] + w["w"] / 2, w["y"] + w["h"] / 2
    zoom = float(stop.get("zoom", 1.0)) or 1.0
    vw = min(cw_canvas, cw_canvas / zoom)
    vh = vw / out_aspect
    if vh > ch_canvas:                       # never taller than the canvas
        vh = ch_canvas; vw = vh * out_aspect
    x = min(max(0, cx - vw / 2), cw_canvas - vw)
    y = min(max(0, cy - vh / 2), ch_canvas - vh)
    return round(x), round(y), round(vw), round(vh)


def camera_timeline(stops, windows, canvas, out_aspect=16 / 9):
    """Camera stops -> [(start, end, from_vp, to_vp), ...] and total seconds.
    `transition` (seconds, into a stop) eases the viewport; `hold` holds it."""
    segs, t = [], 0.0
    prev = focus_rect(stops[0], windows, canvas, out_aspect)
    for i, stop in enumerate(stops):
        vp = focus_rect(stop, windows, canvas, out_aspect)
        trans = float(stop.get("transition", 0.0)) if i > 0 else 0.0
        if trans > 0:
            segs.append((t, t + trans, prev, vp)); t += trans
        hold = float(stop.get("hold", 2.0))
        segs.append((t, t + hold, vp, vp)); t += hold
        prev = vp
    return segs, t


def viewport_at(segs, t):
    """Eased (smoothstep) viewport at time t; holds the last viewport past the end."""
    for (s, e, a, b) in segs:
        if s <= t <= e:
            p = 0.0 if e == s else (t - s) / (e - s)
            pe = p * p * (3 - 2 * p)
            return tuple(round(a[k] + (b[k] - a[k]) * pe) for k in range(4))
    return segs[-1][3]
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m unittest discover -s tests -p test_diorama_layout.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add assets/scripts/diorama_layout.py tests/test_diorama_layout.py
git commit -m "feat(diorama): camera focus rect, eased timeline, viewport-at (pure)"
```

---

### Task 3: Canvas composite filter (pure cmd builder)

**Files:** Create `assets/scripts/make-diorama.py`; Test `tests/test_make_diorama.py`.

`build_canvas_filter` returns an ffmpeg `-filter_complex` string that scales the backdrop to the canvas and overlays each window clip at its `(x, y)`, scaled to its `w` (height auto). Input order: `[0:v]` = backdrop, `[1:v]..[N:v]` = window clips in order.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_make_diorama.py
import importlib.util, os, sys, unittest
SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "assets", "scripts")
sys.path.insert(0, SCRIPTS)
spec = importlib.util.spec_from_file_location("make_diorama", os.path.join(SCRIPTS, "make-diorama.py"))
md = importlib.util.module_from_spec(spec); spec.loader.exec_module(md)

CANVAS = {"width": 3840, "height": 2160}
WINDOWS = [
    {"id": "a", "x": 200, "y": 200, "w": 1280},
    {"id": "b", "x": 2300, "y": 1100, "w": 1280},
]


class TestCanvasFilter(unittest.TestCase):
    def test_scales_backdrop_to_canvas(self):
        fc = md.build_canvas_filter(WINDOWS, CANVAS)
        self.assertIn("[0:v]scale=3840:2160", fc)

    def test_one_overlay_per_window_at_its_offset(self):
        fc = md.build_canvas_filter(WINDOWS, CANVAS)
        self.assertEqual(fc.count("overlay="), 2)
        self.assertIn("overlay=200:200", fc)
        self.assertIn("overlay=2300:1100", fc)

    def test_window_scaled_to_its_width(self):
        fc = md.build_canvas_filter(WINDOWS, CANVAS)
        self.assertIn("[1:v]scale=1280:-2", fc)   # window 'a' to width 1280
        self.assertIn("[2:v]scale=1280:-2", fc)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m unittest discover -s tests -p test_make_diorama.py -v`
Expected: FAIL — module/function not found

- [ ] **Step 3: Implement `build_canvas_filter` in `make-diorama.py`**

```python
# assets/scripts/make-diorama.py
"""make-diorama.py — build a diorama scene: composite N windows on a big canvas,
overlay the mascot at canvas coords, then move an eased camera over it.

  python make-diorama.py <plan.json> <out.mp4>

plan.json (written by build-scenes.sh): {canvas, backdrop, windows:[{id,x,y,w,clip}],
camera:[...], mascot:{frames_dir, timeline}|null, duration, fps}.

build_canvas_filter()/build_camera_filter() are the pure, unit-tested ffmpeg
builders; diorama_layout.py holds the geometry. The graph is verified end-to-end
by tests/smoke_build.sh's diorama tier.
"""
import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from diorama_layout import camera_timeline, viewport_at  # noqa: E402


def build_canvas_filter(windows, canvas):
    """Backdrop ([0:v]) scaled to canvas, then each window clip ([i:v], i>=1)
    scaled to its width and overlaid at (x, y). Returns the filter_complex up to
    label [canvas]."""
    parts = [f"[0:v]scale={canvas['width']}:{canvas['height']},setsar=1[bg]"]
    src = "[bg]"
    for i, w in enumerate(windows, 1):
        parts.append(f"[{i}:v]scale={w['w']}:-2,setsar=1[w{i}]")
        label = "[canvas]" if i == len(windows) else f"[c{i}]"
        parts.append(f"{src}[w{i}]overlay={w['x']}:{w['y']}{label}")
        src = f"[c{i}]"
    return ";".join(parts)
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m unittest discover -s tests -p test_make_diorama.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add assets/scripts/make-diorama.py tests/test_make_diorama.py
git commit -m "feat(diorama): canvas composite ffmpeg filter (pure)"
```

---

### Task 4: Camera filter (pure cmd builder)

**Files:** Modify `assets/scripts/make-diorama.py`, `tests/test_make_diorama.py`.

`build_camera_filter` turns the camera segments into an animated crop of `[canvas]` → `out_w×out_h`. Approach: ONE `crop` with `eval=frame` and piecewise `t`-expressions for x/y/w/h (smoothstep within each transition, constant within holds), then `scale=out_w:out_h`. The expression for each coordinate is a nested `if(between(t,s,e), <eased>, ...)` chain over the segments.

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/test_make_diorama.py
class TestCameraFilter(unittest.TestCase):
    SEGS = [(0.0, 2.0, (0, 0, 1920, 1080), (0, 0, 1920, 1080)),
            (2.0, 3.0, (0, 0, 1920, 1080), (800, 400, 960, 540))]

    def test_crops_then_scales_to_output(self):
        f = md.build_camera_filter(self.SEGS, 3840, 2160, 1920, 1080, fps=30)
        self.assertIn("crop=", f)
        self.assertIn("eval=frame", f)
        self.assertIn("scale=1920:1080", f)

    def test_expression_covers_each_segment_window(self):
        f = md.build_camera_filter(self.SEGS, 3840, 2160, 1920, 1080, fps=30)
        self.assertIn("between(t,0.000,2.000)", f)
        self.assertIn("between(t,2.000,3.000)", f)

    def test_transition_uses_smoothstep(self):
        f = md.build_camera_filter(self.SEGS, 3840, 2160, 1920, 1080, fps=30)
        # the moving segment eases x from 0 toward 800 with a smoothstep p*p*(3-2*p)
        self.assertIn("(3-2*", f)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m unittest discover -s tests -p test_make_diorama.py -v`
Expected: FAIL — `build_camera_filter` not defined

- [ ] **Step 3: Implement `build_camera_filter` in `make-diorama.py`**

```python
def _coord_expr(segs, idx):
    """Piecewise ffmpeg expression for viewport coordinate `idx`
    (0=x,1=y,2=w,3=h) over the camera segments: smoothstep within each segment,
    constant for holds (a==b makes the eased term collapse to the value)."""
    expr = f"{segs[-1][3][idx]}"  # default = last segment's end value
    for (s, e, a, b) in reversed(segs):
        dur = e - s
        if dur <= 0:
            continue
        p = f"clip((t-{s:.3f})/{dur:.3f},0,1)"
        pe = f"({p}*{p}*(3-2*{p}))"
        val = f"({a[idx]}+({b[idx]}-{a[idx]})*{pe})"
        expr = f"if(between(t,{s:.3f},{e:.3f}),{val},{expr})"
    return expr


def build_camera_filter(segs, canvas_w, canvas_h, out_w, out_h, fps):
    """Animated crop of [canvas] following the camera segments, scaled to output.
    Consumes label [canvas], produces [vout]."""
    x = _coord_expr(segs, 0); y = _coord_expr(segs, 1)
    w = _coord_expr(segs, 2); h = _coord_expr(segs, 3)
    return (f"[canvas]crop=w='{w}':h='{h}':x='{x}':y='{y}':eval=frame,"
            f"scale={out_w}:{out_h},setsar=1[vout]")
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m unittest discover -s tests -p test_make_diorama.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add assets/scripts/make-diorama.py tests/test_make_diorama.py
git commit -m "feat(diorama): eased animated-crop camera filter (pure)"
```

---

### Task 5: make-diorama.py main — assemble canvas → mascot → camera

**Files:** Modify `assets/scripts/make-diorama.py`.

Glue (verified by the Task 9 smoke, not unit tests — it shells out to ffmpeg):
1. Read `plan.json`. Inputs = `[backdrop] + [w["clip"] for w in windows]`.
2. Build the canvas video: `ffmpeg -i backdrop -i w1 ... -filter_complex "<build_canvas_filter> ; [canvas]trim=duration=DUR,setpts=PTS-STARTPTS[v]" -map [v] -t DUR canvas.mp4` (loop/pad shorter window clips with `tpad`/`-stream_loop` so all cover DUR — reuse normalize-clip.py per window before compositing for simplicity).
3. If `mascot` present: render is already done (frames_dir passed in); resolve the mascot timeline to canvas positions (Task 6 helper) and call `overlay-mascot.py` semantics via its `build_overlay_cmd(canvas.mp4, canvas_m.mp4, frames_dir, timeline, positions, fps, 1.0)` — import overlay-mascot as a module and reuse, OR shell `python overlay-mascot.py` with a canvas-space timeline json. Use the in-process import to pass the explicit `positions`.
4. Apply the camera: `ffmpeg -i canvas_m.mp4 -filter_complex "<build_camera_filter>" -map [vout] -r fps -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p out.mp4`.

- [ ] **Step 1: Implement `main()`**

```python
def _probe(path, entries):
    out = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", entries, "-of", "csv=p=0", path]).decode().strip()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plan_json"); ap.add_argument("out")
    a = ap.parse_args()
    with open(a.plan_json, encoding="utf-8") as f:
        plan = json.load(f)
    canvas, windows = plan["canvas"], plan["windows"]
    dur, fps = float(plan["duration"]), int(plan.get("fps", 30))
    workdir = os.path.dirname(os.path.abspath(a.out)) or "."

    # 1. canvas composite (each window clip normalized to DUR first)
    import importlib.util
    nc = importlib.util.spec_from_file_location(
        "normalize_clip", os.path.join(os.path.dirname(__file__), "normalize-clip.py"))
    normmod = importlib.util.module_from_spec(nc); nc.loader.exec_module(normmod)
    inputs = ["-i", plan["backdrop"]]
    for w in windows:
        normmod.main(["normalize-clip.py", w["clip"], str(dur)])  # pin each window to DUR
        inputs += ["-i", w["clip"]]
    # Fill each window's CANVAS HEIGHT (h) from its clip aspect at the target
    # width — the layout/camera functions need it; plan-scenes only set x/y/w.
    for w in windows:
        cw, ch = (int(v) for v in _probe(w["clip"], "stream=width,height").split(","))
        w["h"] = round(w["w"] * ch / cw)
    canvas_mp4 = os.path.join(workdir, ".diorama-canvas.mp4")
    fc = build_canvas_filter(windows, canvas) + \
        f";[canvas]trim=duration={dur:.3f},setpts=PTS-STARTPTS[v]"
    subprocess.check_call(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *inputs,
        "-filter_complex", fc, "-map", "[v]", "-t", f"{dur:.3f}",
        "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", canvas_mp4])

    # 2. mascot on the canvas (optional)
    src = canvas_mp4
    if plan.get("mascot"):
        from importlib import util as _u
        om = _u.spec_from_file_location("overlay_mascot",
            os.path.join(os.path.dirname(__file__), "overlay-mascot.py"))
        ovl = _u.module_from_spec(om); om.loader.exec_module(ovl)
        m = plan["mascot"]
        sprite_wh = tuple(int(v) for v in _probe(
            os.path.join(m["frames_dir"], "idle", "f_001.png"), "stream=width,height").split(","))
        timeline = diorama_timeline(m["keyframes"], dur)            # keyframes -> segments+walks
        positions = resolve_canvas_positions(timeline, windows, sprite_wh)
        cmd = ovl.build_overlay_cmd(canvas_mp4, os.path.join(workdir, ".diorama-m.mp4"),
            m["frames_dir"], timeline, positions, m["fps"], 1.0)
        if cmd:
            subprocess.check_call(cmd); src = os.path.join(workdir, ".diorama-m.mp4")

    # 3. camera
    segs, cam_total = camera_timeline(plan["camera"], {w["id"]: w for w in windows}, canvas)
    cf = build_camera_filter(segs, canvas["width"], canvas["height"], 1920, 1080, fps)
    subprocess.check_call(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", src,
        "-filter_complex", cf, "-map", "[vout]", "-r", str(fps),
        "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", a.out])
    print(f"  diorama -> {a.out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Syntax check**

Run: `python -c "import ast; ast.parse(open('assets/scripts/make-diorama.py').read()); print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add assets/scripts/make-diorama.py
git commit -m "feat(diorama): make-diorama main — canvas, mascot, camera"
```

---

### Task 6: Mascot canvas-position resolution

**Files:** Modify `assets/scripts/make-diorama.py`, `tests/test_make_diorama.py`.

`resolve_canvas_positions(timeline, windows, sprite_wh)` mirrors overlay-mascot's `resolve_anchors`, but each segment's position is a window-relative `at_window`/`anchor` (resolved via `window_anchor`) instead of a screen corner. Returns the per-segment `positions` list `build_overlay_cmd` expects (plain `(x,y)` for static, `((x0,y0),(x1,y1))` for moves).

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/test_make_diorama.py
class TestCanvasPositions(unittest.TestCase):
    WINS = [{"id": "a", "x": 100, "y": 200, "w": 1280, "h": 720},
            {"id": "b", "x": 2300, "y": 1100, "w": 1280, "h": 720}]

    def test_static_segment_uses_window_anchor(self):
        tl = [{"at": 0, "until": 3, "emotion": "idle",
               "at_window": "a", "anchor": "top"}]
        pos = md.resolve_canvas_positions(tl, self.WINS, (160, 140))
        self.assertEqual(pos[0], (100 + (1280 - 160) // 2, 200 - 140))

    def test_move_segment_resolves_both_windows(self):
        tl = [{"at": 0, "until": 0.8, "emotion": "walk",
               "move": {"from_window": "a", "from_anchor": "top",
                        "to_window": "b", "to_anchor": "beside"}}]
        pos = md.resolve_canvas_positions(tl, self.WINS, (160, 140))
        self.assertEqual(pos[0][0], (100 + (1280 - 160) // 2, 200 - 140))
        self.assertEqual(pos[0][1], (2300 + 1280 + 8, 1100 + (720 - 140) // 2))
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m unittest discover -s tests -p test_make_diorama.py -v`
Expected: FAIL — `resolve_canvas_positions` not defined

- [ ] **Step 3: Implement**

```python
from diorama_layout import window_anchor  # add to imports


def resolve_canvas_positions(timeline, windows, sprite_wh):
    """Per-segment canvas anchors for the mascot. Static segs carry at_window+anchor;
    move segs carry move.{from,to}_{window,anchor}. Returns the positions list
    overlay-mascot.build_overlay_cmd expects."""
    by_id = {w["id"]: w for w in windows}
    sw, sh = sprite_wh
    out = []
    for seg in timeline:
        if "move" in seg:
            mv = seg["move"]
            out.append((window_anchor(by_id[mv["from_window"]], mv["from_anchor"], sw, sh),
                        window_anchor(by_id[mv["to_window"]], mv["to_anchor"], sw, sh)))
        else:
            out.append(window_anchor(by_id[seg["at_window"]], seg["anchor"], sw, sh))
    return out
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m unittest discover -s tests -p test_make_diorama.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add assets/scripts/make-diorama.py tests/test_make_diorama.py
git commit -m "feat(diorama): resolve window-relative mascot positions for the overlay"
```

**Note for the implementer:** the diorama mascot timeline must carry `at_window`/`anchor` (and `move.{from,to}_{window,anchor}`) — so the diorama does NOT use `resolve-mascot-timeline.py`'s screen-position resolver. In Task 7, plan-scenes builds a diorama mascot timeline directly from `mascot.keyframes`: a segment per keyframe span (sorted by `at`, clamped to duration), and a `walk` move segment inserted (reusing `MOVE_SECONDS = 0.8`) when consecutive keyframes target different windows. The emotion frames are rendered by the existing render-mascot at build time and `sprite_wh` is probed from `frames_dir/idle/f_001.png`.

---

### Task 7: plan-scenes.py — resolve the `diorama` scene

**Files:** Modify `assets/scripts/plan-scenes.py`; Test `tests/test_diorama_plan.py`.

In `custom_arc()`, add a `diorama` branch building the plan entry: resolve window sources (`resolve_source` for `source` paths; a `browser_capture` spec for `url` windows), pass through `canvas`/`camera`/`duration`, and build the mascot timeline (window-relative keyframes → segments + walk moves) into the entry.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_diorama_plan.py
import importlib.util, os, sys, unittest
SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "assets", "scripts")
sys.path.insert(0, SCRIPTS)
spec = importlib.util.spec_from_file_location("plan_scenes", os.path.join(SCRIPTS, "plan-scenes.py"))
ps = importlib.util.module_from_spec(spec); spec.loader.exec_module(ps)


class TestDioramaPlan(unittest.TestCase):
    SCENE = {"type": "diorama", "duration": 12,
             "canvas": {"width": 3840, "height": 2160, "backdrop": "assets/desk.jpg"},
             "windows": [{"id": "a", "source": "footage/a.mp4", "x": 100, "y": 100, "w": 1280},
                         {"id": "b", "url": "http://localhost:3000", "x": 2300, "y": 800, "w": 1280}],
             "camera": [{"focus": "a", "zoom": 1.5, "hold": 4},
                        {"focus": "b", "zoom": 1.5, "hold": 5, "transition": 1.0}],
             "mascot": {"keyframes": [{"at": 0, "emotion": "idle", "at_window": "a", "anchor": "top"},
                                      {"at": 5, "emotion": "point", "at_window": "b", "anchor": "beside"}]}}

    def test_entry_has_diorama_fields(self):
        plan = ps.custom_arc([self.SCENE])
        e = plan[0]
        self.assertEqual(e["type"], "diorama")
        self.assertEqual(len(e["windows"]), 2)
        self.assertEqual(e["camera"][1]["focus"], "b")

    def test_url_window_gets_a_capture_spec_source_passes_through(self):
        e = ps.custom_arc([self.SCENE])[0]
        a, b = e["windows"]
        self.assertIn("a.mp4", a["source"])         # source path resolved
        self.assertIn("capture", b)                 # url window -> browser_capture spec

    def test_mascot_timeline_has_walk_move_between_windows(self):
        e = ps.custom_arc([self.SCENE])[0]
        tl = e["mascot"]["timeline"]
        self.assertTrue(any("move" in s for s in tl))           # walk inserted
        self.assertTrue(any(s.get("at_window") == "a" for s in tl))
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m unittest discover -s tests -p test_diorama_plan.py -v`
Expected: FAIL — diorama not handled (KeyError/Unknown type)

- [ ] **Step 3: Implement the `diorama` branch in `custom_arc()`**

Add alongside the other `elif t == ...` branches (mirror `before_after`'s capture-half pattern for url windows; build the mascot timeline like `resolve-mascot-timeline._resolve_keyframes` but keeping `at_window`/`anchor` and inserting `walk` moves with `move.{from,to}_{window,anchor}` when adjacent keyframes differ):

```python
        elif t == "diorama":
            entry["mp4"] = f"videos/{sid}.mp4"
            entry["canvas"] = sc["canvas"]
            entry["camera"] = sc["camera"]
            entry["windows"] = []
            for i, win in enumerate(sc["windows"]):
                w = {"id": win["id"], "x": win["x"], "y": win["y"], "w": win["w"]}
                if win.get("source"):
                    w["source"] = resolve_source(win["source"])
                elif win.get("url"):
                    w["capture"] = {
                        "url": win["url"], "output": f"videos/{sid}_{win['id']}.mp4",
                        "cursor": win.get("cursor", True),
                        "settle_ms": win.get("settle_ms", 1200), "tail_ms": win.get("tail_ms", 1500),
                        "viewport": win.get("viewport", {"width": 1280, "height": 720}),
                        "actions": win.get("actions", []),
                        "warmup": should_warmup(win["url"], win.get("warmup")),
                        "auth": bool(win.get("auth", False)), "trim_start_ms": win.get("trim_start_ms"),
                        "clip": win.get("clip"),
                    }
                else:
                    sys.exit(f"diorama window '{win.get('id')}' needs a source or url")
                if win.get("chrome"):
                    w["chrome"] = True; w["title"] = win.get("title", win["id"])
                entry["windows"].append(w)
            kf = sorted(sc.get("mascot", {}).get("keyframes", []), key=lambda k: k["at"])
            entry["mascot"] = {"keyframes": kf} if kf else None
```

**`_diorama_timeline` helper (concrete).** plan-scenes passes the sorted `keyframes`
through; make-diorama expands them into segments + walk-moves at build time. Add
this to `make-diorama.py` next to `resolve_canvas_positions`, modeled on
`resolve-mascot-timeline.py::_resolve_keyframes` but keeping window targets:

```python
MOVE_SECONDS = 0.8

def diorama_timeline(keyframes, duration):
    """Sorted window-keyframes -> contiguous segments to `duration`, with a `walk`
    move inserted when consecutive keyframes target different windows."""
    kf = [k for k in sorted(keyframes, key=lambda k: k["at"]) if k["at"] < duration]
    segs = []
    for i, k in enumerate(kf):
        start = k["at"]
        end = kf[i + 1]["at"] if i + 1 < len(kf) else duration
        if i > 0 and kf[i]["at_window"] != kf[i - 1]["at_window"]:
            mv = min(MOVE_SECONDS, (end - start) / 2)
            segs.append({"at": start, "until": start + mv, "emotion": "walk",
                         "move": {"from_window": kf[i - 1]["at_window"],
                                  "from_anchor": kf[i - 1]["anchor"],
                                  "to_window": k["at_window"], "to_anchor": k["anchor"]}})
            start += mv
        segs.append({"at": start, "until": end, "emotion": k["emotion"],
                     "at_window": k["at_window"], "anchor": k["anchor"]})
    return segs
```

Call it in `make-diorama.main` to turn `plan["mascot"]["keyframes"]` into the
timeline before `resolve_canvas_positions`. Unit-test it: 2 keyframes on different
windows → a base segment, a `walk` move with `from_window`/`to_window`, and a tail
segment covering `duration`.

- [ ] **Step 4: Run to verify it passes**

Run: `python -m unittest discover -s tests -p test_diorama_plan.py -v`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `python -m unittest discover -s tests`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add assets/scripts/plan-scenes.py tests/test_diorama_plan.py
git commit -m "feat(diorama): resolve diorama scene in plan-scenes"
```

---

### Task 8: build-scenes.sh — the `diorama` case + build.sh wiring

**Files:** Modify `assets/scripts/build-scenes.sh`, `assets/scripts/build.sh`.

- [ ] **Step 1: Add the `diorama` case** in build-scenes.sh's `case "$type"` (before the `*)` default). It records any `url` windows (each window's `capture` spec via record-browser, like before_after halves), renders the mascot if configured, writes a diorama plan json, and runs make-diorama.py:

```bash
    diorama)
      echo "$extra" > ".scene-$id.json"
      # record any url-window halves
      python - "$id" <<'PY'
import json, sys, subprocess, os
sid = sys.argv[1]
e = json.load(open(f".scene-{sid}.json"))
for w in e["windows"]:
    if "capture" in w:
        json.dump(w["capture"], open(f".scene-{sid}-{w['id']}.json", "w"))
        subprocess.check_call(["node", "record-browser.mjs", f".scene-{sid}-{w['id']}.json"])
        subprocess.check_call(["python", "cut-clip.py", w["capture"]["output"]])
        w["clip"] = w["capture"]["output"]
    else:
        w["clip"] = w["source"]
# backdrop: resolve from config bg or a solid color fallback
e["backdrop"] = e.get("canvas", {}).get("backdrop") or "color=c=0x0a0705"
# mascot frames already rendered into ./mascot by build.sh; attach if present
if e.get("mascot") and os.path.isdir("mascot"):
    e["mascot"] = {"keyframes": e["mascot"]["keyframes"], "frames_dir": "mascot",
                   "fps": json.load(open("mascot/mascot-meta.json"))["fps"]}
else:
    e["mascot"] = None
e["fps"] = 30
json.dump(e, open(f".diorama-{sid}.json", "w"))
PY
      python make-diorama.py ".diorama-$id.json" "$mp4"
      rm -f ".scene-$id.json" ".scene-$id"-*.json ".diorama-$id.json" ;;
```

(If `backdrop` is a `color=...` lavfi string, make-diorama.main must accept it as `-f lavfi -i <color>...:s=canvasWxH:d=DUR`; add that in make-diorama: when `backdrop` starts with `color=`, use lavfi input.)

- [ ] **Step 2: Add the new scripts to build.sh's cp list** (the brace list) — append `diorama_layout.py,make-diorama.py`.

- [ ] **Step 3: Bash syntax + suite**

Run: `bash -n assets/scripts/build-scenes.sh && bash -n assets/scripts/build.sh && python -m unittest discover -s tests`
Expected: clean + all pass

- [ ] **Step 4: Regenerate the scripts VERSION (drift guard)**

Run: `python assets/scripts/scripts_fingerprint.py --write assets/scripts`

- [ ] **Step 5: Commit**

```bash
git add assets/scripts/build-scenes.sh assets/scripts/build.sh assets/scripts/VERSION
git commit -m "feat(diorama): build-scenes diorama case + cp wiring"
```

---

### Task 9: Integration smoke + bump scene cache

**Files:** Modify `tests/smoke_build.sh`, `assets/scripts/scene_cache.py`, `tests/test_scene_cache.py`.

- [ ] **Step 1: Bump `scene_cache.VERSION`** "3" → "4" (new scene type / compositor); update the `test_version_bumped` assertion to "4".

- [ ] **Step 2: Add a diorama tier to `tests/smoke_build.sh`** — after the full-build smoke (gated on the same node+edge-tts+Playwright availability), build a tiny diorama from two generated source clips and assert a non-blank 1920×1080 clip:

```bash
# (full smoke section) — append a diorama scene to a second smoke project
# Two lavfi source clips as windows, a 2-stop camera, a mascot keyframe per window.
# Generate sources:
ffmpeg -y -v error -f lavfi -i "testsrc2=s=1280x720:d=6" "$PROJ/footage/a.mp4"
ffmpeg -y -v error -f lavfi -i "testsrc2=s=1280x720:d=6,hue=h=120" "$PROJ/footage/b.mp4"
# brand.yaml scenes.sequence gets one diorama scene + endcards; rebuild; assert:
#   videos/final-with-captions.mp4 exists, 1920x1080, duration > 8, mid-frame non-blank
```

(Add a `mkdir -p "$PROJ/footage"` and a diorama-flavored brand.yaml variant; reuse the existing non-blank colour-count probe. Keep it inside the already-gated full tier so CI's smoke-full job exercises it.)

- [ ] **Step 3: Run the diorama smoke locally** (with the Playwright node_modules):

Run: `DEMO_SMOKE_NODE_MODULES=/path/to/node_modules bash tests/smoke_build.sh`
Expected: `SMOKE PASS` including the diorama build → a non-blank 1920×1080 clip.

- [ ] **Step 4: Regenerate VERSION + full suite**

Run: `python assets/scripts/scripts_fingerprint.py --write assets/scripts && python -m unittest discover -s tests`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add tests/smoke_build.sh assets/scripts/scene_cache.py tests/test_scene_cache.py assets/scripts/VERSION
git commit -m "test(diorama): integration smoke + scene-cache bump"
```

---

### Task 10: Docs + a real diorama example

**Files:** Modify `assets/brand.example.yaml`, `SKILL.md`; Create `assets/mockup-diorama-note` reference in SKILL.

- [ ] **Step 1: Document the scene** in `assets/brand.example.yaml` (a commented `diorama` sequence block: canvas, windows with id/x/y/w/source-or-url/chrome, camera stops, mascot keyframes with at_window/anchor) and in `SKILL.md` (a `### Diorama scene` subsection under scene types: what it is, the config, v1 boundaries — static windows, mascot placed at window anchors, heavier render).

- [ ] **Step 2: Full suite + bash -n**

Run: `python -m unittest discover -s tests && bash -n assets/scripts/build.sh`
Expected: pass

- [ ] **Step 3: Commit**

```bash
git add assets/brand.example.yaml SKILL.md
git commit -m "docs(diorama): brand.example + SKILL diorama scene docs"
```

---

### Task 11: End-to-end verification (Fractal diorama)

**Files:** none (verification only).

- [ ] **Step 1: Full unit suite**

Run: `python -m unittest discover -s tests`
Expected: all pass.

- [ ] **Step 2: Build a real diorama** in the Fractal demo project (the three existing mockups as three windows + a camera tour + the kangaroo hopping window-to-window):
  - Add a `diorama` scene to a scratch copy of `orchestrator-core/demo-video/brand.yaml` using the three mockups (or their captured clips) as window sources, a 3-stop camera, and kangaroo keyframes (`at_window` per beat).
  - `bash scripts/build.sh` → verify `final-framed.mp4`: windows visible on the canvas, camera pans between them, kangaroo hops across.
  - Extract frames at camera-hold and mid-pan timestamps to confirm the pan + the mascot on a window.

- [ ] **Step 3: Push + open PR**

```bash
git push -u origin feat/diorama-scene
```

---

## Out of scope (future)
- Moving/animating window positions; parallax canvas layers.
- Physics edge-walking (mascot is placed at anchors, not collision-walked).
- Per-window independent camera (one shared camera path).
