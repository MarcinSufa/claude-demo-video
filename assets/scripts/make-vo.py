"""Generates voiceover MP3 + word-level timing JSON.

Providers (voice.provider in brand.yaml):
  edge-tts    (default) — Microsoft Edge TTS, streaming, free, no API key.
  elevenlabs  — ElevenLabs with-timestamps API, paid, per-line content-addressed
                cache. Every uncached line must be pre-approved by spend-gate.py
                (see .spend-approved.json / SKILL.md Cost-gate protocol) — this
                script never computes or prints its own approval code.

Outputs:
  vo.mp3              — concatenated audio
  vo-words.json       — word timing for caption generation (per-word abs start + duration)
"""
import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys

import elevenlabs_api
import timing_util
import vo_audio
# `edge_tts` is imported lazily, only inside gen_segments_edge() — importing it
# unconditionally here would require it even for provider=elevenlabs, which has
# no use for it (A1.5).

# ── Config-driven: read voice + voiceover from .build/config.json ──────
CONFIG_PATH = os.environ.get("DEMO_CONFIG", ".build/config.json")
if not os.path.exists(CONFIG_PATH):
    raise SystemExit(f"Missing {CONFIG_PATH} — run: python scripts/apply-brand.py first")
with open(CONFIG_PATH, encoding="utf-8") as _f:
    _cfg = json.load(_f)

_voice = _cfg.get("voice", {})
PROVIDER = _voice.get("provider", "edge-tts")
VOICE = _voice.get("voice_id", "en-US-AndrewNeural")
RATE = _voice.get("rate", "+0%")
LEADING_OFFSET_SEC = float(_voice.get("leading_silence", 0.2))

# Pronunciation map: respell brand terms for the TTS voice (e.g. a Polish voice
# reads "Asistel" as "A-śi-stel"; respell to "Assystel" for English-ish sound).
# Captions still show the ORIGINAL spelling — we reverse-map the spoken token back.
# Shared by both providers.
PRONOUNCE = {str(k): str(v) for k, v in (_voice.get("pronounce") or {}).items()}
PRONOUNCE_REV = {v.lower(): k for k, v in PRONOUNCE.items()}


def apply_pronounce(text):
    """Replace whole-word brand terms with their respellings for TTS."""
    out = text
    for original, spoken in PRONOUNCE.items():
        out = re.sub(rf"\b{re.escape(original)}\b", spoken, out)
    return out


def display_word(token):
    """Map a spoken token back to its original spelling for captions."""
    m = re.match(r"^(.*?)([.,!?:;]*)$", token)
    core, punct = m.group(1), m.group(2)
    if core.lower() in PRONOUNCE_REV:
        return PRONOUNCE_REV[core.lower()] + punct
    return token


# voiceover: list of {text, pause_after}
SCRIPT = [(item["text"], float(item.get("pause_after", 0.5)))
          for item in _cfg.get("voiceover", [])]
if not SCRIPT:
    raise SystemExit("config.json has no `voiceover` lines — edit brand.yaml")

WORK = ".vo"
os.makedirs(WORK, exist_ok=True)


def get_duration(path):
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path,
    ])
    return float(out.decode().strip())


# ── edge-tts provider ───────────────────────────────────────────────────
async def gen_segments_edge():
    """Stream each segment, save audio + collect word boundaries."""
    import edge_tts

    segments = []
    for i, (text, pause) in enumerate(SCRIPT):
        path = f"{WORK}/seg_{i:02d}.mp3"
        spoken = apply_pronounce(text)            # what the TTS voice reads
        comm = edge_tts.Communicate(spoken, VOICE, rate=RATE, boundary="WordBoundary")
        words = []
        with open(path, "wb") as audio_file:
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    audio_file.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    words.append({
                        "text": display_word(chunk["text"]),   # caption shows original spelling
                        "offset_sec": chunk["offset"] / 10_000_000,
                        "duration_sec": chunk["duration"] / 10_000_000,
                    })
        segments.append({"path": path, "text": text, "pause_after": pause, "words": words})
        print(f"  seg {i:02d}: {len(words)} words · {text[:55]}")
    return segments


APPROVAL_RECORD = ".spend-approved.json"


def _load_approval():
    """spend-gate.py's .spend-approved.json, written on a passing `check` --
    the single source of truth for what's approved (A1.2). Never computed or
    regenerated here."""
    if not os.path.exists(APPROVAL_RECORD):
        return None
    try:
        with open(APPROVAL_RECORD, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


# elevenlabs provider ─────────────────────────────────────────────────
def gen_segments_elevenlabs():
    root = os.environ.get("DEMO_ROOT", "..")

    if _voice.get("rate"):
        print("WARNING: voice.rate is ignored for provider=elevenlabs (edge-tts only)")

    cache_dir = os.path.join(root, ".tts-cache", "elevenlabs")
    os.makedirs(cache_dir, exist_ok=True)

    voice_cfg = {k: v for k, v in _voice.items()
                 if k in ("voice_id", "model_id", "output_format", "language_code", "settings")}

    planned = []
    for text, pause in SCRIPT:
        spoken = apply_pronounce(text)
        cache_key = elevenlabs_api.tts_cache_key(voice_cfg, spoken)
        audio_path = os.path.join(cache_dir, f"{cache_key}.mp3")
        json_path = os.path.join(cache_dir, f"{cache_key}.json")
        cached = os.path.exists(audio_path) and os.path.exists(json_path)
        planned.append({"text": text, "pause": pause, "spoken": spoken,
                         "cache_key": cache_key, "audio_path": audio_path,
                         "json_path": json_path, "cached": cached})

    # A1.2: check approval BEFORE the key -- an uncached line unapproved must
    # exit 4 regardless of whether a key even exists (an unapproved request
    # can never be attempted, so a missing key isn't the reason it's refused).
    uncached = [p for p in planned if not p["cached"]]
    if uncached:
        approved = _load_approval()
        # A2.2: an approval only covers the EXACT voiceover it was computed
        # against -- a script edited after `spend-gate check` must never ride
        # the old approval, even if the edit happens to keep some other line
        # uncached-with-a-matching-key by coincidence.
        if approved is not None:
            live_sha = timing_util.voiceover_sha(_cfg.get("voiceover", []))
            if approved.get("voiceover_sha") != live_sha:
                print(
                    "voiceover changed since the spend-gate approval (voiceover_sha "
                    "mismatch) - run spend-gate again (see SKILL.md Cost-gate "
                    "protocol). No network call made.", file=sys.stderr)
                sys.exit(4)
        approved_keys = set((approved or {}).get("tts_keys") or [])
        missing = [p for p in uncached if p["cache_key"] not in approved_keys]
        if missing:
            print(
                f"{len(missing)} uncached elevenlabs TTS line(s) are not in the approved "
                "spend record - run spend-gate first (see SKILL.md Cost-gate protocol). "
                "No network call made.", file=sys.stderr)
            sys.exit(4)

    key = None
    if uncached:
        key = elevenlabs_api.load_key(root=root)
        if not key:
            print(
                "voice.provider=elevenlabs but no API key found - set ELEVENLABS_API_KEY "
                "or DEMO_ELEVENLABS_ENV_FILE (or <root>/.env)", file=sys.stderr)
            sys.exit(3)

    segments = []
    for p in planned:
        if not p["cached"]:
            audio, alignment, headers = elevenlabs_api.tts_request(key, voice_cfg, p["spoken"])
            tmp_audio = p["audio_path"] + ".tmp"
            with open(tmp_audio, "wb") as f:
                f.write(audio)
            os.replace(tmp_audio, p["audio_path"])
            sidecar = {"alignment": alignment,
                       "character_cost": headers.get("xi-character-cost", "unknown")}
            tmp_json = p["json_path"] + ".tmp"
            with open(tmp_json, "w", encoding="utf-8") as f:
                json.dump(sidecar, f)
            os.replace(tmp_json, p["json_path"])
            elevenlabs_api.ledger_append(root, {
                "kind": "tts", "cache_key": p["cache_key"], "characters": len(p["spoken"]),
                "status": "success", "character_cost": sidecar["character_cost"]})
        with open(p["json_path"], encoding="utf-8") as f:
            sidecar = json.load(f)
        words_raw = elevenlabs_api.alignment_to_words(sidecar["alignment"])
        words = [{"text": display_word(w["text"]), "offset_sec": w["offset_sec"],
                  "duration_sec": w["duration_sec"]} for w in words_raw]
        segments.append({"path": p["audio_path"], "text": p["text"],
                          "pause_after": p["pause"], "words": words})
        print(f"  seg: {len(words)} words {'(cached)' if p['cached'] else ''} · {p['text'][:55]}")
    return segments


def _voice_sha(voice_cfg):
    canonical = json.dumps(voice_cfg, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def main():
    print(f"[1/3] Generating {len(SCRIPT)} segments via {PROVIDER}"
          + (f" ({VOICE})" if PROVIDER == "edge-tts" else ""))
    if PROVIDER == "edge-tts":
        segments = asyncio.run(gen_segments_edge())
    elif PROVIDER == "elevenlabs":
        segments = gen_segments_elevenlabs()
    else:
        sys.exit(f"Unknown voice.provider '{PROVIDER}' - use edge-tts or elevenlabs")

    print("[2/3] Concatenating with pacing pauses")
    vo_audio.concat_with_pauses(
        [(seg["path"], seg["pause_after"]) for seg in segments], "vo.mp3")

    print(f"[3/3] Computing absolute word timings (offset by {LEADING_OFFSET_SEC}s for mix delay)")
    cursor = LEADING_OFFSET_SEC
    all_lines = []
    seg_durs = []  # aligned 1:1 with all_lines (segments with no words are skipped)
    for seg in segments:
        seg_dur = get_duration(seg["path"])
        line_words = []
        for w in seg["words"]:
            line_words.append({
                "text": w["text"],
                "start": round(cursor + w["offset_sec"], 4),
                "duration": round(w["duration_sec"], 4),
            })
        if line_words:
            all_lines.append({
                "text": seg["text"],
                "line_start": line_words[0]["start"],
                "line_end": round(line_words[-1]["start"] + line_words[-1]["duration"], 4),
                "words": line_words,
            })
            seg_durs.append(seg_dur)
        cursor += seg_dur + seg["pause_after"]

    voice_sha_cfg = {k: v for k, v in _voice.items() if k != "pronounce"}
    words_data = {"leading_offset": LEADING_OFFSET_SEC,
                  "script_sha": timing_util.voiceover_sha(_cfg.get("voiceover", [])),
                  "voice_sha": _voice_sha(voice_sha_cfg),
                  "lines": all_lines}
    with open("vo-words.json", "w") as f:
        json.dump(words_data, f, indent=2)

    vo_dur = get_duration("vo.mp3")
    word_count = sum(len(line["words"]) for line in all_lines)
    print(f"\nDone -> vo.mp3 ({vo_dur:.1f}s) + vo-words.json ({word_count} words, {len(all_lines)} lines)")

    # Self-calibration (P3-1 follow-up): this run just told us, for real, how
    # fast this exact voice actually speaks. Cache it keyed on
    # timing_util.calibration_key() -- verbatim per (provider, voice, rate/model),
    # no rate-neutral extrapolation -- so the NEXT `--plan` on this project uses a
    # measured rate instead of the uncalibrated 115 default.
    internal_pauses = [seg["pause_after"] for seg in segments[:-1]]
    measured = timing_util.measure_voice_rate(words_data, internal_pauses, seg_durs)
    cache_path = "vo-calibration.json"
    try:
        cache = json.load(open(cache_path, encoding="utf-8")) if os.path.exists(cache_path) else {}
    except (OSError, ValueError):
        cache = {}
    cal_key = timing_util.calibration_key(_voice)
    cache[cal_key] = measured
    with open(cache_path, "w") as f:
        json.dump(cache, f, indent=2)
    print(f"  calibration: {cal_key} measured ~{measured['wpm']:.0f} wpm "
          f"(per-line overhead {measured['per_line_overhead']:.2f}s) -> {cache_path}")
    for line in timing_util.calibration_paste_lines(measured):
        print(line)


if __name__ == "__main__":
    main()
