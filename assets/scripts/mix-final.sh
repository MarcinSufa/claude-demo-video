#!/usr/bin/env bash
# Mixes vo.mp3 + music bed (sidechain ducked under voice) and muxes to video.
# Honors music.mode: none (voice only) | file | procedural. Reads music.volume.
# Output: videos/final-with-audio.mp4
set -e
cd "$(dirname "$0")"

VIDEO=videos/final-rough.mp4
VO=vo.mp3
MUSIC=music.mp3
OUT=videos/final-with-audio.mp4
CFG="${DEMO_CONFIG:-config.json}"

[ -f "$VO" ] || { echo "Missing $VO — run: python make-vo.py"; exit 1; }

MUSIC_VOL=0.45
[ -f "$CFG" ] && MUSIC_VOL=$(python -c "import json;print(json.load(open('$CFG')).get('music',{}).get('volume',0.45))")

VIDEO_DUR=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$VIDEO")

# ── P0-1 safety net: never silently truncate narration ──
# Below, the voice is apad-padded then hard-cut with `-t "$VIDEO_DUR"`. If the
# voiceover runs past the video, the closing line is lost with no warning. Gate it.
python check-timing.py "$VIDEO" vo-words.json || exit 1

if [ -f .music-none ] || [ ! -f "$MUSIC" ]; then
  # ── Voice only (music.mode: none) ──
  echo "Mixing: voice only (no music bed)"
  ffmpeg -y -hide_banner -loglevel error \
    -i "$VIDEO" -i "$VO" \
    -filter_complex "[1:a]adelay=200|200,volume=1.0,apad,loudnorm=I=-16:LRA=11:TP=-1.5[aout]" \
    -map 0:v -map "[aout]" -c:v copy -c:a aac -b:a 192k -ar 48000 -t "$VIDEO_DUR" "$OUT"
else
  # ── Voice + music bed (sidechain ducked) ──
  echo "Mixing: voice + music (vol ${MUSIC_VOL}, sidechain ducked)"
  ffmpeg -y -hide_banner -loglevel error \
    -i "$VIDEO" -i "$VO" -i "$MUSIC" \
    -filter_complex "\
      [1:a]adelay=200|200,volume=1.0,apad,asplit=2[voice][voiceDuck];\
      [2:a]volume=${MUSIC_VOL}[music];\
      [music][voiceDuck]sidechaincompress=threshold=0.04:ratio=4:attack=15:release=300:makeup=1[ducked];\
      [ducked][voice]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,\
        loudnorm=I=-16:LRA=11:TP=-1.5[aout]" \
    -map 0:v -map "[aout]" -c:v copy -c:a aac -b:a 192k -ar 48000 -t "$VIDEO_DUR" "$OUT"
fi

echo ""
echo "Done -> $OUT"
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$OUT" | awk '{printf "Duration: %.2fs\n", $1}'
