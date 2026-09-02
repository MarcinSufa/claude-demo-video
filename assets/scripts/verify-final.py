"""verify-final.py: post-mux checks that block the build instead of the operator.

  python verify-final.py videos/final-with-captions.mp4 --rough videos/final-rough.mp4

Checks, each named in the output:
  duration   the output matches the rough cut within 0.5 s
  audio      an audio stream exists, and the last 3 s are not silent when the
             narration (vo-words.json) ends inside them
  flash      no frame brighter than --threshold (signalstats YAVG, default 120) that is
             also --margin (default 60) above the file's median brightness
  captions   captions.srt cues printed next to the scene table, for eyeballing
Exit 1 with the failing check named.
"""
import argparse
import json
import os
import re
import statistics
import subprocess
import sys

import timing_util

DURATION_TOLERANCE_S = 0.5
FLASH_MARGIN = 60.0
TAIL_S = 3.0
SILENCE_DB = -50.0


def duration_problem(video_s, rough_s, tolerance=DURATION_TOLERANCE_S):
    if abs(video_s - rough_s) <= tolerance:
        return None
    return (f"duration {video_s:.2f}s differs from the rough cut {rough_s:.2f}s "
            f"by more than {tolerance}s")


def parse_yavg(text):
    series = []
    t = None
    for line in text.splitlines():
        m = re.search(r"pts_time:(\S+)", line)
        if m:
            t = float(m.group(1))
            continue
        m = re.search(r"YAVG=(\S+)", line)
        if m and t is not None:
            series.append((t, float(m.group(1))))
    return series


def flash_problem(series, threshold, margin=FLASH_MARGIN):
    if not series:
        return None
    median = statistics.median(value for _, value in series)
    for t, value in series:
        if value > threshold and value > median + margin:
            return (f"white flash: frame at {t:.1f}s has YAVG {value:.0f} "
                    f"(threshold {threshold:g}, file median {median:.0f} + margin {margin:g})")
    return None


def audio_problem(has_audio, tail_db, narration_in_tail):
    if not has_audio:
        return "no audio stream in the output"
    if narration_in_tail and (tail_db is None or tail_db < SILENCE_DB):
        level = "unmeasurable" if tail_db is None else f"{tail_db:.1f} dB"
        return f"audio is silent in the last {TAIL_S:.0f}s ({level}) although narration ends there"
    return None


def parse_srt(text):
    cues = []
    stamp = r"(\d+):(\d+):(\d+)[,.](\d+)"
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = block.strip().splitlines()
        for i, line in enumerate(lines):
            m = re.match(rf"\s*{stamp}\s*-->\s*{stamp}", line)
            if m:
                h1, m1, s1, ms1, h2, m2, s2, ms2 = (int(x) for x in m.groups())
                start = h1 * 3600 + m1 * 60 + s1 + ms1 / 1000
                end = h2 * 3600 + m2 * 60 + s2 + ms2 / 1000
                cues.append((start, end, " ".join(lines[i + 1:]).strip()))
                break
    return cues


def caption_rows(scenes, cues, speedup, crossfade):
    rows = []
    cursor = 0.0
    for i, scene in enumerate(scenes):
        name = scene.get("name", scene.get("id", "?"))
        raw = scene.get("duration")
        if raw is None:
            rows.append((name, "(no duration: cannot place captions)"))
            continue
        start = cursor - (crossfade if i else 0.0)
        end = start + float(raw) / speedup
        texts = [text for s, e, text in cues if s < end and e > start]
        rows.append((name, " | ".join(texts) if texts else "(no caption)"))
        cursor = end
    return rows


def _run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def probe_duration(path):
    out = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", path])
    return float(out.stdout.strip())


def probe_has_audio(path):
    out = _run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                "stream=codec_type", "-of", "csv=p=0", path])
    return "audio" in out.stdout


def probe_tail_db(path):
    out = _run(["ffmpeg", "-v", "info", "-sseof", f"-{TAIL_S}", "-i", path, "-vn",
                "-af", "volumedetect", "-f", "null", "-"])
    m = re.search(r"mean_volume:\s*(-?[\d.]+) dB", out.stderr)
    return float(m.group(1)) if m else None


def probe_yavg(path):
    out = _run(["ffmpeg", "-v", "error", "-i", path, "-an",
                "-vf", "scale=320:-2,signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-",
                "-f", "null", "-"])
    return parse_yavg(out.stdout)


def _load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("video")
    ap.add_argument("--rough", required=True)
    ap.add_argument("--threshold", type=float, default=120.0)
    ap.add_argument("--margin", type=float, default=FLASH_MARGIN)
    ap.add_argument("--captions", default="captions.srt")
    ap.add_argument("--plan", default="scene-plan.json")
    ap.add_argument("--words", default="vo-words.json")
    ap.add_argument("--config", default=os.environ.get("DEMO_CONFIG", "config.json"))
    args = ap.parse_args(argv)

    failures = []

    def report(name, problem):
        print(f"  [{'FAIL' if problem else 'PASS'}] {name}" + (f": {problem}" if problem else ""))
        if problem:
            failures.append(name)

    video_s = probe_duration(args.video)
    report("duration", duration_problem(video_s, probe_duration(args.rough)))

    speech_end = timing_util.speech_end_seconds(_load_json(args.words, {}))
    narration_in_tail = speech_end > video_s - TAIL_S
    has_audio = probe_has_audio(args.video)
    tail_db = probe_tail_db(args.video) if has_audio else None
    report("audio", audio_problem(has_audio, tail_db, narration_in_tail))

    report("flash", flash_problem(probe_yavg(args.video), args.threshold, args.margin))

    scenes = _load_json(args.plan, {}).get("scenes", [])
    if scenes and os.path.exists(args.captions):
        subs = _load_json(args.config, {}).get("subs", {})
        with open(args.captions, encoding="utf-8") as f:
            cues = parse_srt(f.read())
        print("\n  captions per scene (eyeball caption vs scene):")
        for name, text in caption_rows(scenes, cues, float(subs.get("speedup", 1.2)),
                                       float(subs.get("crossfade", 0.6))):
            print(f"    {name:<22} {text}")
        print()

    if failures:
        print(f"verify-final FAILED: {', '.join(failures)}")
        return 1
    print(f"verify-final OK ({video_s:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
