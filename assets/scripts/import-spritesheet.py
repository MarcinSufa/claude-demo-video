"""import-spritesheet.py — import a sprite sheet + Aseprite-style JSON into the
mascot frames_dir contract the overlay consumes.

Lets any external art source (libresprite/Aseprite export, pixel-plugin, a hand
sheet) feed the pipeline without our pixel-grid format: we slice the sheet by
the JSON's frame rects + frameTags and write <out>/<anim>/f_%03d.png +
<out>/mascot-meta.json — exactly what render-mascot.py emits.

  python import-spritesheet.py <sheet.png> <frames.json> <out_dir> [--fps N] [--name X]

parse_sheet_plan() is the pure, unit-tested core; cropping is ffmpeg glue.
Supports Aseprite "array" frames (list) and "hash" frames (dict, insertion order).
"""
import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mascot_data import ensure_emotion_dirs  # noqa: E402


def _frames_list(doc):
    """Normalise Aseprite frames (array or hash) to an ordered list of frame dicts."""
    fr = doc["frames"]
    if isinstance(fr, list):
        return fr
    # hash form: dict keyed by filename; dict preserves insertion order
    return list(fr.values())


def parse_sheet_plan(doc, fps_override=None, name=None):
    """Aseprite JSON -> {fps, name, anims: {tag_name: [rect, ...]}} where rect is
    (x, y, w, h). Requires meta.frameTags. fps derived from the first tagged
    frame's duration (ms), overridable."""
    frames = _frames_list(doc)
    meta = doc.get("meta", {})
    tags = meta.get("frameTags")
    if not tags:
        raise ValueError("no meta.frameTags — tag your animations (idle/walk/...) in the export")

    def rect(f):
        r = f["frame"]
        return (r["x"], r["y"], r["w"], r["h"])

    anims = {}
    first_dur = None
    for t in tags:
        a, b = t["from"], t["to"]
        if a < 0 or b >= len(frames) or a > b:
            raise ValueError(f"tag '{t.get('name')}' range {a}..{b} out of bounds (frames={len(frames)})")
        if t["name"] in anims:
            print(f"  WARNING: duplicate frameTag '{t['name']}' — last one wins", file=sys.stderr)
        anims[t["name"]] = [rect(frames[i]) for i in range(a, b + 1)]
        if first_dur is None:
            first_dur = frames[a].get("duration", 0)

    if fps_override:
        fps = float(fps_override)
    elif first_dur:
        fps = round(1000.0 / first_dur, 3)
    else:
        fps = 7.0
    return {"fps": fps, "name": name or meta.get("image", "imported"), "anims": anims}


def _crop(sheet, rect, out_png):
    x, y, w, h = rect
    subprocess.check_call([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", sheet, "-vf", f"crop={w}:{h}:{x}:{y}", "-frames:v", "1", out_png])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sheet")
    ap.add_argument("json")
    ap.add_argument("out_dir")
    ap.add_argument("--fps", type=float, default=None)
    ap.add_argument("--name", default=None)
    a = ap.parse_args()
    with open(a.json, encoding="utf-8") as f:
        doc = json.load(f)
    try:
        plan = parse_sheet_plan(doc, a.fps, a.name)
    except (ValueError, KeyError) as e:
        sys.exit(f"import-spritesheet: {e}")
    os.makedirs(a.out_dir, exist_ok=True)
    for anim, rects in plan["anims"].items():
        d = os.path.join(a.out_dir, anim)
        os.makedirs(d, exist_ok=True)
        for i, rect in enumerate(rects, 1):
            _crop(a.sheet, rect, os.path.join(d, f"f_{i:03d}.png"))
        print(f"  import {anim}: {len(rects)} frames")
    # external sheets may not tag every emotion the scenes use — fill the gaps
    # from idle so the overlay never hard-fails on a missing emotion dir.
    ensure_emotion_dirs(a.out_dir)
    with open(os.path.join(a.out_dir, "mascot-meta.json"), "w", encoding="utf-8") as f:
        json.dump({"fps": plan["fps"], "name": plan["name"]}, f)
    print(f"  imported -> {a.out_dir} (fps {plan['fps']})")


if __name__ == "__main__":
    main()
