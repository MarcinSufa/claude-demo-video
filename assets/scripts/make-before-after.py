#!/usr/bin/env python3
"""make-before-after.py — compose a labeled BEFORE/AFTER scene from two clips.

Reads a `before_after` plan entry (emitted by plan-scenes.py) and writes ONE
composed mp4 that the rest of the pipeline (assemble.sh) treats as a single scene:

  - layout: sequential   -> before clip (labeled) then after clip (labeled), concatenated.
  - layout: side_by_side -> the two clips placed side by side, each labeled.

Each half is a *finished* clip referenced by `source` (an external mp4) or
`capture.output` (a clip build-scenes.sh just recorded via record-browser.mjs).
Both halves are scaled+padded to the target frame so they always line up, and a
colored bottom banner is burned in (red = before, green = after by default).

Usage:
  make-before-after.py <entry.json> <out.mp4> [--width 1920] [--height 1080] [--font PATH]

The filter graph is built by the pure `build_filter()` function so it can be
unit-tested without ffmpeg (see tests/test_before_after.py).
"""
import argparse
import json
import os
import subprocess
import sys

# Default banner colors (ffmpeg 0xRRGGBB): before = red, after = green.
BEFORE_COLOR = "0xb91c1c"
AFTER_COLOR = "0x15803d"

FONT_CANDIDATES = [
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
]


def find_font(explicit=None):
    """Pick a usable .ttf for drawtext (explicit wins, else first existing candidate)."""
    if explicit and os.path.exists(explicit):
        return explicit
    for c in FONT_CANDIDATES:
        if os.path.exists(c):
            return c
    return None  # drawtext falls back to its default font dir


def half_clip_path(half):
    """Resolve a half's finished clip path: explicit `source`, else `capture.output`."""
    if half.get("source"):
        return half["source"]
    cap = half.get("capture") or {}
    if cap.get("output"):
        return cap["output"]
    raise SystemExit("before_after half needs a 'source' path or a 'capture.output'")


_ASCII_PUNCT = {
    "—": "-", "–": "-", "‒": "-",  # em/en/figure dash
    "‘": "'", "’": "'", "“": '"', "”": '"',  # smart quotes
    "…": "...", " ": " ", "→": "->",
}


def ascii_label(s):
    """Banner labels render through ffmpeg drawtext, whose textfile reader is not
    reliably UTF-8 on Windows. Map common unicode punctuation to ASCII so a label
    like "BEFORE — the bug" shows correctly as "BEFORE - the bug"."""
    for k, v in _ASCII_PUNCT.items():
        s = s.replace(k, v)
    return s.encode("ascii", "ignore").decode("ascii")


def _esc_path(p):
    """Escape a path for use inside a drawtext option value (':' and '\\' are special).
    A Windows path like C:/Fonts/x.ttf becomes C\\:/Fonts/x.ttf."""
    return p.replace("\\", "/").replace(":", "\\:")


def _label_tf(textfile, font, color):
    """drawtext a bottom banner whose text is read from a UTF-8 file (robust on
    Windows for em-dashes / any unicode that `text=` mangles)."""
    fontclause = f"fontfile='{_esc_path(font)}':" if font else ""
    return (
        f"drawtext={fontclause}textfile='{_esc_path(textfile)}':x=(w-text_w)/2:y=h-58:"
        f"fontsize=30:fontcolor=white:box=1:boxcolor={color}@0.9:boxborderw=16"
    )


def _fit(w, h):
    return (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
    )


def build_filter(
    layout,
    width,
    height,
    before_textfile,
    after_textfile,
    font=None,
    half_duration=None,
    before_color=BEFORE_COLOR,
    after_color=AFTER_COLOR,
):
    """Return (filter_complex, out_label). Pure — unit-tested, no ffmpeg needed.

    Input [0:v] is the BEFORE clip, [1:v] is the AFTER clip. Labels are read from
    UTF-8 text files (before_textfile/after_textfile).
    """
    trim = f"trim=duration={float(half_duration)}," if half_duration else ""
    lb = _label_tf(before_textfile, font, before_color)
    la = _label_tf(after_textfile, font, after_color)
    if layout == "side_by_side":
        hw = width // 2
        fb, fa = _fit(hw, height), _fit(hw, height)
        fc = (
            f"[0:v]{trim}{fb},{lb},fps=30,setpts=PTS-STARTPTS[b];"
            f"[1:v]{trim}{fa},{la},fps=30,setpts=PTS-STARTPTS[a];"
            f"[b][a]hstack=inputs=2[v]"
        )
    elif layout == "sequential":
        fb, fa = _fit(width, height), _fit(width, height)
        fc = (
            f"[0:v]{trim}{fb},{lb},fps=30,setpts=PTS-STARTPTS[b];"
            f"[1:v]{trim}{fa},{la},fps=30,setpts=PTS-STARTPTS[a];"
            f"[b][a]concat=n=2:v=1:a=0[v]"
        )
    else:
        raise SystemExit(f"before_after: unknown layout '{layout}' (sequential|side_by_side)")
    return fc, "[v]"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("entry", help="path to the before_after plan entry JSON")
    ap.add_argument("out", help="output mp4 path")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--font", default=None)
    args = ap.parse_args()

    with open(args.entry, encoding="utf-8") as f:
        entry = json.load(f)

    before = entry["before"]
    after = entry["after"]
    bpath = half_clip_path(before)
    apath = half_clip_path(after)
    for p in (bpath, apath):
        if not os.path.exists(p):
            sys.exit(f"before_after: clip not found: {p}")

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    # Write labels to UTF-8 files so drawtext renders unicode (em-dash etc.) correctly.
    btf = args.out + ".before.txt"
    atf = args.out + ".after.txt"
    with open(btf, "w", encoding="utf-8") as f:
        f.write(ascii_label(before.get("label", "BEFORE")))
    with open(atf, "w", encoding="utf-8") as f:
        f.write(ascii_label(after.get("label", "AFTER")))

    fc, outlab = build_filter(
        entry.get("layout", "sequential"),
        args.width,
        args.height,
        btf,
        atf,
        font=find_font(args.font),
        half_duration=entry.get("half_duration"),
    )
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", bpath, "-i", apath,
        "-filter_complex", fc, "-map", outlab,
        "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p", "-an",
        args.out,
    ]
    r = subprocess.run(cmd)
    for tmp in (btf, atf):
        try:
            os.remove(tmp)
        except OSError:
            pass
    if r.returncode != 0:
        sys.exit(f"ffmpeg failed composing before/after -> {args.out}")
    print(f"  before/after ({entry.get('layout', 'sequential')}) -> {args.out}")


if __name__ == "__main__":
    main()
