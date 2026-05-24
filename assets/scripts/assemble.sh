#!/usr/bin/env bash
# Assembles all scenes into a single 1920x1080 30fps rough cut with cross-fades.
# Output: videos/final-rough.mp4 (no audio)
set -e
cd "$(dirname "$0")"

# Config-driven values (config.json lives alongside in the .build working dir)
CFG="${DEMO_CONFIG:-config.json}"
if [ -f "$CFG" ]; then
  BG="0x$(python -c "import json;print(json.load(open('$CFG'))['subs']['palette_bg'].lstrip('#'))")"
  XF=$(python -c "import json;print(json.load(open('$CFG'))['subs']['crossfade'])")
  SPEEDUP=$(python -c "import json;print(json.load(open('$CFG'))['subs']['speedup'])")
else
  BG="0x0a0705"; XF=0.6; SPEEDUP=1.20
fi
W=1920
H=1080
FPS=30

NORM_DIR="$(pwd)/.normalized"
mkdir -p "$NORM_DIR"

normalize() {
  local in="$1" out="$2"
  if [ -f "$out" ] && [ "$out" -nt "$in" ]; then
    echo "  → cached: $(basename "$out")"
    return
  fi
  echo "  → normalizing + speed ${SPEEDUP}x: $(basename "$in")"
  ffmpeg -y -hide_banner -loglevel error -i "$in" \
    -vf "scale=${W}:${H}:force_original_aspect_ratio=decrease,pad=${W}:${H}:(ow-iw)/2:(oh-ih)/2:color=${BG},setsar=1,setpts=PTS/${SPEEDUP},fps=${FPS}" \
    -c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p -an \
    "$out"
}

# Scene order comes from scene-plan.json (default 7-scene arc OR custom_scenes)
PLAN="${DEMO_PLAN:-scene-plan.json}"
[ -f "$PLAN" ] || { echo "Missing $PLAN — run plan-scenes.py first"; exit 1; }

# Ordered list of source mp4 paths
mapfile -t SCENE_MP4S < <(python -c "import json;[print(s['mp4']) for s in json.load(open('$PLAN'))['scenes']]" | tr -d '\r')
N=${#SCENE_MP4S[@]}
[ "$N" -ge 2 ] || { echo "Need >=2 scenes, got $N"; exit 1; }

echo "[1/2] Normalize $N scenes to ${W}x${H} ${FPS}fps (speed ${SPEEDUP}x)"
NORM_LIST=()
for i in "${!SCENE_MP4S[@]}"; do
  src="${SCENE_MP4S[$i]}"
  [ -f "$src" ] || { echo "  missing scene mp4: $src"; exit 1; }
  out="$NORM_DIR/s$((i+1)).mp4"
  normalize "$src" "$out"
  NORM_LIST+=("$out")
done

echo "[2/2] Cross-fade chain (dynamic, $N scenes)"
# Build + run the xfade chain in python (clean offset math for any N)
python - "$XF" "$NORM_DIR" "$N" videos/final-rough.mp4 <<'PY'
import subprocess, sys
XF = float(sys.argv[1]); NORM = sys.argv[2]; N = int(sys.argv[3]); OUT = sys.argv[4]

def dur(p):
    out = subprocess.check_output(["ffprobe","-v","error","-select_streams","v",
        "-show_entries","stream=duration","-of","csv=p=0", p]).decode().strip()
    return float(out)

inputs, durs = [], []
for i in range(1, N+1):
    p = f"{NORM}/s{i}.mp4"; inputs += ["-i", p]; durs.append(dur(p))

# Cumulative xfade offsets
offsets = []
acc = durs[0] - XF
for i in range(1, N):
    offsets.append(round(acc, 3))
    acc += durs[i] - XF
final = round(acc + XF, 2)

# Filtergraph: chain xfades
parts, prev = [], "[0:v]"
for i in range(1, N):
    label = "[vout]" if i == N-1 else f"[v{i}]"
    parts.append(f"{prev}[{i}:v]xfade=transition=fade:duration={XF}:offset={offsets[i-1]}{label}")
    prev = label
fc = ";".join(parts)

print(f"  final duration ~{final}s")
cmd = ["ffmpeg","-y","-hide_banner","-loglevel","error", *inputs,
       "-filter_complex", fc, "-map", "[vout]",
       "-c:v","libx264","-preset","slow","-crf","18","-pix_fmt","yuv420p",
       "-movflags","+faststart", OUT]
sys.exit(subprocess.run(cmd).returncode)
PY

echo ""
echo "Done -> videos/final-rough.mp4"
ls -la videos/final-rough.mp4
