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


def estimate_vo_seconds(voiceover, wpm=115):
    """Estimate speech-end time WITHOUT running TTS (for the dry-run plan).

    speech_end ~= total_words / wpm * 60 + sum(internal pause_after).
    The final line's pause_after is trailing silence, so it's excluded -- this
    keeps the estimate comparable to speech_end_seconds(). Returns 0.0 if empty.
    """
    items = list(voiceover or [])
    if not items:
        return 0.0
    total_words = sum(len(str(it.get("text", "")).split()) for it in items)
    internal_pauses = sum(float(it.get("pause_after", 0.0)) for it in items[:-1])
    return total_words / wpm * 60 + internal_pauses
