# Diorama Window Chrome + Guardrails Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render opt-in macOS-traffic-light title bars around diorama windows (so a bare clip reads as a real app window), and add two guardrails — reject a non-16:9 canvas, and clamp mascot anchors into the canvas.

**Architecture:** Pure ffmpeg, no new deps. `build_canvas_filter` overlays each chrome window's clip `BAR_H` px lower; a separate post-composite `chrome_filter` draws the bar (`drawbox`) + traffic-light dots (a generated round-dots RGBA PNG, `overlay`) + title (`drawtext` via the existing `make-before-after` helpers) on the assembled canvas. Pure cores (`assert_canvas_16_9`, `chrome_metrics`, `_ffcolor`, `dots_rgba`, `chrome_filter`, the anchor clamp, the plan passthrough) are unit-tested; the ffmpeg graph is verified by the smoke diorama with `chrome: true`.

**Tech Stack:** Python 3.10+ stdlib, ffmpeg/ffprobe, bash, unittest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-13-diorama-window-chrome-design.md`.
**Branch:** `feat/diorama-chrome` (off `main`, which has the merged diorama scene). Tests run from repo root: `python -m unittest discover -s tests` (260 green at start). A single test file runs directly: `python tests/test_make_diorama.py -v`. Hyphenated scripts are imported via `importlib.util.spec_from_file_location` (copy `tests/test_make_diorama.py`'s loader).

## File structure

- **Modify `assets/scripts/diorama_layout.py`** — add `assert_canvas_16_9(canvas, tol=0.01)` (pure: raises on non-16:9).
- **Modify `assets/scripts/make-diorama.py`** — `BAR_H` constant; `_ffcolor()` (hex→`0xRRGGBB`); `chrome_metrics()` (bar→derived sizes); `dots_rgba()` (3-dot strip RGBA bytes); `chrome_filter()` (post-composite bar/dots/title filter); `build_canvas_filter()` chrome clip-offset; `resolve_canvas_positions()` gains `canvas` + clamp; `main()` aspect guard, window `H += BAR_H`, dots-PNG generation, title textfiles, input wiring.
- **Create `assets/scripts/diorama_plan.py`** — pure `build_plan(scene, clips, chrome_style)` (the make-diorama plan dict, incl. chrome/title), extracted from the build-scenes heredoc so it is unit-testable.
- **Modify `assets/scripts/build-scenes.sh`** — diorama heredoc records url windows, reads the palette, then calls `diorama_plan.build_plan`.
- **Modify `assets/scripts/build.sh`** — add `diorama_plan.py` to the cp list.
- **Modify `SKILL.md`, `assets/brand.example.yaml`** — document `chrome: true` + `title:`.
- **Modify `tests/smoke_build.sh`** — `chrome: true` on the smoke diorama's window `a`.
- **Tests:** `tests/test_diorama_layout.py`, `tests/test_make_diorama.py`, and a new `tests/test_diorama_plan_build.py`.

Reused unchanged: `make-before-after.py` (`find_font`, `ascii_label`, `_esc_path`), `render-mascot.py` (the `ffmpeg -f rawvideo -pix_fmt rgba` PNG technique).

---

### Task 1: Guardrail 1 — `assert_canvas_16_9` (pure) + wire into main()

**Files:**
- Modify: `assets/scripts/diorama_layout.py`
- Modify: `assets/scripts/make-diorama.py:main()`
- Test: `tests/test_diorama_layout.py`

- [ ] **Step 1: Write the failing test** (append to `tests/test_diorama_layout.py`, and add `assert_canvas_16_9` to the import on line 28)

```python
class TestAssertCanvas16x9(unittest.TestCase):
    def test_accepts_16_9(self):
        from diorama_layout import assert_canvas_16_9
        assert_canvas_16_9({"width": 2560, "height": 1440})   # no raise
        assert_canvas_16_9({"width": 1920, "height": 1080})

    def test_rejects_other_aspect(self):
        from diorama_layout import assert_canvas_16_9
        with self.assertRaises(ValueError):
            assert_canvas_16_9({"width": 2560, "height": 1200})

    def test_error_names_the_dimensions(self):
        from diorama_layout import assert_canvas_16_9
        with self.assertRaises(ValueError) as cm:
            assert_canvas_16_9({"width": 2000, "height": 1000})
        self.assertIn("2000x1000", str(cm.exception))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python tests/test_diorama_layout.py -v`
Expected: FAIL — `ImportError: cannot import name 'assert_canvas_16_9'`.

- [ ] **Step 3: Implement** (add to `assets/scripts/diorama_layout.py`, after the module docstring's helpers — e.g. just below `_bbox`)

```python
def assert_canvas_16_9(canvas, tol=0.01):
    """Raise ValueError unless the canvas is 16:9 (within tol). The diorama camera
    frames a 16:9 region via zoompan; a non-16:9 canvas would distort silently."""
    w, h = canvas["width"], canvas["height"]
    if abs(w / h - 16 / 9) > tol:
        raise ValueError(f"diorama canvas must be 16:9 (got {w}x{h})")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python tests/test_diorama_layout.py -v`
Expected: PASS.

- [ ] **Step 5: Wire into `make-diorama.py:main()`** — add the import to the existing `from diorama_layout import (...)` block, and call it right after `canvas, windows = plan["canvas"], plan["windows"]`:

```python
from diorama_layout import (  # noqa: E402
    assert_canvas_16_9, camera_duration, camera_timeline, viewport_at, window_anchor)
```

```python
    canvas, windows = plan["canvas"], plan["windows"]
    assert_canvas_16_9(canvas)          # fail loud, not silent zoompan distortion
```

- [ ] **Step 6: Run the full suite**

Run: `python -m unittest discover -s tests -p 'test_*.py'`
Expected: OK (no regressions).

- [ ] **Step 7: Commit**

```bash
git add assets/scripts/diorama_layout.py assets/scripts/make-diorama.py tests/test_diorama_layout.py
git commit -m "feat(diorama-chrome): assert_canvas_16_9 guardrail"
```

---

### Task 2: Guardrail 2 — clamp mascot anchors into the canvas

**Files:**
- Modify: `assets/scripts/make-diorama.py` (`resolve_canvas_positions` + its `main()` call site)
- Test: `tests/test_make_diorama.py`

- [ ] **Step 1: Update the failing test** — the existing `TestCanvasPositions` calls `resolve_canvas_positions(tl, self.WINS, (160, 140))`; it must now pass a `canvas`. Replace that class with:

```python
class TestCanvasPositions(unittest.TestCase):
    WINS = [{"id": "a", "x": 100, "y": 200, "w": 1280, "h": 720},
            {"id": "b", "x": 2300, "y": 1100, "w": 1280, "h": 720}]
    CANVAS = {"width": 3840, "height": 2160}

    def test_static_segment_uses_window_anchor(self):
        tl = [{"at": 0, "until": 3, "emotion": "idle", "at_window": "a", "anchor": "top"}]
        pos = md.resolve_canvas_positions(tl, self.WINS, (160, 140), self.CANVAS)
        self.assertEqual(pos[0], (100 + (1280 - 160) // 2, 200 - 140))

    def test_move_segment_resolves_both_windows(self):
        tl = [{"at": 0, "until": 0.8, "emotion": "walk",
               "move": {"from_window": "a", "from_anchor": "top",
                        "to_window": "b", "to_anchor": "beside"}}]
        pos = md.resolve_canvas_positions(tl, self.WINS, (160, 140), self.CANVAS)
        self.assertEqual(pos[0][0], (100 + (1280 - 160) // 2, 200 - 140))
        self.assertEqual(pos[0][1], (2300 + 1280 + 8, 1100 + (720 - 140) // 2))

    def test_anchor_clamped_into_canvas(self):
        # window 'b' is at the right/bottom edge; a 'beside' anchor would land the
        # sprite off-canvas — it must clamp to within [0, canvas - sprite]
        small = {"width": 3300, "height": 1300}
        tl = [{"at": 0, "until": 3, "emotion": "point", "at_window": "b", "anchor": "beside"}]
        x, y = md.resolve_canvas_positions(tl, self.WINS, (160, 140), small)[0]
        self.assertLessEqual(x + 160, small["width"])
        self.assertLessEqual(y + 140, small["height"])
        self.assertGreaterEqual(x, 0)
        self.assertGreaterEqual(y, 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python tests/test_make_diorama.py -v`
Expected: FAIL — `resolve_canvas_positions() takes 3 positional arguments but 4 were given`.

- [ ] **Step 3: Implement** — in `assets/scripts/make-diorama.py`, add the clamp helper and the `canvas` parameter:

```python
def _clamp_xy(xy, sprite_wh, canvas):
    """Keep a sprite anchor inside the canvas: x in [0, W-sw], y in [0, H-sh]."""
    x, y = xy
    sw, sh = sprite_wh
    return (min(max(0, x), canvas["width"] - sw),
            min(max(0, y), canvas["height"] - sh))


def resolve_canvas_positions(timeline, windows, sprite_wh, canvas):
    """Per-segment canvas anchors for the mascot, clamped into the canvas. Static
    segs carry at_window+anchor; move segs carry move.{from,to}_{window,anchor}."""
    by_id = {w["id"]: w for w in windows}
    sw, sh = sprite_wh
    out = []
    for seg in timeline:
        if "move" in seg:
            mv = seg["move"]
            out.append((_clamp_xy(window_anchor(by_id[mv["from_window"]], mv["from_anchor"], sw, sh), sprite_wh, canvas),
                        _clamp_xy(window_anchor(by_id[mv["to_window"]], mv["to_anchor"], sw, sh), sprite_wh, canvas)))
        else:
            out.append(_clamp_xy(window_anchor(by_id[seg["at_window"]], seg["anchor"], sw, sh), sprite_wh, canvas))
    return out
```

- [ ] **Step 4: Update the `main()` call site** — pass `canvas`:

```python
        positions = resolve_canvas_positions(timeline, windows, sprite_wh, canvas)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python tests/test_make_diorama.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add assets/scripts/make-diorama.py tests/test_make_diorama.py
git commit -m "feat(diorama-chrome): clamp mascot anchors into the canvas"
```

---

### Task 3: Plan passthrough — `diorama_plan.build_plan` (chrome/title + chrome_style)

**Files:**
- Create: `assets/scripts/diorama_plan.py`
- Modify: `assets/scripts/build-scenes.sh` (diorama case), `assets/scripts/build.sh` (cp list)
- Test: `tests/test_diorama_plan_build.py`

**Context:** Today the diorama case's inline heredoc builds the make-diorama plan and silently drops `chrome`/`title`. Extract the *plan-building* (not the recording) into a pure `build_plan(scene, clips, chrome_style)` so it can be tested, and carry chrome through it.

- [ ] **Step 1: Write the failing test** — create `tests/test_diorama_plan_build.py`:

```python
# tests/test_diorama_plan_build.py
import importlib.util, os, sys, unittest
SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "assets", "scripts")
spec = importlib.util.spec_from_file_location("diorama_plan", os.path.join(SCRIPTS, "diorama_plan.py"))
dp = importlib.util.module_from_spec(spec); spec.loader.exec_module(dp)

SCENE = {"canvas": {"width": 2560, "height": 1440, "backdrop": "color=c=0x121214"},
         "camera": [{"focus": "a", "hold": 2}, {"focus": "b", "hold": 2, "transition": 1}],
         "windows": [{"id": "a", "x": 1, "y": 2, "w": 900, "chrome": True, "title": "worker"},
                     {"id": "b", "x": 3, "y": 4, "w": 900}],
         "mascot": {"keyframes": [{"at": 0, "emotion": "idle", "at_window": "a", "anchor": "top"}]},
         "duration": 12}
CLIPS = {"a": "videos/da.mp4", "b": "footage/b.mp4"}
STYLE = {"bar_bg": "#17171a", "rule": "#2c2c32", "fg": "#f4efe3"}  # raw brand hex; make-diorama _ffcolor's it


class TestBuildPlan(unittest.TestCase):
    def test_carries_chrome_and_title(self):
        plan = dp.build_plan(SCENE, CLIPS, STYLE)
        a, b = plan["windows"]
        self.assertTrue(a["chrome"]); self.assertEqual(a["title"], "worker")
        self.assertEqual(a["clip"], "videos/da.mp4")
        self.assertFalse(b.get("chrome", False))   # b has no chrome
        self.assertEqual(b["clip"], "footage/b.mp4")

    def test_chrome_style_present_only_when_a_window_has_chrome(self):
        self.assertEqual(dp.build_plan(SCENE, CLIPS, STYLE)["chrome_style"], STYLE)
        plain = {**SCENE, "windows": [{"id": "a", "x": 1, "y": 2, "w": 900}]}
        self.assertIsNone(dp.build_plan(plain, {"a": "x.mp4"}, STYLE).get("chrome_style"))

    def test_backdrop_and_duration_and_mascot_pass_through(self):
        plan = dp.build_plan(SCENE, CLIPS, STYLE)
        self.assertEqual(plan["backdrop"], "color=c=0x121214")
        self.assertEqual(plan["duration"], 12)
        self.assertEqual(plan["mascot"]["keyframes"][0]["at_window"], "a")
        self.assertEqual(plan["fps"], 30)

    def test_default_backdrop_when_canvas_has_none(self):
        s = {**SCENE, "canvas": {"width": 2560, "height": 1440}}
        self.assertEqual(dp.build_plan(s, CLIPS, STYLE)["backdrop"], "color=c=0x0a0705")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python tests/test_diorama_plan_build.py -v`
Expected: FAIL — `No such file or directory: '.../diorama_plan.py'`.

- [ ] **Step 3: Implement** — create `assets/scripts/diorama_plan.py`:

```python
# assets/scripts/diorama_plan.py
"""diorama_plan.py — build the make-diorama plan dict from a resolved diorama
scene. Pure (no I/O): build-scenes.sh records the url windows + reads the palette,
then calls build_plan(). Kept separate from recording so it is unit-testable.
"""


def build_plan(scene, clips, chrome_style, fps=30):
    """scene (the diorama entry minus id/type/mp4) + clips {win_id: clip_path} +
    chrome_style {bar_bg, rule, fg} -> the make-diorama plan dict.

    Carries chrome/title per window; attaches chrome_style only when some window
    has chrome. backdrop falls back to a dark solid; mascot/duration pass through.
    """
    windows = []
    has_chrome = False
    for w in scene["windows"]:
        win = {"id": w["id"], "x": w["x"], "y": w["y"], "w": w["w"], "clip": clips[w["id"]]}
        if w.get("chrome"):
            win["chrome"] = True
            win["title"] = w.get("title", w["id"])
            has_chrome = True
        windows.append(win)
    plan = {
        "canvas": scene["canvas"],
        "camera": scene["camera"],
        "windows": windows,
        "fps": fps,
        "backdrop": (scene.get("canvas") or {}).get("backdrop") or "color=c=0x0a0705",
        "mascot": scene.get("mascot"),
    }
    if scene.get("duration") is not None:
        plan["duration"] = scene["duration"]
    if has_chrome:
        plan["chrome_style"] = chrome_style
    return plan
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python tests/test_diorama_plan_build.py -v`
Expected: PASS.

- [ ] **Step 5: Rewire `build-scenes.sh`** — replace the diorama case's inline python heredoc body with: record url windows, read the palette, call `build_plan`. Replace the existing `python - "$id" <<'PY' ... PY` block in the `diorama)` case with:

```bash
      python - "$id" <<'PY'
import importlib.util, json, os, subprocess, sys
sid = sys.argv[1]
dps = importlib.util.spec_from_file_location("diorama_plan", "diorama_plan.py")
dp = importlib.util.module_from_spec(dps); dps.loader.exec_module(dp)
e = json.load(open(f".scene-{sid}.json"))
clips = {}
for w in e["windows"]:
    if "capture" in w:                       # a live url window — record it now
        cap = w["capture"]
        json.dump(cap, open(f".scene-{sid}-{w['id']}.json", "w"))
        subprocess.check_call(["node", "record-browser.mjs", f".scene-{sid}-{w['id']}.json"])
        subprocess.check_call(["python", "cut-clip.py", cap["output"]])  # focus (no-op if unused)
        clips[w["id"]] = cap["output"]
    else:
        clips[w["id"]] = w["source"]
pal = json.load(open("config.json")).get("palette", {})   # raw brand palette (apply-brand emits it)
style = {"bar_bg": pal.get("end_card_bg", "#17171a"),
         "rule":   pal.get("rule", "#2c2c32"),
         "fg":     pal.get("fg", "#f4efe3")}               # raw #RRGGBB; make-diorama _ffcolor's it
json.dump(dp.build_plan(e, clips, style), open(f".diorama-{sid}.json", "w"))
PY
```

(`config.json` carries the raw brand palette at top-level `config["palette"]` — see `apply-brand.py` line 337 — with keys `bg`/`fg`/`accent`/`rule`/`end_card_bg`. The `.get(...)` fallbacks keep it working if the brand omits a key.)

- [ ] **Step 6: Add `diorama_plan.py` to `build.sh`'s cp list** — append it inside the brace list next to `make-diorama.py`:

```bash
...,diorama_layout.py,make-diorama.py,diorama_plan.py} "$BUILD/"
```

- [ ] **Step 7: Bash syntax + suite**

Run: `bash -n assets/scripts/build-scenes.sh && bash -n assets/scripts/build.sh && python -m unittest discover -s tests -p 'test_*.py'`
Expected: clean + OK.

- [ ] **Step 8: Commit**

```bash
git add assets/scripts/diorama_plan.py assets/scripts/build-scenes.sh assets/scripts/build.sh tests/test_diorama_plan_build.py
git commit -m "feat(diorama-chrome): carry chrome/title into the make-diorama plan (testable build_plan)"
```

---

### Task 4: Pure helpers — `_ffcolor` + `chrome_metrics`

**Files:**
- Modify: `assets/scripts/make-diorama.py`
- Test: `tests/test_make_diorama.py`

- [ ] **Step 1: Write the failing test** (append to `tests/test_make_diorama.py`)

```python
class TestChromeHelpers(unittest.TestCase):
    def test_ffcolor_normalizes_hex(self):
        self.assertEqual(md._ffcolor("#1e1714"), "0x1e1714")
        self.assertEqual(md._ffcolor("2c2c32"), "0x2c2c32")
        self.assertEqual(md._ffcolor("0xabcdef"), "0xabcdef")

    def test_chrome_metrics_scale_from_bar_height(self):
        m = md.chrome_metrics(40)
        self.assertEqual(m["strip_w"], 3 * m["d"] + 2 * m["gap"])
        self.assertEqual(m["strip_h"], m["d"])
        self.assertGreater(m["title_x"], m["pad"] + m["strip_w"])  # title right of dots
        for k in ("d", "gap", "pad", "title_x", "title_fs"):
            self.assertGreater(m[k], 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python tests/test_make_diorama.py -v`
Expected: FAIL — `module 'make_diorama' has no attribute '_ffcolor'`.

- [ ] **Step 3: Implement** (add to `assets/scripts/make-diorama.py`, near the top after imports)

```python
BAR_H = 40   # title-bar height in canvas px (constant — real title bars are ~fixed)


def _ffcolor(c):
    """'#1e1714' / '1e1714' / '0x1e1714' -> '0x1e1714' for ffmpeg drawbox/drawtext."""
    c = str(c)
    if c.startswith("0x"):
        return c
    return "0x" + c.lstrip("#")


def chrome_metrics(bar_h):
    """Derived chrome sizes from the bar height (so they scale together and are
    unit-testable): dot diameter/gap, left pad, dots-strip size, title x + font."""
    d = max(8, round(bar_h * 0.30))
    gap = max(4, round(d * 0.6))
    pad = round(bar_h * 0.5)
    strip_w = 3 * d + 2 * gap
    return {"d": d, "gap": gap, "pad": pad, "strip_w": strip_w, "strip_h": d,
            "title_x": pad + strip_w + round(bar_h * 0.5),
            "title_fs": max(10, round(bar_h * 0.42))}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python tests/test_make_diorama.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add assets/scripts/make-diorama.py tests/test_make_diorama.py
git commit -m "feat(diorama-chrome): _ffcolor + chrome_metrics pure helpers"
```

---

### Task 5: `dots_rgba` — the traffic-light strip (pure painter)

**Files:**
- Modify: `assets/scripts/make-diorama.py`
- Test: `tests/test_make_diorama.py`

- [ ] **Step 1: Write the failing test** (append to `tests/test_make_diorama.py`)

```python
class TestDotsRgba(unittest.TestCase):
    def test_byte_length_matches_strip(self):
        m = md.chrome_metrics(40)
        buf = md.dots_rgba(m)
        self.assertEqual(len(buf), m["strip_w"] * m["strip_h"] * 4)

    def test_first_dot_centre_is_opaque_red(self):
        m = md.chrome_metrics(40)
        buf = md.dots_rgba(m)
        cx, cy = m["d"] // 2, m["d"] // 2          # centre of dot 0
        o = (cy * m["strip_w"] + cx) * 4
        self.assertEqual((buf[o], buf[o + 1], buf[o + 2]), (0xff, 0x5f, 0x57))
        self.assertGreater(buf[o + 3], 250)         # opaque

    def test_corner_is_transparent(self):
        m = md.chrome_metrics(40)
        buf = md.dots_rgba(m)
        self.assertEqual(buf[3], 0)                  # top-left pixel alpha == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python tests/test_make_diorama.py -v`
Expected: FAIL — `module 'make_diorama' has no attribute 'dots_rgba'`.

- [ ] **Step 3: Implement** (add to `assets/scripts/make-diorama.py`)

```python
DOT_COLORS = [(0xff, 0x5f, 0x57), (0xfe, 0xbc, 0x2e), (0x7f, 0xbf, 0x7f)]  # red/amber/green


def dots_rgba(metrics):
    """Raw RGBA bytes for the three traffic-light dots on a transparent strip
    (strip_w x strip_h). Filled circles with a 1px anti-aliased edge. No Pillow —
    the bytes are piped to ffmpeg as rawvideo, like render-mascot.py."""
    w, h = metrics["strip_w"], metrics["strip_h"]
    d, gap = metrics["d"], metrics["gap"]
    r = d / 2.0
    buf = bytearray(w * h * 4)                      # zero-filled = transparent
    for i, (cr, cg, cb) in enumerate(DOT_COLORS):
        cx = i * (d + gap) + r
        cy = r
        for y in range(h):
            for x in range(w):
                dist = ((x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2) ** 0.5
                cov = max(0.0, min(1.0, r - dist + 0.5))   # coverage at the edge
                a = int(round(cov * 255))
                if a == 0:
                    continue
                o = (y * w + x) * 4
                if a <= buf[o + 3]:
                    continue
                buf[o], buf[o + 1], buf[o + 2], buf[o + 3] = cr, cg, cb, a
    return bytes(buf)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python tests/test_make_diorama.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add assets/scripts/make-diorama.py tests/test_make_diorama.py
git commit -m "feat(diorama-chrome): dots_rgba traffic-light strip painter"
```

---

### Task 6: `chrome_filter` (post-composite) + `build_canvas_filter` clip-offset

**Files:**
- Modify: `assets/scripts/make-diorama.py`
- Test: `tests/test_make_diorama.py`

**Context:** `chrome_filter` draws bar + dots + title on the assembled `[canvas]` for each chrome window. `build_canvas_filter` overlays a chrome window's clip `BAR_H` px lower so the bar sits above it.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_make_diorama.py`)

```python
class TestChromeFilter(unittest.TestCase):
    WINS = [{"id": "a", "x": 100, "y": 200, "w": 900, "chrome": True, "title_file": "ta.txt"},
            {"id": "b", "x": 1500, "y": 200, "w": 900}]   # b: no chrome
    STYLE = {"bar_bg": "0x17171a", "rule": "0x2c2c32", "fg": "0xf4efe3"}

    def test_draws_bar_dots_title_for_chrome_window_only(self):
        f = md.chrome_filter(self.WINS, in_label="canvas", out_label="vout",
                             dots_index=3, style=self.STYLE, font="C:/f.ttf")
        # bar drawbox at the chrome window's (x, y) with its width and BAR_H
        self.assertIn(f"drawbox=x=100:y=200:w=900:h={md.BAR_H}", f)
        self.assertIn("0x17171a", f)                    # bar bg colour
        self.assertIn("overlay=", f)                    # dots overlay
        self.assertIn("ta.txt", f.replace("\\", ""))    # title textfile
        self.assertEqual(f.count("drawbox=x=100:y=200:w=900"), 1)   # exactly one bar (window a)
        self.assertNotIn("x=1500", f)                   # window b (no chrome, x=1500) untouched

    def test_passthrough_when_no_chrome_windows(self):
        plain = [{"id": "b", "x": 0, "y": 0, "w": 900}]
        f = md.chrome_filter(plain, in_label="canvas", out_label="vout",
                             dots_index=None, style=None, font=None)
        self.assertEqual(f, "[canvas]null[vout]")       # nothing to draw

    def test_dots_input_split_per_chrome_window(self):
        wins = [dict(self.WINS[0]), {"id": "c", "x": 50, "y": 50, "w": 800,
                                     "chrome": True, "title_file": "tc.txt"}]
        f = md.chrome_filter(wins, in_label="canvas", out_label="vout",
                             dots_index=3, style=self.STYLE, font=None)
        self.assertIn("[3:v]split=2", f)                # one dots copy per chrome window


class TestCanvasClipOffset(unittest.TestCase):
    def test_chrome_window_clip_overlaid_below_the_bar(self):
        wins = [{"id": "a", "x": 100, "y": 200, "w": 900, "chrome": True}]
        f = md.build_canvas_filter(wins, {"width": 2560, "height": 1440})
        self.assertIn(f"overlay=100:{200 + md.BAR_H}", f)    # clip pushed down by BAR_H

    def test_plain_window_clip_overlaid_at_origin(self):
        wins = [{"id": "a", "x": 100, "y": 200, "w": 900}]
        f = md.build_canvas_filter(wins, {"width": 2560, "height": 1440})
        self.assertIn("overlay=100:200", f)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python tests/test_make_diorama.py -v`
Expected: FAIL — `module 'make_diorama' has no attribute 'chrome_filter'` (and the offset asserts fail).

- [ ] **Step 3: Implement** — update `build_canvas_filter` to offset chrome clips, and add `chrome_filter`:

```python
def build_canvas_filter(windows, canvas):
    """Backdrop ([0:v]) scaled to canvas, then each window clip ([i:v], i>=1)
    scaled to its width and overlaid at (x, y) — chrome windows' clips are pushed
    down by BAR_H to leave room for the title bar drawn later. Ends at [canvas]."""
    parts = [f"[0:v]scale={canvas['width']}:{canvas['height']},setsar=1[bg]"]
    src = "[bg]"
    for i, w in enumerate(windows, 1):
        parts.append(f"[{i}:v]scale={w['w']}:-2,setsar=1[w{i}]")
        label = "[canvas]" if i == len(windows) else f"[c{i}]"
        wy = w["y"] + (BAR_H if w.get("chrome") else 0)
        parts.append(f"{src}[w{i}]overlay={w['x']}:{wy}{label}")
        src = f"[c{i}]"
    return ";".join(parts)


def chrome_filter(windows, in_label, out_label, dots_index, style, font):
    """Draw the title bar (drawbox), traffic-light dots (overlay of input
    [dots_index]) and title (drawtext, textfile) on `in_label` for each chrome
    window, producing `out_label`. A no-op `null` when no window has chrome."""
    chrome = [w for w in windows if w.get("chrome")]
    if not chrome:
        return f"[{in_label}]null[{out_label}]"
    m = chrome_metrics(BAR_H)
    fontclause = f"fontfile='{_esc_path(font)}':" if font else ""
    parts = [f"[{dots_index}:v]split={len(chrome)}" + "".join(f"[dots{i}]" for i in range(len(chrome)))]
    src = in_label
    for i, w in enumerate(chrome):
        x, y, ww = w["x"], w["y"], w["w"]
        nxt = out_label if i == len(chrome) - 1 else f"chr{i}"
        bar = (f"drawbox=x={x}:y={y}:w={ww}:h={BAR_H}:color={style['bar_bg']}:t=fill,"
               f"drawbox=x={x}:y={y + BAR_H - 2}:w={ww}:h=2:color={style['rule']}:t=fill")
        dots_x, dots_y = x + m["pad"], y + (BAR_H - m["strip_h"]) // 2
        title = (f"drawtext={fontclause}textfile='{_esc_path(w['title_file'])}':"
                 f"x={x + m['title_x']}:y={y}+({BAR_H}-text_h)/2:"
                 f"fontsize={m['title_fs']}:fontcolor={style['fg']}")
        parts.append(f"[{src}]{bar}[chrb{i}]")
        parts.append(f"[chrb{i}][dots{i}]overlay={dots_x}:{dots_y}[chrd{i}]")
        parts.append(f"[chrd{i}]{title}[{nxt}]")
        src = nxt
    return ";".join(parts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python tests/test_make_diorama.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add assets/scripts/make-diorama.py tests/test_make_diorama.py
git commit -m "feat(diorama-chrome): chrome_filter (bar+dots+title) + clip BAR_H offset"
```

---

### Task 7: Wire chrome into `main()` (dots PNG, title files, inputs)

**Files:**
- Modify: `assets/scripts/make-diorama.py:main()`

**Context:** Orchestration glue — no new unit test (verified by the smoke in Task 8 + a manual isolation run). It: computes window `H` including `BAR_H` for chrome windows; when chrome windows exist, generates the dots PNG (via the rawvideo pipe), writes each chrome window's title to a UTF-8 textfile, adds the dots PNG as the last `-i` input, and inserts `chrome_filter` between the canvas composite and the trim.

- [ ] **Step 1: Add the make-before-after import** (top of `main()`, beside the existing importlib loads of `normalize-clip`):

```python
    mba = importlib.util.spec_from_file_location(
        "make_before_after", os.path.join(os.path.dirname(__file__), "make-before-after.py"))
    mbamod = importlib.util.module_from_spec(mba); mba.loader.exec_module(mbamod)
```

- [ ] **Step 2: Include `BAR_H` in chrome windows' height** — in the per-window height loop, change:

```python
    for i, w in enumerate(windows):
        cw, ch = (int(v) for v in _probe(w["clip"], "stream=width,height").split(","))
        clip_h = round(w["w"] * ch / cw)
        w["h"] = clip_h + (BAR_H if w.get("chrome") else 0)
        win_clip = os.path.join(workdir, f".diorama-win-{i}.mp4")
        shutil.copyfile(w["clip"], win_clip)
        normmod.main(["normalize-clip.py", win_clip, str(dur)])  # pin the COPY to DUR
        inputs += ["-i", win_clip]
```

- [ ] **Step 3: Generate dots PNG + title files + add the dots input** — after the height/normalize loop and before `canvas_mp4 = ...`, insert:

```python
    chrome_wins = [w for w in windows if w.get("chrome")]
    style, font, dots_index = None, None, None
    if chrome_wins:
        cs = plan["chrome_style"]
        style = {"bar_bg": _ffcolor(cs["bar_bg"]), "rule": _ffcolor(cs["rule"]),
                 "fg": _ffcolor(cs["fg"])}
        font = mbamod.find_font()
        for w in chrome_wins:                       # one UTF-8 textfile per chrome title
            tf = os.path.join(workdir, f".diorama-title-{w['id']}.txt")
            with open(tf, "w", encoding="utf-8", newline="") as f:
                f.write(mbamod.ascii_label(str(w.get("title", w["id"]))))
            w["title_file"] = tf
        dots_png = os.path.join(workdir, ".diorama-dots.png")
        m = chrome_metrics(BAR_H)
        buf = dots_rgba(m)
        proc = subprocess.Popen(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{m['strip_w']}x{m['strip_h']}",
             "-i", "-", "-frames:v", "1", dots_png], stdin=subprocess.PIPE)
        proc.communicate(buf)
        if proc.returncode != 0:
            sys.exit("make-diorama: dots PNG generation failed")
        dots_index = len(windows) + 1               # [0]=backdrop, [1..N]=clips, [N+1]=dots
        inputs += ["-i", dots_png]
```

- [ ] **Step 4: Insert `chrome_filter` into the canvas graph** — change the canvas `fc`/encode block so chrome is drawn between `[canvas]` and the trim:

```python
    canvas_mp4 = os.path.join(workdir, ".diorama-canvas.mp4")
    fc = build_canvas_filter(windows, canvas)
    if chrome_wins:
        fc += ";" + chrome_filter(windows, "canvas", "canvasc", dots_index, style, font)
        last = "canvasc"
    else:
        last = "canvas"
    fc += f";[{last}]trim=duration={dur:.3f},setpts=PTS-STARTPTS[v]"
    subprocess.check_call(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *inputs,
        "-filter_complex", fc, "-map", "[v]", "-t", f"{dur:.3f}", "-r", str(fps),
        "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", canvas_mp4])
```

- [ ] **Step 5: Manual isolation check** — generate two source clips + a chrome plan and build, confirming a bar renders and the output is 1920x1080:

```bash
mkdir -p /c/tmp/chrome-test && cd /c/tmp/chrome-test
cp "$OLDPWD"/assets/scripts/{make-diorama.py,diorama_layout.py,normalize-clip.py,overlay-mascot.py,mascot_data.py,make-before-after.py} .
ffmpeg -y -v error -f lavfi -i "testsrc2=s=1280x720:d=4" a.mp4
ffmpeg -y -v error -f lavfi -i "testsrc2=s=1280x720:d=4,hue=h=120" b.mp4
cat > plan.json <<'JSON'
{"canvas":{"width":2560,"height":1440},"backdrop":"color=c=0x121214","duration":5,"fps":30,
 "chrome_style":{"bar_bg":"0x17171a","rule":"0x2c2c32","fg":"0xf4efe3"},
 "windows":[{"id":"a","clip":"a.mp4","x":200,"y":300,"w":1000,"chrome":true,"title":"worker - session 4"},
            {"id":"b","clip":"b.mp4","x":1360,"y":700,"w":1000}],
 "camera":[{"focus":"a","zoom":1.6,"hold":2.5},{"focus":"b","zoom":1.6,"hold":2.5,"transition":1.0}],
 "mascot":null}
JSON
python make-diorama.py plan.json out.mp4
ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 out.mp4   # expect 1920,1080
ffmpeg -y -v error -ss 0.5 -i out.mp4 -frames:v 1 frame.png    # eyeball: window 'a' has a dark bar + 3 dots + title
```
Expected: `1920,1080`; `frame.png` shows window `a` with a title bar (3 dots + "worker - session 4"), window `b` bare.

- [ ] **Step 6: Run the full suite** (no regressions from the main() changes)

Run: `python -m unittest discover -s tests -p 'test_*.py'`
Expected: OK.

- [ ] **Step 7: Commit**

```bash
git add assets/scripts/make-diorama.py
git commit -m "feat(diorama-chrome): render chrome in make-diorama main (dots PNG, title files, inputs)"
```

---

### Task 8: Docs + smoke + VERSION

**Files:**
- Modify: `SKILL.md`, `assets/brand.example.yaml`, `tests/smoke_build.sh`, `assets/scripts/VERSION`

- [ ] **Step 1: Document `chrome`/`title`** — in `SKILL.md`'s Diorama section, in the `windows:` description, add: a window may set `chrome: true` (and optional `title:`) to draw a macOS-style title bar (traffic-light dots + title) around it — for raw `source`/`url` clips that don't bring their own window frame; the bar adds `BAR_H` to the window's height; long titles may clip. Mirror a one-line `chrome: true, title: "worker"` in the `assets/brand.example.yaml` diorama window comment block.

- [ ] **Step 2: Enable chrome in the smoke** — in `tests/smoke_build.sh`, the diorama scene's window `a`: add `chrome: true` and a title. Change the line:

```yaml
        - { id: a, source: "footage/da.mp4", x: 120, y: 300, w: 1000 }
```
to:
```yaml
        - { id: a, source: "footage/da.mp4", x: 120, y: 300, w: 1000, chrome: true, title: "worker" }
```

The existing diorama assertions (1920x1080 + `nonblank` + source-intact) already cover that the chrome filter graph runs end-to-end.

- [ ] **Step 3: Run the diorama smoke** (with a Playwright node_modules + node on PATH)

Run: `DEMO_SMOKE_NODE_MODULES=/path/to/node_modules bash tests/smoke_build.sh`
Expected: `SMOKE PASS` (the chrome window builds without error; clip is non-blank 1920x1080).

- [ ] **Step 4: Regenerate VERSION + full suite**

Run: `python assets/scripts/scripts_fingerprint.py --write assets/scripts && python -m unittest discover -s tests -p 'test_*.py'`
Expected: OK.

- [ ] **Step 5: Commit**

```bash
git add SKILL.md assets/brand.example.yaml tests/smoke_build.sh assets/scripts/VERSION
git commit -m "docs(diorama-chrome): document chrome/title + smoke chrome window + VERSION"
```

---

## Out of scope (deferred — see spec)
- Title in the brand mono font; per-window chrome colour overrides; address-bar/tab variants; rounded corners/shadows; HTML-rendered chrome.
- Truncating long titles (may clip in v1).
