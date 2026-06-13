# assets/scripts/make-diorama.py
"""make-diorama.py — build a diorama scene: composite N windows on a big canvas,
overlay the mascot at canvas coords, then move an eased camera over it.

  python make-diorama.py <plan.json> <out.mp4>

plan.json (written by build-scenes.sh): {canvas, backdrop, windows:[{id,x,y,w,clip}],
camera:[...], mascot:{frames_dir, timeline}|null, duration, fps}.

build_canvas_filter()/build_camera_filter() are the pure, unit-tested ffmpeg
builders; diorama_layout.py holds the geometry. The graph is verified end-to-end
by tests/smoke_build.sh's diorama tier.
"""
import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from diorama_layout import camera_timeline, viewport_at  # noqa: E402


def build_canvas_filter(windows, canvas):
    """Backdrop ([0:v]) scaled to canvas, then each window clip ([i:v], i>=1)
    scaled to its width and overlaid at (x, y). Returns the filter_complex up to
    label [canvas]."""
    parts = [f"[0:v]scale={canvas['width']}:{canvas['height']},setsar=1[bg]"]
    src = "[bg]"
    for i, w in enumerate(windows, 1):
        parts.append(f"[{i}:v]scale={w['w']}:-2,setsar=1[w{i}]")
        label = "[canvas]" if i == len(windows) else f"[c{i}]"
        parts.append(f"{src}[w{i}]overlay={w['x']}:{w['y']}{label}")
        src = f"[c{i}]"
    return ";".join(parts)


def _coord_expr(segs, idx):
    """Piecewise ffmpeg expression for viewport coordinate `idx`
    (0=x,1=y,2=w,3=h) over the camera segments: smoothstep within each segment,
    constant for holds (a==b makes the eased term collapse to the value)."""
    expr = f"{segs[-1][3][idx]}"  # default = last segment's end value
    for (s, e, a, b) in reversed(segs):
        dur = e - s
        if dur <= 0:
            continue
        p = f"clip((t-{s:.3f})/{dur:.3f},0,1)"
        pe = f"({p}*{p}*(3-2*{p}))"
        val = f"({a[idx]}+({b[idx]}-{a[idx]})*{pe})"
        expr = f"if(between(t,{s:.3f},{e:.3f}),{val},{expr})"
    return expr


def build_camera_filter(segs, canvas_w, canvas_h, out_w, out_h, fps):
    """Animated crop of [canvas] following the camera segments, scaled to output.
    Consumes label [canvas], produces [vout]."""
    x = _coord_expr(segs, 0); y = _coord_expr(segs, 1)
    w = _coord_expr(segs, 2); h = _coord_expr(segs, 3)
    return (f"[canvas]crop=w='{w}':h='{h}':x='{x}':y='{y}':eval=frame,"
            f"scale={out_w}:{out_h},setsar=1[vout]")
