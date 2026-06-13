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


def assert_canvas_16_9(canvas, tol=0.01):
    """Raise ValueError unless the canvas is 16:9 (within tol). The diorama camera
    frames a 16:9 region via zoompan; a non-16:9 canvas would distort silently."""
    w, h = canvas["width"], canvas["height"]
    if abs(w / h - 16 / 9) > tol:
        raise ValueError(f"diorama canvas must be 16:9 (got {w}x{h})")


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
        if mascot_xy is None:                # v1 cannot follow the mascot (the tour is
            raise ValueError(                # built before mascot positions are known)
                "focus 'mascot' needs a mascot position; not supported in v1 camera "
                "tours — use a window id or 'all'")
        cx, cy = mascot_xy
    else:
        w = windows[focus]
        cx, cy = w["x"] + w["w"] / 2, w["y"] + w["h"] / 2
    zoom = float(stop.get("zoom", 1.0)) or 1.0
    vw = min(cw_canvas, cw_canvas / zoom)
    vh = vw / out_aspect
    if vh > ch_canvas:                       # never taller than the canvas
        vh = ch_canvas; vw = vh * out_aspect
    vw, vh = round(vw), round(vh)            # round size first so the clamp below uses
    x = min(max(0, round(cx - vw / 2)), cw_canvas - vw)   # the SAME dims we return, and
    y = min(max(0, round(cy - vh / 2)), ch_canvas - vh)   # the rect can't sit past the edge
    return x, y, vw, vh


def camera_duration(stops):
    """Total seconds of a camera tour: each stop's `hold`, plus its `transition`
    for stops after the first. Geometry-independent (no windows needed), so a
    diorama with no explicit `duration` can default to its tour length. MUST stay
    in lockstep with camera_timeline's accumulated total (asserted in tests)."""
    total = 0.0
    for i, stop in enumerate(stops):
        if i > 0:
            total += float(stop.get("transition", 0.0))
        total += float(stop.get("hold", 2.0))
    return total


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
