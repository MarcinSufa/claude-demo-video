#!/usr/bin/env bash
# Provides the music bed. Three modes (from brand.yaml music.mode):
#   procedural — generate a soft warm ambient pad (ffmpeg sine + reverb). DEFAULT.
#   file       — use a real track you supply (music.file). Free sources:
#                  Pixabay Music, Free Music Archive (CC0), YouTube Audio Library.
#   none       — no music bed (voice only).
set -e
cd "$(dirname "$0")"

CFG="${DEMO_CONFIG:-config.json}"
MODE="procedural"; MFILE=""
if [ -f "$CFG" ]; then
  MODE=$(python -c "import json;print(json.load(open('$CFG')).get('music',{}).get('mode','procedural'))")
  MFILE=$(python -c "import json;print(json.load(open('$CFG')).get('music',{}).get('file',''))")
fi

case "$MODE" in
  none)
    echo "music mode: none — skipping music bed"
    rm -f music.mp3
    : > .music-none   # sentinel so mix-final knows to skip
    exit 0 ;;
  file)
    [ -f .music-none ] && rm -f .music-none
    # Resolve file relative to project root (one level up from .build) or absolute
    SRC="$MFILE"
    [ -f "$SRC" ] || SRC="../$MFILE"
    [ -f "$SRC" ] || { echo "music.mode=file but '$MFILE' not found (looked in .build and project root)"; exit 1; }
    echo "music mode: file — using $MFILE"
    # Normalize to mp3 192k so mix-final treats it uniformly
    ffmpeg -y -hide_banner -loglevel error -i "$SRC" -c:a libmp3lame -b:a 192k -ar 44100 music.mp3
    echo "Done -> music.mp3 (from $MFILE)"
    exit 0 ;;
esac

# ── procedural (default) ──
[ -f .music-none ] && rm -f .music-none
DUR=60

# C minor chord — C3 + Eb3 + G3 + C4 — soft and contemplative
ffmpeg -y -hide_banner -loglevel error \
  -f lavfi -i "sine=frequency=130.81:duration=${DUR}" \
  -f lavfi -i "sine=frequency=155.56:duration=${DUR}" \
  -f lavfi -i "sine=frequency=196.00:duration=${DUR}" \
  -f lavfi -i "sine=frequency=261.63:duration=${DUR}" \
  -f lavfi -i "sine=frequency=311.13:duration=${DUR}" \
  -filter_complex "\
    [0]volume=0.5[a0];\
    [1]volume=0.35[a1];\
    [2]volume=0.3[a2];\
    [3]volume=0.2[a3];\
    [4]volume=0.15[a4];\
    [a0][a1][a2][a3][a4]amix=inputs=5:duration=longest:normalize=0,\
    aecho=0.8:0.6:880|1760|2640:0.35|0.22|0.15,\
    lowpass=f=1600,\
    highpass=f=80,\
    dynaudnorm=f=400:g=15,\
    afade=t=in:st=0:d=4,afade=t=out:st=$(awk "BEGIN{print $DUR-5}"):d=5" \
  -c:a libmp3lame -b:a 192k -ar 44100 \
  music.mp3

echo "Done -> music.mp3 (${DUR}s procedural warm pad)"
