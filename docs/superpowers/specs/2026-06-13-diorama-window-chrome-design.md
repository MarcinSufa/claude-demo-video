# Diorama Window Chrome + Guardrails — Design

**Date:** 2026-06-13
**Status:** Approved
**Builds on:** the merged diorama scene (`make-diorama.py` canvas composite + `zoompan` camera + window-relative mascot — PR #12, on `main`).
**Branch:** `feat/diorama-chrome`.

## Goal

Render an opt-in **title bar ("window chrome")** around diorama windows so a bare `source`/`url` clip reads as a real app/terminal window, and close two silent footguns the diorama ships with today: a non-16:9 canvas that distorts under `zoompan`, and mascot anchors that can fall off the canvas edge.

## Background — what exists

`chrome: true` and `title:` are **already accepted** per window in `plan-scenes.py` (`custom_arc` diorama branch, ~L263–264: `w["chrome"] = True; w["title"] = win.get("title", win["id"])`), but they go nowhere:

- `build-scenes.sh`'s diorama heredoc builds each make-diorama plan window as `{id, x, y, w, clip}` and drops `chrome`/`title`.
- `make-diorama.build_canvas_filter` only scales + overlays each clip.

So `chrome`/`title` are a **silent no-op**. The Fractal mockups draw their own CSS chrome (macOS traffic lights `#ff5f57` / `#febc2e` / `#7fbf7f`); this feature gives the same look to windows that don't bring their own.

## Design

### Chrome look (decided)

macOS traffic lights: three filled **round** dots — red `#ff5f57`, amber `#febc2e`, green `#7fbf7f` — at the left of a title bar, with the window `title` to their right. Bar background uses the brand palette (`end_card_bg`), a 2px bottom rule in `rule`, title in the brand `fg`. Dot colours are fixed literals (the macOS look), not brand-derived.

### Rendering — pure ffmpeg (no browser, no Pillow)

Chrome is drawn inside the canvas composite, per window with `chrome: true`:

- **Bar + rule:** two `drawbox` fills — the bar (`x=WX:y=WY:w=W:h=BAR_H:color=<end_card_bg>:t=fill`) and a 2px bottom rule.
- **Dots:** a small **round-dots RGBA PNG** generated once via the same raw-RGBA→PNG technique `render-mascot.py` uses (paint three filled, lightly anti-aliased circles into an RGBA buffer, pipe to `ffmpeg -f rawvideo -pix_fmt rgba`). It is added as one ffmpeg input, `split` to N, and `overlay`-ed into each chrome bar's left, vertically centered. **Round dots are pixels, not a `●` glyph** — the pipeline already sanitizes drawtext to ASCII because its text reader is unreliable with unicode on Windows (`make-before-after.py`), so a `●` glyph is off the table.
- **Title:** one `drawtext`, reusing `make-before-after.py`'s helpers (imported): `find_font()` (system-font fallback list → a usable `.ttf`) to resolve the font, `_esc_path()` for the drawtext path, and a per-window UTF-8 **textfile** (`textfile=`) with the title ASCII-sanitized. Positioned right of the dots, vertically centered.

The bar/rule/fg colours travel in the diorama plan JSON (a `chrome_style` block `build-scenes.sh` fills from `config.json`'s palette), so `make-diorama` stays config-agnostic (same as how it already gets `backdrop`/`fps` from the plan). `make-diorama` resolves the drawtext font itself via the imported `find_font()` (no font path in the plan JSON, no bash↔python font dance). When no window has chrome, the `chrome_style` block and the dots input are omitted entirely.

### Geometry — a chrome window = bar + clip stacked

- `BAR_H` is a **constant** 40 canvas px (real title bars are ~constant height regardless of window size; also lets one dots PNG serve every chrome window).
- For a chrome window: the clip is overlaid at `(WX, WY + BAR_H)`; the bar is drawn at `(WX, WY)` spanning width `W`, `BAR_H` tall.
- The window's **layout height** becomes `H = BAR_H + clip_h` (where `clip_h = round(W * clip_ch / clip_cw)` from the clip aspect). This `H` is what `focus_rect` / `camera_timeline` / `window_anchor` consume — so the camera frames the whole window *including* its chrome, and `top`/`on`/`beside` anchors are relative to the bar+clip rect.
- Derived sizes via a pure `chrome_metrics(BAR_H)` helper (so they're unit-testable): dot diameter ≈ `round(BAR_H*0.32)`, dot gap, left pad ≈ `round(BAR_H*0.5)`, title x ≈ `round(BAR_H*1.9)`, title font size ≈ `round(BAR_H*0.42)`.
- Windows **without** chrome are unchanged: `H = clip_h`, clip overlaid at `(WX, WY)`, no bar.

### Guardrail 1 — canvas must be 16:9

`make-diorama.main()` validates the canvas aspect before building. A pure helper `assert_canvas_16_9(canvas, tol=0.01)` in `diorama_layout.py` raises `ValueError("diorama canvas must be 16:9 (got {w}x{h})")` when `abs(w/h - 16/9) > tol`. **Error, not auto-pad** — auto-padding to 16:9 would shift every window's canvas coordinate (YAGNI). The existing docs already state the 16:9 requirement; this makes it fail loud instead of distorting silently under `zoompan`.

### Guardrail 2 — mascot anchors clamp into the canvas

`resolve_canvas_positions` gains a `canvas` argument and clamps each resolved anchor `(x, y)` to `x ∈ [0, canvas_w - sprite_w]`, `y ∈ [0, canvas_h - sprite_h]`. Move segments clamp both endpoints. `window_anchor` (pure geometry in `diorama_layout.py`) is unchanged — clamping happens at the resolve layer, which is the one that knows the canvas. This stops `beside`/`top` on an edge window from pushing the sprite off-canvas.

## Data flow

1. **`plan-scenes.py`** — already emits `chrome`/`title` on diorama window entries. *No change.*
2. **`build-scenes.sh`** diorama heredoc — carry `chrome`/`title` into each make-diorama plan window; when any window has chrome, add a `chrome_style` block to the plan JSON (`bar_bg`, `rule`, `fg` from `config.json`'s palette). The drawtext font is resolved inside `make-diorama` (via the imported `find_font()`), not here.
3. **`make-diorama.py`**:
   - `main()` — call `assert_canvas_16_9(canvas)`; compute `H = BAR_H + clip_h` for chrome windows (else `clip_h`); when chrome windows exist, generate the dots PNG and write per-window title textfiles, add the dots `-i` input.
   - `build_canvas_filter(windows, canvas, chrome_style=None)` — for each window: scale clip to `W`, overlay at `(x, y + BAR_H if chrome else y)`; for chrome windows also emit the bar/rule `drawbox`, the dots `overlay`, and the title `drawtext`. Factor a pure `chrome_chain(win, metrics, chrome_style, dots_label)` returning one window's chrome substring (unit-tested like `build_camera_filter`).
   - `resolve_canvas_positions(timeline, windows, sprite_wh, canvas)` — clamp anchors.

## Testing

- **Pure unit tests** (no ffmpeg): `chrome_metrics(BAR_H)` derived sizes; `chrome_chain(...)` emits the bar drawbox, dots overlay, and title drawtext with the right coords/colours and the `BAR_H` clip offset; a chrome window's `H` includes `BAR_H` while a plain window's does not; `assert_canvas_16_9` raises on 2560×1200 and passes on 2560×1440; `resolve_canvas_positions` keeps an edge-window anchor inside the canvas (and clamps both move endpoints).
- **Integration:** add one `chrome: true` window to the smoke diorama scene and keep the existing 1920×1080 + non-blank assertions (proves the chrome filter graph runs end-to-end). Reuse the existing `nonblank` helper.

## Files

- `assets/scripts/make-diorama.py` — chrome rendering (`chrome_chain`, `chrome_metrics`, `BAR_H`), `build_canvas_filter` chrome branch + clip offset, window-`H` incl. bar, dots-PNG generation + title textfiles in `main()`, `resolve_canvas_positions` clamp, `assert_canvas_16_9` call.
- `assets/scripts/diorama_layout.py` — `assert_canvas_16_9`.
- `assets/scripts/build-scenes.sh` — carry `chrome`/`title`; inject `chrome_style`.
- `SKILL.md`, `assets/brand.example.yaml` — document `chrome: true` + `title:` per window.
- `tests/test_make_diorama.py`, `tests/test_diorama_layout.py`, `tests/smoke_build.sh` — the tests above.
- `assets/scripts/VERSION` — regenerate (drift guard).

## Out of scope (future)

- Title in the brand **mono** font (JetBrains Mono) — needs the `.ttf` locally for drawtext; v1 uses the `find_font()` system fallback.
- Per-window chrome colour overrides; address-bar / tab chrome variants.
- Rounded window corners or drop shadows on the window body.
- HTML-rendered chrome (Playwright) for pixel-perfect mockup parity — pure-ffmpeg chosen to keep the compositor browser-free.
