"""timing_util -- shared VO/video alignment logic.

Used by check-timing.py (P0-1 safety-net gate) and dry-run-plan.py (P3-1).
Pure functions only -- no ffmpeg, no TTS, no I/O -- so they stay unit-testable.
"""
import hashlib


def voiceover_sha(voiceover):
    """Fingerprint of the narration text alone, stored in vo-words.json so a
    later --plan can tell a current measurement from a stale one."""
    joined = "\n".join(str(it.get("text", "")) for it in (voiceover or []))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


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

    When fed measure_voice_rate()'s own output back in, this is conservative
    by one segment's trailing pad, not exact: per_line_overhead is an average
    over all lines, but only the LAST line's trailing pad is missing from
    speech_end (speech_end is last-WORD end, not segment end), and this
    function has no way to withhold just that one line's share of the
    average. The result lands that amount OVER the real speech_end -- safe
    for the P0-1 truncation check this feeds, since it never under-predicts.
    """
    items = list(voiceover or [])
    if not items:
        return 0.0
    total_words = sum(len(str(it.get("text", "")).split()) for it in items)
    internal_pauses = sum(float(it.get("pause_after", 0.0)) for it in items[:-1])
    return (total_words / wpm * 60 + internal_pauses
            + leading_offset + per_line_overhead * len(items))


def measure_voice_rate(words_data, pause_afters, seg_durs=None):
    """Derive the effective words-per-minute (and, data permitting, a per-line
    overhead term) a real completed TTS run actually spoke at.

    Pure: takes already-loaded vo-words.json data (see speech_end_seconds), the
    authored internal pause_after seconds (same convention as
    estimate_vo_seconds -- one per line, excluding the trailing pause), and
    optionally each line's real mp3 SEGMENT duration (make-vo.py already
    computes this per segment via ffprobe -- `seg_dur` -- before this is
    called). All file reading/ffprobe belongs in the caller.

    wpm's fit depends on whether `seg_durs` is available:

    - Without `seg_durs`: wpm is fit from the AGGREGATE totals,
      speaking_seconds = speech_end - leading_offset - sum(pause_afters);
      wpm = total_words / speaking_seconds * 60. This "speaking_seconds"
      already includes whatever segment padding sits inside speech_end --
      there is no independent overhead measurement available yet, so it is
      absorbed into the rate rather than reported separately.
    - With `seg_durs`: wpm is instead fit from PURE speaking time -- the sum
      of each line's own word span (line_end - line_start), excluding
      padding entirely. This keeps wpm and per_line_overhead independent and
      additive, so estimate_vo_seconds's
      `words/wpm*60 + leading + pauses + overhead*n` reconstructs speech_end
      to within one segment's trailing pad, instead of double-counting the
      padding that a speech_end-based wpm already absorbed (grok-review2.md
      finding A). It is not exact: per_line_overhead is an AVERAGE across
      lines, but the last line's own trailing pad is the one term
      speech_end never includes (speech_end is last-WORD end, not segment
      end) and estimate_vo_seconds has no way to single that line out from
      the average, so the reconstruction lands exactly that amount over
      speech_end -- conservative (never truncates), see estimate_vo_seconds.
      NOTE: this makes the reported wpm READ HIGHER than the no-seg_durs
      fit for the same recording -- the two are measuring different things
      (pure articulation rate vs. rate-including-padding) and must not be
      compared as if they were the same quantity.

    leading_offset defaults to the first line's line_start when vo-words.json's
    own "leading_offset" key is absent.

    per_line_overhead is edge-tts's per-segment padding (silence baked into
    each segment mp3 before/after the spoken words, scaling with line count
    rather than word count -- see fusion-timing.md D4), measured as
    seg_dur_i - (line_end_i - line_start_i): the real segment length minus
    that line's own word span. This is an INDEPENDENT measurement (seg_dur
    comes from ffprobe on the actual mp3, not from the wpm fit above) -- unlike
    the previous approach, which fit wpm so total speaking time equalled the
    sum of line durations and then computed residuals against that same fit;
    those residuals summed to zero by construction, so they measured nothing
    (grok-review.md finding 3). Without `seg_durs`, nothing is measured and
    per_line_overhead is reported as 0.0 (never a fabricated identity).

    Returns a dict: wpm, per_line_overhead, total_words, leading_offset,
    internal_pauses, speech_end, line_count.
    """
    lines = list(words_data.get("lines") or [])
    # Count words the same way estimate_vo_seconds does -- str.split() on the
    # authored line text -- not len(ln["words"]), the raw edge-tts
    # WordBoundary token count (finding 2). The two disagree on hyphenated
    # words and contractions (edge-tts emits separate tokens for "well-known"
    # and "can't"'s suffix), which inflates the WordBoundary count relative
    # to split(). A wpm fit against that inflated count reads too high, and
    # estimate_vo_seconds -- which always divides a split()-word count by
    # wpm -- then UNDER-predicts real narration length: the exact
    # silent-truncation failure this whole subsystem exists to catch. Fitting
    # wpm in the same unit estimate_vo_seconds consumes closes that gap.
    # Every real vo-words.json line carries "text" (make-vo.py always writes
    # it -- see all_lines construction); the len(words) fallback only
    # matters for a caller that hands in a words-token list with no text
    # field at all, which never happens in production.
    total_words = sum(
        len(str(ln["text"]).split()) if ln.get("text") else len(ln.get("words") or [])
        for ln in lines
    )
    leading_offset = float(words_data.get(
        "leading_offset", lines[0]["line_start"] if lines else 0.0))
    internal_pauses = sum(float(p) for p in (pause_afters or []))
    speech_end = max((float(ln["line_end"]) for ln in lines), default=0.0)
    speaking_seconds = speech_end - leading_offset - internal_pauses
    wpm = (total_words / speaking_seconds * 60) if speaking_seconds > 0 else 0.0

    per_line_overhead = 0.0
    if seg_durs and len(seg_durs) == len(lines) and lines:
        residuals = []
        word_spans = []
        for ln, seg_dur in zip(lines, seg_durs):
            word_span = float(ln["line_end"]) - float(ln["line_start"])
            word_spans.append(word_span)
            residuals.append(float(seg_dur) - word_span)
        per_line_overhead = sum(residuals) / len(residuals)
        pure_speaking_seconds = sum(word_spans)
        if pure_speaking_seconds > 0:
            wpm = total_words / pure_speaking_seconds * 60

    return {
        "wpm": wpm,
        "per_line_overhead": per_line_overhead,
        "total_words": total_words,
        "leading_offset": leading_offset,
        "internal_pauses": internal_pauses,
        "speech_end": speech_end,
        "line_count": len(lines),
    }


def calibration_paste_lines(measured):
    """Lines make-vo.py prints so an author has everything --plan needs, even
    without vo-calibration.json on disk (grok-review2.md residual 1: a clean
    `.build` -- e.g. a fresh checkout with only brand.yaml committed -- that
    pastes just `wpm:` silently loses leading_offset/per_line_overhead).

    `wpm` and leading offset both have a brand.yaml key (`voice.wpm`,
    `voice.leading_silence` -- see resolve_wpm in dry-run-plan.py, which
    falls back to the latter when no cache entry exists). per_line_overhead
    has no brand.yaml key at all -- it is supplied ONLY by the cache file,
    so this makes that (narrower) limitation explicit instead of letting the
    paste imply nothing but wpm survives a fresh checkout.
    """
    return [
        "  paste into brand.yaml to lock in the rate:",
        "    voice:",
        f"      wpm: {measured['wpm']:.0f}",
        f"      leading_silence: {measured['leading_offset']:.2f}",
        f"  (per-line overhead {measured['per_line_overhead']:.2f}s has no "
        f"brand.yaml key -- keep vo-calibration.json in .build/ so --plan "
        f"can still read it; without that file it defaults to 0.0)",
    ]


def _composite_local_cut(entry, raw_dur, speedup, composite_speedup):
    """Local offset -- in `raw_dur`'s OWN units -- within a composite scene's
    own on-screen footage, where a before_after (layout: sequential) scene
    visually flips BEFORE->AFTER. None when the scene isn't a recognised
    composite -- in that case scene_spans() emits no sub-boundary for it.

    An explicit `cut_at`/`half_duration` is ALWAYS authored in pre-speedup
    source-footage seconds (plan-scenes.py copies the brand.yaml value
    through untouched) regardless of what `raw_dur` itself represents. To
    land in raw_dur's own units it is scaled by `speedup / composite_speedup`:
    when raw_dur is itself pre-speedup (the common case, composite_speedup
    == speedup) this is a no-op. When raw_dur is a POST-speedup measurement
    (e.g. probed from an already-normalized clip, so the caller passes
    speedup=1.0 for the duration math) composite_speedup carries the REAL
    project speedup so the authored value still converts correctly -- see
    scene_spans().

    The no-explicit-split fallback (raw_dur / 2.0) needs no such conversion:
    it is derived FROM raw_dur, so it is already in raw_dur's own units.
    """
    if not entry or entry.get("type") != "before_after":
        return None
    if entry.get("layout", "sequential") != "sequential":
        return None  # side_by_side shows both halves at once -- no temporal cut
    explicit = entry.get("cut_at")
    if explicit is None:
        explicit = entry.get("half_duration")  # plan-scenes.py only ever emits this one
    if explicit is not None:
        return float(explicit) * speedup / composite_speedup
    return raw_dur / 2.0  # no explicit split authored -- assume an even cut


def scene_spans(raw_durations, speedup=1.0, crossfade=0.6, scene_plan=None,
                 composite_speedup=None):
    """Per-scene (start, end, meta) spans in the assembled, crossfaded timeline.

    Mirrors assemble.sh's chained xfade: each scene plays raw/speedup seconds,
    consecutive scenes overlap by `crossfade`. The final span's end always
    equals predict_video_seconds(raw_durations, speedup, crossfade) -- same
    invariant, restated as a per-scene breakdown instead of just the total.

    `raw_durations` / `speedup`: `raw_durations` can be either PRE-speedup
    source-footage seconds (the normal case -- matches predict_video_seconds
    and every caller except the one below) or, if the caller only has
    POST-speedup measured lengths (e.g. probed from .normalized/s{i}.mp4,
    which assemble.sh already divided by speedup before this function ever
    sees them), pass speedup=1.0 so raw/speedup performs no further scaling.

    `composite_speedup` (optional, defaults to `speedup`): a composite
    scene's `cut_at`/`half_duration` (see _composite_local_cut) is ALWAYS
    authored in pre-speedup source-footage seconds, independent of what
    `raw_durations` represents above. When raw_durations is itself
    pre-speedup, composite_speedup == speedup and no separate value is
    needed (the default covers this, and every existing caller). When
    raw_durations is a POST-speedup measurement (speedup=1.0 above), pass
    the REAL project speedup here so the authored cut still converts into
    the same (post-speedup) units as raw_durations -- this is the fix for
    the composite-cut unit mismatch: mixing a pre-speedup half_duration into
    post-speedup durations with no conversion silently misplaces (or, past
    a factor-2 speedup, entirely drops) the internal sub-boundary.

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
    cs = speedup if composite_speedup is None else composite_speedup
    spans = []
    prev_end = None
    for i, raw in enumerate(raws):
        dur = raw / speedup
        start = 0.0 if i == 0 else prev_end - crossfade
        end = start + dur
        prev_end = end
        entry = scene_plan[i] if scene_plan and i < len(scene_plan) else None
        local_cut = _composite_local_cut(entry, raw, speedup, cs)
        if local_cut is not None and 0.0 < local_cut < raw:
            # boundary is relative to this scene's crossfade-shifted `start`,
            # not a naive unshifted cumulative sum -- every scene after the
            # first has already been pulled left by `i * crossfade` worth of
            # overlap with its predecessors, and the internal cut must move
            # with it (see brief-timing.md Problem B / CON evidence sampling
            # the real render frame-by-frame).
            boundary = start + local_cut / speedup
            spans.append((start, boundary, {"hard_right": True}))
            spans.append((boundary, end, {"hard_left": True}))
        elif local_cut is not None:
            # entry WAS a recognised composite before_after/sequential scene
            # (that's the only way _composite_local_cut returns non-None) but
            # the converted local_cut fell outside this scene's own raw
            # length -- typically an authored half_duration that no longer
            # fits once speedup pushes the scene's real on-screen length
            # down (finding 3). Dropping the sub-boundary here is still
            # correct (a negative-length sub-span would be nonsensical), but
            # silently is not: this is exactly the kind of internal cut
            # Problem B exists to catch, so surface it as a warning the
            # caller can print (see scene_ownership()).
            spans.append((start, end, {"warning": (
                f"warning: composite cut at scene {i + 1} ({start:.2f}-{end:.2f}s) "
                f"fell out of range (local_cut={local_cut:.2f}s, raw={raw:.2f}s) "
                f"and was dropped -- the internal before/after boundary is not "
                f"being checked for this scene"
            )}))
        else:
            spans.append((start, end, {}))
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
        # A dropped-composite-cut warning (scene_spans(), finding 3) travels
        # in span meta, not computed here -- carry it through so the caller
        # (check-timing.py) only has to check one place. Degeneracy below can
        # co-occur with it; keep both instead of one clobbering the other.
        warning = meta.get("warning")
        if dur < 2 * crossfade:
            degeneracy_warning = (
                f"warning: scene span {start:.2f}-{end:.2f}s ({dur:.2f}s) is "
                f"shorter than 2*crossfade ({2 * crossfade:.2f}s) -- the "
                f"chained xfade overlaps itself here; treat this scene's "
                f"timing as unreliable"
            )
            warning = f"{warning}; {degeneracy_warning}" if warning else degeneracy_warning
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
    footage that bleeds into AFTER footage past the 21.4s cut is flagged with
    overrun 2.2 (line ends at 23.6s), while a tuned line landing within
    tolerance of the cut is not flagged.

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
