"""check-timing.py -- P0-1 safety-net gate.

Compares the real speech-end (from vo-words.json) against the assembled video
length and FAILS the build if narration would be silently truncated. Wired into
mix-final.sh just before the audio mux (where the `-t VIDEO_DUR` cut happens).

  python check-timing.py <video.mp4> [vo-words.json]

Exit 0 = fits (prints OK). Exit 1 = narration overruns the video.
Override with env DEMO_ALLOW_TRUNCATE=1 (warns but exits 0).
"""
import json
import os
import subprocess
import sys

import timing_util

# A stale vo-words.json loaded here reads as a correct-looking analysis of the
# WRONG data (Problem C: an old root-level vo-words.json from a different
# project). Gap beyond which "words is older than this video" stops being
# normal pipeline ordering (make-vo runs long before assemble) and starts
# looking like a leftover artifact from an earlier session.
STALE_WORDS_GAP_SECONDS = 3600


def _probe_duration(path):
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path,
    ])
    return float(out.decode().strip())


def main(argv):
    video = argv[1] if len(argv) > 1 else "videos/final-rough.mp4"
    words_path = argv[2] if len(argv) > 2 else "vo-words.json"
    if not os.path.exists(video):
        sys.exit(f"check-timing: missing video {video}")
    if not os.path.exists(words_path):
        sys.exit(f"check-timing: missing {words_path} -- run make-vo.py first")

    words_abspath = os.path.abspath(words_path)
    words_mtime = os.path.getmtime(words_path)
    video_mtime = os.path.getmtime(video)
    print(f"  timing: loaded {words_abspath} (mtime {words_mtime:.0f})")
    gap = video_mtime - words_mtime
    if gap > STALE_WORDS_GAP_SECONDS:
        print(
            f"\n[X] TIMING CHECK FAILED\n"
            f"  {words_abspath} is {gap / 60:.0f} min older than {video} -- "
            f"this looks like a stale/leftover words file from an earlier "
            f"session, not the one that generated this video.\n"
            f"  Fix: rebuild (python make-vo.py) so vo-words.json matches "
            f"the current script.\n", file=sys.stderr)
        return 1

    with open(words_path, encoding="utf-8") as f:
        words = json.load(f)
    speech_end = timing_util.speech_end_seconds(words)
    video_dur = _probe_duration(video)
    ok, msg = timing_util.check_alignment(speech_end, video_dur)

    if ok:
        print(f"  timing: {msg}")
        _check_scene_alignment(words)
        return 0

    if os.environ.get("DEMO_ALLOW_TRUNCATE") == "1":
        print(f"  timing: {msg}")
        print("  DEMO_ALLOW_TRUNCATE=1 set -- proceeding despite truncation.")
        _check_scene_alignment(words)
        return 0

    print(f"\n[X] TIMING CHECK FAILED\n  {msg}\n", file=sys.stderr)
    return 1


def _check_scene_alignment(words):
    """Warn-only per-scene VO alignment (Problem B). Never allowed to fail the
    build the truncation gate above would have passed -- any error here just
    prints a warning and moves on.

    Needs scene-plan.json (the resolved scene sequence) and config.json (for
    `subs.crossfade`), both written earlier in the same build. Post-build
    scene durations come from probing .normalized/s{i}.mp4 -- the same files
    assemble.sh itself probes to build its xfade chain -- not from config,
    which can be absent (`duration:` is optional) or stale after autofit.

    These probed durations are ALREADY divided by `subs.speedup`
    (assemble.sh's normalize() applies setpts=PTS/SPEEDUP before this check
    ever runs), so scene_spans() is called with speedup=1.0 -- no further
    scaling of the durations themselves. But a composite before_after scene's
    `cut_at`/`half_duration` in scene-plan.json is still authored in
    PRE-speedup seconds, so it needs the REAL project speedup to land in the
    same (post-speedup) units as the probed durations -- passed separately as
    composite_speedup. Mixing the two without this conversion was a FATAL bug
    (see .conduct/grok-review.md finding 1): at the default speedup 1.2 it
    misplaced the internal cut by ~2.3s, and past speedup 2.0 it dropped the
    sub-boundary entirely.
    """
    try:
        plan_path = os.environ.get("DEMO_PLAN", "scene-plan.json")
        config_path = os.environ.get("DEMO_CONFIG", "config.json")
        if not (os.path.exists(plan_path) and os.path.exists(config_path)):
            return
        plan = json.load(open(plan_path, encoding="utf-8"))["scenes"]
        cfg = json.load(open(config_path, encoding="utf-8"))
        subs = cfg.get("subs", {})
        crossfade = float(subs.get("crossfade", 0.6))
        speedup = float(subs.get("speedup", 1.20))

        durs = []
        for i in range(1, len(plan) + 1):
            clip = f".normalized/s{i}.mp4"
            if not os.path.exists(clip):
                # Not every scene normalized yet (e.g. --only) -- skip, but
                # say so: a silent skip here hides the exact per-scene
                # alignment check (Problem B) this whole function exists to
                # run (finding 3).
                print(f"  timing: scene alignment check skipped ({clip} not built yet)")
                return
            durs.append(_probe_duration(clip))

        spans = timing_util.scene_spans(durs, speedup=1.0, crossfade=crossfade,
                                         scene_plan=plan, composite_speedup=speedup)
        ownership = timing_util.scene_ownership(spans, crossfade)
        for window in ownership:
            if window.get("warning"):
                print(f"  timing: {window['warning']}")

        result = timing_util.check_scene_alignment(words.get("lines") or [], ownership)
        for violation in result.get("violations", []):
            print(f"  timing: WARNING scene alignment -- {violation['message']}")
    except Exception as exc:  # noqa: BLE001 -- must degrade to a warning, never break the build
        print(f"  timing: scene alignment check skipped (error: {exc})")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
