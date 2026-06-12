"""overlay-mascot.py — composite the rendered mascot onto a finished scene clip.

  python overlay-mascot.py <capture.mp4> <out.mp4> <frames_dir> <timeline.json> [--speedup 1.2]

Runs AFTER cut-clip + normalize (spec §5): the timeline targets the final clip.
One looped PNG-sequence input per distinct emotion; each timeline segment is an
overlay with enable='between(t,A,B)'. anchor_xy()/build_overlay_cmd() are the
pure, unit-tested core.
"""
import argparse
import json
import os
import subprocess
import sys

MARGIN_PX = 24                # side margin from the frame edge
CAPTION_CLEARANCE_PX = 200    # lift above the burned caption band (spec §5)


def anchor_xy(position, video_w, video_h, sprite_w, sprite_h):
    horiz = "right" if position.endswith("right") else "left"
    vert = "top" if position.startswith("top") else "bottom"
    x = video_w - sprite_w - MARGIN_PX if horiz == "right" else MARGIN_PX
    y = MARGIN_PX if vert == "top" else video_h - sprite_h - CAPTION_CLEARANCE_PX
    return x, y


OFFSCREEN_PAD_PX = 4          # how far below the frame "offscreen-bottom" sits
DEFAULT_POSITION = "bottom-right"


def resolve_anchors(timeline, video_w, video_h, sprite_w, sprite_h):
    """Per-segment anchor points resolved from each segment's `position`.

    Plain segments -> one (x, y). Move segments -> ((x0, y0), (x1, y1)) for the
    `move.from` / `move.to` anchors. Pseudo-anchor "offscreen-bottom" keeps the
    home x of the previous real position (or bottom-right) and drops below the
    frame so the sprite slides out of view.
    """
    def named(pos, prev_pos):
        if pos == "offscreen-bottom":
            hx, _ = anchor_xy(prev_pos or DEFAULT_POSITION,
                              video_w, video_h, sprite_w, sprite_h)
            return hx, video_h + OFFSCREEN_PAD_PX
        return anchor_xy(pos, video_w, video_h, sprite_w, sprite_h)

    anchors, prev_pos = [], None
    for seg in timeline:
        pos = seg.get("position", DEFAULT_POSITION)
        if "move" in seg:
            frm, to = seg["move"]["from"], seg["move"]["to"]
            anchors.append((named(frm, prev_pos), named(to, frm)))
        else:
            anchors.append(named(pos, prev_pos))
        if pos != "offscreen-bottom":
            prev_pos = pos
    return anchors


def _segment_xy(seg, anchor):
    """The overlay x/y for one segment: ints for static segments, ffmpeg
    `t`-expressions (quoted) for moves and emotion motion."""
    at, dur = seg["at"], seg["until"] - seg["at"]
    if "move" in seg:
        (x0, y0), (x1, y1) = anchor
        prog = f"clip((t-{at:.3f})/{dur:.3f},0,1)"
        return (f"'{x0}+({x1}-{x0})*{prog}'", f"'{y0}+({y1}-{y0})*{prog}'")
    x, y = anchor
    if seg["emotion"] == "celebrate":   # bounce
        return x, f"'{y}-18*abs(sin((t-{at:.3f})*4))'"
    if seg["emotion"] == "panic":       # shake
        return f"'{x}+4*sin((t-{at:.3f})*18)'", y
    return x, y


def build_overlay_cmd(capture, out, frames_dir, timeline, positions, fps, speedup):
    """Full ffmpeg argv, or None when there is nothing to overlay.

    `positions` is the per-segment anchor list from resolve_anchors()."""
    if not timeline:
        return None
    emotions = []
    for seg in timeline:
        if seg["emotion"] not in emotions:
            emotions.append(seg["emotion"])
    eff_fps = round(fps * speedup, 4)
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", capture]
    for emo in emotions:
        cmd += ["-stream_loop", "-1", "-framerate", str(eff_fps),
                "-i", os.path.join(frames_dir, emo, "f_%03d.png").replace("\\", "/")]
    parts, src = [], "[0:v]"
    for i, seg in enumerate(timeline):
        inp = emotions.index(seg["emotion"]) + 1
        label = f"[v{i}]" if i < len(timeline) - 1 else "[vout]"
        x, y = _segment_xy(seg, positions[i])
        # shortest=1: the looped PNG inputs never EOF; end each stage with the
        # finite main chain or ffmpeg encodes forever.
        parts.append(
            f"{src}[{inp}:v]overlay={x}:{y}:shortest=1:"
            f"enable='between(t,{seg['at']:.3f},{seg['until']:.3f})'{label}")
        src = f"[v{i}]"
    # -shortest: the looped PNG inputs never EOF; bound the output to the capture.
    cmd += ["-filter_complex", ";".join(parts), "-map", "[vout]", "-map", "0:a?",
            "-shortest",
            "-c:v", "libx264", "-preset", "slow", "-crf", "18",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            "-c:a", "copy", out]
    return cmd


def _probe_wh(path):
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "csv=p=0", path])
    w, h = out.decode().strip().split(",")
    return int(w), int(h)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("capture")
    ap.add_argument("out")
    ap.add_argument("frames_dir")
    ap.add_argument("timeline_json")
    ap.add_argument("--speedup", type=float, default=1.0)
    args = ap.parse_args()
    with open(args.timeline_json, encoding="utf-8") as f:
        data = json.load(f)
    tl, stub = data["timeline"], data["stub"]
    if not tl:
        sys.exit(0)  # nothing to do; caller handles the copy
    vw, vh = _probe_wh(args.capture)
    sw, sh = _probe_wh(os.path.join(args.frames_dir, tl[0]["emotion"], "f_001.png"))
    fallback = stub.get("position", DEFAULT_POSITION)
    for seg in tl:
        seg.setdefault("position", fallback)
    positions = resolve_anchors(tl, vw, vh, sw, sh)
    with open(os.path.join(args.frames_dir, "mascot-meta.json"), encoding="utf-8") as f:
        fps = json.load(f)["fps"]
    cmd = build_overlay_cmd(args.capture, args.out, args.frames_dir, tl,
                            positions, fps, args.speedup)
    subprocess.check_call(cmd)
    print(f"  mascot overlaid -> {args.out}")


if __name__ == "__main__":
    main()
