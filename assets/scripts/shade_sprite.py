"""shade_sprite.py — procedural "selout" shading for flat pixel-grid mascots.

A flat mascot (single fill per slot) gets dimensionality automatically, with no
art rework, by enriching every animation frame. This is "shader v2": instead of
just dimming the body color at the rims, it shifts HUE the way pixel artists do —
light reads warm, shadow reads cool — so flat fills look painted, not dimmed.

  - hue-shifted ramp: a body cell whose neighbor ABOVE is outside the silhouette
    becomes `hi` (lighter value, hue rotated WARMER toward yellow, slightly
    desaturated — light feels warm). A cell whose neighbor BELOW is outside
    becomes `shade` (darker value, hue rotated COOLER toward blue/purple, slightly
    more saturated — shadow feels cool). Vertical-only rims read cleanly at small
    sizes (diagonal rims speckle).
  - two-step shadow: a deeper `shade2` (cooler + darker still than `shade`) lands
    on the very bottom row of the silhouette and under overhangs (a body/belly
    cell with another fill cell directly above and open space below — e.g. under
    the chin/pouch), giving a value gradient instead of one flat shadow band.
  - boundary dither: at the body->shade transition the row just above each `shade`
    rim gets a subtle 1-cell checkerboard of body/shade, so the value step has
    texture instead of a hard line. Gated by `dither=True` (default on).
  - eye catch-light: the top-left cell of each eye blob becomes a near-white
    `glow`, so flat eyes look wet/alive.

Deterministic, dependency-free (colorsys is stdlib). `shade_mascot()` is the
pure, unit-tested core; the new slots (`hi`/`shade`/`shade2`/`glow`) are derived
from the body colour so any palette works. Opt in per project with
`mascot.shade: true` in brand.yaml.

  python shade_sprite.py <in.json> <out.json> [--body body --belly belly --eyes eyes --outline outline] [--no-dither]
"""
import argparse
import colorsys
import json
import sys

# Hue targets (degrees) the ramp rotates toward. Light rotates toward yellow,
# shadow toward blue-purple — the classic warm-light / cool-shadow pixel-art move.
_WARM_HUE = 60.0   # yellow
_COOL_HUE = 270.0  # blue-purple

# Per-step rotation caps (degrees). shade2 rotates further toward cool than shade.
_HI_HUE_STEP = 14.0
_SHADE_HUE_STEP = 16.0
_SHADE2_HUE_STEP = 26.0


def _hex_to_rgb01(c):
    return tuple(int(c[i:i + 2], 16) / 255.0 for i in (1, 3, 5))


def _rgb01_to_hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(v * 255))) for v in rgb)


def _mix(a_hex, b_hex, t):
    a = [int(a_hex[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(b_hex[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def lighten(c, t):
    return _mix(c, "#ffffff", t)


def darken(c, t):
    return _mix(c, "#000000", t)


def _rotate_hue(hue_deg, target_deg, max_step):
    """Rotate hue toward target along the shorter arc, by at most max_step deg."""
    diff = (target_deg - hue_deg + 180.0) % 360.0 - 180.0  # signed shortest delta
    step = max(-max_step, min(max_step, diff))
    return (hue_deg + step) % 360.0


def _shift(c, *, dv, ds, hue_target, hue_step):
    """Return c with value/saturation deltas and hue rotated toward a target.

    dv/ds are additive in HSV space (clamped to [0,1]); hue_step caps rotation.
    Pure brightness-only fallback kicks in for near-grey colours (low saturation),
    where a hue shift would tint a neutral and read as a colour cast, not light.
    """
    r, g, b = _hex_to_rgb01(c)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    if s >= 0.06:  # near-greys ramp by value only — a hue/sat shift would tint
        h = _rotate_hue(h * 360.0, hue_target, hue_step) / 360.0
        s = max(0.0, min(1.0, s + ds))
    v = max(0.0, min(1.0, v + dv))
    return _rgb01_to_hex(colorsys.hsv_to_rgb(h, s, v))


def hi_color(c):
    """Highlight: brighter, warmer (toward yellow), slightly desaturated."""
    return _shift(c, dv=+0.10, ds=-0.10, hue_target=_WARM_HUE, hue_step=_HI_HUE_STEP)


def shade_color(c):
    """Shadow: darker, cooler (toward blue-purple), slightly more saturated."""
    return _shift(c, dv=-0.16, ds=+0.08, hue_target=_COOL_HUE, hue_step=_SHADE_HUE_STEP)


def shade2_color(c):
    """Deep shadow: darker + cooler still than shade_color, for the floor/overhangs."""
    return _shift(c, dv=-0.30, ds=+0.13, hue_target=_COOL_HUE, hue_step=_SHADE2_HUE_STEP)


def shade_mascot(m, body="body", belly="belly", eyes="eyes", outline="outline",
                 dither=True):
    """Return a NEW enriched mascot dict (input is not mutated).

    Requires a `body` slot; `belly`/`eyes`/`outline` are optional and skipped
    cleanly when the character has no such slot. `dither=True` adds a subtle
    body/shade checkerboard row above the bottom rim to soften the value step.
    """
    if body not in m.get("palette", {}):
        raise ValueError(f"shade_sprite: mascot has no '{body}' palette slot")
    legend = dict(m["legend"])
    palette = dict(m["palette"])

    used = set(legend)

    def free_char(*prefs):
        for ch in prefs:
            if ch not in used:
                used.add(ch)
                return ch
        for o in range(33, 127):
            ch = chr(o)
            if ch not in used:
                used.add(ch)
                return ch
        raise RuntimeError("shade_sprite: no free legend char")

    body_hex = palette[body]
    hi_c = free_char("h", "H")
    legend[hi_c] = "hi"
    palette["hi"] = hi_color(body_hex)
    sh_c = free_char("s", "S")
    legend[sh_c] = "shade"
    palette["shade"] = shade_color(body_hex)
    sh2_c = free_char("x", "X")
    legend[sh2_c] = "shade2"
    palette["shade2"] = shade2_color(body_hex)
    gl_c = free_char("c", "C")
    legend[gl_c] = "glow"
    palette["glow"] = "#fff6ec"

    body_chars = {ch for ch, slot in m["legend"].items() if slot == body}
    belly_chars = {ch for ch, slot in m["legend"].items() if slot == belly}
    eye_chars = {ch for ch, slot in m["legend"].items() if slot == eyes}
    fill_chars = body_chars | belly_chars

    def enrich(frame):
        h, w = len(frame), len(frame[0])

        def outside(r, c):
            if r < 0 or c < 0 or r >= h or c >= w:
                return True
            slot = legend.get(frame[r][c])
            return slot is None or slot == outline

        def is_fill(r, c):
            return 0 <= r < h and 0 <= c < w and frame[r][c] in fill_chars

        out = [list(row) for row in frame]
        for r in range(h):
            for c in range(w):
                ch = frame[r][c]
                if ch in fill_chars:
                    top_open = outside(r - 1, c)
                    bot_open = outside(r + 1, c)
                    if ch in body_chars and top_open:
                        # top rim catches the warm highlight
                        out[r][c] = hi_c
                    elif bot_open:
                        # bottom rim: deepest shadow on the silhouette floor /
                        # under an overhang (fill directly above), else mid shadow
                        out[r][c] = sh2_c if is_fill(r - 1, c) else sh_c
                elif ch in eye_chars:
                    up_eye = r > 0 and frame[r - 1][c] in eye_chars
                    left_eye = c > 0 and frame[r][c - 1] in eye_chars
                    if not up_eye and not left_eye:
                        out[r][c] = gl_c

        if dither:
            # One subtle checkerboard row directly above each shade/shade2 rim:
            # interior body cells flip to shade on a checker so the value step
            # reads as texture, not a hard line. Body cells only (keep belly clean),
            # and only where the cell below became a shadow this pass.
            shade_set = {sh_c, sh2_c}
            for r in range(h):
                for c in range(w):
                    if out[r][c] in body_chars and r + 1 < h and out[r + 1][c] in shade_set:
                        if (r + c) % 2 == 0:
                            out[r][c] = sh_c
        return ["".join(row) for row in out]

    new = dict(m)
    new["name"] = m.get("name", "mascot") + "-shaded"
    new["legend"] = legend
    new["palette"] = palette
    new["animations"] = {
        name: [enrich(f) for f in frames] for name, frames in m["animations"].items()
    }
    return new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inp")
    ap.add_argument("out")
    ap.add_argument("--body", default="body")
    ap.add_argument("--belly", default="belly")
    ap.add_argument("--eyes", default="eyes")
    ap.add_argument("--outline", default="outline")
    ap.add_argument("--no-dither", action="store_true",
                    help="disable the boundary dither (default: dither on)")
    a = ap.parse_args()
    with open(a.inp, encoding="utf-8") as f:
        m = json.load(f)
    try:
        out = shade_mascot(m, a.body, a.belly, a.eyes, a.outline,
                           dither=not a.no_dither)
    except ValueError as e:
        sys.exit(str(e))
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print(f"  mascot shaded -> {a.out} (+hi/shade/shade2/glow)")


if __name__ == "__main__":
    main()
