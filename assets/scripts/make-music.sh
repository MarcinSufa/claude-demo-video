#!/usr/bin/env bash
# Generates a soft warm ambient pad as placeholder music (60s).
# Procedural — uses ffmpeg sine waves + reverb + lowpass for a warm drone.
# Replace with a real licensed track before publishing.
set -e
cd "$(dirname "$0")"

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

echo "Done → music.mp3 (${DUR}s warm pad placeholder)"
