# Before / after task demos (`before_after` scene)

To show a task's outcome — the bug, then the fix — use a **`before_after`** scene.
It takes two clips, burns a colored banner on each (red = before, green = after by
default), and joins them — `layout: sequential` (before then after) or
`side_by_side` (the two clips next to each other).

```yaml
sequence:
  - hero
  - type: before_after
    before: { source: "footage/before.mp4", label: "BEFORE — the bug" }
    after:  { source: "footage/after.mp4",  label: "AFTER — the fix" }
    layout: sequential        # or "side_by_side"
    half_duration: 8          # optional: trim each half to N seconds
  - endcards
```

Each half is a **clip path / `{ source }`**, or a **`browser_capture` spec**
(`{ url, actions, auth, ... }`) that the pipeline records for you — so you can
point `before` at the deployed/no-fix URL and `after` at the fixed branch and let
it capture both. A `source` path is taken **relative to your demo project
directory** (where `brand.yaml` lives, e.g. `footage/before.mp4`), or absolute.
How to produce the two clips for a *code* change:

1. Record the **before** against the no-fix state (deployed URL, or the base
   branch's dev server), e.g. via a Playwright/e2e run with `video: 'on'`, or a
   `before_after` half with `before: { url: <staging>, actions: [...] }`.
2. Record the **after** against the fixed branch the same way (a second dev server
   on another port + re-auth, or `after: { url: <local-fix>, ... }`).
3. Drive the *same* interaction in both so the comparison is honest; trim with
   `half_duration` and label each side.

**Focus the capture on what changed.** A `before_after` capture half is a
`browser_capture` spec, so its `actions` take focus controls: `glow`/`highlight`
to pulse the touched element (the selector must match exactly one node, or the
recording stops naming the action, selector and count), `waitToast` to guarantee an error/success
notification is on screen, and per-action `speed` (ramp out a slow load) + `zoom`
(Ken Burns onto the toast/field). Off-screen targets are auto-scrolled into view
before interaction. So a bug→fix demo reads clearly — the viewer sees the toast in
BEFORE and its absence in AFTER, full-frame, without watching spinners. See
`references/scene-config.md` → *Focus & pacing*. (`clip` frames one region for the
whole half; `speed`/`zoom` are time-windowed and composable with it.)

Banner labels render through ffmpeg `drawtext`, which is not reliably UTF-8 on
Windows — labels are auto-sanitized to ASCII (an em-dash becomes `-`), so keep
them short and plain.
