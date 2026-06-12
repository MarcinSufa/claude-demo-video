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
