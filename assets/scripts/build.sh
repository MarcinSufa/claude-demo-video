#!/usr/bin/env bash
# /demo-video build orchestrator.
# Everything runs inside a flat .build/ working dir (rendered templates + copied
# scripts), exactly mirroring the proven reference layout. Final video copied to videos/.
#
# Usage (run from project root, where brand.yaml lives):
#   bash scripts/build.sh                 # full build
#   bash scripts/build.sh --plan          # P3-1 dry run: scene/VO length estimate, no render
#   bash scripts/build.sh --no-cache      # P0-2: ignore cached scene clips, recapture all
#   bash scripts/build.sh --only c2       # P0-2: force-recapture scene c2, reuse the rest
set -euo pipefail

# P3-2: keep non-Latin VO logs (Polish etc.) readable regardless of the OS console codepage.
export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1

ROOT="$(pwd)"
SKILL_SCRIPTS="$(cd "$(dirname "$0")" && pwd)"   # .../scripts
BUILD=".build"

# ─── Progress bar + elapsed/ETA ─────────────────────────────────────────
BUILD_START=$(date +%s)
step() {                       # step <percent> <label...>
  local pct=$1; shift
  local label="$*"
  local width=22
  local filled=$((pct * width / 100))
  local i bar=""
  for ((i = 0; i < width; i++)); do [ "$i" -lt "$filled" ] && bar+="█" || bar+="░"; done
  local el=$(( $(date +%s) - BUILD_START ))
  printf "\n[%s] %3d%%  %-28s %dm%02ds\n" "$bar" "$pct" "$label" $((el / 60)) $((el % 60))
}

[ -f brand.yaml ] || { echo "Missing brand.yaml — run /demo-video init or copy assets/brand.example.yaml"; exit 1; }

# ─── Flags ──────────────────────────────────────────────────────────────
PLAN_ONLY=0; NO_CACHE=0; ONLY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --plan)            PLAN_ONLY=1 ;;
    --no-cache|--force) NO_CACHE=1 ;;
    --only)            shift; ONLY="${1:-}" ;;
    --only=*)          ONLY="${1#--only=}" ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
  shift
done

# ─── 0. Base prerequisites (needed just to compile + resolve the plan) ──
step 4 "Verifying prerequisites"
for cmd in ffmpeg ffprobe python; do command -v $cmd >/dev/null || { echo "Missing: $cmd"; exit 1; }; done
python -c "import yaml" 2>/dev/null || { echo "Missing: pip install --user pyyaml"; exit 1; }

# ─── 1. Compile brand → .build/ + copy runtime scripts ──────────────────
step 10 "Compiling brand.yaml"
python "$SKILL_SCRIPTS/apply-brand.py" --brand brand.yaml --templates templates --out "$BUILD"
cp "$SKILL_SCRIPTS"/{make-vo.py,make-captions.py,make-music.sh,plan-scenes.py,build-scenes.sh,assemble.sh,mix-final.sh,burn-captions.sh,record-frame.mjs,record-graph.mjs,record-endcards.mjs,record-browser.mjs,make-auth.mjs,timing_util.py,check-timing.py,dry-run-plan.py,normalize-clip.py,scene_cache.py,prereqs.py,autofit.py} "$BUILD/"
mkdir -p "$BUILD/videos"

cd "$BUILD"
export DEMO_CONFIG=config.json

# Resolve the scene plan early (cheap) — drives both --plan and the arc-aware gate.
python plan-scenes.py

# ─── --plan: dry run (estimate VO + video length), then exit ────────────
if [ "$PLAN_ONLY" = "1" ]; then
  rc=0; python dry-run-plan.py || rc=$?
  exit $rc
fi

# Rough ETA from the scene count (TTS + captures + assemble/encode dominate).
N_SCENES=$(python -c "import json;print(len(json.load(open('scene-plan.json'))['scenes']))")
EST_LO=$(( (45 + N_SCENES * 18) / 60 )); EST_HI=$(( (75 + N_SCENES * 30) / 60 + 1 ))
echo "  Estimated build time: ~${EST_LO}-${EST_HI} min ($N_SCENES scenes). Live progress below."

# ─── 0b. Arc-aware prerequisite gate (full build) ───────────────────────
# Playwright is always needed (end-card / graph / terminal-on-desk composite use it).
command -v node >/dev/null || { echo "Missing: node"; exit 1; }
python -c "import edge_tts" 2>/dev/null || { echo "Missing: pip install --user edge-tts"; exit 1; }
[ -d "$ROOT/node_modules/playwright" ] || { echo "Missing: pnpm add playwright && pnpm exec playwright install chromium"; exit 1; }
# VHS/Docker is needed ONLY for terminal / multi-agent scenes.
if python prereqs.py needs-vhs scene-plan.json; then
  command -v vhs >/dev/null || command -v docker >/dev/null || {
    echo "Missing: VHS (winget install charmbracelet.vhs) or Docker — required for terminal/multi-agent scenes"; exit 1; }
fi

# ─── node_modules + backdrop into .build/ ───────────────────────────────
[ -e node_modules ] || ln -s "$ROOT/node_modules" node_modules 2>/dev/null || cp -r "$ROOT/node_modules" node_modules
BACKDROP_SRC="$(python -c "import json;print(json.load(open('config.json'))['subs']['backdrop_source'])")"
if [[ "$BACKDROP_SRC" == http* ]]; then
  echo "  downloading backdrop..."
  curl -L -s -o videos/backdrop.jpg "$BACKDROP_SRC" || echo "  (backdrop download failed — frame uses bg color)"
elif [ -f "$ROOT/$BACKDROP_SRC" ]; then
  cp "$ROOT/$BACKDROP_SRC" videos/backdrop.jpg
elif [ -f "$BACKDROP_SRC" ]; then
  cp "$BACKDROP_SRC" videos/backdrop.jpg
fi

# Local server for Playwright HTML scenes (serves .build/)
if ! curl -s -o /dev/null http://localhost:8765/; then
  python -m http.server 8765 >/dev/null 2>&1 &
  SERVER_PID=$!
  trap "kill $SERVER_PID 2>/dev/null || true" EXIT
  sleep 1
fi

# ─── 2-8. Pipeline ──────────────────────────────────────────────────────
step 26 "Voiceover (Edge TTS)";     python make-vo.py
step 34 "Captions";                 python make-captions.py
# Always (re)generate so a changed music.mode/style/file actually takes effect
# (previously cached by file existence, so style changes were silently ignored).
step 40 "Music bed"; bash make-music.sh
# P2-1: log in once if an auth block is configured (authed scenes reuse the session)
if [ "$(python -c "import json;print(bool(json.load(open('config.json')).get('auth',{}).get('login_url')))")" = "True" ]; then
  step 46 "Auth login (storageState)"; node make-auth.mjs
fi
step 52 "Recording scenes";         DEMO_NO_CACHE="$NO_CACHE" DEMO_ONLY="$ONLY" bash build-scenes.sh
# P0-1 (opt-in): fit playback speed to the voiceover length
if [ "$(python -c "import json;print(json.load(open('config.json')).get('scenes',{}).get('autofit',False))")" = "True" ]; then
  step 76 "Auto-fit speed to voiceover"; python autofit.py
fi
step 80 "Assembling crossfade";     bash assemble.sh
step 90 "Mixing audio + captions";  bash mix-final.sh; bash burn-captions.sh
step 96 "Compositing frame";        node record-frame.mjs
step 100 "Done"

# ─── Copy out ───────────────────────────────────────────────────────────
cd "$ROOT"; mkdir -p videos
cp "$BUILD/videos/final-framed.mp4" videos/
cp "$BUILD/videos/final-with-captions.mp4" videos/ 2>/dev/null || true
cp "$BUILD/captions.srt" videos/ 2>/dev/null || true

echo ""
echo "Done -> videos/final-framed.mp4"
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 videos/final-framed.mp4 | awk '{printf "Duration: %.1fs\n", $1}'
