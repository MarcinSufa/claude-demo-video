"""normalize-clip.py -- pin a scene clip to an exact duration (P0-3).

browser_capture / VHS clip lengths jitter run-to-run, which makes VO<->video
alignment a guessing game. When a scene declares `duration:`, build-scenes.sh
calls this to trim (if long) or freeze-frame pad (if short) to EXACTLY that.

  python normalize-clip.py <clip.mp4> <target_seconds>

decide_normalization() is the pure, unit-tested core; main() is ffprobe/ffmpeg glue.
"""
import subprocess
import sys


def decide_normalization(measured, target, epsilon=0.05):
    """Pick the action to hit `target` seconds from a `measured`-second clip.

    Returns (action, value):
      ("none", target)          when |measured - target| <= epsilon
      ("trim", target)          when measured > target + epsilon  (value = final length)
      ("pad",  target-measured) when measured < target - epsilon  (value = seconds to add)
    """
    if abs(measured - target) <= epsilon:
        return "none", target
    if measured > target:
        return "trim", target
    return "pad", target - measured


def _probe_duration(path):
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path,
    ])
    return float(out.decode().strip())


def main(argv):
    if len(argv) != 3:
        sys.exit("usage: python normalize-clip.py <clip.mp4> <target_seconds>")
    clip, target = argv[1], float(argv[2])
    measured = _probe_duration(clip)
    action, value = decide_normalization(measured, target)
    if action == "none":
        print(f"  normalize {clip}: {measured:.2f}s ~= {target:.2f}s (ok)")
        return
    tmp = clip + ".norm.mp4"
    if action == "trim":
        vf = None
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
               "-i", clip, "-t", f"{value:.3f}",
               "-c:v", "libx264", "-preset", "slow", "-crf", "18",
               "-pix_fmt", "yuv420p", "-movflags", "+faststart", tmp]
        print(f"  normalize {clip}: {measured:.2f}s -> trim to {target:.2f}s")
    else:  # pad: freeze the last frame for `value` extra seconds
        vf = f"tpad=stop_mode=clone:stop_duration={value:.3f}"
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
               "-i", clip, "-vf", vf,
               "-c:v", "libx264", "-preset", "slow", "-crf", "18",
               "-pix_fmt", "yuv420p", "-movflags", "+faststart", tmp]
        print(f"  normalize {clip}: {measured:.2f}s -> pad +{value:.2f}s to {target:.2f}s")
    subprocess.run(cmd, check=True)
    import os
    os.replace(tmp, clip)


if __name__ == "__main__":
    main(sys.argv)
