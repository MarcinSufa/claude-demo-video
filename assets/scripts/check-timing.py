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

    with open(words_path, encoding="utf-8") as f:
        words = json.load(f)
    speech_end = timing_util.speech_end_seconds(words)
    video_dur = _probe_duration(video)
    ok, msg = timing_util.check_alignment(speech_end, video_dur)

    if ok:
        print(f"  timing: {msg}")
        return 0

    if os.environ.get("DEMO_ALLOW_TRUNCATE") == "1":
        print(f"  timing: {msg}")
        print("  DEMO_ALLOW_TRUNCATE=1 set -- proceeding despite truncation.")
        return 0

    print(f"\n[X] TIMING CHECK FAILED\n  {msg}\n", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
