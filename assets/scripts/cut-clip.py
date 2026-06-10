#!/usr/bin/env python3
"""cut-clip.py — focus a recorded browser clip using its events sidecar.

record-browser.mjs writes `<clip>.events.json` describing each action's time span,
playback speed, and optional zoom focal point. This applies them to the clip:

  - speed-ramp dead time (a `wait` over a slow load) so no spinner lingers
  - Ken-Burns-zoom onto the region that changed (a toast corner, an edited field)

so the viewer always sees the relevant part of the UI, full-frame. It is a no-op
(leaves the clip untouched, exit 0) when no action set `speed`/`zoom` — so it is
safe to run after every browser capture.

Usage:
  cut-clip.py <clip.mp4> [--events <path>] [--fps 30]

The timeline + filter graph are built by the pure `build_timeline()` /
`build_filter()` functions so they can be unit-tested without ffmpeg
(see tests/test_cut_clip.py).
"""
import argparse
import json
import os
import subprocess
import sys


def build_timeline(events, duration):
    """Cover [0, duration] with contiguous (start, end, speed, zoom) segments.

    Event spans carry their speed/zoom; gaps between/around them pass through at
    1x with no zoom. Overlapping or out-of-range events are clamped. Pure."""
    segs = []
    cursor = 0.0
    ordered = sorted(
        ({"start": max(0.0, float(e["start"])), "end": min(float(duration), float(e["end"])),
          "speed": float(e.get("speed") or 1) or 1, "zoom": e.get("zoom")}
         for e in events),
        key=lambda e: e["start"],
    )
    for e in ordered:
        start = max(e["start"], cursor)   # clip overlaps against what we've emitted
        end = e["end"]
        if end <= start:
            continue
        if start > cursor:
            segs.append((cursor, start, 1.0, None))   # gap before this event
        segs.append((start, end, e["speed"], e["zoom"]))
        cursor = end
    if cursor < duration:
        segs.append((cursor, float(duration), 1.0, None))
    if not segs:                                       # no usable events at all
        segs = [(0.0, float(duration), 1.0, None)]
    return segs


def zoom_chain(w, h, z, fx, fy):
    """crop to a 1/z window centered on the normalized focal point, then scale back."""
    cw, ch = w / z, h / z
    x = min(max(fx * w - cw / 2, 0), w - cw)
    y = min(max(fy * h - ch / 2, 0), h - ch)
    cw, ch = int(cw // 2 * 2), int(ch // 2 * 2)
    return f"crop={cw}:{ch}:{int(x)}:{int(y)},scale={w}:{h}"


def build_filter(segments, w, h, fps=30):
    """Return (filter_complex, out_label) for the segment list. Pure."""
    parts, labels = [], []
    for i, (start, end, speed, zoom) in enumerate(segments):
        chain = [f"trim={start:.3f}:{end:.3f}"]
        chain.append("setpts=(PTS-STARTPTS)" if speed == 1 else f"setpts=(PTS-STARTPTS)/{speed}")
        if zoom:
            chain.append(zoom_chain(w, h, float(zoom["z"]), float(zoom["fx"]), float(zoom["fy"])))
        chain += [f"fps={fps}", "setsar=1"]
        parts.append(f"[0:v]{','.join(chain)}[v{i}]")
        labels.append(f"[v{i}]")
    concat = "".join(labels) + f"concat=n={len(labels)}:v=1:a=0[outv]"
    return ";".join(parts + [concat]), "[outv]"


def has_work(events):
    """True when any event asks for a non-1 speed or a zoom (else cut is a no-op)."""
    return any((float(e.get("speed") or 1) != 1) or e.get("zoom") for e in events)


def _probe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True,
    ).stdout.strip()
    return float(out) if out else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clip", help="clip mp4 to focus (rewritten in place)")
    ap.add_argument("--events", default=None, help="events sidecar (default: <clip>.events.json)")
    ap.add_argument("--fps", type=int, default=30)
    args = ap.parse_args()

    events_path = args.events or f"{args.clip}.events.json"
    if not os.path.exists(events_path):
        return  # nothing to do — clip stays as recorded

    meta = json.load(open(events_path, encoding="utf-8"))
    events = meta.get("events", [])
    if not has_work(events):
        return  # no speed/zoom requested — leave the clip untouched

    vp = meta.get("viewport", {})
    w, h = int(vp.get("width", 1920)), int(vp.get("height", 1080))
    duration = _probe_duration(args.clip)
    if duration <= 0:
        sys.exit(f"cut-clip: could not read duration of {args.clip}")

    segments = build_timeline(events, duration)
    fc, outlab = build_filter(segments, w, h, args.fps)

    tmp = args.clip + ".cut.mp4"
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", args.clip,
           "-filter_complex", fc, "-map", outlab, "-r", str(args.fps),
           "-c:v", "libx264", "-preset", "slow", "-crf", "18",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", tmp]
    r = subprocess.run(cmd)
    if r.returncode != 0 or not os.path.exists(tmp):
        sys.exit(f"cut-clip: ffmpeg failed focusing {args.clip}")
    os.replace(tmp, args.clip)
    print(f"  focused ({len(segments)} segments) -> {args.clip}")


if __name__ == "__main__":
    main()
