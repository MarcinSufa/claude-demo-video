"""Generates karaoke-style ASS subtitles from vo-words.json.

Reads:  vo-words.json (produced by make-vo.py)
Writes: captions.ass — burned later via burn-captions.sh
        captions.srt — standard subtitles (line-level, for YouTube etc.)
"""
import json
import os
from pathlib import Path

# ── Config-driven palette ──────────────────────────────────────────────
# ASS uses &HBBGGRR& (BGR), not RGB. Convert from brand palette hex.
def _hex_to_ass_bgr(hex_color, alpha="00"):
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    rr, gg, bb = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha}{bb}{gg}{rr}&".upper()

_cfg_path = os.environ.get("DEMO_CONFIG", ".build/config.json")
_pal = {}
if os.path.exists(_cfg_path):
    with open(_cfg_path, encoding="utf-8") as _f:
        _pal = json.load(_f).get("subs", {})

BONE = _hex_to_ass_bgr(_pal.get("palette_fg", "#dcd7cf"))      # default text
BRASS = _hex_to_ass_bgr(_pal.get("palette_accent", "#dbaf71")) # highlighted word
BG_BOX = _hex_to_ass_bgr(_pal.get("palette_bg", "#0a0705"), alpha="66")  # soft box ~40%
SHADOW = "&H80000000&"  # black 50% alpha


def s_to_ass(seconds):
    """Convert seconds to ASS timecode H:MM:SS.cc"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def s_to_srt(seconds):
    """Convert seconds to SRT timecode HH:MM:SS,mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s_int = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s_int:02d},{ms:03d}"


def build_ass(data):
    """Build karaoke ASS with per-word \\k highlight from line-level timing."""
    header = f"""[Script Info]
Title: ExoVault Demo Captions
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,JetBrains Mono,40,{BRASS},{BONE},{SHADOW},{BG_BOX},0,0,0,0,100,100,0,0,1,2,4,2,80,80,120,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    lines_out = []
    for line in data["lines"]:
        start_t = s_to_ass(line["line_start"])
        # Hold the line ~400ms past the last word's end so reader can finish
        end_t = s_to_ass(line["line_end"] + 0.4)
        # Build karaoke text: each word gets a \k<duration_centiseconds> tag
        karaoke = ""
        prev_end = line["line_start"]
        for w in line["words"]:
            # Gap before this word (if any) — silence between words
            gap_s = max(0, w["start"] - prev_end)
            if gap_s > 0.05:
                karaoke += "{\\k%d} " % int(round(gap_s * 100))
            # Highlight duration for the word itself
            karaoke += "{\\k%d}%s " % (int(round(w["duration"] * 100)), w["text"])
            prev_end = w["start"] + w["duration"]
        karaoke = karaoke.rstrip()
        lines_out.append(
            f"Dialogue: 0,{start_t},{end_t},Default,,0,0,0,,{karaoke}"
        )

    return header + "\n".join(lines_out) + "\n"


def build_srt(data):
    """Build standard SRT — one cue per line, full text."""
    cues = []
    for i, line in enumerate(data["lines"], 1):
        start = s_to_srt(line["line_start"])
        end = s_to_srt(line["line_end"] + 0.4)
        cues.append(f"{i}\n{start} --> {end}\n{line['text']}\n")
    return "\n".join(cues)


def main():
    src = Path("vo-words.json")
    if not src.exists():
        raise SystemExit("vo-words.json not found — run: python make-vo.py")
    data = json.loads(src.read_text())

    ass = build_ass(data)
    Path("captions.ass").write_text(ass, encoding="utf-8")
    print(f"  captions.ass  -> {sum(1 for _ in ass.splitlines() if _.startswith('Dialogue'))} lines (karaoke)")

    srt = build_srt(data)
    Path("captions.srt").write_text(srt, encoding="utf-8")
    print(f"  captions.srt  -> {len(data['lines'])} cues (line-level)")


if __name__ == "__main__":
    main()
