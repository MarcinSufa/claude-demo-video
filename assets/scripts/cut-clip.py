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
import math
import os
import subprocess
import sys


def _num(v, default=None):
    """Parse v as a finite float; return default for None/non-numeric/NaN/inf."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return f if math.isfinite(f) else default


def _sane_speed(speed):
    """Clamp a (user-authored) playback speed to a positive finite float; default 1.0."""
    f = _num(speed, 1.0)
    return f if f > 0 else 1.0


def _sane_zoom(zoom):
    """Validate a user-authored zoom → {z, fx, fy} (z>1, fx/fy clamped to 0..1), else None.

    Drops anything that isn't a dict carrying a finite z>1 (z<=1 is a full-frame no-op),
    so a malformed/edge zoom object is ignored rather than aborting the build."""
    if not isinstance(zoom, dict):
        return None
    z = _num(zoom.get("z"))
    if z is None or z <= 1:
        return None
    fx = min(max(_num(zoom.get("fx"), 0.5), 0.0), 1.0)
    fy = min(max(_num(zoom.get("fy"), 0.5), 0.0), 1.0)
    return {"z": z, "fx": fx, "fy": fy}


def build_timeline(events, duration):
    """Cover [0, duration] with contiguous (start, end, speed, zoom) segments.

    Event spans carry their speed/zoom; gaps between/around them pass through at
    1x with no zoom. Overlapping or out-of-range events are clamped. Pure."""
    segs = []
    cursor = 0.0
    ordered = sorted(
        ({"start": max(0.0, float(e["start"])), "end": min(float(duration), float(e["end"])),
          "speed": _sane_speed(e.get("speed")), "zoom": e.get("zoom")}
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
    """crop to a 1/z window centered on the normalized focal point, then scale back.

    Clamps the window to an even-pixel rect that always fits inside the frame, so
    edge inputs (tiny/huge z, focal point in a corner) still yield a valid filter."""
    if not z > 0:                       # 0 / negative / NaN → no magnification
        z = 1.0
    cw = min(w, max(2, int((w / z) // 2 * 2)))
    ch = min(h, max(2, int((h / z) // 2 * 2)))
    x = int(min(max(fx * w - cw / 2, 0), w - cw))
    y = int(min(max(fy * h - ch / 2, 0), h - ch))
    return f"crop={cw}:{ch}:{x}:{y},scale={w}:{h}"


def build_filter(segments, w, h, fps=30):
    """Return (filter_complex, out_label) for the segment list. Pure."""
    parts, labels = [], []
    for i, (start, end, speed, zoom) in enumerate(segments):
        speed = _sane_speed(speed)
        zoom = _sane_zoom(zoom)
        chain = [f"trim={start:.3f}:{end:.3f}"]
        chain.append("setpts=(PTS-STARTPTS)" if speed == 1 else f"setpts=(PTS-STARTPTS)/{speed}")
        if zoom:
            chain.append(zoom_chain(w, h, zoom["z"], zoom["fx"], zoom["fy"]))
        chain += [f"fps={fps}", "setsar=1"]
        parts.append(f"[0:v]{','.join(chain)}[v{i}]")
        labels.append(f"[v{i}]")
    concat = "".join(labels) + f"concat=n={len(labels)}:v=1:a=0[outv]"
    return ";".join(parts + [concat]), "[outv]"


def has_work(events):
    """True when any event asks for a non-1 speed or a usable zoom (else cut is a no-op)."""
    return any(_sane_speed(e.get("speed")) != 1 or _sane_zoom(e.get("zoom")) for e in events)


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

    with open(events_path, encoding="utf-8") as f:
        meta = json.load(f)
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
