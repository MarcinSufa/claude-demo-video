"""spend-gate.py -- estimate/refuse billed ElevenLabs calls before any network I/O.

Run from `.build` (build.sh copies elevenlabs_api.py, music_plan.py, timing_util.py
alongside). Reads config.json + scene-plan.json + the $DEMO_ROOT caches that
make-vo.py / make-music-elevenlabs.py would consult, and reproduces their exact
cache keys -- this script itself never performs network I/O.

  python spend-gate.py estimate   # print the Billed services block + approval code, exit 0
  python spend-gate.py check      # exit 0 if nothing uncached (or approved), else print + exit 4
"""
import hashlib
import json
import math
import os
import re
import sys

import elevenlabs_api
import timing_util

CONFIG = os.environ.get("DEMO_CONFIG", "config.json")
PLAN = os.environ.get("DEMO_PLAN", "scene-plan.json")


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
    names = [s.get("name", s.get("id")) for s in plan_scenes]
    return [(name, sp[0], sp[1]) for name, sp in zip(names, spans)]


def music_estimate(cfg, root, plan_scenes):
    music = cfg.get("music", {})
    if music.get("mode") != "elevenlabs":
        return None

    cache_dir = os.path.join(root, ".music-cache", "elevenlabs")

    spans = _predicted_spans(plan_scenes, cfg)
    if spans is None:
        total = sum(float(s.get("duration") or 0) for s in plan_scenes)
        cap_s = int(math.ceil(max(total, 1) / 5.0) * 5)
        return {"pinned": False, "cap_seconds": cap_s, "key": f"cap:{cap_s}s", "cached": False}

    total_s = spans[-1][2]
    try:
        import music_plan
    except ImportError:
        return {"pinned": True, "seconds": round(total_s, 1), "key": None, "cached": False}

    sections = music_plan.sections_from_spans(spans, total_s)
    plan = music_plan.composition_plan(music, sections)
    model_id = music.get("model_id", "music_v1")
    output_format = music.get("output_format", "mp3_44100_192")
    seed = music.get("seed")
    key_src = json.dumps({"plan": plan, "model_id": model_id,
                           "output_format": output_format, "seed": seed}, sort_keys=True)
    key = hashlib.sha256(key_src.encode("utf-8")).hexdigest()
    cached = os.path.exists(os.path.join(cache_dir, f"{key}.mp3"))
    return {"pinned": True, "seconds": round(total_s, 1), "key": key, "cached": cached}


def billed_block(tts, music):
    lines = []
    billed = False
    if tts and tts["n_uncached"] > 0:
        billed = True
        lines.append(f"tts: {tts['n_uncached']}/{tts['n_total']} lines uncached, {tts['characters']} characters")
    if music and not music.get("cached"):
        billed = True
        if music.get("pinned"):
            lines.append(f"music: uncached, ~{music['seconds']} s requested")
        else:
            lines.append(f"music: uncached, ~{music['cap_seconds']} s requested (duration not pinned, capped)")
    elif music and music.get("cached"):
        lines.append("music: cached")
    if not billed:
        return "Billed services: none", False
    return "Billed services\n" + "\n".join(f"  {l}" for l in lines), True


def compute(cfg, plan_scenes, root):
    tts = tts_estimate(cfg, root)
    music = music_estimate(cfg, root, plan_scenes)
    block, billed = billed_block(tts, music)
    uncached_keys = tts["uncached_keys"] if tts else []
    music_key = music["key"] if music else None
    code = elevenlabs_api.approval_code(uncached_keys, music_key)
    return block, billed, code


def main(argv):
    if len(argv) != 2 or argv[1] not in ("estimate", "check"):
        sys.exit("usage: spend-gate.py estimate|check")
    if not os.path.exists(CONFIG):
        sys.exit(f"Missing {CONFIG}")
    if not os.path.exists(PLAN):
        sys.exit(f"Missing {PLAN}")
    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    with open(PLAN, encoding="utf-8") as f:
        plan_scenes = json.load(f).get("scenes", [])
    root = os.environ.get("DEMO_ROOT", "..")

    block, billed, code = compute(cfg, plan_scenes, root)

    if argv[1] == "estimate":
        print(block)
        if billed:
            print(f"APPROVAL CODE: {code}")
        return 0

    if not billed:
        return 0
    if os.environ.get("DEMO_APPROVE_SPEND") == code:
        return 0
    print(block)
    print(f"APPROVAL CODE: {code}")
    return 4


if __name__ == "__main__":
    sys.exit(main(sys.argv))
