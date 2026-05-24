"""autofit.py — P0-1 (opt-in): adjust scenes.speedup so the video holds the voiceover.

Runs AFTER make-vo (real VO length) and build-scenes (real clip durations), BEFORE
assemble. Computes the speedup that makes video >= speech_end + tail_margin and writes it
back to config.json (subs.speedup) for assemble.sh. If it can't fit within the clamp, it
warns and leaves speedup unchanged (mix-final's timing gate still prevents shipping a
truncated video). Only invoked when scenes.autofit is true (build.sh gates this).
"""
import json
import os
import shutil
import subprocess
import sys

import timing_util

CONFIG = os.environ.get("DEMO_CONFIG", "config.json")
PLAN = os.environ.get("DEMO_PLAN", "scene-plan.json")
TAIL_MARGIN = 1.0


def _probe(path):
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path,
    ])
    return float(out.decode().strip())


def main():
    cfg = json.load(open(CONFIG, encoding="utf-8"))
    plan = json.load(open(PLAN, encoding="utf-8"))["scenes"]
    words = json.load(open("vo-words.json", encoding="utf-8"))

    speech_end = timing_util.speech_end_seconds(words)
    crossfade = float(cfg.get("subs", {}).get("crossfade", 0.6))
    old = float(cfg.get("subs", {}).get("speedup", 1.20))

    sigma = 0.0
    for s in plan:
        mp4 = s["mp4"]
        if not os.path.exists(mp4):
            sys.exit(f"autofit: missing scene clip {mp4} -- run build-scenes first")
        sigma += _probe(mp4)
    n = len(plan)

    vo_target = speech_end + TAIL_MARGIN
    sp, fits = timing_util.solve_speedup(sigma, vo_target, n, crossfade)

    if not fits:
        print(f"  autofit: can't fit narration (ends {speech_end:.1f}s + {TAIL_MARGIN:.1f}s tail) "
              f"within speed clamp [0.8,1.4] (raw {sigma:.1f}s, {n} scenes). Leaving speedup {old}. "
              f"Shorten the script or lengthen scenes; mix-final will gate truncation.")
        return 0

    video = sigma / sp - (n - 1) * crossfade
    cfg["subs"]["speedup"] = round(sp, 4)
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    # assemble's .normalized cache is mtime-only (not speed-aware) -> bust it so scenes
    # re-normalize at the new speed.
    shutil.rmtree(".normalized", ignore_errors=True)
    print(f"  autofit: speedup {old} -> {sp:.3f} (raw {sigma:.1f}s, narration ends {speech_end:.1f}s, "
          f"~video {video:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
