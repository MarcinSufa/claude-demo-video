#!/usr/bin/env bash
# Burns karaoke ASS captions into the final video.
# Input:  videos/final-with-audio.mp4 + captions.ass
# Output: videos/final-with-captions.mp4
set -e
cd "$(dirname "$0")"

[ -f videos/final-with-audio.mp4 ] || { echo "Need videos/final-with-audio.mp4 — run bash mix-final.sh"; exit 1; }
[ -f captions.ass ] || { echo "Need captions.ass — run python make-captions.py"; exit 1; }

# ffmpeg's subtitles filter needs forward-slash path escaped for Windows
ASS_PATH=$(realpath captions.ass | sed 's|/|\\\\:/|; s|^\\\\:/|/|')

ffmpeg -y -hide_banner -loglevel error \
  -i videos/final-with-audio.mp4 \
  -vf "subtitles=captions.ass" \
  -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p \
  -c:a copy -movflags +faststart \
  videos/final-with-captions.mp4

echo "Done -> videos/final-with-captions.mp4"
ls -la videos/final-with-captions.mp4
