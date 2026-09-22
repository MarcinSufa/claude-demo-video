"""make-music-elevenlabs.py -- compose a music bed via ElevenLabs Music (paid).

Spans come from the REAL assembled scenes (.normalized/s<i>.mp4, written by
assemble.sh) so sections line up with what actually plays, not an estimate.

Amendment A1: this script never computes or prints its own approval code (three
independent formulas for "the same" code -- spend-gate, make-vo, make-music --
could disagree the moment TTS+music were both uncached). It instead reads
`.spend-approved.json` (written by `spend-gate.py check`) and checks the real
track length against the approved BUDGET (`music_max_seconds`).

Amendment A2: the approval only covers the EXACT music config it was computed
against (`music_cfg_sha`, excluding `volume` -- a post-mix bed level, not part
of the request). A retry of a previously rejected track is allowed ONLY when
the approval record's own `retry_rejected` flag is true (set by spend-gate.py
at check time) -- the DEMO_RETRY_REJECTED env var alone is never enough, so a
build script can't silently re-bill a rejected track just by having the env
var set without having re-run spend-gate. Each rejected attempt gets its own
quarantine file (`<key>-<n>.mp3`), so retries never overwrite the evidence of
a prior rejection.

  python make-music-elevenlabs.py --output music-src

On success writes --output (mp3) and exits 0. Exits 3 if no API key is found
(only reached once a real request is actually needed). Exits 4 if there is no
approval record, the record's music_cfg_sha doesn't match the live config, or
the real length exceeds the approved budget (no network call in any case).
Exits 5 if a track was already rejected for this exact request and the
approval's retry_rejected flag is not true (no fallback, no re-bill without
an explicit, re-approved opt-in), or if the newly-fetched track itself has a
dropout (quarantined; the build fails with no fallback -- an approved paid
call producing a bad track must be visibly retried, never silently swapped
for library/procedural).
"""
import argparse
import glob
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
APPROVAL_RECORD = ".spend-approved.json"


def _load_approval():
    if not os.path.exists(APPROVAL_RECORD):
        return None
    try:
        with open(APPROVAL_RECORD, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


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
    return timing_util.name_scene_spans(plan_scenes, spans)


def compute_plan_and_key(cfg, plan_scenes):
    music = cfg.get("music", {})
    spans = real_spans(cfg, plan_scenes)
    total_s = spans[-1][2] if spans else 0.0
    try:
        sections = music_plan.sections_from_spans(spans, total_s)
    except ValueError as e:
        sys.exit(f"make-music-elevenlabs: {e} (real assembled length {total_s:.1f}s "
                  "is too short to compose a track for -- add scenes or raise "
                  "scene durations)")
    plan = music_plan.composition_plan(music, sections)
    model_id = music.get("model_id", "music_v1")
    output_format = music.get("output_format", "mp3_44100_192")
    seed = music.get("seed")
    key_src = json.dumps({"plan": plan, "model_id": model_id,
                           "output_format": output_format, "seed": seed}, sort_keys=True)
    cache_key = hashlib.sha256(key_src.encode("utf-8")).hexdigest()
    return plan, model_id, output_format, seed, cache_key, total_s


def _rejected_attempts(rejected_dir, cache_key):
    """A2.4: every quarantined attempt for this exact request, `<key>*.mp3` --
    not just `<key>.mp3` -- so a second rejection is detected too."""
    return sorted(glob.glob(os.path.join(rejected_dir, f"{cache_key}*.mp3")))


def _next_rejected_path(rejected_dir, cache_key):
    n = len(_rejected_attempts(rejected_dir, cache_key)) + 1
    candidate = os.path.join(rejected_dir, f"{cache_key}-{n}.mp3")
    while os.path.exists(candidate):
        n += 1
        candidate = os.path.join(rejected_dir, f"{cache_key}-{n}.mp3")
    return candidate


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    with open(PLAN, encoding="utf-8") as f:
        plan_scenes = json.load(f).get("scenes", [])
    root = os.environ.get("DEMO_ROOT", "..")

    plan, model_id, output_format, seed, cache_key, total_s = compute_plan_and_key(cfg, plan_scenes)
    cache_dir = os.path.join(root, ".music-cache", "elevenlabs")
    os.makedirs(cache_dir, exist_ok=True)
    cached_path = os.path.join(cache_dir, f"{cache_key}.mp3")

    if not os.path.exists(cached_path):
        approved = _load_approval()
        budget = (approved or {}).get("music_max_seconds")
        if not approved or budget is None:
            print(
                "music.mode=elevenlabs has no approved spend record - run spend-gate "
                "first (see SKILL.md Cost-gate protocol). No network call made.",
                file=sys.stderr)
            sys.exit(4)

        # A2.2: the approval only covers the EXACT music config it was
        # computed against (volume excluded -- a post-mix level, not part of
        # what gets requested).
        live_music_sha = music_plan.music_cfg_sha(cfg.get("music", {}))
        if approved.get("music_cfg_sha") != live_music_sha:
            print(
                "music config changed since the spend-gate approval (music_cfg_sha "
                "mismatch) - run spend-gate again (see SKILL.md Cost-gate "
                "protocol). No network call made.", file=sys.stderr)
            sys.exit(4)

        if total_s > budget:
            print(
                f"real music length ({total_s:.1f}s) exceeds the approved budget "
                f"({budget}s) - scenes grew since the last spend-gate approval; "
                "re-run spend-gate to get a fresh approval. No network call made.",
                file=sys.stderr)
            sys.exit(4)

        rejected_dir = os.path.join(cache_dir, "rejected")
        existing_rejected = _rejected_attempts(rejected_dir, cache_key)
        # A2.3: DEMO_RETRY_REJECTED alone is never enough -- only the approval
        # record's own retry_rejected (set by spend-gate.py check, at check
        # time) authorizes retrying a request that was already rejected.
        if existing_rejected and approved.get("retry_rejected") is not True:
            names = ", ".join(os.path.basename(p) for p in existing_rejected)
            print(
                f"a track for this exact request was already rejected (silence "
                f"dropout): {names}. Not re-billing automatically - set "
                "DEMO_RETRY_REJECTED=1 and re-run spend-gate to retry, or change "
                "the request.", file=sys.stderr)
            sys.exit(5)

        key = elevenlabs_api.load_key(root=root)
        if not key:
            print("music.mode=elevenlabs but no API key found - set ELEVENLABS_API_KEY "
                  "or DEMO_ELEVENLABS_ENV_FILE (or <root>/.env)", file=sys.stderr)
            sys.exit(3)

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
            os.makedirs(rejected_dir, exist_ok=True)
            rejected_path = _next_rejected_path(rejected_dir, cache_key)
            shutil.move(tmp_path, rejected_path)
            elevenlabs_api.ledger_append(root, {
                "kind": "music", "cache_key": cache_key, "status": "rejected_dropout",
                "character_cost": headers.get("xi-character-cost", "unknown")})
            print(f"elevenlabs music has silence dropouts: {dropouts} - quarantined "
                  f"to {rejected_path}. Build failed; no fallback is generated - "
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
