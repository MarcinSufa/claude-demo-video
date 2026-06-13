"""shade_sprite.py — procedural "selout" shading for flat pixel-grid mascots.

A flat mascot (single fill per slot) gets dimensionality automatically, with no
art rework, by enriching every animation frame:

  - directional rim: a body cell whose neighbor ABOVE is outside the silhouette
    becomes a lighter `hi` slot (light from the top); a cell whose neighbor BELOW
    is outside becomes a darker `shade` slot. Vertical-only rims read cleanly at
    small sizes (diagonal rims speckle).
  - eye catch-light: the top-left cell of each eye blob becomes a near-white
    `glow`, so flat eyes look wet/alive.

Deterministic, dependency-free. `shade_mascot()` is the pure, unit-tested core;
the new slots (`hi`/`shade`/`glow`) are derived from the body colour so any
palette works. Opt in per project with `mascot.shade: true` in brand.yaml.

  python shade_sprite.py <in.json> <out.json> [--body body --belly belly --eyes eyes --outline outline]
"""
import argparse
import json
import sys


def _mix(a_hex, b_hex, t):
    a = [int(a_hex[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(b_hex[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def lighten(c, t):
    return _mix(c, "#ffffff", t)


def darken(c, t):
    return _mix(c, "#000000", t)


def shade_mascot(m, body="body", belly="belly", eyes="eyes", outline="outline"):
    """Return a NEW enriched mascot dict (input is not mutated).

    Requires a `body` slot; `belly`/`eyes`/`outline` are optional and skipped
    cleanly when the character has no such slot.
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

    hi_c = free_char("h", "H")
    legend[hi_c] = "hi"
    palette["hi"] = lighten(palette[body], 0.30)
    sh_c = free_char("s", "S")
    legend[sh_c] = "shade"
    palette["shade"] = darken(palette[body], 0.18)
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

        out = [list(row) for row in frame]
        for r in range(h):
            for c in range(w):
                ch = frame[r][c]
                if ch in fill_chars:
                    if ch in body_chars and outside(r - 1, c):
                        out[r][c] = hi_c
                    elif outside(r + 1, c):
                        out[r][c] = sh_c
                elif ch in eye_chars:
                    up_eye = r > 0 and frame[r - 1][c] in eye_chars
                    left_eye = c > 0 and frame[r][c - 1] in eye_chars
                    if not up_eye and not left_eye:
                        out[r][c] = gl_c
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
    a = ap.parse_args()
    with open(a.inp, encoding="utf-8") as f:
        m = json.load(f)
    try:
        out = shade_mascot(m, a.body, a.belly, a.eyes, a.outline)
    except ValueError as e:
        sys.exit(str(e))
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print(f"  mascot shaded -> {a.out} (+hi/shade/glow)")


if __name__ == "__main__":
    main()
