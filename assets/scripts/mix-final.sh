#!/usr/bin/env bash
# Mixes vo.mp3 + music.mp3 (sidechain ducked under voice) and muxes to video.
# Output: videos/final-with-audio.mp4
set -e
cd "$(dirname "$0")"

VIDEO=videos/final-rough.mp4
VO=vo.mp3
MUSIC=music.mp3
OUT=videos/final-with-audio.mp4

[ -f "$VO" ] || { echo "Missing $VO — run: python make-vo.py"; exit 1; }
[ -f "$MUSIC" ] || { echo "Missing $MUSIC — run: bash make-music.sh"; exit 1; }

# Pad VO with 0.5s leading silence so first line lands ~0.5s into the video
# Mix: voice at -2dB, music at -22dB ducked by voice (sidechain compress)
ffmpeg -y -hide_banner -loglevel error \
  -i "$VIDEO" \
  -i "$VO" \
  -i "$MUSIC" \
  -filter_complex "\
    [1:a]adelay=200|200,volume=1.0,apad,asplit=2[voice][voiceDuck];\
    [2:a]volume=0.45[music];\
    [music][voiceDuck]sidechaincompress=threshold=0.04:ratio=4:attack=15:release=300:makeup=1[ducked];\
    [ducked][voice]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,\
      loudnorm=I=-16:LRA=11:TP=-1.5[aout]" \
  -map 0:v -map "[aout]" \
  -c:v copy \
  -c:a aac -b:a 192k -ar 48000 \
  -t $(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$VIDEO") \
  "$OUT"

echo ""
echo "Done → $OUT"
ls -la "$OUT"
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$OUT" | awk '{printf "Duration: %.2fs\n", $1}'
