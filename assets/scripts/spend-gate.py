"""spend-gate.py -- estimate/refuse billed ElevenLabs calls before any network I/O.

Run from `.build` (build.sh copies elevenlabs_api.py, timing_util.py, music_plan.py
alongside). Reads config.json + scene-plan.json + the $DEMO_ROOT caches that
make-vo.py would consult, and reproduces make-vo's exact TTS cache keys -- this
script itself never performs network I/O.

  python spend-gate.py estimate   # print the Billed services block + approval code, exit 0
  python spend-gate.py check      # exit 0 if nothing uncached (or approved), else print + exit 4

Amendment A1: `check`, on success, writes `.spend-approved.json` (in the CURRENT
directory -- `.build`) -- the single approval record make-vo.py /
make-music-elevenlabs.py consult. They never recompute or print their own
approval code: three independent formulas for the same code (spend-gate,
make-vo, make-music) could disagree the moment TTS+music were both uncached,
deadlocking approval. Music is approved as a BUDGET (`music_max_seconds`),
never a specific composition-plan hash -- the real plan can only be built once
the video is actually assembled, and an unchanged budget must not force
re-approval on every rebuild.

Amendment A2: a stale record from a PRIOR build must never silently authorize
a later, different request. `check` deletes any existing record FIRST, before
any other work, and only ever writes a fresh one atomically after a pass --
so a failed check always leaves no record at all. The record also carries
`voiceover_sha` / `music_cfg_sha` fingerprints of the exact config it was
approved against (make-vo.py / make-music-elevenlabs.py refuse on mismatch),
and `retry_rejected` -- whether DEMO_RETRY_REJECTED=1 was set at check time --
which is the ONLY thing that authorizes retrying a previously rejected music
track (the env var alone, read later by make-music, is not enough).
"""
import json
import math
import os
import re
import sys

import elevenlabs_api
import music_plan
import timing_util

CONFIG = os.environ.get("DEMO_CONFIG", "config.json")
PLAN = os.environ.get("DEMO_PLAN", "scene-plan.json")
APPROVAL_RECORD = ".spend-approved.json"


def _apply_pronounce(text, pronounce):
    out = text
    for original, spoken in pronounce.items():
        out = re.sub(rf"\b{re.escape(original)}\b", spoken, out)
    return out


def _voice_cfg_fields(voice):
    return {k: v for k, v in voice.items()
            if k in ("voice_id", "model_id", "output_format", "language_code", "settings")}


def tts_estimate(cfg, root):
    voice = cfg.get("voice", {})
    if voice.get("provider") != "elevenlabs":
        return None
    pronounce = {str(k): str(v) for k, v in (voice.get("pronounce") or {}).items()}
    voice_cfg = _voice_cfg_fields(voice)
    cache_dir = os.path.join(root, ".tts-cache", "elevenlabs")
    lines = cfg.get("voiceover", [])
    uncached_keys, n_chars = [], 0
    for item in lines:
        spoken = _apply_pronounce(item.get("text", ""), pronounce)
        key = elevenlabs_api.tts_cache_key(voice_cfg, spoken)
        audio_path = os.path.join(cache_dir, f"{key}.mp3")
        json_path = os.path.join(cache_dir, f"{key}.json")
        if not (os.path.exists(audio_path) and os.path.exists(json_path)):
            uncached_keys.append(key)
            n_chars += len(spoken)
    return {"n_total": len(lines), "n_uncached": len(uncached_keys),
            "characters": n_chars, "uncached_keys": uncached_keys}


def _predicted_spans(plan_scenes, cfg):
    subs = cfg.get("subs", {})
    speedup = float(subs.get("speedup", 1.2))
    crossfade = float(subs.get("crossfade", 0.6))
    durations = [s.get("duration") for s in plan_scenes]
    if not durations or any(d is None for d in durations):
        return None
    spans = timing_util.scene_spans([float(d) for d in durations], speedup, crossfade, plan_scenes)
    return timing_util.name_scene_spans(plan_scenes, spans)


def music_budget_seconds(plan_scenes, music):
    """A1.1: `music_max_seconds` = predicted film seconds rounded up to 5s when
    every scene has `duration`, else `music.max_seconds` from brand.yaml, else
    None (caller refuses). The predicted figure is the RAW SUM of scene
    durations (not run through speedup/crossfade) -- a deliberately generous
    upper bound: speedup and crossfade only ever shrink the real film, so this
    never under-budgets, and it doesn't depend on the estimate's speedup
    default matching whatever the real build resolves."""
    durations = [s.get("duration") for s in plan_scenes]
    if durations and all(d is not None for d in durations):
        total = sum(float(d) for d in durations)
        return int(math.ceil(total / 5.0) * 5)
    explicit = music.get("max_seconds")
    if explicit is not None:
        return int(explicit)
    return None


def rejected_tracks(root):
    d = os.path.join(root, ".music-cache", "elevenlabs", "rejected")
    if not os.path.isdir(d):
        return []
    return sorted(f for f in os.listdir(d) if f.endswith(".mp3"))


def billed_block(tts, music_billed, music_max_seconds, retry_billed):
    lines = []
    billed = False
    if tts and tts["n_uncached"] > 0:
        billed = True
        lines.append(f"tts: {tts['n_uncached']}/{tts['n_total']} lines uncached, {tts['characters']} characters")
    if music_billed:
        billed = True
        lines.append(f"music: uncached, ~{music_max_seconds} s requested")
    if retry_billed:
        billed = True
        lines.append("retry of a rejected music track")
    if not billed:
        return "Billed services: none", False
    return "Billed services\n" + "\n".join(f"  {l}" for l in lines), True


def _write_approval(code, tts_keys, music_max_seconds, voiceover_sha, music_cfg_sha, retry_rejected):
    record = {
        "code": code,
        "tts_keys": tts_keys,
        "music_max_seconds": music_max_seconds,
        "voiceover_sha": voiceover_sha,
        "music_cfg_sha": music_cfg_sha,
        "retry_rejected": retry_rejected,
    }
    tmp_path = APPROVAL_RECORD + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(record, f)
    os.replace(tmp_path, APPROVAL_RECORD)


_RECORD_FIELDS = ("code", "tts_keys", "music_max_seconds", "voiceover_sha",
                   "music_cfg_sha", "retry_rejected")


def _is_recognized_record(record):
    return isinstance(record, dict) and any(k in record for k in _RECORD_FIELDS)


def main(argv):
    if len(argv) != 2 or argv[1] not in ("estimate", "check"):
        sys.exit("usage: spend-gate.py estimate|check")

    if argv[1] == "check":
        # A2.1: a stale record must never authorize a DIFFERENT later request.
        # Remove it before anything else can fail/short-circuit -- a failed
        # check must leave no record at all, not a leftover from a prior run.
        # A record that doesn't even look like ours (unreadable, or a foreign/
        # corrupt shape -- not a normal re-run's own well-formed prior record)
        # is surfaced as a one-time refusal so it's never silently discarded:
        # the operator sees it was there, then re-runs check on a clean slate.
        unrecognized = False
        if os.path.exists(APPROVAL_RECORD):
            try:
                with open(APPROVAL_RECORD, encoding="utf-8") as f:
                    old_record = json.load(f)
                unrecognized = not _is_recognized_record(old_record)
            except (OSError, ValueError):
                unrecognized = True
            try:
                os.remove(APPROVAL_RECORD)
            except FileNotFoundError:
                pass
        if unrecognized:
            print(
                "found and removed a stale or unrecognized .spend-approved.json "
                "- run spend-gate check again now that it is cleared.",
                file=sys.stderr)
            return 4

    if not os.path.exists(CONFIG):
        sys.exit(f"Missing {CONFIG}")
    if not os.path.exists(PLAN):
        sys.exit(f"Missing {PLAN}")
    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    with open(PLAN, encoding="utf-8") as f:
        plan_scenes = json.load(f).get("scenes", [])
    root = os.environ.get("DEMO_ROOT", "..")

    music = cfg.get("music", {})
    music_mode = music.get("mode") == "elevenlabs"
    retry_env = os.environ.get("DEMO_RETRY_REJECTED") == "1"

    music_max_seconds = None
    if music_mode:
        music_max_seconds = music_budget_seconds(plan_scenes, music)
        if music_max_seconds is None:
            print(
                "music.mode=elevenlabs needs a predictable length to budget spend: "
                "either give every scene a `duration:` (so it can be predicted "
                "automatically) or set `music.max_seconds` explicitly in brand.yaml.",
                file=sys.stderr)
            return 4

    rejected = rejected_tracks(root) if music_mode else []
    retry_billed = music_mode and retry_env and bool(rejected)

    tts = tts_estimate(cfg, root)
    uncached_keys = tts["uncached_keys"] if tts else []
    block, billed = billed_block(tts, music_mode, music_max_seconds, retry_billed)
    music_part = f"music<={music_max_seconds}s" if music_mode else None
    code = elevenlabs_api.approval_code(uncached_keys, music_part)

    voiceover_sha = timing_util.voiceover_sha(cfg.get("voiceover", []))
    music_cfg_sha = music_plan.music_cfg_sha(music)

    if argv[1] == "estimate":
        print(block)
        if rejected:
            print(f"note: {len(rejected)} previously rejected track(s) in "
                  ".music-cache/elevenlabs/rejected/ (silence dropout) -- retry "
                  "with DEMO_RETRY_REJECTED=1, or change the request: "
                  + ", ".join(rejected))
        if billed:
            print(f"APPROVAL CODE: {code}")
        return 0

    # check
    if not billed:
        _write_approval(None, [], music_max_seconds, voiceover_sha, music_cfg_sha, retry_env)
        return 0
    if os.environ.get("DEMO_APPROVE_SPEND") == code:
        _write_approval(code, uncached_keys, music_max_seconds, voiceover_sha, music_cfg_sha, retry_env)
        return 0
    print(block)
    print(f"APPROVAL CODE: {code}")
    return 4


if __name__ == "__main__":
    sys.exit(main(sys.argv))
