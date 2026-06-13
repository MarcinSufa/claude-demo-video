"""render-mascot.py — render mascot.json animations to transparent PNG frames.

  python render-mascot.py <mascot.json> <out_dir> [--target-height 140]

Writes <out_dir>/<anim>/f_%03d.png for every animation. PNGs come out of
ffmpeg (rawvideo RGBA piped in), so there is no Pillow dependency.
grid_to_rgba()/upscale_factor() are the pure, unit-tested core.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

# Ensure mascot_data (same directory) is importable regardless of cwd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
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
    # Clear stale frames: switching characters or shrinking an animation must not
    # leave old f_NNN.png files behind (overlay reads the whole f_%03d sequence).
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
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
        "-pix_fmt", "rgba",
        os.path.join(out_dir, "f_%03d.png"),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        proc.stdin.write(first)
        for frame in frames[1:]:
            buf, _, _ = grid_to_rgba(frame, legend, palette, cell, overrides)
            proc.stdin.write(buf)
    except OSError:
        pass  # ffmpeg exited early; proc.wait() below reports the failure
    finally:
        try:
            proc.stdin.close()
        except OSError:
            pass
    if proc.wait() != 0:
        sys.exit(f"render-mascot: ffmpeg failed for animation '{anim}'")
    return len(frames)


# Emotions that must read as perfectly still — their feet should never drift.
# Auto-anchored so a 1px breathing wobble can't read as jitter. Locomotion
# (walk/enter/exit) and dynamic poses (celebrate jump, panic, point) are left
# alone — anchoring those would flatten their intended vertical motion.
ANCHOR_EMOTIONS = ("idle", "type", "sleep")


def anchor_feet(frames, transparent):
    """Shift each frame down so its lowest non-transparent row sits at a constant
    baseline (the lowest across the set). Removes vertical jitter while keeping
    the deformation (breathing happens at the top, feet stay planted)."""
    def bottom(f):
        rows = [r for r, row in enumerate(f) if any(c not in transparent for c in row)]
        return rows[-1] if rows else len(f) - 1
    target = max(bottom(f) for f in frames)
    w = len(frames[0][0])
    blank = transparent[0] * w
    out = []
    for f in frames:
        d = target - bottom(f)
        out.append(([blank] * d + list(f))[:len(f)] if d > 0 else list(f))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mascot_json")
    ap.add_argument("out_dir")
    ap.add_argument("--target-height", type=int, default=DEFAULT_TARGET_H)
    ap.add_argument("--scale", type=float, default=None,
                    help="brand.yaml mascot.scale — overrides the file's own scale")
    ap.add_argument("--no-anchor", action="store_true",
                    help="disable auto feet-anchoring of idle/type/sleep")
    args = ap.parse_args()
    mascot = load_mascot(args.mascot_json)
    validate_mascot(mascot)
    if args.scale is not None:
        if args.scale <= 0:
            sys.exit("render-mascot: --scale must be > 0")
        mascot["scale"] = args.scale
    transparent = [ch for ch, slot in mascot["legend"].items() if slot is None]
    for anim, frames in mascot["animations"].items():
        if not args.no_anchor and anim in ANCHOR_EMOTIONS and transparent and len(frames) > 1:
            frames = anchor_feet(frames, transparent)
        n = render_animation(mascot, anim, frames,
                             os.path.join(args.out_dir, anim),
                             target_h=args.target_height)
        print(f"  mascot {anim}: {n} frames")
    with open(os.path.join(args.out_dir, "mascot-meta.json"), "w",
              encoding="utf-8") as f:
        json.dump({"fps": mascot["fps"], "name": mascot["name"]}, f)


if __name__ == "__main__":
    main()
