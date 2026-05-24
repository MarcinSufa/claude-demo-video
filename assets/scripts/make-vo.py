"""Generates voiceover MP3 + word-level timing JSON using Edge TTS streaming API.

Voice: en-US-AndrewNeural (Warm, Confident, Authentic — Anthropic-style)
Outputs:
  vo.mp3              — concatenated audio (~53s)
  vo-words.json       — word timing for caption generation (per-word abs start + duration)
"""
import asyncio
import json
import os
import subprocess
import edge_tts

# ── Config-driven: read voice + voiceover from .build/config.json ──────
CONFIG_PATH = os.environ.get("DEMO_CONFIG", ".build/config.json")
if not os.path.exists(CONFIG_PATH):
    raise SystemExit(f"Missing {CONFIG_PATH} — run: python scripts/apply-brand.py first")
with open(CONFIG_PATH, encoding="utf-8") as _f:
    _cfg = json.load(_f)

import re

_voice = _cfg.get("voice", {})
VOICE = _voice.get("voice_id", "en-US-AndrewNeural")
RATE = _voice.get("rate", "+0%")
LEADING_OFFSET_SEC = float(_voice.get("leading_silence", 0.2))

# Pronunciation map: respell brand terms for the TTS voice (e.g. a Polish voice
# reads "Asistel" as "A-śi-stel"; respell to "Assystel" for English-ish sound).
# Captions still show the ORIGINAL spelling — we reverse-map the spoken token back.
PRONOUNCE = {str(k): str(v) for k, v in (_voice.get("pronounce") or {}).items()}
# reverse: spoken respelling (lowercased) -> original display form
PRONOUNCE_REV = {v.lower(): k for k, v in PRONOUNCE.items()}


def apply_pronounce(text):
    """Replace whole-word brand terms with their respellings for TTS."""
    out = text
    for original, spoken in PRONOUNCE.items():
        out = re.sub(rf"\b{re.escape(original)}\b", spoken, out)
    return out


def display_word(token):
    """Map a spoken WordBoundary token back to its original spelling for captions."""
    # strip trailing punctuation for matching, re-attach after
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


async def gen_segments():
    """Stream each segment, save audio + collect word boundaries."""
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


def get_duration(path):
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path,
    ])
    return float(out.decode().strip())


def silence(dur, cache={}):
    key = round(dur, 2)
    if key in cache: return cache[key]
    p = f"{WORK}/sil_{int(dur * 1000)}.mp3"
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
        "-t", str(dur), "-c:a", "libmp3lame", "-b:a", "128k", p,
    ], check=True)
    cache[key] = p
    return p


def main():
    print(f"[1/3] Streaming {len(SCRIPT)} segments via Edge TTS ({VOICE})")
    segments = asyncio.run(gen_segments())

    print(f"[2/3] Concatenating with pacing pauses")
    list_path = f"{WORK}/concat.txt"
    with open(list_path, "w") as f:
        for seg in segments:
            f.write(f"file '{os.path.abspath(seg['path'])}'\n")
            if seg["pause_after"] > 0:
                f.write(f"file '{os.path.abspath(silence(seg['pause_after']))}'\n")

    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", list_path,
        "-c:a", "libmp3lame", "-b:a", "192k", "vo.mp3",
    ], check=True)

    print(f"[3/3] Computing absolute word timings (offset by {LEADING_OFFSET_SEC}s for mix delay)")
    cursor = LEADING_OFFSET_SEC
    all_lines = []
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
        cursor += seg_dur + seg["pause_after"]

    with open("vo-words.json", "w") as f:
        json.dump({"leading_offset": LEADING_OFFSET_SEC, "lines": all_lines}, f, indent=2)

    vo_dur = get_duration("vo.mp3")
    word_count = sum(len(line["words"]) for line in all_lines)
    print(f"\nDone -> vo.mp3 ({vo_dur:.1f}s) + vo-words.json ({word_count} words, {len(all_lines)} lines)")


if __name__ == "__main__":
    main()
