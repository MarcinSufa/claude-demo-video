"""make-music-elevenlabs.py -- compose a music bed via ElevenLabs Music (paid).

Spans come from the REAL assembled scenes (.normalized/s<i>.mp4, written by
assemble.sh) so sections line up with what actually plays, not an estimate.
Defence in depth: spend-gate.py already refuses an unapproved build before
assemble.sh runs, but an uncached request here re-checks the same approval
code before making any network call, in case the ledger/cache changed
between the gate check and this step.

  python make-music-elevenlabs.py --output music-src

On success writes --output (mp3) and exits 0. Exits 4 if the request is
uncached and unapproved (no network call). Exits 5 if the returned track has
a silence dropout -- the file is quarantined to .music-cache/elevenlabs/rejected/
and the build fails with no fallback (an approved paid call producing a bad
track must be visibly retried, never silently swapped for library/procedural).
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

import elevenlabs_api
import music_plan
import timing_util

CONFIG = os.environ.get("DEMO_CONFIG", "config.json")
PLAN = os.environ.get("DEMO_PLAN", "scene-plan.json")


def _scene_durations(plan_scenes):
    durations = []
    for i, s in enumerate(plan_scenes, start=1):
        clip = os.path.join(".normalized", f"s{i}.mp4")
        if os.path.exists(clip):
            out = subprocess.check_output([
                "ffprobe", "-v", "error", "-select_streams", "v",
                "-show_entries", "stream=duration", "-of", "csv=p=0", clip])
            durations.append(float(out.decode().strip()))
        else:
            durations.append(float(s.get("duration") or 0.0))
    return durations


def real_spans(cfg, plan_scenes):
    subs = cfg.get("subs", {})
    speedup = float(subs.get("speedup", 1.2))
    crossfade = float(subs.get("crossfade", 0.6))
    durations = _scene_durations(plan_scenes)
    # .normalized/s<i>.mp4 durations are already POST-speedup, so speedup=1.0
    # here -- but a before_after cut_at is always authored pre-speedup, so the
    # real project speedup is passed as composite_speedup for that conversion
    # (see timing_util.scene_spans).
    spans = timing_util.scene_spans(durations, speedup=1.0, crossfade=crossfade,
                                     scene_plan=plan_scenes, composite_speedup=speedup)
    names = [s.get("name", s.get("id")) for s in plan_scenes]
    return [(name, sp[0], sp[1]) for name, sp in zip(names, spans)]


def compute_plan_and_key(cfg, plan_scenes):
    music = cfg.get("music", {})
    spans = real_spans(cfg, plan_scenes)
    total_s = spans[-1][2] if spans else 0.0
    sections = music_plan.sections_from_spans(spans, total_s)
    plan = music_plan.composition_plan(music, sections)
    model_id = music.get("model_id", "music_v1")
    output_format = music.get("output_format", "mp3_44100_192")
    seed = music.get("seed")
    key_src = json.dumps({"plan": plan, "model_id": model_id,
                           "output_format": output_format, "seed": seed}, sort_keys=True)
    cache_key = hashlib.sha256(key_src.encode("utf-8")).hexdigest()
    return plan, model_id, output_format, seed, cache_key, total_s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    with open(PLAN, encoding="utf-8") as f:
        plan_scenes = json.load(f).get("scenes", [])
    root = os.environ.get("DEMO_ROOT", "..")

    key = elevenlabs_api.load_key(root=root)
    if not key:
        print("music.mode=elevenlabs but no API key found — set ELEVENLABS_API_KEY "
              "or DEMO_ELEVENLABS_ENV_FILE (or <root>/.env)", file=sys.stderr)
        sys.exit(3)

    plan, model_id, output_format, seed, cache_key, total_s = compute_plan_and_key(cfg, plan_scenes)
    cache_dir = os.path.join(root, ".music-cache", "elevenlabs")
    os.makedirs(cache_dir, exist_ok=True)
    cached_path = os.path.join(cache_dir, f"{cache_key}.mp3")

    if not os.path.exists(cached_path):
        code = elevenlabs_api.approval_code([], cache_key)
        if os.environ.get("DEMO_APPROVE_SPEND") != code:
            print(f"elevenlabs music would bill ~{total_s:.1f}s of audio — "
                  f"re-run with DEMO_APPROVE_SPEND={code} after review. "
                  "No network call made.", file=sys.stderr)
            sys.exit(4)

        audio, headers = elevenlabs_api.music_request(
            key, plan, model_id=model_id, output_format=output_format, seed=seed)
        tmp_path = cached_path + ".tmp"
        with open(tmp_path, "wb") as f:
            f.write(audio)

        probe = subprocess.run([
            "ffmpeg", "-hide_banner", "-i", tmp_path,
            "-af", "silencedetect=noise=-45dB:d=1.0", "-f", "null", "-"],
            capture_output=True, text=True)
        dropouts = music_plan.find_dropouts(probe.stderr, total_s)
        if dropouts:
            rejected_dir = os.path.join(cache_dir, "rejected")
            os.makedirs(rejected_dir, exist_ok=True)
            rejected_path = os.path.join(rejected_dir, f"{cache_key}.mp3")
            shutil.move(tmp_path, rejected_path)
            elevenlabs_api.ledger_append(root, {
                "kind": "music", "cache_key": cache_key, "status": "rejected_dropout",
                "character_cost": headers.get("xi-character-cost", "unknown")})
            print(f"elevenlabs music has silence dropouts: {dropouts} — quarantined "
                  f"to {rejected_path}. Build failed; no fallback is generated — "
                  "retry the build.", file=sys.stderr)
            sys.exit(5)

        os.replace(tmp_path, cached_path)
        elevenlabs_api.ledger_append(root, {
            "kind": "music", "cache_key": cache_key, "status": "success",
            "character_cost": headers.get("xi-character-cost", "unknown")})

    shutil.copyfile(cached_path, args.output)
    print(f"make-music-elevenlabs: -> {args.output} ({total_s:.1f}s, cache {cache_key[:12]})")


if __name__ == "__main__":
    main()
