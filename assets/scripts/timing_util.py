"""timing_util -- shared VO/video alignment logic.

Used by check-timing.py (P0-1 safety-net gate) and dry-run-plan.py (P3-1).
Pure functions only -- no ffmpeg, no TTS, no I/O -- so they stay unit-testable.
"""


def speech_end_seconds(words_data):
    """End time (s) of the last spoken word, from vo-words.json data.

    Structure (make-vo.py): {"lines": [{"line_end": float, ...}, ...]}.
    We use the max line_end (= last word start+duration) -- this is the real
    "speech end", which excludes the trailing pause baked into vo.mp3's length.
    Returns 0.0 when there are no lines.
    """
    lines = words_data.get("lines") or []
    if not lines:
        return 0.0
    return max(float(ln["line_end"]) for ln in lines)


def check_alignment(speech_end, video_dur, tail_margin=1.0, epsilon=0.15):
    """Decide whether narration fits inside the video.

    Returns (ok, message). Not ok when the last spoken word ends more than
    `epsilon` seconds past the end of the video -- i.e. narration would be
    silently truncated (the Asistel "cut punchline" bug).

    `tail_margin` is advisory: when ok but the gap is tighter than tail_margin,
    the message flags it so the author can add breathing room.
    """
    overrun = speech_end - video_dur
    if overrun > epsilon:
        msg = (
            f"Voiceover ({speech_end:.1f}s) exceeds video ({video_dur:.1f}s) by "
            f"{overrun:.1f}s -- closing narration will be cut. "
            f"Fix: shorten the script / reduce pause_after, lengthen scenes "
            f"(scene `duration:`), or raise scenes.speedup. "
            f"Override (NOT recommended) with DEMO_ALLOW_TRUNCATE=1."
        )
        return False, msg
    gap = video_dur - speech_end
    if gap < tail_margin:
        return True, (
            f"OK but tight: only {gap:.1f}s of video after the last word "
            f"(< {tail_margin:.1f}s tail margin)."
        )
    return True, f"OK: narration ends {gap:.1f}s before video end."


def predict_video_seconds(raw_durations, speedup=1.0, crossfade=0.6):
    """Predicted final video length from raw scene clip lengths.

    Validated against real builds (spec appendix):
        video = sum(raw) / speedup - (N - 1) * crossfade
    assemble.sh applies setpts=PTS/speedup to EVERY scene, then overlaps
    consecutive scenes by `crossfade` seconds. Returns 0.0 for no scenes.
    """
    raws = list(raw_durations or [])
    n = len(raws)
    if n == 0:
        return 0.0
    return sum(raws) / speedup - (n - 1) * crossfade


def solve_speedup(sigma_raw, vo_target, n, crossfade=0.6, clamp_lo=0.8, clamp_hi=1.4):
    """Auto-fit (P0-1, opt-in): the playback speedup that makes the video just hold
    the narration. Returns (speedup, fits).

    From video = sigma_raw/speedup - (n-1)*crossfade >= vo_target:
        speedup* = sigma_raw / (vo_target + (n-1)*crossfade)   (max speedup that still fits)
    Clamp to [clamp_lo, clamp_hi]. `fits` is False only when even the slowest allowed
    speed can't hold the VO (vo too long) -> caller should warn, not silently truncate.
    """
    denom = vo_target + (n - 1) * crossfade
    if denom <= 0:
        return clamp_hi, True
    star = sigma_raw / denom
    clamped = max(clamp_lo, min(clamp_hi, star))
    fits = clamped <= star + 1e-9  # using clamped speed, is video >= vo_target?
    return clamped, fits


def estimate_vo_seconds(voiceover, wpm=115, leading_offset=0.0, per_line_overhead=0.0):
    """Estimate speech-end time WITHOUT running TTS (for the dry-run plan).

    speech_end ~= total_words / wpm * 60 + sum(internal pause_after)
                  + leading_offset + per_line_overhead * n_lines.
    The final line's pause_after is trailing silence, so it's excluded -- this
    keeps the estimate comparable to speech_end_seconds(). Returns 0.0 if empty.

    `leading_offset` and `per_line_overhead` are calibration terms measured by
    measure_voice_rate() from a real build (see dry-run-plan.py); both default
    to 0.0, which reproduces the original word-rate-only estimate exactly.
    """
    items = list(voiceover or [])
    if not items:
        return 0.0
    total_words = sum(len(str(it.get("text", "")).split()) for it in items)
    internal_pauses = sum(float(it.get("pause_after", 0.0)) for it in items[:-1])
    return (total_words / wpm * 60 + internal_pauses
            + leading_offset + per_line_overhead * len(items))


def measure_voice_rate(words_data, pause_afters):
    """Derive the effective words-per-minute (and, data permitting, a per-line
    overhead term) a real completed TTS run actually spoke at.

    Pure: takes already-loaded vo-words.json data (see speech_end_seconds) plus
    the authored internal pause_after seconds (same convention as
    estimate_vo_seconds -- one per line, excluding the trailing pause). All
    file reading belongs in the caller (make-vo.py writes .build/vo-calibration.json
    from this).

    wpm is fit from the AGGREGATE totals: speaking_seconds = speech_end -
    leading_offset - sum(pause_afters); wpm = total_words / speaking_seconds * 60.
    leading_offset defaults to the first line's line_start when vo-words.json's
    own "leading_offset" key is absent.

    per_line_overhead is a constant-per-line residual (edge-tts segment padding
    that scales with line count, not word count -- see fusion-timing.md D4):
    each line's OWN (line_end - line_start) excludes inter-line pauses, so
    duration_i = words_i/wpm*60 + overhead is measurable per line once wpm is
    known. Needs >=2 lines to be meaningful (a single line has nothing to
    separate the per-line constant from); with fewer it is reported as 0.0.

    Returns a dict: wpm, per_line_overhead, total_words, leading_offset,
    internal_pauses, speech_end, line_count.
    """
    lines = list(words_data.get("lines") or [])
    total_words = sum(len(ln.get("words") or []) for ln in lines)
    leading_offset = float(words_data.get(
        "leading_offset", lines[0]["line_start"] if lines else 0.0))
    internal_pauses = sum(float(p) for p in (pause_afters or []))
    speech_end = max((float(ln["line_end"]) for ln in lines), default=0.0)
    speaking_seconds = speech_end - leading_offset - internal_pauses
    wpm = (total_words / speaking_seconds * 60) if speaking_seconds > 0 else 0.0

    per_line_overhead = 0.0
    if wpm > 0 and len(lines) >= 2:
        residuals = []
        for ln in lines:
            words = len(ln.get("words") or [])
            dur = float(ln["line_end"]) - float(ln["line_start"])
            residuals.append(dur - words / wpm * 60)
        per_line_overhead = sum(residuals) / len(residuals)

    return {
        "wpm": wpm,
        "per_line_overhead": per_line_overhead,
        "total_words": total_words,
        "leading_offset": leading_offset,
        "internal_pauses": internal_pauses,
        "speech_end": speech_end,
        "line_count": len(lines),
    }


def _composite_local_cut(entry, raw_dur):
    """Local (pre-speedup) offset, within a composite scene's own raw on-screen
    footage, where a before_after (layout: sequential) scene visually flips
    BEFORE->AFTER. None when the scene isn't a recognised composite -- in that
    case scene_spans() emits no sub-boundary for it.
    """
    if not entry or entry.get("type") != "before_after":
        return None
    if entry.get("layout", "sequential") != "sequential":
        return None  # side_by_side shows both halves at once -- no temporal cut
    if entry.get("cut_at") is not None:
        return float(entry["cut_at"])
    if entry.get("half_duration") is not None:
        return float(entry["half_duration"])
    return raw_dur / 2.0  # no explicit split authored -- assume an even cut


def scene_spans(raw_durations, speedup=1.0, crossfade=0.6, scene_plan=None):
    """Per-scene (start, end, meta) spans in the assembled, crossfaded timeline.

    Mirrors assemble.sh's chained xfade: each scene plays raw/speedup seconds,
    consecutive scenes overlap by `crossfade`. The final span's end always
    equals predict_video_seconds(raw_durations, speedup, crossfade) -- same
    invariant, restated as a per-scene breakdown instead of just the total.

    scene_plan (optional): the resolved scene-plan.json `scenes` list, same
    order as raw_durations. A `before_after` entry with `layout: sequential`
    gets an EXTRA sub-span for its internal BEFORE->AFTER cut (see
    _composite_local_cut) -- without this, a check that only looks at
    inter-scene boundaries misses cuts that happen INSIDE a scene, which is
    the actual defect this feature exists to catch (brief-timing.md Problem B).

    Each span is a tuple (start, end, meta) where meta marks which of its
    edges are a hard cut rather than a blended crossfade transition (e.g. the
    internal before_after split has no blend -- scene_ownership() must not
    shrink that edge like it does a real inter-scene boundary). Returns []
    for no scenes.
    """
    raws = list(raw_durations or [])
    n = len(raws)
    if n == 0:
        return []
    spans = []
    naive_cursor = 0.0
    prev_end = None
    for i, raw in enumerate(raws):
        dur = raw / speedup
        start = 0.0 if i == 0 else prev_end - crossfade
        end = start + dur
        prev_end = end
        entry = scene_plan[i] if scene_plan and i < len(scene_plan) else None
        local_cut = _composite_local_cut(entry, raw)
        if local_cut is not None and 0.0 < local_cut < raw:
            boundary = naive_cursor + local_cut / speedup
            spans.append((start, boundary, {"hard_right": True}))
            spans.append((boundary, end, {"hard_left": True}))
        else:
            spans.append((start, end, {}))
        naive_cursor += dur
    return spans


def scene_ownership(spans, crossfade=0.6):
    """Per-span 'ownership window' -- the time range a viewer would attribute
    to that (sub-)scene, shrunk by half a crossfade at each BLENDED edge (the
    xfade overlap region genuinely belongs to both neighbours). A span's own
    hard-cut edges (the internal before_after flip scene_spans() inserts, and
    the very first/last edge of the whole video) are never shrunk -- there is
    no blend there.

    Also carries a degeneracy warning (does not raise) when a span is shorter
    than 2*crossfade: the chained xfade would triple-overlap and every
    duration formula in this module would silently be wrong for it.
    """
    spans = list(spans or [])
    n = len(spans)
    tolerance = crossfade / 2.0
    windows = []
    for i, span in enumerate(spans):
        start, end = float(span[0]), float(span[1])
        meta = span[2] if len(span) > 2 else {}
        hard_left = bool(meta.get("hard_left"))
        hard_right = bool(meta.get("hard_right"))
        left_shrink = 0.0 if (i == 0 or hard_left) else tolerance
        right_shrink = 0.0 if (i == n - 1 or hard_right) else tolerance
        dur = end - start
        warning = None
        if dur < 2 * crossfade:
            warning = (
                f"warning: scene span {start:.2f}-{end:.2f}s ({dur:.2f}s) is "
                f"shorter than 2*crossfade ({2 * crossfade:.2f}s) -- the "
                f"chained xfade overlaps itself here; treat this scene's "
                f"timing as unreliable"
            )
        windows.append({
            "index": i,
            "raw_start": start,
            "raw_end": end,
            "start": start + left_shrink,
            "end": end - right_shrink,
            "tolerance": tolerance,
            "warning": warning,
        })
    return windows


def _owning_window(t, ownership):
    for w in ownership:
        if w["raw_start"] <= t < w["raw_end"]:
            return w
    if ownership and t >= ownership[-1]["raw_end"]:
        return ownership[-1]
    return ownership[0] if ownership else None


def check_scene_alignment(lines, ownership, tolerance=None):
    """Flag voiceover lines that overrun the scene window they start in.

    `lines`: vo-words.json-shaped dicts, each needs line_start/line_end (or
    start/end). `ownership`: scene_ownership() output. `tolerance` overrides
    every window's own (crossfade/2) tolerance when given.

    A line is attributed to the window it STARTS in -- that is the scene the
    narration is "about" -- and any part of the line still playing past that
    window's end (or before its start) is the overrun. This reproduces the
    real CON-9725 incident exactly: a bug-description line starting on BEFORE
    footage that bleeds 1.6s into AFTER footage is flagged with overrun 1.6,
    while a tuned line landing within tolerance of the cut is not flagged.

    Returns {"ok": bool, "violations": [...]}. Pure -- no I/O.
    """
    violations = []
    for idx, line in enumerate(lines or []):
        ls = float(line.get("line_start", line.get("start", 0.0)))
        le = float(line.get("line_end", line.get("end", ls)))
        window = _owning_window(ls, ownership)
        if window is None:
            continue
        tol = tolerance if tolerance is not None else window.get("tolerance", 0.0)
        overrun = 0.0
        if le > window["end"] + tol:
            overrun = le - window["end"]
        elif ls < window["start"] - tol:
            overrun = window["start"] - ls
        if overrun > 1e-9:
            violations.append({
                "line_index": idx,
                "text": line.get("text", ""),
                "line_start": ls,
                "line_end": le,
                "window_start": window["start"],
                "window_end": window["end"],
                "overrun": round(overrun, 3),
                "message": (
                    f"line {idx} ({ls:.1f}-{le:.1f}s) overruns its scene "
                    f"window ({window['start']:.1f}-{window['end']:.1f}s) "
                    f"by {overrun:.1f}s"
                ),
            })
    return {"ok": not violations, "violations": violations}
