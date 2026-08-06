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


def resolve_wpm(cfg):
    """Which wpm --plan should use, and where it came from.

    Resolution order (fusion-timing.md Decision/A): explicit voice.wpm always
    wins > a calibration-cache hit for this exact (voice_id, rate) > the
    uncalibrated 115 default. --plan prints the source so a stale/absent
    cache is never mistaken for a calibrated estimate.

    Returns (wpm, leading_offset, per_line_overhead, source_label).
    """
    voice_cfg = cfg.get("voice", {})
    explicit = voice_cfg.get("wpm")
    if explicit is not None:
        return float(explicit), 0.0, 0.0, "explicit voice.wpm"

    voice_id = voice_cfg.get("voice_id", "en-US-AndrewNeural")
    rate = voice_cfg.get("rate", "+0%")
    if os.path.exists(CALIBRATION_CACHE):
        try:
            cache = json.load(open(CALIBRATION_CACHE, encoding="utf-8"))
        except (OSError, ValueError):
            cache = {}
        entry = cache.get(f"{voice_id}|{rate}")
        if entry:
            return (float(entry.get("wpm", 115)),
                    float(entry.get("leading_offset", 0.0)),
                    float(entry.get("per_line_overhead", 0.0)),
                    "calibration cache")

    return 115.0, 0.0, 0.0, "uncalibrated default (115 wpm)"


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

    print(f"\n  Voiceover estimate (no TTS): ~{vo_est:.1f}s")

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
