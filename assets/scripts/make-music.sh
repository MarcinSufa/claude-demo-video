#!/usr/bin/env bash
# Provides the music bed (music.mp3), fitted to the final video length.
# Modes (brand.yaml music.mode):
#   library    fetch a CC0 / public-domain track for music.style (calm, uplift, tech, bugfix)
#              from the manifest, cached per user; falls back to procedural with a WARNING
#   procedural synthesize a per-mood pad plus arpeggio (offline, no downloads)
#   file       use a track you supply (music.file); a missing file is a hard error
#   none       voice only
set -e
cd "$(dirname "$0")"

CFG="${DEMO_CONFIG:-config.json}"
MANIFEST="${DEMO_MUSIC_MANIFEST:-music/manifest.yaml}"
VIDEO=videos/final-rough.mp4

read_music() {
  python -c "import json,sys;print(json.load(open(sys.argv[1])).get('music',{}).get(sys.argv[2],sys.argv[3]))" "$CFG" "$1" "$2"
}
MODE=procedural; STYLE=calm; MFILE=""
if [ -f "$CFG" ]; then
  MODE=$(read_music mode procedural)
  STYLE=$(read_music style calm)
  MFILE=$(read_music file "")
fi
[ "$STYLE" = "warm" ] && STYLE=calm

bed_duration() {
  if [ -f "$VIDEO" ]; then
    ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$VIDEO"
    return
  fi
  python - "$CFG" <<'PY'
import json, os, sys
import timing_util
plan = json.load(open("scene-plan.json")) if os.path.exists("scene-plan.json") else {"scenes": []}
raws = [s.get("duration") for s in plan["scenes"]]
cfg = json.load(open(sys.argv[1])) if os.path.exists(sys.argv[1]) else {}
subs = cfg.get("subs", {})
if raws and all(r is not None for r in raws):
    print(round(timing_util.predict_video_seconds(
        [float(r) for r in raws], float(subs.get("speedup", 1.2)), float(subs.get("crossfade", 0.6))), 2))
else:
    print(60)
PY
}
DUR=$(bed_duration)
FADE_OUT_START=$(awk "BEGIN{d=$DUR; print (d > 6) ? d - 5 : d / 2}")

# fit_bed <source> : loop or trim the source to the video length, fade both ends, mp3 192k 44.1k
fit_bed() {
  ffmpeg -y -hide_banner -loglevel error -stream_loop -1 -i "$1" -t "$DUR" \
    -af "afade=t=in:st=0:d=2,afade=t=out:st=$FADE_OUT_START:d=5" \
    -c:a libmp3lame -b:a 192k -ar 44100 music.mp3
}

case "$MODE" in
  none)
    echo "music mode: none (voice only)"
    rm -f music.mp3
    : > .music-none
    exit 0 ;;
  file)
    rm -f .music-none
    SRC="$MFILE"
    [ -f "$SRC" ] || SRC="../$MFILE"
    [ -f "$SRC" ] || { echo "music.mode=file but '$MFILE' not found (looked in .build and project root)"; exit 1; }
    fit_bed "$SRC"
    echo "Done -> music.mp3 (${DUR}s, looped from $MFILE)"
    exit 0 ;;
  library)
    rm -f .music-none music-src
    if [ ! -f "$MANIFEST" ]; then
      echo "WARNING: music manifest not found ($MANIFEST), falling back to procedural '$STYLE'"
    else
      rc=0; python fetch-music.py --manifest "$MANIFEST" --style "$STYLE" --output music-src || rc=$?
      if [ "$rc" -eq 0 ]; then
        fit_bed music-src
        rm -f music-src
        echo "Done -> music.mp3 (${DUR}s, library track for '$STYLE')"
        exit 0
      elif [ "$rc" -eq 3 ]; then
        echo "music.mode=library: cannot write the fetched track into .build (see error above)"
        exit 3
      fi
      echo "WARNING: could not fetch a '$STYLE' library track, falling back to procedural '$STYLE'"
    fi ;;
  procedural) rm -f .music-none ;;
  *) echo "WARNING: unknown music.mode '$MODE', using procedural"; rm -f .music-none ;;
esac

# Procedural: four chords per mood, each a detuned three-voice pad under a plucked
# arpeggio, rendered once and looped to the video length by fit_bed.
case "$STYLE" in
  uplift)
    chords=( "261.63 329.63 392.00" "220.00 261.63 329.63" "174.61 220.00 261.63" "196.00 246.94 293.66" )
    CHORD=6; STEP=0.75; ARP_GAIN=0.22; DECAY=3; TONE="lowpass=f=2600,highpass=f=70" ;;
  tech)
    chords=( "164.81 246.94 329.63" "130.81 196.00 261.63" "146.83 220.00 293.66" "123.47 185.00 246.94" )
    CHORD=4; STEP=0.25; ARP_GAIN=0.2; DECAY=8; TONE="tremolo=f=4:d=0.35,lowpass=f=3200,highpass=f=60" ;;
  bugfix)
    chords=( "174.61 220.00 261.63" "196.00 246.94 293.66" "220.00 261.63 329.63" "261.63 329.63 392.00" )
    CHORD=4; STEP=0.5; ARP_GAIN=0.26; DECAY=5; TONE="vibrato=f=5:d=0.08,lowpass=f=3000,highpass=f=80" ;;
  *)
    chords=( "130.81 155.56 196.00" "103.83 130.81 155.56" "116.54 146.83 174.61" "98.00 116.54 146.83" )
    CHORD=8; STEP=2; ARP_GAIN=0.16; DECAY=1.5; TONE="lowpass=f=1600,highpass=f=80" ;;
esac

WORK=.music-work; rm -rf "$WORK"; mkdir -p "$WORK"
LIST="$WORK/list.txt"; : > "$LIST"
for c in 0 1 2 3; do
  read -r f1 f2 f3 <<< "${chords[$c]}"
  a1=$(awk "BEGIN{print $f1*2}"); a2=$(awk "BEGIN{print $f2*2}"); a3=$(awk "BEGIN{print $f3*2}")
  CYCLE=$(awk "BEGIN{print $STEP*3}")
  ARP="sin(2*PI*if(lt(mod(t,$CYCLE),$STEP),$a1,if(lt(mod(t,$CYCLE),$STEP*2),$a2,$a3))*mod(t,$STEP))*exp(-$DECAY*mod(t,$STEP))*$ARP_GAIN"
  ffmpeg -y -hide_banner -loglevel error \
    -f lavfi -i "sine=frequency=$f1:duration=$CHORD" \
    -f lavfi -i "sine=frequency=$(awk "BEGIN{print $f2*1.003}"):duration=$CHORD" \
    -f lavfi -i "sine=frequency=$(awk "BEGIN{print $f3*0.997}"):duration=$CHORD" \
    -f lavfi -i "aevalsrc='$ARP':s=44100:d=$CHORD" \
    -filter_complex "[0]volume=0.42[a];[1]volume=0.3[b];[2]volume=0.24[c];[3]aformat=channel_layouts=mono[d];[a][b][c][d]amix=inputs=4:normalize=0,afade=t=in:st=0:d=0.4,afade=t=out:st=$(awk "BEGIN{print $CHORD-0.8}"):d=0.8" \
    "$WORK/seg_$c.wav"
  echo "file 'seg_$c.wav'" >> "$LIST"
done
ffmpeg -y -hide_banner -loglevel error -f concat -safe 0 -i "$LIST" \
  -af "aecho=0.8:0.6:600|1200:0.3|0.18,$TONE,dynaudnorm=f=400:g=15" "$WORK/loop.wav"
fit_bed "$WORK/loop.wav"
rm -rf "$WORK"
echo "Done -> music.mp3 (${DUR}s procedural '$STYLE')"
