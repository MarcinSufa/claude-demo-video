"""render-mascot.py — render mascot.json animations to transparent PNG frames.

  python render-mascot.py <mascot.json> <out_dir> [--target-height 140]

Writes <out_dir>/<anim>/f_%03d.png for every animation. PNGs come out of
ffmpeg (rawvideo RGBA piped in), so there is no Pillow dependency.
grid_to_rgba()/upscale_factor() are the pure, unit-tested core.
"""
import argparse
import os
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
    proc.stdin.write(first)
    for frame in frames[1:]:
        buf, _, _ = grid_to_rgba(frame, legend, palette, cell, overrides)
        proc.stdin.write(buf)
    proc.stdin.close()
    if proc.wait() != 0:
        sys.exit(f"render-mascot: ffmpeg failed for animation '{anim}'")
    return len(frames)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mascot_json")
    ap.add_argument("out_dir")
    ap.add_argument("--target-height", type=int, default=DEFAULT_TARGET_H)
    args = ap.parse_args()
    mascot = load_mascot(args.mascot_json)
    validate_mascot(mascot)
    for anim, frames in mascot["animations"].items():
        n = render_animation(mascot, anim, frames,
                             os.path.join(args.out_dir, anim),
                             target_h=args.target_height)
        print(f"  mascot {anim}: {n} frames")


if __name__ == "__main__":
    main()
