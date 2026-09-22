"""music_plan.py -- turn scene spans into an ElevenLabs Music composition_plan.

Pure functions only -- no ffmpeg, no network. Used by spend-gate.py (estimate)
and make-music-elevenlabs.py (real build) so both agree on the exact plan
shape (and therefore the exact cache/approval key).
"""
import math
import re

FIRST_STYLES = ["sparse intro", "quiet but continuous"]
MIDDLE_STYLES = ["steady build", "room for a narrator"]
LAST_STYLES = ["resolve", "sustained final chord", "clean ending"]

_SIL_START = re.compile(r"silence_start:\s*([-\d.]+)")
_SIL_END = re.compile(r"silence_end:\s*([-\d.]+)")


def _split_long(name, dur_ms):
    """Split a section longer than 120000 ms into even parts (remainder on the last)."""
    if dur_ms <= 120000:
        return [(name, dur_ms)]
    n_parts = math.ceil(dur_ms / 120000)
    base, remainder = divmod(dur_ms, n_parts)
    return [(name, base) for _ in range(n_parts - 1)] + [(name, base + remainder)]


def sections_from_spans(spans, total_s, local_styles=None):
    if total_s < 3:
        raise ValueError("music_plan.sections_from_spans: total_s must be >= 3 seconds")
    spans = list(spans or [])
    if not spans:
        raise ValueError("music_plan.sections_from_spans: spans must be non-empty")
    local_styles = local_styles or {}
    total_ms = round(total_s * 1000)

    names = [s[0] for s in spans]
    n = len(spans)
    # Boundaries = each span's end except the last, rounded to the nearest 0.5s.
    rounded_ends_ms = [round(round(spans[i][2] * 2) / 2 * 1000) for i in range(n - 1)]

    prev = 0
    raw_durations_ms = []
    for cut in rounded_ends_ms + [total_ms]:
        cut = max(prev, min(cut, total_ms))
        raw_durations_ms.append(cut - prev)
        prev = cut
    raw_sections = list(zip(names, raw_durations_ms))

    # Merge sections shorter than 3000ms into the previous section; the first
    # merges forward into the next (no predecessor to absorb it into). The
    # LAST section is never merged away -- dropping it would silently lose the
    # "final chord" position even when the closing scene is brief.
    merged = []
    m = len(raw_sections)
    i = 0
    while i < m:
        name, dur = raw_sections[i]
        is_last = i == m - 1
        if dur < 3000 and not is_last and m > 1:
            if merged:
                merged[-1] = (merged[-1][0], merged[-1][1] + dur)
            else:
                nxt_name, nxt_dur = raw_sections[i + 1]
                merged.append((nxt_name, dur + nxt_dur))
                i += 1
        else:
            merged.append((name, dur))
        i += 1

    final = []
    for name, dur in merged:
        final.extend(_split_long(name, dur))

    n_final = len(final)
    sections = []
    for idx, (name, dur) in enumerate(final):
        if local_styles.get(name) is not None:
            styles = list(local_styles[name])
        elif idx == 0:
            styles = list(FIRST_STYLES)
        elif n_final > 1 and idx == n_final - 1:
            styles = list(LAST_STYLES)
        else:
            styles = list(MIDDLE_STYLES)
        sections.append({
            "section_name": name,
            "positive_local_styles": styles,
            "negative_local_styles": ["silence", "vocals"],
            "duration_ms": dur,
            "lines": [],
        })
    return sections


def _dedup(items):
    seen = []
    for x in items:
        if x not in seen:
            seen.append(x)
    return seen


def composition_plan(music_cfg, sections):
    positive = music_cfg.get("styles") or ["instrumental", "cinematic ambient electronic", "warm analog"]
    negative = _dedup(list(music_cfg.get("negative_styles", [])) + ["vocals", "silence", "drops out"])
    return {
        "positive_global_styles": positive,
        "negative_global_styles": negative,
        "sections": sections,
    }


def find_dropouts(silencedetect_stderr, total_s, head=0.5, tail=3.0):
    events = []
    for line in (silencedetect_stderr or "").splitlines():
        m = _SIL_START.search(line)
        if m:
            events.append(("start", float(m.group(1))))
            continue
        m = _SIL_END.search(line)
        if m:
            events.append(("end", float(m.group(1))))

    gaps = []
    open_start = None
    for kind, t in events:
        if kind == "start":
            open_start = t
        elif kind == "end" and open_start is not None:
            gaps.append((open_start, t))
            open_start = None
    if open_start is not None:
        gaps.append((open_start, total_s))

    tail_start = total_s - tail
    return [(s, e) for s, e in gaps if not (e <= head or s >= tail_start)]
