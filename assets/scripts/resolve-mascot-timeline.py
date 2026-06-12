"""resolve-mascot-timeline.py — stage-2 mascot emotion timeline (spec §4).

Merges the stage-1 mascot_plan stub with post-capture truth: the final
normalized clip duration (ffprobe) and the capture's .events.json windows
(waitToast / speed). Writes <clip>.mascot.json for overlay-mascot.py.

  python resolve-mascot-timeline.py <scene-plan.json> <scene-id>

resolve_timeline()/toast_emotion() are the pure, unit-tested core.

Sidecar schema from record-browser.mjs (normalized in main() before passing
to the pure core):
  { output, viewport, trimStart,
    events: [{ label, start, end, speed, zoom }] }
  label == "waitToast" iff the action was a waitToast step.
  speed > 1 means the action carried a speed-ramp directive.
The normalization maps these to {kind, at, until, text?} for resolve_timeline().
"""
import json
import os
import re
import subprocess
import sys

ERROR_TOAST = re.compile(r"error|fail|invalid|denied", re.IGNORECASE)


def toast_emotion(text):
    return "panic" if ERROR_TOAST.search(text or "") else "point"


def _fill(timeline, base_emotion, duration):
    """Sort event segments, clamp to [0, duration], fill gaps with base_emotion."""
    segs = sorted((s for s in timeline if s["at"] < duration), key=lambda s: s["at"])
    out, cursor = [], 0.0
    for s in segs:
        at, until = max(0.0, s["at"]), min(duration, s["until"])
        if until <= at:
            continue
        if until <= cursor:
            continue
        at = max(at, cursor)
        if at > cursor:
            out.append({"at": cursor, "until": at, "emotion": base_emotion})
        out.append({"at": at, "until": until, "emotion": s["emotion"]})
        cursor = until
    if cursor < duration:
        out.append({"at": cursor, "until": duration, "emotion": base_emotion})
    return out


def resolve_timeline(stub, duration, events=None, layout=None, half_duration=None):
    if not stub.get("enabled"):
        return []
    # before_after sequential: two halves, no event merge (the halves were
    # composed from separately-captured clips; their events don't map 1:1).
    if "before" in stub:
        split = min(half_duration, duration) if half_duration else duration / 2.0
        if split >= duration:
            return [{"at": 0.0, "until": duration, "emotion": stub["before"]}]
        return [
            {"at": 0.0, "until": split, "emotion": stub["before"]},
            {"at": split, "until": duration, "emotion": stub["after"]},
        ]
    base = stub.get("emotion", "idle")
    windows = []
    for ev in events or []:
        if ev.get("until") is None or ev.get("at") is None:
            continue
        if ev.get("kind") == "waitToast":
            windows.append({"at": ev["at"], "until": ev["until"],
                            "emotion": toast_emotion(ev.get("text"))})
        elif ev.get("kind") == "speed":
            windows.append({"at": ev["at"], "until": ev["until"], "emotion": "sleep"})
    return _fill(windows, base, duration)


def _normalize_sidecar_events(raw_events):
    """Convert record-browser.mjs event format to resolve_timeline()'s {kind,at,until,text?}.

    record-browser.mjs writes:
      { label: str, start: float, end: float, speed: number, zoom: any }
    where label == "waitToast" for waitToast actions, and speed > 1 for speed-ramp actions.
    Note: a single event can be both a waitToast AND carry speed > 1; we emit both windows
    so the timeline captures both semantics (speed-ramp wins visually in cut-clip, but the
    mascot should show panic/point for the toast, not sleep).
    """
    normalized = []
    for ev in raw_events:
        at, until = ev.get("start"), ev.get("end")
        if at is None or until is None or until <= at:
            continue
        label = ev.get("label", "")
        speed = ev.get("speed", 1)
        is_toast = ev.get("kind") == "waitToast" or label == "waitToast"
        if is_toast:
            normalized.append({"kind": "waitToast", "at": at, "until": until,
                                "text": ev.get("text", "")})
        if speed and speed > 1:
            normalized.append({"kind": "speed", "at": at, "until": until})
    return normalized


def _probe_duration(path):
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path])
    return float(out.decode().strip())


def main(argv):
    if len(argv) != 3:
        sys.exit("usage: python resolve-mascot-timeline.py <scene-plan.json> <id>")
    plan_path, sid = argv[1], argv[2]
    with open(plan_path, encoding="utf-8") as f:
        entry = next((s for s in json.load(f)["scenes"] if s["id"] == sid), None)
    if entry is None:
        sys.exit(f"no scene '{sid}' in {plan_path}")
    stub = entry.get("mascot_plan", {"enabled": False})
    clip = entry["mp4"]
    # Probe the pristine pre-overlay capture when it exists (build-scenes.sh keeps
    # it at <mp4>.capture.mp4); $mp4 itself may hold last build's overlaid clip.
    probe_src = clip + ".capture.mp4" if os.path.exists(clip + ".capture.mp4") else clip
    duration = _probe_duration(probe_src)
    events = None
    events_path = probe_src + ".events.json"   # capture sidecar, if the recorder wrote one
    if not os.path.exists(events_path):
        events_path = clip + ".events.json"
    if os.path.exists(events_path):
        with open(events_path, encoding="utf-8") as f:
            raw = json.load(f)
        # Normalize from record-browser.mjs format {label,start,end,speed,zoom}
        # to the {kind,at,until,text?} format expected by resolve_timeline().
        events = _normalize_sidecar_events(raw.get("events", []))
    tl = resolve_timeline(stub, duration, events=events,
                          layout=entry.get("layout"),
                          half_duration=entry.get("half_duration"))
    out = probe_src + ".mascot.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"stub": stub, "duration": duration, "timeline": tl}, f, indent=2)
    print(f"  mascot timeline {sid}: {len(tl)} segments -> {out}")


if __name__ == "__main__":
    main(sys.argv)
