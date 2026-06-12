# Mascot Phase 4: Motion, Keyframes, Art v2 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement task-by-task. Steps use checkbox syntax.

**Goal:** Make the mascot alive — user-choreographed keyframes per scene, walking between screen positions, emotion motion (bounce/shake/hide), and a redrawn higher-fidelity octopus.

**Architecture:** Keyframes flow stage-1 (`mascot_stub` passes `keyframes` through) → stage-2 (`resolve_timeline` converts them to position-carrying segments and inserts `walk` move-segments between differing positions) → compositor (`build_overlay_cmd` resolves a named anchor per segment, lerps x/y during move segments via ffmpeg `t` expressions, and adds per-emotion offset expressions). Art is data-only: `octopus.json` redrawn on a 24×20 grid with `outline`/`shade` slots and a `walk` animation.

**Spec:** `docs/superpowers/specs/2026-06-12-mascot-overlay-design.md` → "Phase 4 addendum".
**Branch:** `feat/mascot-overlay` (continue). Tests: `python -m unittest discover -s tests` (154 green at start).

---

### Task 1: Art v2 — NEW original character `tessel` (subdividing-squares critter)

**Files:** Create `assets/mascots/tessel.json`; keep octopus as-is in the roster; add `"walk"` to `REQUIRED_ANIMATIONS` in `assets/scripts/mascot_data.py` (octopus therefore ALSO needs a walk animation — add a simple 2-frame tentacle stride to octopus.json); golden test for tessel's idle frame in `tests/test_render_mascot.py`.

**Design brief (user-approved direction — do NOT draw an octopus):** an original
block-critter derived from the Fractal logo's subdividing-squares motif.
Anti-reference lessons from Clawd (style only, not the character): few LARGE
deliberate shapes, flat colors, clean silhouette, two big dark eyes, stubby
legs; no texture noise, no thin stripes.

- Canvas 22 wide × 18 tall, `cell_px: 6`.
- Slots: `body` (cream `#F4EFE3`), `quad` (coral `#E08D6E` — the subdivided
  corner squares baked into the body, echoing the logo), `eyes` (near-black
  `#26262b`, 2×2 each), `accent` (gold `#e3b76e`, tiny — cheek/antenna),
  `outline` (deep `#3a352c` 1-cell silhouette edge).
- Body: a rounded square (~14×11) with a 2×2-ish coral quadrant pattern in one
  corner (top-left), two big eyes, 3 stubby legs (2×2 each). Big readable face,
  lots of flat body area.
- Animations: `idle` (3: breath bob + blink frame), `type` (3: legs drum),
  `walk` (4: leg stride + 1px body bob), `panic` (3: body tilts, eyes wide 3×2,
  quads scatter 1px), `celebrate` (4: SIGNATURE — body subdivides into four
  smaller squares that separate 1–2 cells and reassemble), `sleep` (2: eyes as
  2-wide lines, body squashed 1 row), `point` (2: one side grows a 4-cell arm),
  `enter` (3: assembles from four quarter-squares rising), `exit` (3: reverse).
- `validate_mascot` passes; preview EVERY animation with the block-art printer
  and iterate until each pose reads instantly at terminal size; the celebrate
  subdivision must visibly echo the logo.
- Golden test: render tessel, decoded-RGBA sha256 of `idle/f_001.png`, run twice.
- Commit: `feat(mascot): tessel — original subdividing-squares roster character + walk cycles`.

### Task 2: Keyframes — stage-1 passthrough + stage-2 segments with positions

**Files:** Modify `assets/scripts/plan-scenes.py` (mascot_stub), `assets/scripts/resolve-mascot-timeline.py`; tests in `tests/test_mascot_plan.py`, `tests/test_mascot_timeline.py`.

Stage-1 (`mascot_stub`): when the scene override has `keyframes` (non-empty list), copy it into the stub as `stub["keyframes"]` (list of `{at, emotion, position?}` dicts; validate `at` is a number ≥0 and `emotion` is a string — exit with a clear message otherwise). Keyframes coexist with the default `emotion` (used before the first keyframe if its `at` > 0).

Stage-2 (`resolve_timeline`): when `stub["keyframes"]` present, they REPLACE event-based resolution:
1. Sort by `at`, clamp to `[0, duration)`, drop keyframes at/after duration.
2. Build segments: keyframe i spans `[at_i, at_{i+1})`, last spans to `duration`. If the first keyframe's `at` > 0, prepend a base segment `[0, at_0)` with the stub's default emotion/position.
3. Each segment carries `position` (its keyframe's, else inherited from the previous segment, else `stub["position"]`).
4. **Move segments:** when consecutive segments' positions differ, carve a move segment of `MOVE_SECONDS = 0.8` (or half the later segment, whichever is smaller) from the START of the later segment: `{at, until, emotion: "walk", move: {from: <prev position>, to: <new position>}}`. The remainder of the later segment keeps its own emotion/position.
5. Output segments now always include `position`; event-based (non-keyframe) timelines get `position: stub["position"]` on every segment so the compositor has one shape.

Tests (pure core): keyframes replace events; base-segment prepend; clamping; position inheritance; move segment carved with correct from/to and `walk` emotion; move shorter than 0.8s when the segment is tiny; single-position keyframes produce no move segments.

Commit: `feat(mascot): keyframe choreography — positioned segments + walk moves`.

### Task 3: Compositor — per-segment anchors, lerped moves, emotion motion

**Files:** Modify `assets/scripts/overlay-mascot.py`; tests in `tests/test_overlay_mascot.py`.

- `anchor_xy` unchanged; add `resolve_anchors(timeline, vw, vh, sw, sh)` → per-segment `(x, y)` from each segment's `position` name (plus `"offscreen-bottom"` → `(home_x, vh)` used by `hide`).
- `build_overlay_cmd` changes:
  - Per-segment x/y instead of one global pos. For a plain segment: constants.
  - **Move segment:** `x = x0 + (x1-x0)*min(1, max(0, (t-AT)/DUR))` written as an ffmpeg expression string (single quotes around the whole overlay filter arg already present — make sure commas inside `min()/max()` don't break filter parsing; use `clip((t-AT)/DUR,0,1)` which avoids commas problems? ffmpeg expr has `clip(x,min,max)`; commas are FINE inside `overlay=x='expr'` quoting — verify with a real ffmpeg run in tests' smoke step).
  - **Emotion modifiers** (y/x offsets added to the segment's base):
    - `celebrate`: `y_base - 18*abs(sin((t-AT)*4))` (bounce)
    - `panic`: `x_base + 4*sin((t-AT)*18)` (shake)
    - `hide` (pseudo-emotion, maps to `exit` animation frames then offscreen): treat as a move segment to `offscreen-bottom` playing `exit`; subsequent un-hide is just the next keyframe's position (move plays `enter`... keep v1 simple: `hide` slides down playing `exit`; a following keyframe with a position slides back up playing `walk`).
  - `walk` uses the new `walk` animation frames; `move.from/to` resolved via `resolve_anchors`.
- Unit tests on the generated filter_complex string: per-segment enables unchanged; move segment contains a `clip(` lerp expression with both x anchors; celebrate segment's y contains `sin`; panic x contains `sin`; plain segments remain constant ints.
- Smoke (manual step in task): 8s lavfi clip, keyframed timeline `idle@0 (bottom-right) → point@3 (bottom-left) → celebrate@6`, verify with extracted frames at t=2 (right), t=3.5 (mid-walk, between anchors), t=5 (left), t=7 (left, bouncing — differs frame-to-frame).
- Commit: `feat(mascot): per-segment anchors, walking moves, emotion motion expressions`.

### Task 4: Config plumbing + docs

**Files:** `assets/brand.example.yaml`, `SKILL.md`, `assets/scripts/dry-run-plan.py` (mascot note shows `keyframes: N` when present). Document the keyframes syntax:

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

Tests for the dry-run note. Commit: `docs(mascot): keyframe choreography docs + dry-run reporting`.

### Task 5: Re-choreograph + rebuild the Fractal video

In `c:\Users\sufam\IdeaProjects\orchestrator-core\demo-video`: sync the updated scripts + new octopus into the project (scripts/ copy, regenerate mascot.json with the same brand remap on the v2 art), add keyframes per scene matched to the VO beats (hero: enter→idle→point at the wordmark; board: type→point at the develop column (bottom-left)→celebrate near "merged"; worker-reviewer: type→panic on findings→walk to bottom-left→celebrate on APPROVED), rebuild, verify frames at the choreography beats, deliver the video.

---

## Out of scope
Corner auto-flip from clip/zoom rects (only if free), prop/window interactions (v2), additional roster characters.
