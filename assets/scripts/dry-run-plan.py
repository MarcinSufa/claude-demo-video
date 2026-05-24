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
    wpm = float(cfg.get("voice", {}).get("wpm", 115))

    vo_est = timing_util.estimate_vo_seconds(cfg.get("voiceover", []), wpm=wpm)
    n = len(plan)

    print(f"\n  Dry run -- {n} scenes, speedup {speedup}x, crossfade {crossfade}s, ~{wpm:.0f} wpm\n")
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
        print(f"  {name:<22} {s['type']:<16} {raw_s:>9} {fin_s:>9}")

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
