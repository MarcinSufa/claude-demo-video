# Mascot Overlay Implementation Plan (Spec Phases 1–3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Composite a brand-colored pixel mascot (octopus first) onto every scene clip of a /demo-video build, with an auto-resolved per-scene emotion timeline and a layered capture/overlay cache.

**Architecture:** Mascot sprites are pixel-grid JSON data rendered to transparent PNG frame sequences by `render-mascot.py` (RGBA piped to ffmpeg — no Pillow). `plan-scenes.py` attaches a `mascot_plan` stub per scene; after capture + normalize, `resolve-mascot-timeline.py` merges the stub with real clip duration and `.events.json` into an exact `[{at, until, emotion}]` timeline; `overlay-mascot.py` composites via ffmpeg `overlay` + `enable=between(t,..)`. `build-scenes.sh` keeps the pristine capture at `<mp4>.capture.mp4` so a mascot change re-overlays without re-recording (two-layer cache in `scene_cache.py`, VERSION bumped to 2).

**Tech Stack:** Python 3.10+ stdlib, ffmpeg/ffprobe, bash, unittest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-12-mascot-overlay-design.md`. This plan implements spec phases 1–3. Phases 4 (moments + corner flip) and 5 (full roster) are a follow-up plan.

**Branch:** `feat/mascot-overlay`. All script paths are in `assets/scripts/`; tests run with `python -m unittest discover -s tests` from the repo root (existing tests add `assets/scripts` to `sys.path` — copy the pattern from `tests/test_scene_cache.py`).

---

### Task 1: Mascot data format + octopus + loader/validator

**Files:**
- Create: `assets/mascots/octopus.json`
- Create: `assets/scripts/mascot_data.py`
- Test: `tests/test_mascot_data.py`

The format: a mascot is `legend` (char → palette-slot or null for transparent), `palette` (slot → default hex), and `animations` (name → list of frames; a frame is a list of equal-length strings of legend chars). `cell_px` and `fps` pin deterministic rendering.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_mascot_data.py
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "assets", "scripts"))
from mascot_data import load_mascot, validate_mascot, MascotError  # noqa: E402

MINIMAL = {
    "name": "blob",
    "cell_px": 6,
    "scale": 1.0,
    "fps": 8,
    "legend": {".": None, "b": "body", "e": "eyes"},
    "palette": {"body": "#e07a5f", "eyes": "#1a1a1a"},
    "animations": {
        "idle": [[".b.", "beb", ".b."], [".b.", "bbb", ".b."]],
        "type": [[".b.", "beb", "b.b"]],
        "panic": [["e.e", ".b.", "b.b"]],
        "celebrate": [["b.b", ".b.", "..."]],
        "sleep": [["...", ".b.", "bbb"]],
        "point": [["..b", ".bb", ".b."]],
        "enter": [["...", "...", ".b."]],
        "exit": [[".b.", "...", "..."]],
    },
}


class TestValidate(unittest.TestCase):
    def test_minimal_valid(self):
        validate_mascot(MINIMAL)  # should not raise

    def test_missing_animation_rejected(self):
        bad = json.loads(json.dumps(MINIMAL))
        del bad["animations"]["panic"]
        with self.assertRaisesRegex(MascotError, "panic"):
            validate_mascot(bad)

    def test_unknown_legend_char_rejected(self):
        bad = json.loads(json.dumps(MINIMAL))
        bad["animations"]["idle"][0][0] = "xb."
        with self.assertRaisesRegex(MascotError, "idle.*frame 0.*'x'"):
            validate_mascot(bad)

    def test_ragged_frame_rejected(self):
        bad = json.loads(json.dumps(MINIMAL))
        bad["animations"]["idle"][0][1] = "bb"
        with self.assertRaisesRegex(MascotError, "idle.*frame 0.*width"):
            validate_mascot(bad)

    def test_legend_slot_missing_from_palette_rejected(self):
        bad = json.loads(json.dumps(MINIMAL))
        bad["legend"]["h"] = "hat"  # no "hat" in palette
        with self.assertRaisesRegex(MascotError, "hat"):
            validate_mascot(bad)

    def test_bad_hex_rejected(self):
        bad = json.loads(json.dumps(MINIMAL))
        bad["palette"]["body"] = "tomato"
        with self.assertRaisesRegex(MascotError, "body"):
            validate_mascot(bad)


class TestLoad(unittest.TestCase):
    def test_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "m.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump(MINIMAL, f)
            m = load_mascot(p)
            self.assertEqual(m["name"], "blob")

    def test_load_missing_file(self):
        with self.assertRaises(MascotError):
            load_mascot("no/such/mascot.json")


class TestOctopusShips(unittest.TestCase):
    def test_bundled_octopus_validates(self):
        p = os.path.join(os.path.dirname(__file__), "..", "assets", "mascots", "octopus.json")
        validate_mascot(load_mascot(p))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_mascot_data -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mascot_data'`

- [ ] **Step 3: Implement `mascot_data.py`**

```python
# assets/scripts/mascot_data.py
"""mascot_data.py — load + validate a mascot pixel-grid data file.

A mascot is deterministic data, not an image: legend (char -> palette slot),
palette (slot -> hex), animations (name -> frames of equal-width rows).
This module is the single format authority; render-mascot.py and the brand
remap helper both consume it.
"""
import json
import os
import re

REQUIRED_ANIMATIONS = (
    "idle", "type", "panic", "celebrate", "sleep", "point", "enter", "exit",
)
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


class MascotError(Exception):
    pass


def load_mascot(path):
    if not os.path.exists(path):
        raise MascotError(f"mascot file not found: {path}")
    with open(path, encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            raise MascotError(f"invalid JSON in {path}: {e}") from e
    return data


def validate_mascot(m):
    for key in ("name", "cell_px", "fps", "legend", "palette", "animations"):
        if key not in m:
            raise MascotError(f"missing required key '{key}'")
    legend, palette, anims = m["legend"], m["palette"], m["animations"]
    for slot, color in palette.items():
        if not _HEX.match(color):
            raise MascotError(f"palette slot '{slot}' has invalid hex '{color}'")
    for ch, slot in legend.items():
        if slot is not None and slot not in palette:
            raise MascotError(f"legend char '{ch}' maps to unknown palette slot '{slot}'")
    for name in REQUIRED_ANIMATIONS:
        if name not in anims or not anims[name]:
            raise MascotError(f"missing or empty required animation '{name}'")
    for name, frames in anims.items():
        for fi, frame in enumerate(frames):
            if not frame:
                raise MascotError(f"animation '{name}' frame {fi} is empty")
            width = len(frame[0])
            for row in frame:
                if len(row) != width:
                    raise MascotError(
                        f"animation '{name}' frame {fi} has inconsistent row width")
                for ch in row:
                    if ch not in legend:
                        raise MascotError(
                            f"animation '{name}' frame {fi} uses char '{ch}' "
                            f"not in legend")
```

- [ ] **Step 4: Create `assets/mascots/octopus.json`**

A 16-wide × 12-tall octopus, Anthropic-Clawd-adjacent but original. Two slots beyond body/eyes: `belly` (lighter underside) and `accent` (cheeks/highlights — the slot brand remapping targets first). Author 2 frames per animation minimum (idle/type get 2–4; enter/exit can be 2). Keep grids hand-editable. Example shape for `idle` frame 0 (all 8 animations follow the same legend):

```json
{
  "name": "octopus",
  "cell_px": 8,
  "scale": 1.0,
  "fps": 7,
  "legend": {".": null, "b": "body", "l": "belly", "e": "eyes", "a": "accent"},
  "palette": {
    "body": "#d97757",
    "belly": "#e8a087",
    "eyes": "#141414",
    "accent": "#b35a3e"
  },
  "animations": {
    "idle": [
      [
        "....bbbbbbbb....",
        "..bbbbbbbbbbbb..",
        ".bbbbbbbbbbbbbb.",
        ".bbe.bbbbbb.ebb.",
        ".bbe.bbbbbb.ebb.",
        ".bbbbbbbbbbbbbb.",
        ".bablllllllbab..",
        ".bbllllllllllbb.",
        "..bbbbbbbbbbbb..",
        "..b.b..bb..b.b..",
        ".bb.bb.bb.bb.bb.",
        ".b...b....b...b."
      ],
      [
        "....bbbbbbbb....",
        "..bbbbbbbbbbbb..",
        ".bbbbbbbbbbbbbb.",
        ".bbe.bbbbbb.ebb.",
        ".bbe.bbbbbb.ebb.",
        ".bbbbbbbbbbbbbb.",
        ".bablllllllbab..",
        ".bbllllllllllbb.",
        "..bbbbbbbbbbbb..",
        ".b..b..bb..b..b.",
        ".bb.bb.bb.bb.bb.",
        "..b...b..b...b.."
      ]
    ],
    "type": ["<2-3 frames: tentacle tips alternate up/down quickly>"],
    "panic": ["<2 frames: eyes wide ('e' doubled), tentacles raised>"],
    "celebrate": ["<2-3 frames: body bounces up one row, tentacles spread>"],
    "sleep": ["<2 frames: eyes as single dots, body squashed one row shorter>"],
    "point": ["<2 frames: one side tentacle extended horizontally>"],
    "enter": ["<2 frames: rising from below — bottom rows only, then full>"],
    "exit": ["<2 frames: reverse of enter>"]
  }
}
```

The implementer authors real grids for the bracketed animations following the idle pattern (same 16×12 canvas, same legend). Quality bar: each animation must read at a glance when flipped between frames; verify by eye in Step 6.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m unittest tests.test_mascot_data -v`
Expected: PASS (8 tests)

- [ ] **Step 6: Visual sanity check of the grids**

Run a quick terminal preview (prints each frame with `█` for filled cells):

```bash
python - <<'PY'
import json
m = json.load(open("assets/mascots/octopus.json"))
for name, frames in m["animations"].items():
    print(f"== {name} ==")
    for fr in frames:
        print("\n".join(r.replace(".", " ").replace("b", "█").replace("l", "▒").replace("e", "●").replace("a", "▓") for r in fr))
        print("---")
PY
```

Eyeball each animation; fix grids until they read clearly.

- [ ] **Step 7: Commit**

```bash
git add assets/mascots/octopus.json assets/scripts/mascot_data.py tests/test_mascot_data.py
git commit -m "feat(mascot): pixel-grid data format, validator, octopus roster character"
```

---

### Task 2: `render-mascot.py` — grids → transparent PNG frames

**Files:**
- Create: `assets/scripts/render-mascot.py`
- Test: `tests/test_render_mascot.py`

Pure core `grid_to_rgba()` converts one frame to raw RGBA bytes (nearest-neighbor: each cell becomes `cell_px × scale` square pixels). Glue pipes the bytes to ffmpeg (`-f rawvideo -pix_fmt rgba`) to write PNGs — no Pillow.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_render_mascot.py
import importlib
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "assets", "scripts"))
rm = importlib.import_module("render-mascot")

LEGEND = {".": None, "b": "body"}
PALETTE = {"body": "#ff0000"}


class TestGridToRgba(unittest.TestCase):
    def test_dimensions(self):
        buf, w, h = rm.grid_to_rgba(["b.", ".b"], LEGEND, PALETTE, cell_px=3)
        self.assertEqual((w, h), (6, 6))
        self.assertEqual(len(buf), 6 * 6 * 4)

    def test_filled_cell_is_opaque_color(self):
        buf, w, h = rm.grid_to_rgba(["b"], LEGEND, PALETTE, cell_px=2)
        # every pixel of the 2x2 block is (255, 0, 0, 255)
        for px in range(w * h):
            self.assertEqual(tuple(buf[px * 4:px * 4 + 4]), (255, 0, 0, 255))

    def test_transparent_cell_has_zero_alpha(self):
        buf, w, h = rm.grid_to_rgba(["."], LEGEND, PALETTE, cell_px=1)
        self.assertEqual(buf[3], 0)

    def test_palette_override_wins(self):
        buf, _, _ = rm.grid_to_rgba(["b"], LEGEND, PALETTE, cell_px=1,
                                    overrides={"body": "#00ff00"})
        self.assertEqual(tuple(buf[0:4]), (0, 255, 0, 255))

    def test_hex_to_rgb(self):
        self.assertEqual(rm.hex_to_rgb("#dbaf71"), (219, 175, 113))


class TestTargetHeight(unittest.TestCase):
    def test_scale_pins_output_height(self):
        # 12 rows * cell_px 8 = 96 native px; target_height 144 -> integer factor 1
        # (factor = max(1, round(target / native))); scale multiplies target.
        self.assertEqual(rm.upscale_factor(native_h=96, target_h=140, scale=1.0), 1)
        self.assertEqual(rm.upscale_factor(native_h=96, target_h=280, scale=1.0), 3)
        self.assertEqual(rm.upscale_factor(native_h=96, target_h=140, scale=2.0), 3)


if __name__ == "__main__":
    unittest.main()
```

Note the import trick: the filename has a hyphen (matching sibling scripts like `cut-clip.py`, which tests import via `importlib`) — check `tests/test_cut_clip.py` and copy its exact import mechanism if it differs.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_render_mascot -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement `render-mascot.py`**

```python
# assets/scripts/render-mascot.py
"""render-mascot.py — render mascot.json animations to transparent PNG frames.

  python render-mascot.py <mascot.json> <out_dir> [--target-height 140]

Writes <out_dir>/<anim>/f_%03d.png for every animation. PNGs come out of
ffmpeg (rawvideo RGBA piped in), so there is no Pillow dependency.
grid_to_rgba()/upscale_factor() are the pure, unit-tested core.
"""
import argparse
import os
import subprocess
import sys

from mascot_data import load_mascot, validate_mascot

DEFAULT_TARGET_H = 140  # on-screen mascot height at 1080p, pre-scale


def hex_to_rgb(s):
    return tuple(int(s[i:i + 2], 16) for i in (1, 3, 5))


def grid_to_rgba(frame, legend, palette, cell_px, overrides=None):
    """One pixel-grid frame -> (raw RGBA bytes, width_px, height_px)."""
    colors = dict(palette)
    if overrides:
        colors.update(overrides)
    rows, width = len(frame), len(frame[0])
    w, h = width * cell_px, rows * cell_px
    buf = bytearray(w * h * 4)
    for ry, row in enumerate(frame):
        for cx, ch in enumerate(row):
            slot = legend[ch]
            if slot is None:
                continue
            r, g, b = hex_to_rgb(colors[slot])
            for py in range(ry * cell_px, (ry + 1) * cell_px):
                base = (py * w + cx * cell_px) * 4
                for px in range(cell_px):
                    o = base + px * 4
                    buf[o:o + 4] = bytes((r, g, b, 255))
    return bytes(buf), w, h


def upscale_factor(native_h, target_h, scale):
    """Integer nearest-neighbor factor to hit ~target_h*scale from native_h."""
    return max(1, round((target_h * scale) / native_h))


def render_animation(mascot, anim, frames, out_dir, overrides=None, target_h=DEFAULT_TARGET_H):
    os.makedirs(out_dir, exist_ok=True)
    legend, palette, cell = mascot["legend"], mascot["palette"], mascot["cell_px"]
    native_h = len(frames[0]) * cell
    factor = upscale_factor(native_h, target_h, mascot.get("scale", 1.0))
    first, w, h = grid_to_rgba(frames[0], legend, palette, cell, overrides)
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{w}x{h}",
        "-framerate", str(mascot["fps"]), "-i", "-",
        "-vf", f"scale={w * factor}:{h * factor}:flags=neighbor",
        os.path.join(out_dir, "f_%03d.png"),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    proc.stdin.write(first)
    for frame in frames[1:]:
        buf, _, _ = grid_to_rgba(frame, legend, palette, cell, overrides)
        proc.stdin.write(buf)
    proc.stdin.close()
    if proc.wait() != 0:
        sys.exit(f"render-mascot: ffmpeg failed for animation '{anim}'")
    return len(frames)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mascot_json")
    ap.add_argument("out_dir")
    ap.add_argument("--target-height", type=int, default=DEFAULT_TARGET_H)
    args = ap.parse_args()
    mascot = load_mascot(args.mascot_json)
    validate_mascot(mascot)
    for anim, frames in mascot["animations"].items():
        n = render_animation(mascot, anim, frames,
                             os.path.join(args.out_dir, anim),
                             target_h=args.target_height)
        print(f"  mascot {anim}: {n} frames")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_render_mascot -v`
Expected: PASS

- [ ] **Step 5: Manual smoke render**

```bash
python assets/scripts/render-mascot.py assets/mascots/octopus.json /tmp/mascot-out
ls /tmp/mascot-out/idle/
```

Expected: `f_001.png f_002.png` per animation. Open one PNG — crisp pixels, transparent background.

- [ ] **Step 6: Commit**

```bash
git add assets/scripts/render-mascot.py tests/test_render_mascot.py
git commit -m "feat(mascot): render pixel grids to transparent PNG frames via ffmpeg pipe"
```

---

### Task 3: `plan-scenes.py` — attach `mascot_plan` stub per scene

**Files:**
- Modify: `assets/scripts/plan-scenes.py` (add helper + wire into `resolve_sequence`/`custom_arc`/`main`)
- Test: `tests/test_mascot_plan.py`

Stage-1 of the resolver: defaults by scene type + user overrides, written as `entry["mascot_plan"]`. No timing here — that's Task 5.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_mascot_plan.py
import importlib.util
import os
import sys
import unittest

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "assets", "scripts")
sys.path.insert(0, SCRIPTS)
spec = importlib.util.spec_from_file_location(
    "plan_scenes", os.path.join(SCRIPTS, "plan-scenes.py"))
ps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ps)

CFG = {"character": "octopus", "enabled": True, "position": "bottom-right", "scale": 1.0}


class TestMascotStub(unittest.TestCase):
    def test_disabled_globally(self):
        stub = ps.mascot_stub({"enabled": False}, {"type": "terminal"}, scene_override=None)
        self.assertFalse(stub["enabled"])

    def test_default_emotion_by_type(self):
        self.assertEqual(ps.mascot_stub(CFG, {"type": "terminal"}, None)["emotion"], "type")
        self.assertEqual(ps.mascot_stub(CFG, {"type": "graph"}, None)["emotion"], "idle")
        self.assertEqual(ps.mascot_stub(CFG, {"type": "multi_agent"}, None)["emotion"], "type")
        self.assertEqual(ps.mascot_stub(CFG, {"type": "browser_capture"}, None)["emotion"], "idle")

    def test_endcards_disabled_by_default(self):
        self.assertFalse(ps.mascot_stub(CFG, {"type": "endcards"}, None)["enabled"])

    def test_endcards_can_be_forced_on(self):
        stub = ps.mascot_stub(CFG, {"type": "endcards"}, {"enabled": True})
        self.assertTrue(stub["enabled"])

    def test_scene_override_emotion_and_position(self):
        stub = ps.mascot_stub(CFG, {"type": "browser_capture"},
                              {"emotion": "celebrate", "position": "bottom-left"})
        self.assertEqual(stub["emotion"], "celebrate")
        self.assertEqual(stub["position"], "bottom-left")

    def test_before_after_halves(self):
        stub = ps.mascot_stub(CFG, {"type": "before_after", "layout": "sequential"}, None)
        self.assertEqual(stub["before"], "panic")
        self.assertEqual(stub["after"], "celebrate")

    def test_before_after_side_by_side_single_emotion(self):
        stub = ps.mascot_stub(CFG, {"type": "before_after", "layout": "side_by_side"}, None)
        self.assertEqual(stub["emotion"], "point")
        self.assertNotIn("before", stub)

    def test_scene_override_disable(self):
        stub = ps.mascot_stub(CFG, {"type": "terminal"}, {"enabled": False})
        self.assertFalse(stub["enabled"])

    def test_no_mascot_config_means_disabled(self):
        stub = ps.mascot_stub({}, {"type": "terminal"}, None)
        self.assertFalse(stub["enabled"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_mascot_plan -v`
Expected: FAIL — `AttributeError: module 'plan_scenes' has no attribute 'mascot_stub'`

- [ ] **Step 3: Implement `mascot_stub()` in `plan-scenes.py`**

Add after `resolve_source()` (around line 41):

```python
# Default whole-scene emotion per scene type (stage-1; exact timing is resolved
# at build time by resolve-mascot-timeline.py against the real clip).
MASCOT_TYPE_DEFAULTS = {
    "terminal": "type",
    "multi_agent": "type",
    "graph": "idle",
    "browser_capture": "idle",
    "html_mockup": "idle",
    "screen_recording": "idle",
}


def mascot_stub(mascot_cfg, entry, scene_override):
    """Stage-1 mascot resolution: defaults + overrides, no timing.
    mascot_cfg is config.json's `mascot` block; scene_override is the scene's
    `mascot:` dict (or None). Returns the mascot_plan stub for this entry."""
    ov = scene_override or {}
    enabled = bool(mascot_cfg.get("enabled", bool(mascot_cfg)))
    if entry.get("type") == "endcards" and "enabled" not in ov:
        enabled = False  # off by default on endcards (spec)
    if "enabled" in ov:
        enabled = bool(ov["enabled"])
    stub = {
        "enabled": enabled,
        "character": mascot_cfg.get("character", "octopus"),
        "position": ov.get("position", mascot_cfg.get("position", "bottom-right")),
        "scale": mascot_cfg.get("scale", 1.0),
    }
    if not enabled:
        return stub
    t = entry.get("type")
    if t == "before_after" and entry.get("layout", "sequential") == "sequential":
        stub["before"] = ov.get("before", "panic")
        stub["after"] = ov.get("after", "celebrate")
    elif t == "before_after":  # side_by_side: one emotion, no half split (spec)
        stub["emotion"] = ov.get("emotion", "point")
    else:
        stub["emotion"] = ov.get("emotion", MASCOT_TYPE_DEFAULTS.get(t, "idle"))
    return stub
```

Wire it in `main()` after the plan is resolved (before the `json.dump`):

```python
    mascot_cfg = cfg.get("mascot", {})
    overrides_by_id = {}
    # custom scenes carry their own `mascot:` dict; resolve_sequence/custom_arc
    # don't see config, so map overrides from the original sequence items here.
    seq = scenes.get("sequence") or scenes.get("custom_scenes") or []
    for entry in plan:
        ov = entry.pop("_mascot_override", None)
        entry["mascot_plan"] = mascot_stub(mascot_cfg, entry, ov)
```

And in `custom_arc()`, right before `plan.append(entry)`:

```python
        if sc.get("mascot") is not None:
            entry["_mascot_override"] = sc["mascot"]
```

(Built-in string scenes have no per-scene override — only the global config applies; that's fine for v1.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_mascot_plan -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Run the full suite to catch regressions**

Run: `python -m unittest discover -s tests`
Expected: all pass (existing plan/cache tests unaffected)

- [ ] **Step 6: Commit**

```bash
git add assets/scripts/plan-scenes.py tests/test_mascot_plan.py
git commit -m "feat(mascot): stage-1 mascot_plan stub in scene planning"
```

---### Task 4: `scene_cache.py` v2 — capture key ignores mascot; overlay layer added

**Files:**
- Modify: `assets/scripts/scene_cache.py`
- Test: `tests/test_scene_cache.py` (extend)

Two-layer cache per spec §5b. Capture key = today's key but with `mascot_plan` stripped (mascot changes must NOT re-record). Overlay key = capture clip content + mascot.json content + resolved timeline JSON. Bump VERSION to "2" (recorder output semantics change: pristine copy).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_scene_cache.py`, following its existing import pattern)

```python
class TestMascotCacheLayers(unittest.TestCase):
    def test_capture_key_ignores_mascot_plan(self):
        entry = {"id": "s1", "type": "terminal", "mp4": "a.mp4", "tape": None}
        with_mascot = dict(entry, mascot_plan={"enabled": True, "emotion": "type"})
        self.assertEqual(scene_cache.cache_key(entry), scene_cache.cache_key(with_mascot))

    def test_capture_key_still_sensitive_to_entry(self):
        a = {"id": "s1", "type": "terminal", "mp4": "a.mp4"}
        b = {"id": "s1", "type": "terminal", "mp4": "b.mp4"}
        self.assertNotEqual(scene_cache.cache_key(a), scene_cache.cache_key(b))

    def test_overlay_key_changes_with_timeline(self):
        import tempfile, os, json
        with tempfile.TemporaryDirectory() as d:
            clip = os.path.join(d, "c.mp4")
            mascot = os.path.join(d, "m.json")
            open(clip, "wb").write(b"fakevideo")
            open(mascot, "w").write('{"name":"octopus"}')
            t1 = [{"at": 0, "until": 5, "emotion": "idle"}]
            t2 = [{"at": 0, "until": 5, "emotion": "panic"}]
            k1 = scene_cache.overlay_key(clip, mascot, t1)
            k2 = scene_cache.overlay_key(clip, mascot, t2)
            self.assertNotEqual(k1, k2)

    def test_overlay_key_changes_with_clip_content(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            clip = os.path.join(d, "c.mp4")
            mascot = os.path.join(d, "m.json")
            open(mascot, "w").write("{}")
            t = [{"at": 0, "until": 5, "emotion": "idle"}]
            open(clip, "wb").write(b"v1")
            k1 = scene_cache.overlay_key(clip, mascot, t)
            open(clip, "wb").write(b"v2")
            self.assertNotEqual(k1, scene_cache.overlay_key(clip, mascot, t))

    def test_version_bumped(self):
        self.assertEqual(scene_cache.VERSION, "2")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_scene_cache -v`
Expected: new tests FAIL (no `overlay_key`, VERSION is "1", capture key differs with mascot_plan)

- [ ] **Step 3: Implement in `scene_cache.py`**

Change `VERSION = "1"` → `VERSION = "2"`. In `cache_key()`, strip the mascot stub before hashing:

```python
def cache_key(entry, dep_files=()):
    """Deterministic sha256 over the plan entry + dependent file contents + VERSION.
    mascot_plan is excluded: mascot changes re-OVERLAY (overlay_key), never re-record."""
    entry = {k: v for k, v in entry.items() if k != "mascot_plan"}
    h = hashlib.sha256()
    ...  # rest unchanged
```

Add after `is_fresh()`:

```python
def overlay_key(capture_path, mascot_json_path, timeline):
    """Cache key for the overlay layer: pristine capture content + mascot data +
    resolved timeline. Any of the three changing re-composites; none re-records."""
    h = hashlib.sha256()
    h.update(("overlay-cache-v" + VERSION).encode())
    for p in (capture_path, mascot_json_path):
        try:
            with open(p, "rb") as f:
                h.update(f.read())
        except FileNotFoundError:
            h.update(b"\x00MISSING:" + os.path.basename(p).encode())
    h.update(json.dumps(timeline, sort_keys=True).encode())
    return h.hexdigest()
```

Add CLI subcommands so bash can use it (extend `main()`):

```python
    # overlay-check <clip> <capture> <mascot.json> <timeline.json>  -> 0 fresh / 1 stale
    # overlay-save  <clip> <capture> <mascot.json> <timeline.json>
    if argv[1] in ("overlay-check", "overlay-save"):
        clip, capture, mascot, tl_path = argv[2:6]
        with open(tl_path, encoding="utf-8") as f:
            timeline = json.load(f)
        key = overlay_key(capture, mascot, timeline)
        sha = clip + ".overlay.sha"
        if argv[1] == "overlay-check":
            return 0 if is_fresh(clip, sha, key) else 1
        with open(sha, "w", encoding="utf-8", newline="\n") as f:
            f.write(key + "\n")
        return 0
```

(Adjust the usage/arg-count guard at the top of `main()` accordingly: 4 args for check/save, 6 for overlay-check/overlay-save.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_scene_cache -v`
Expected: PASS, including pre-existing tests

- [ ] **Step 5: Commit**

```bash
git add assets/scripts/scene_cache.py tests/test_scene_cache.py
git commit -m "feat(mascot): two-layer scene cache - capture vs overlay, VERSION 2"
```

---

### Task 5: `resolve-mascot-timeline.py` — stage-2 exact timeline

**Files:**
- Create: `assets/scripts/resolve-mascot-timeline.py`
- Test: `tests/test_mascot_timeline.py`

Pure core `resolve_timeline(stub, duration, events=None, layout=None, half_duration=None)` → ordered, non-overlapping `[{at, until, emotion}]` covering `[0, duration]`. Glue reads the stub from `scene-plan.json`, the events sidecar if present, ffprobes the final clip, writes `<clip>.mascot.json`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_mascot_timeline.py
import importlib.util
import os
import sys
import unittest

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "assets", "scripts")
sys.path.insert(0, SCRIPTS)
spec = importlib.util.spec_from_file_location(
    "resolve_mascot_timeline", os.path.join(SCRIPTS, "resolve-mascot-timeline.py"))
rt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rt)

STUB = {"enabled": True, "emotion": "idle", "position": "bottom-right", "scale": 1.0}


def cover(tl, duration):
    """Assert segments are ordered, non-overlapping, and cover [0, duration]."""
    assert tl[0]["at"] == 0
    for a, b in zip(tl, tl[1:]):
        assert abs(a["until"] - b["at"]) < 1e-6
    assert abs(tl[-1]["until"] - duration) < 1e-6


class TestWholeScene(unittest.TestCase):
    def test_single_emotion_fills_scene(self):
        tl = rt.resolve_timeline(STUB, duration=10.0)
        cover(tl, 10.0)
        self.assertEqual([s["emotion"] for s in tl], ["idle"])

    def test_disabled_returns_empty(self):
        tl = rt.resolve_timeline({"enabled": False}, duration=10.0)
        self.assertEqual(tl, [])


class TestBeforeAfter(unittest.TestCase):
    def test_sequential_halves_split_at_midpoint(self):
        stub = dict(STUB, before="panic", after="celebrate")
        stub.pop("emotion")
        tl = rt.resolve_timeline(stub, duration=16.0, layout="sequential")
        cover(tl, 16.0)
        self.assertEqual(tl[0], {"at": 0.0, "until": 8.0, "emotion": "panic"})
        self.assertEqual(tl[1], {"at": 8.0, "until": 16.0, "emotion": "celebrate"})

    def test_half_duration_pins_the_split(self):
        stub = dict(STUB, before="panic", after="celebrate")
        stub.pop("emotion")
        tl = rt.resolve_timeline(stub, duration=14.0, layout="sequential",
                                 half_duration=6.0)
        self.assertEqual(tl[0]["until"], 6.0)
        cover(tl, 14.0)


class TestEvents(unittest.TestCase):
    def test_error_toast_window_becomes_panic(self):
        events = [{"kind": "waitToast", "text": "Error: save failed",
                   "at": 3.0, "until": 5.5}]
        tl = rt.resolve_timeline(STUB, duration=10.0, events=events)
        cover(tl, 10.0)
        self.assertEqual([s["emotion"] for s in tl], ["idle", "panic", "idle"])
        self.assertEqual(tl[1]["at"], 3.0)
        self.assertEqual(tl[1]["until"], 5.5)

    def test_benign_toast_becomes_point(self):
        events = [{"kind": "waitToast", "text": "Saved successfully",
                   "at": 3.0, "until": 5.0}]
        tl = rt.resolve_timeline(STUB, duration=10.0, events=events)
        self.assertEqual(tl[1]["emotion"], "point")

    def test_speed_ramp_becomes_sleep(self):
        events = [{"kind": "speed", "at": 2.0, "until": 6.0}]
        tl = rt.resolve_timeline(STUB, duration=10.0, events=events)
        self.assertEqual([s["emotion"] for s in tl], ["idle", "sleep", "idle"])

    def test_events_beyond_duration_are_clamped(self):
        events = [{"kind": "waitToast", "text": "error", "at": 8.0, "until": 14.0}]
        tl = rt.resolve_timeline(STUB, duration=10.0, events=events)
        cover(tl, 10.0)
        self.assertEqual(tl[-1]["emotion"], "panic")
        self.assertEqual(tl[-1]["until"], 10.0)


class TestToastSeverity(unittest.TestCase):
    def test_severity_regex(self):
        for text in ("Error: x", "request FAILED", "invalid token", "access denied"):
            self.assertEqual(rt.toast_emotion(text), "panic")
        self.assertEqual(rt.toast_emotion("3 items copied"), "point")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_mascot_timeline -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement `resolve-mascot-timeline.py`**

```python
# assets/scripts/resolve-mascot-timeline.py
"""resolve-mascot-timeline.py — stage-2 mascot emotion timeline (spec §4).

Merges the stage-1 mascot_plan stub with post-capture truth: the final
normalized clip duration (ffprobe) and the capture's .events.json windows
(waitToast / speed). Writes <clip>.mascot.json for overlay-mascot.py.

  python resolve-mascot-timeline.py <scene-plan.json> <scene-id>

resolve_timeline()/toast_emotion() are the pure, unit-tested core.
"""
import json
import os
import re
import subprocess
import sys

ERROR_TOAST = re.compile(r"error|fail|invalid|denied", re.IGNORECASE)


def toast_emotion(text):
    return "panic" if ERROR_TOAST.search(text or "") else "point"


def _fill(timeline, base_emotion, duration):
    """Sort event segments, clamp to [0, duration], fill gaps with base_emotion."""
    segs = sorted((s for s in timeline if s["at"] < duration), key=lambda s: s["at"])
    out, cursor = [], 0.0
    for s in segs:
        at, until = max(0.0, s["at"]), min(duration, s["until"])
        if until <= cursor:
            continue
        at = max(at, cursor)
        if at > cursor:
            out.append({"at": cursor, "until": at, "emotion": base_emotion})
        out.append({"at": at, "until": until, "emotion": s["emotion"]})
        cursor = until
    if cursor < duration:
        out.append({"at": cursor, "until": duration, "emotion": base_emotion})
    return out


def resolve_timeline(stub, duration, events=None, layout=None, half_duration=None):
    if not stub.get("enabled"):
        return []
    # before_after sequential: two halves, no event merge (the halves were
    # composed from separately-captured clips; their events don't map 1:1).
    if "before" in stub:
        split = min(half_duration, duration) if half_duration else duration / 2.0
        return [
            {"at": 0.0, "until": split, "emotion": stub["before"]},
            {"at": split, "until": duration, "emotion": stub["after"]},
        ]
    base = stub.get("emotion", "idle")
    windows = []
    for ev in events or []:
        if ev.get("until") is None or ev.get("at") is None:
            continue
        if ev.get("kind") == "waitToast":
            windows.append({"at": ev["at"], "until": ev["until"],
                            "emotion": toast_emotion(ev.get("text"))})
        elif ev.get("kind") == "speed":
            windows.append({"at": ev["at"], "until": ev["until"], "emotion": "sleep"})
    return _fill(windows, base, duration)


def _probe_duration(path):
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path])
    return float(out.decode().strip())


def main(argv):
    if len(argv) != 3:
        sys.exit("usage: python resolve-mascot-timeline.py <scene-plan.json> <id>")
    plan_path, sid = argv[1], argv[2]
    with open(plan_path, encoding="utf-8") as f:
        entry = next((s for s in json.load(f)["scenes"] if s["id"] == sid), None)
    if entry is None:
        sys.exit(f"no scene '{sid}' in {plan_path}")
    stub = entry.get("mascot_plan", {"enabled": False})
    clip = entry["mp4"]
    duration = _probe_duration(clip)
    events = None
    events_path = clip + ".events.json"   # written by record-browser.mjs
    if os.path.exists(events_path):
        with open(events_path, encoding="utf-8") as f:
            events = json.load(f)
    tl = resolve_timeline(stub, duration, events=events,
                          layout=entry.get("layout"),
                          half_duration=entry.get("half_duration"))
    out = clip + ".mascot.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"stub": stub, "duration": duration, "timeline": tl}, f, indent=2)
    print(f"  mascot timeline {sid}: {len(tl)} segments -> {out}")


if __name__ == "__main__":
    main(sys.argv)
```

**Verify the events sidecar contract before relying on it:** open `assets/scripts/record-browser.mjs` and confirm the actual filename + shape of the events file it writes (the spec calls it `<output>.events.json` with waitToast/speed windows; if the real keys differ — e.g. `type` instead of `kind`, ms instead of seconds — adapt the `kind`/`at`/`until` reads in `main()` (NOT the pure core or its tests) and convert units at the boundary. If record-browser.mjs does not yet write an events sidecar at all, add a small JSON dump there of `{kind, text, at, until}` per waitToast/speed action with timestamps relative to the trimmed clip start, in seconds.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_mascot_timeline -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add assets/scripts/resolve-mascot-timeline.py tests/test_mascot_timeline.py
git commit -m "feat(mascot): stage-2 timeline resolver from clip duration + capture events"
```

---

### Task 6: `overlay-mascot.py` — composite the mascot onto a clip

**Files:**
- Create: `assets/scripts/overlay-mascot.py`
- Test: `tests/test_overlay_mascot.py`

Pure core `build_overlay_cmd()` produces the full ffmpeg argv from (capture path, frames dir, timeline, position, video size, fps, speedup). One looped image-sequence input per distinct emotion in the timeline; each segment is an `overlay ... enable='between(t,A,B)'` link in the filter graph. Position honors `caption_clearance_px` (default 200, spec §5).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_overlay_mascot.py
import importlib.util
import os
import sys
import unittest

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "assets", "scripts")
sys.path.insert(0, SCRIPTS)
spec = importlib.util.spec_from_file_location(
    "overlay_mascot", os.path.join(SCRIPTS, "overlay-mascot.py"))
om = importlib.util.module_from_spec(spec)
spec.loader.exec_module(om)

TL = [
    {"at": 0.0, "until": 4.0, "emotion": "idle"},
    {"at": 4.0, "until": 6.0, "emotion": "panic"},
    {"at": 6.0, "until": 10.0, "emotion": "idle"},
]


class TestPosition(unittest.TestCase):
    def test_bottom_right_clears_captions(self):
        x, y = om.anchor_xy("bottom-right", video_w=1920, video_h=1080,
                            sprite_w=160, sprite_h=140)
        self.assertEqual(x, 1920 - 160 - om.MARGIN_PX)
        self.assertEqual(y, 1080 - 140 - om.CAPTION_CLEARANCE_PX)

    def test_bottom_left(self):
        x, y = om.anchor_xy("bottom-left", 1920, 1080, 160, 140)
        self.assertEqual(x, om.MARGIN_PX)

    def test_top_right(self):
        x, y = om.anchor_xy("top-right", 1920, 1080, 160, 140)
        self.assertEqual(y, om.MARGIN_PX)


class TestCmd(unittest.TestCase):
    def test_one_input_per_distinct_emotion(self):
        cmd = om.build_overlay_cmd("in.mp4", "out.mp4", "mascot", TL,
                                   pos=(1700, 740), fps=7, speedup=1.0)
        # inputs: in.mp4 + idle + panic (idle reused, not duplicated)
        self.assertEqual(cmd.count("-i"), 3)
        joined = " ".join(cmd)
        self.assertIn("mascot/idle/f_%03d.png", joined)
        self.assertIn("mascot/panic/f_%03d.png", joined)

    def test_enable_windows_match_timeline(self):
        cmd = om.build_overlay_cmd("in.mp4", "out.mp4", "mascot", TL,
                                   pos=(1700, 740), fps=7, speedup=1.0)
        fc = cmd[cmd.index("-filter_complex") + 1]
        self.assertIn("between(t,0.000,4.000)", fc)
        self.assertIn("between(t,4.000,6.000)", fc)
        self.assertIn("between(t,6.000,10.000)", fc)

    def test_speedup_compensates_fps(self):
        # spec §5: animation fps is bumped by the scene's effective speedup so
        # assemble.sh's setpts doesn't slow the pixel animation on screen.
        cmd = om.build_overlay_cmd("in.mp4", "out.mp4", "mascot", TL,
                                   pos=(0, 0), fps=7, speedup=1.4)
        joined = " ".join(cmd)
        self.assertIn("-framerate 9.8", joined)

    def test_empty_timeline_returns_none(self):
        self.assertIsNone(om.build_overlay_cmd("in.mp4", "out.mp4", "mascot", [],
                                               pos=(0, 0), fps=7, speedup=1.0))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_overlay_mascot -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement `overlay-mascot.py`**

```python
# assets/scripts/overlay-mascot.py
"""overlay-mascot.py — composite the rendered mascot onto a finished scene clip.

  python overlay-mascot.py <capture.mp4> <out.mp4> <frames_dir> <timeline.json> [--speedup 1.2]

Runs AFTER cut-clip + normalize (spec §5): the timeline targets the final clip.
One looped PNG-sequence input per distinct emotion; each timeline segment is an
overlay with enable='between(t,A,B)'. anchor_xy()/build_overlay_cmd() are the
pure, unit-tested core.
"""
import argparse
import json
import os
import subprocess
import sys

MARGIN_PX = 24                # side margin from the frame edge
CAPTION_CLEARANCE_PX = 200    # lift above the burned caption band (spec §5)


def anchor_xy(position, video_w, video_h, sprite_w, sprite_h):
    horiz = "right" if position.endswith("right") else "left"
    vert = "top" if position.startswith("top") else "bottom"
    x = video_w - sprite_w - MARGIN_PX if horiz == "right" else MARGIN_PX
    y = MARGIN_PX if vert == "top" else video_h - sprite_h - CAPTION_CLEARANCE_PX
    return x, y


def build_overlay_cmd(capture, out, frames_dir, timeline, pos, fps, speedup):
    """Full ffmpeg argv, or None when there is nothing to overlay."""
    if not timeline:
        return None
    emotions = []
    for seg in timeline:
        if seg["emotion"] not in emotions:
            emotions.append(seg["emotion"])
    eff_fps = round(fps * speedup, 4)
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", capture]
    for emo in emotions:
        cmd += ["-stream_loop", "-1", "-framerate", str(eff_fps),
                "-i", os.path.join(frames_dir, emo, "f_%03d.png").replace("\\", "/")]
    x, y = pos
    parts, src = [], "[0:v]"
    for i, seg in enumerate(timeline):
        inp = emotions.index(seg["emotion"]) + 1
        label = f"[v{i}]" if i < len(timeline) - 1 else "[vout]"
        parts.append(
            f"{src}[{inp}:v]overlay={x}:{y}:"
            f"enable='between(t,{seg['at']:.3f},{seg['until']:.3f})'{label}")
        src = f"[v{i}]"
    cmd += ["-filter_complex", ";".join(parts), "-map", "[vout]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "slow", "-crf", "18",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            "-c:a", "copy", out]
    return cmd


def _probe_wh(path):
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "csv=p=0", path])
    w, h = out.decode().strip().split(",")
    return int(w), int(h)


def _sprite_wh(frames_dir, emotion):
    first = os.path.join(frames_dir, emotion, "f_001.png")
    return _probe_wh(first)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("capture")
    ap.add_argument("out")
    ap.add_argument("frames_dir")
    ap.add_argument("timeline_json")
    ap.add_argument("--speedup", type=float, default=1.0)
    args = ap.parse_args()
    with open(args.timeline_json, encoding="utf-8") as f:
        data = json.load(f)
    tl, stub = data["timeline"], data["stub"]
    if not tl:
        sys.exit(0)  # nothing to do; caller handles the copy
    vw, vh = _probe_wh(args.capture)
    sw, sh = _sprite_wh(args.frames_dir, tl[0]["emotion"])
    pos = anchor_xy(stub.get("position", "bottom-right"), vw, vh, sw, sh)
    with open(os.path.join(os.path.dirname(args.frames_dir) or ".", "mascot-meta.json"),
              encoding="utf-8") as f:
        fps = json.load(f)["fps"]
    cmd = build_overlay_cmd(args.capture, args.out, args.frames_dir, tl,
                            pos, fps, args.speedup)
    subprocess.check_call(cmd)
    print(f"  mascot overlaid -> {args.out}")


if __name__ == "__main__":
    main()
```

Also make `render-mascot.py` write `mascot-meta.json` inside the frames dir (in `main()`, after the render loop):

```python
    with open(os.path.join(args.out_dir, "mascot-meta.json"), "w",
              encoding="utf-8") as f:
        json.dump({"fps": mascot["fps"], "name": mascot["name"]}, f)
```

…and in `overlay-mascot.py`'s `main()`, read the fps from `os.path.join(args.frames_dir, "mascot-meta.json")` (replace the `os.path.dirname(...)` open shown above with that path).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_overlay_mascot -v`
Expected: PASS

- [ ] **Step 5: Manual smoke test on a real clip**

```bash
python assets/scripts/render-mascot.py assets/mascots/octopus.json /tmp/mascot
ffmpeg -y -f lavfi -i "color=c=0x223344:s=1920x1080:d=10" -c:v libx264 -pix_fmt yuv420p /tmp/base.mp4
cat > /tmp/tl.json <<'EOF'
{"stub": {"enabled": true, "position": "bottom-right"},
 "duration": 10.0,
 "timeline": [{"at": 0, "until": 4, "emotion": "idle"},
              {"at": 4, "until": 7, "emotion": "panic"},
              {"at": 7, "until": 10, "emotion": "celebrate"}]}
EOF
python assets/scripts/overlay-mascot.py /tmp/base.mp4 /tmp/out.mp4 /tmp/mascot /tmp/tl.json
```

Open `/tmp/out.mp4`: octopus idles bottom-right, panics at 4s, celebrates at 7s, sits 200px above the bottom edge.

- [ ] **Step 6: Commit**

```bash
git add assets/scripts/overlay-mascot.py assets/scripts/render-mascot.py tests/test_overlay_mascot.py
git commit -m "feat(mascot): ffmpeg overlay compositor with emotion enable windows"
```

---

### Task 7: `build-scenes.sh` integration — capture phase + overlay phase

**Files:**
- Modify: `assets/scripts/build-scenes.sh`

Flow per scene (spec §5b): capture (cached) → normalize → save pristine `<mp4>.capture.mp4` → resolve timeline → overlay (cached) → final `<mp4>`. The pristine copy is what re-overlays consume on capture-cache hits.

- [ ] **Step 1: Restructure the loop**

Replace the cache-hit `continue` (lines 35–42) and add an overlay phase after the duration-normalize block (line 96–99). The full new tail of the loop body:

```bash
  # P0-2 capture layer: reuse the pristine capture when nothing affecting it changed.
  captured_fresh=1
  if [ "$type" != "screen_recording" ] && [ "$force" = "0" ] \
     && [ -f "$mp4.capture.mp4" ] \
     && python scene_cache.py check "$PLAN" "$id" 2>/dev/null; then
    echo "  -> capture cached (unchanged), skipping recording"
    captured_fresh=0
  fi

  if [ "$captured_fresh" = "1" ]; then
    case "$type" in
      ... # existing case body, UNCHANGED
    esac

    # P0-3: pin the clip to an explicit duration when the scene declares one.
    dur=$(echo "$extra" | python -c "import json,sys;d=json.load(sys.stdin).get('duration');print(d if d is not None else '')")
    if [ -n "$dur" ]; then
      python normalize-clip.py "$mp4" "$dur"
    fi

    # Preserve the pristine (pre-mascot) clip; the overlay layer reads from it.
    [ "$type" != "screen_recording" ] && cp "$mp4" "$mp4.capture.mp4"
    [ "$type" != "screen_recording" ] && python scene_cache.py save "$PLAN" "$id"
  fi

  # Mascot overlay layer (spec §5/5b): runs on the FINAL normalized clip.
  enabled=$(echo "$extra" | python -c "import json,sys;print(1 if json.load(sys.stdin).get('mascot_plan',{}).get('enabled') else 0)")
  if [ "$enabled" = "1" ] && [ -d mascot ]; then
    src="$mp4"; [ -f "$mp4.capture.mp4" ] && src="$mp4.capture.mp4"
    python resolve-mascot-timeline.py "$PLAN" "$id"   # probes $mp4 — see note below
    if [ "$force" = "0" ] \
       && python scene_cache.py overlay-check "$mp4" "$src" mascot.json "$src.mascot.json" 2>/dev/null; then
      echo "  -> overlay cached"
    else
      python overlay-mascot.py "$src" "$mp4.tmp.mp4" mascot "$src.mascot.json" --speedup "${DEMO_SPEEDUP:-1.0}"
      if [ -f "$mp4.tmp.mp4" ]; then mv -f "$mp4.tmp.mp4" "$mp4"; fi
      python scene_cache.py overlay-save "$mp4" "$src" mascot.json "$src.mascot.json"
    fi
  elif [ -f "$mp4.capture.mp4" ]; then
    cp "$mp4.capture.mp4" "$mp4"   # mascot disabled for this scene: ship pristine
  fi
```

Three wiring details the implementer must apply while editing:
1. `resolve-mascot-timeline.py` probes `entry["mp4"]` — but on a fresh overlay run `$mp4` may already hold last build's overlaid clip. Change `main()` in `resolve-mascot-timeline.py` to probe the pristine path when it exists: `clip = entry["mp4"]; probe_src = clip + ".capture.mp4" if os.path.exists(clip + ".capture.mp4") else clip`, and write the sidecar next to `probe_src` (matching what build-scenes.sh passes). Add this to the Task 5 file now if not already done.
2. `DEMO_SPEEDUP` must be exported by `build.sh` from `config.json`'s `scenes.speedup` (add `export DEMO_SPEEDUP=$(python -c "import json;print(json.load(open('config.json')).get('scenes',{}).get('speedup',1.0))")` next to the other env exports in `build.sh` — locate them with `grep -n "export DEMO" assets/scripts/build.sh`).
3. `mascot` dir + `mascot.json` live in `.build/` — produced in Task 8.

- [ ] **Step 2: Shellcheck / dry parse**

Run: `bash -n assets/scripts/build-scenes.sh`
Expected: no syntax errors

- [ ] **Step 3: Run the full unit suite**

Run: `python -m unittest discover -s tests`
Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add assets/scripts/build-scenes.sh assets/scripts/build.sh assets/scripts/resolve-mascot-timeline.py
git commit -m "feat(mascot): wire capture/overlay phases into scene building"
```

---

### Task 8: Config plumbing — `apply-brand.py`, `build.sh`, example config

**Files:**
- Modify: `assets/scripts/apply-brand.py:320-330` (config dict)
- Modify: `assets/scripts/build.sh:57` (script copy list) + mascot render step
- Modify: `assets/brand.example.yaml` (document the mascot block)

- [ ] **Step 1: Pass `mascot` through to config.json**

In `apply-brand.py`, add to the `config = {...}` dict (line ~329):

```python
        "mascot": brand.get("mascot", {}),  # mascot overlay (spec 2026-06-12)
```

- [ ] **Step 2: Copy new scripts + mascot data in `build.sh`**

Extend the `cp` list on line 57 with: `mascot_data.py,render-mascot.py,resolve-mascot-timeline.py,overlay-mascot.py`.

After the copy block, add the mascot prepare step (only when configured):

```bash
# Mascot: resolve mascot.json (next to brand.yaml) and render sprite frames.
MASCOT_ENABLED=$(python -c "import json;m=json.load(open('$BUILD/config.json')).get('mascot',{});print(1 if m.get('enabled', bool(m)) else 0)")
if [ "$MASCOT_ENABLED" = "1" ]; then
  if [ -f "$ROOT/mascot.json" ]; then
    cp "$ROOT/mascot.json" "$BUILD/mascot.json"
  else
    CHAR=$(python -c "import json;print(json.load(open('$BUILD/config.json')).get('mascot',{}).get('character','octopus'))")
    cp "$SKILL_ASSETS/mascots/$CHAR.json" "$BUILD/mascot.json" 2>/dev/null \
      || { echo "WARNING: mascot character '$CHAR' not found and no mascot.json - building mascot-less"; }
  fi
  if [ -f "$BUILD/mascot.json" ]; then
    python "$BUILD/render-mascot.py" "$BUILD/mascot.json" "$BUILD/mascot" \
      || { echo "WARNING: mascot render failed - building mascot-less"; rm -rf "$BUILD/mascot"; }
  fi
fi
```

Check how `build.sh` defines `$SKILL_SCRIPTS` (`grep -n "SKILL_SCRIPTS=" assets/scripts/build.sh`) and define `SKILL_ASSETS` the same way one level up (`SKILL_ASSETS="$(dirname "$SKILL_SCRIPTS")"` if scripts is `assets/scripts`, plus `/mascots`). The warning-not-fail behavior implements the spec's "never block a build" rule.

- [ ] **Step 3: Document in `assets/brand.example.yaml`**

Add a commented block:

```yaml
# Pixel mascot overlay (optional). A pixel-art character reacts to each scene:
# idles, types along, panics at error toasts, celebrates the AFTER reveal.
# mascot:
#   character: octopus      # roster character (or ship your own mascot.json next to brand.yaml)
#   enabled: true
#   position: bottom-right  # bottom-left | top-right | top-left
#   scale: 1.0
# Per-scene override inside scenes.sequence items:
#   - type: before_after
#     mascot: { before: panic, after: celebrate }
#   - type: browser_capture
#     mascot: { enabled: false }
```

- [ ] **Step 4: Run the full suite + bash parse**

Run: `python -m unittest discover -s tests && bash -n assets/scripts/build.sh`
Expected: all pass, no syntax errors

- [ ] **Step 5: Commit**

```bash
git add assets/scripts/apply-brand.py assets/scripts/build.sh assets/brand.example.yaml
git commit -m "feat(mascot): config plumbing - brand.yaml mascot block through to build"
```

---

### Task 9: `mascot_brand.py` — brand palette remap + contrast guard

**Files:**
- Create: `assets/scripts/mascot_brand.py`
- Test: `tests/test_mascot_brand.py`

Init-time helper the agent calls when personalizing: remap mascot palette slots to brand colors with a WCAG ≥3:1 contrast guard against `palette.bg` (spec §2). Pure functions only — the agent does the creative choices; this guarantees legibility.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_mascot_brand.py
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "assets", "scripts"))
from mascot_brand import contrast_ratio, ensure_contrast, remap_palette  # noqa: E402


class TestContrast(unittest.TestCase):
    def test_black_on_white_is_21(self):
        self.assertAlmostEqual(contrast_ratio("#000000", "#ffffff"), 21.0, places=1)

    def test_same_color_is_1(self):
        self.assertAlmostEqual(contrast_ratio("#808080", "#808080"), 1.0, places=2)

    def test_ensure_contrast_passes_through_good_color(self):
        # brass on near-black easily exceeds 3:1
        self.assertEqual(ensure_contrast("#dbaf71", "#0a0705", minimum=3.0), "#dbaf71")

    def test_ensure_contrast_lightens_failing_color_on_dark_bg(self):
        fixed = ensure_contrast("#1a120d", "#0a0705", minimum=3.0)
        self.assertNotEqual(fixed, "#1a120d")
        self.assertGreaterEqual(contrast_ratio(fixed, "#0a0705"), 3.0)

    def test_ensure_contrast_darkens_failing_color_on_light_bg(self):
        fixed = ensure_contrast("#f2ead9", "#fdf8ef", minimum=3.0)
        self.assertGreaterEqual(contrast_ratio(fixed, "#fdf8ef"), 3.0)


class TestRemap(unittest.TestCase):
    def test_remap_applies_mapping_and_guards_body_eyes(self):
        palette = {"body": "#d97757", "eyes": "#141414", "belly": "#e8a087", "accent": "#b35a3e"}
        out = remap_palette(palette, {"body": "#11100f"}, bg="#0a0705")
        self.assertGreaterEqual(contrast_ratio(out["body"], "#0a0705"), 3.0)
        self.assertEqual(out["belly"], "#e8a087")  # unmapped slots untouched


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_mascot_brand -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement `mascot_brand.py`**

```python
# assets/scripts/mascot_brand.py
"""mascot_brand.py — brand-remap helpers for mascot personalization (spec §2).

The agent maps palette slots to brand colors at init; these helpers guarantee
the result stays legible: body and eyes must hit >=3:1 WCAG contrast against
the scene background, else the color is stepped lighter/darker until it does.
"""

GUARDED_SLOTS = ("body", "eyes")
MIN_CONTRAST = 3.0


def _rgb(hex_color):
    return tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5))


def _hex(rgb):
    return "#%02x%02x%02x" % rgb


def _rel_luminance(hex_color):
    def chan(c):
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (chan(v) for v in _rgb(hex_color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a, b):
    la, lb = sorted((_rel_luminance(a), _rel_luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def ensure_contrast(color, bg, minimum=MIN_CONTRAST, step=12):
    """Step `color` toward white (dark bg) or black (light bg) until it clears
    `minimum` contrast against `bg`. Returns the original color when it passes."""
    if contrast_ratio(color, bg) >= minimum:
        return color
    toward_white = _rel_luminance(bg) < 0.5
    r, g, b = _rgb(color)
    for _ in range(30):
        if toward_white:
            r, g, b = min(255, r + step), min(255, g + step), min(255, b + step)
        else:
            r, g, b = max(0, r - step), max(0, g - step), max(0, b - step)
        candidate = _hex((r, g, b))
        if contrast_ratio(candidate, bg) >= minimum:
            return candidate
    return "#ffffff" if toward_white else "#000000"


def remap_palette(palette, mapping, bg):
    """Apply slot->brand-hex `mapping` onto `palette`; guard body/eyes contrast."""
    out = dict(palette)
    out.update(mapping)
    for slot in GUARDED_SLOTS:
        if slot in out:
            out[slot] = ensure_contrast(out[slot], bg)
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_mascot_brand -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add assets/scripts/mascot_brand.py tests/test_mascot_brand.py
git commit -m "feat(mascot): brand remap helpers with WCAG contrast guard"
```

---

### Task 10: Dry run + skill docs

**Files:**
- Modify: `assets/scripts/dry-run-plan.py` (report mascot status)
- Modify: `SKILL.md` (init flow + pipeline + file map + config docs)

- [ ] **Step 1: Extend `dry-run-plan.py`**

Read the script first (`assets/scripts/dry-run-plan.py`) to find its per-scene report loop. Where it prints each scene's line, append mascot status from the plan entry:

```python
        m = s.get("mascot_plan", {})
        mascot_note = ""
        if m.get("enabled"):
            emo = m.get("emotion") or f"{m.get('before')}->{m.get('after')}"
            mascot_note = f"  mascot: {m.get('character', 'octopus')} ({emo})"
```

…and concatenate `mascot_note` onto that scene's printed line. No rendering, no new flag (spec: extend `--plan`, not add one).

- [ ] **Step 2: Verify dry run still passes its tests**

Run: `python -m unittest discover -s tests`
Expected: all pass

- [ ] **Step 3: Update `SKILL.md`**

- Pipeline table (line ~50): add `render-mascot.py → mascot sprite frames (if mascot: configured)` after `apply-brand.py`, and note the overlay inside `build-scenes.sh`'s row.
- File map (line ~280): add `mascot.json` next to `brand.yaml`, and the four new scripts under `scripts/`.
- Init flow (step 2 "For init", line ~150): add — "If the user wants the mascot: read the logo/brand, pick the best-fit roster character, call `mascot_brand.remap_palette` with brand colors, optionally edit accessory cells in the grid, write `mascot.json` next to `brand.yaml`."
- Add a short `## Mascot` section documenting the brand.yaml block (copy the example from Task 8 Step 3) and per-scene overrides.

- [ ] **Step 4: Commit**

```bash
git add assets/scripts/dry-run-plan.py SKILL.md
git commit -m "docs(mascot): dry-run mascot reporting + SKILL.md mascot documentation"
```

---

### Task 11: End-to-end verification

**Files:** none (verification only)

- [ ] **Step 1: Full unit suite**

Run: `python -m unittest discover -s tests`
Expected: all pass

- [ ] **Step 2: Golden-frame check**

```bash
python assets/scripts/render-mascot.py assets/mascots/octopus.json /tmp/golden
python - <<'PY'
import hashlib
h = hashlib.sha256(open("/tmp/golden/idle/f_001.png", "rb").read()).hexdigest()
print("idle frame 0 sha256:", h)
PY
```

Record the hash in `tests/test_render_mascot.py` as a new test (skipped when ffmpeg is unavailable):

```python
class TestGoldenFrame(unittest.TestCase):
    def test_octopus_idle_frame0_is_stable(self):
        import hashlib, shutil, subprocess, tempfile
        if not shutil.which("ffmpeg"):
            self.skipTest("ffmpeg not installed")
        with tempfile.TemporaryDirectory() as d:
            subprocess.check_call([sys.executable,
                os.path.join(SCRIPTS := os.path.join(os.path.dirname(__file__), "..", "assets", "scripts"), "render-mascot.py"),
                os.path.join(SCRIPTS, "..", "mascots", "octopus.json"), d])
            h = hashlib.sha256(open(os.path.join(d, "idle", "f_001.png"), "rb").read()).hexdigest()
            self.assertEqual(h, "<PASTE THE HASH FROM THE RUN ABOVE>")
```

(If the hash differs across ffmpeg versions in practice, relax to comparing decoded RGBA via `ffmpeg -i f_001.png -f rawvideo -pix_fmt rgba -` instead of the PNG container bytes — decoded pixels are deterministic where the container may not be.)

- [ ] **Step 3: Smoke a real build in a sandbox project**

```bash
mkdir -p /tmp/mascot-e2e/demo-video && cd /tmp/mascot-e2e/demo-video
# scaffold per SKILL.md init: copy assets/scripts/*, assets/templates/*, brand.example.yaml -> brand.yaml, package.example.json -> package.json
# enable: arc short (hero/graph/endcards), mascot: {character: octopus, enabled: true}
bash scripts/build.sh --plan      # PASS expected; mascot status printed per scene
bash scripts/build.sh             # full build
```

Verify in the output video: octopus idles bottom-right on hero + graph, absent on endcards. Then change `mascot.position` to `bottom-left` and rebuild — captures must report "capture cached", only overlay re-runs.

- [ ] **Step 4: Commit (golden test) and push**

```bash
git add tests/test_render_mascot.py
git commit -m "test(mascot): golden-frame stability test for octopus idle"
git push -u origin feat/mascot-overlay
```

---

## Out of scope for this plan (follow-up plan)

- **Spec phase 4:** moments (`peek`/`jump`/`hide`/`recoil`), corner auto-flip from `clip`/`zoom` rects, enter/exit suppression across crossfades.
- **Spec phase 5:** remaining roster characters (fox, owl, cat, robot, turtle) + `assets/mascots/schema.json` CI validation job.
- `/demo-video mascot` subcommand for retrofitting existing projects (the init-flow doc in Task 10 covers new projects).
