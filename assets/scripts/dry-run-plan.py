"""dry-run-plan.py -- P3-1 fast pre-flight (no TTS, no capture, no encode).

Estimates voiceover length from word count (~115 wpm) and, when every scene
declares a `duration:`, predicts the final video length via the validated model
(timing_util.predict_video_seconds). Prints a per-scene table and a PASS/WARN
verdict so the P0-1 truncation risk surfaces in ~1s, before any heavy work.

  python dry-run-plan.py            # reads config.json + scene-plan.json (.build)
"""
import json
import os
import sys

import timing_util

CONFIG = os.environ.get("DEMO_CONFIG", "config.json")
PLAN = os.environ.get("DEMO_PLAN", "scene-plan.json")


CALIBRATION_CACHE = "vo-calibration.json"


def _safe_float(value, default=0.0):
    """float() that tolerates missing/None/non-numeric cache values instead of
    raising -- a hand-edited or partially-written vo-calibration.json must
    degrade gracefully, never crash --plan (finding 6)."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _cached_wpm(entry):
    """Validate a calibration-cache wpm value. None if missing, non-numeric,
    or <= 0 -- a null or zero wpm must never reach estimate_vo_seconds, where
    it would crash (float(None)) or divide by zero (finding 6)."""
    if not entry:
        return None
    wpm = _safe_float(entry.get("wpm"), default=None)
    return wpm if wpm and wpm > 0 else None


def resolve_wpm(cfg):
    """Which wpm --plan should use, and where it came from.

    Resolution order (fusion-timing.md Decision/A): explicit voice.wpm always
    wins > a calibration-cache hit for this exact (voice_id, rate) > the
    uncalibrated 115 default. --plan prints the source so a stale/absent
    cache is never mistaken for a calibrated estimate.

    The leading_offset / per_line_overhead calibration terms come from the
    cache entry for this exact (voice_id, rate) whenever one exists -- even
    on the explicit-wpm path. Pinning voice.wpm (our own recommended
    workflow, printed by make-vo.py) only overrides the RATE; it says nothing
    about leading silence or per-segment padding, and forcing those to 0.0
    made following our advice strictly worse than leaving the cache alone
    (finding 4).

    Without a cache entry (fresh checkout, no .build/vo-calibration.json),
    leading_offset falls back to voice.leading_silence -- a real, documented
    brand.yaml key (see brand-config.md, read by make-vo.py as
    LEADING_OFFSET_SEC) -- instead of a bare 0.0. per_line_overhead has no
    such brand.yaml key (it's segment padding, only ever measured from a
    real build), so it stays 0.0 until a cache entry exists.

    Returns (wpm, leading_offset, per_line_overhead, source_label).
    """
    voice_cfg = cfg.get("voice", {})
    voice_id = voice_cfg.get("voice_id", "en-US-AndrewNeural")
    rate = voice_cfg.get("rate", "+0%")

    entry = None
    if os.path.exists(CALIBRATION_CACHE):
        try:
            cache = json.load(open(CALIBRATION_CACHE, encoding="utf-8"))
        except (OSError, ValueError):
            cache = {}
        entry = cache.get(f"{voice_id}|{rate}")

    if entry:
        cached_leading = _safe_float(entry.get("leading_offset"))
        cached_overhead = _safe_float(entry.get("per_line_overhead"))
    else:
        # Same default make-vo.py itself uses for LEADING_OFFSET_SEC.
        cached_leading = _safe_float(voice_cfg.get("leading_silence"), default=0.2)
        cached_overhead = 0.0

    explicit = voice_cfg.get("wpm")
    if explicit is not None:
        explicit_wpm = _safe_float(explicit, default=None)
        if explicit_wpm and explicit_wpm > 0:
            source = "explicit voice.wpm"
            if entry:
                source += " (+ cached leading offset/overhead for this voice/rate)"
            return explicit_wpm, cached_leading, cached_overhead, source
        # An explicit voice.wpm <= 0 is the same crash class as a cached
        # zero/negative wpm (finding 6): it would reach estimate_vo_seconds
        # and either divide by zero or produce a nonsensical estimate. It
        # must still carry cached_leading/cached_overhead (finding 1) --
        # only the RATE is invalid, not the leading-silence/overhead terms.
        return (115.0, cached_leading, cached_overhead,
                "uncalibrated default (115 wpm) -- voice.wpm invalid")

    cached_wpm = _cached_wpm(entry)
    if cached_wpm is not None:
        return cached_wpm, cached_leading, cached_overhead, "calibration cache"

    if entry is not None:
        # entry exists for this voice/rate but its wpm is missing/invalid --
        # don't crash or silently divide by zero downstream, label it
        # clearly. Still carry that entry's own leading_offset/overhead
        # (finding 1): only the wpm field in it is unusable.
        return (115.0, cached_leading, cached_overhead,
                "uncalibrated default (115 wpm) -- cached wpm invalid")

    # No cache entry at all -- the common case (fresh checkout, nothing built
    # yet). cached_leading already fell back to voice.leading_silence (or its
    # 0.2 default) above; return it rather than discarding it (finding 1).
    return 115.0, cached_leading, cached_overhead, "uncalibrated default (115 wpm)"


def measured_vo(cfg, path="vo-words.json"):
    """(speech_end_seconds, source) from a vo-words.json that matches the
    current voiceover, else None so the caller falls back to the estimate.

    A file written by make-vo.py carries script_sha; older files are trusted
    only when their line count matches the voiceover."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    voiceover = cfg.get("voiceover", [])
    lines = data.get("lines") or []
    sha = data.get("script_sha")
    if sha:
        if sha != timing_util.voiceover_sha(voiceover):
            return None
        source = f"measured from {path} ({len(lines)} lines)"
    else:
        if len(lines) != len(voiceover):
            return None
        source = f"measured from {path} ({len(lines)} lines, unverified, no script_sha)"
    return timing_util.speech_end_seconds(data), source


def mascot_note_for(entry):
    """Return a short mascot annotation string for a plan entry, or ''."""
    m = entry.get("mascot_plan", {})
    if not m.get("enabled"):
        return ""
    char = m.get("character", "octopus")
    kf = m.get("keyframes")
    if kf:
        return f"  mascot: {char} ({len(kf)} keyframes)"
    emo = m.get("emotion") or f"{m.get('before')}->{m.get('after')}"
    return f"  mascot: {char} ({emo})"


def main():
    if not os.path.exists(CONFIG):
        sys.exit(f"dry-run: missing {CONFIG} -- run apply-brand.py first")
    if not os.path.exists(PLAN):
        sys.exit(f"dry-run: missing {PLAN} -- run plan-scenes.py first")

    cfg = json.load(open(CONFIG, encoding="utf-8"))
    plan = json.load(open(PLAN, encoding="utf-8"))["scenes"]

    subs = cfg.get("subs", {})
    speedup = float(subs.get("speedup", 1.20))
    crossfade = float(subs.get("crossfade", 0.6))
    wpm, leading_offset, per_line_overhead, wpm_source = resolve_wpm(cfg)

    vo_est = timing_util.estimate_vo_seconds(
        cfg.get("voiceover", []), wpm=wpm,
        leading_offset=leading_offset, per_line_overhead=per_line_overhead)
    measured = measured_vo(cfg)
    if measured:
        vo_est, vo_source = measured
    else:
        vo_source = "estimated from word count, no TTS"
    n = len(plan)

    print(f"\n  Dry run -- {n} scenes, speedup {speedup}x, crossfade {crossfade}s, "
          f"~{wpm:.0f} wpm ({wpm_source})\n")
    print(f"  {'scene':<22} {'type':<16} {'raw dur':>9} {'~final':>9}")
    print(f"  {'-'*22} {'-'*16} {'-'*9} {'-'*9}")

    raws = []
    all_pinned = True
    for s in plan:
        name = s.get("name", s["id"])
        dur = s.get("duration")
        if dur is None:
            all_pinned = False
            raw_s, fin_s = "  (auto)", "        ?"
        else:
            raws.append(float(dur))
            raw_s = f"{float(dur):>7.2f}s"
            fin_s = f"{float(dur)/speedup:>7.2f}s"
        print(f"  {name:<22} {s['type']:<16} {raw_s:>9} {fin_s:>9}{mascot_note_for(s)}")

    print(f"\n  Voiceover length: {vo_est:.1f}s ({vo_source})")

    if all_pinned and n >= 1:
        video = timing_util.predict_video_seconds(raws, speedup, crossfade)
        ok, msg = timing_util.check_alignment(vo_est, video)
        verdict = "PASS" if ok else "WARN"
        print(f"  Predicted video length:      ~{video:.1f}s")
        print(f"\n  [{verdict}] {msg}\n")
        return 0 if ok else 2

    missing = [s.get("name", s["id"]) for s in plan if s.get("duration") is None]
    print(f"  Predicted video length:      indeterminate "
          f"({len(missing)} scene(s) without `duration:`: {', '.join(missing)})")
    print("  Tip: add `duration:` to those scenes for deterministic alignment, "
          "or run a full build -- mix-final.sh still gates truncation.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
