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
