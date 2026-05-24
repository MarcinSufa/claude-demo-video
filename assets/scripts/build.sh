#!/usr/bin/env bash
# /demo-video build orchestrator.
# Everything runs inside a flat .build/ working dir (rendered templates + copied
# scripts), exactly mirroring the proven reference layout. Final video copied to videos/.
#
# Run from project root (where brand.yaml lives):  bash scripts/build.sh
set -euo pipefail

ROOT="$(pwd)"
SKILL_SCRIPTS="$(cd "$(dirname "$0")" && pwd)"   # .../scripts
BUILD=".build"

[ -f brand.yaml ] || { echo "Missing brand.yaml — run /demo-video init or copy assets/brand.example.yaml"; exit 1; }

# --plan = P3-1 dry run: resolve scenes + estimate VO length, no TTS/capture/encode.
PLAN_ONLY=0
for arg in "$@"; do case "$arg" in --plan) PLAN_ONLY=1;; esac; done

# ─── 0. Prerequisites ──────────────────────────────────────────────────
echo "[0/8] Verifying prerequisites..."
for cmd in ffmpeg ffprobe python; do command -v $cmd >/dev/null || { echo "Missing: $cmd"; exit 1; }; done
python -c "import yaml" 2>/dev/null || { echo "Missing: pip install --user pyyaml"; exit 1; }
if [ "$PLAN_ONLY" = "0" ]; then
  command -v node >/dev/null || { echo "Missing: node"; exit 1; }
  python -c "import edge_tts" 2>/dev/null || { echo "Missing: pip install --user edge-tts"; exit 1; }
  command -v vhs >/dev/null || command -v docker >/dev/null || { echo "Missing: VHS (winget install charmbracelet.vhs) or Docker"; exit 1; }
  [ -d node_modules/playwright ] || { echo "Missing: pnpm add playwright && pnpm exec playwright install chromium"; exit 1; }
fi

# ─── 1. Compile brand → .build/ ────────────────────────────────────────
echo "[1/8] Compiling brand.yaml → $BUILD/ ..."
python "$SKILL_SCRIPTS/apply-brand.py" --brand brand.yaml --templates templates --out "$BUILD"

# Copy runtime scripts into .build/ so each `cd $(dirname $0)` operates there
cp "$SKILL_SCRIPTS"/{make-vo.py,make-captions.py,make-music.sh,plan-scenes.py,build-scenes.sh,assemble.sh,mix-final.sh,burn-captions.sh,record-frame.mjs,record-graph.mjs,record-endcards.mjs,record-browser.mjs,timing_util.py,check-timing.py,dry-run-plan.py,normalize-clip.py} "$BUILD/"

mkdir -p "$BUILD/videos"

# ─── --plan: dry run (resolve scenes + estimate VO), then exit ──────────
if [ "$PLAN_ONLY" = "1" ]; then
  cd "$BUILD"; export DEMO_CONFIG=config.json
  python plan-scenes.py
  rc=0; python dry-run-plan.py || rc=$?
  exit $rc
fi

# node_modules + backdrop into .build/ (full build only)
[ -e "$BUILD/node_modules" ] || ln -s "$ROOT/node_modules" "$BUILD/node_modules" 2>/dev/null || cp -r node_modules "$BUILD/node_modules"
BACKDROP_SRC="$(python -c "import json;print(json.load(open('$BUILD/config.json'))['subs']['backdrop_source'])")"
if [[ "$BACKDROP_SRC" == http* ]]; then
  echo "  downloading backdrop..."
  curl -L -s -o "$BUILD/videos/backdrop.jpg" "$BACKDROP_SRC" || echo "  (backdrop download failed — frame uses bg color)"
elif [ -f "$BACKDROP_SRC" ]; then
  cp "$BACKDROP_SRC" "$BUILD/videos/backdrop.jpg"
elif [ -f "$ROOT/$BACKDROP_SRC" ]; then
  cp "$ROOT/$BACKDROP_SRC" "$BUILD/videos/backdrop.jpg"
fi

cd "$BUILD"
export DEMO_CONFIG=config.json

# Local server for Playwright HTML scenes
if ! curl -s -o /dev/null http://localhost:8765/; then
  python -m http.server 8765 >/dev/null 2>&1 &
  SERVER_PID=$!
  trap "kill $SERVER_PID 2>/dev/null || true" EXIT
  sleep 1
fi

# ─── 2-8. Pipeline ─────────────────────────────────────────────────────
echo "[2/8] Voiceover (Edge TTS)...";   python make-vo.py
echo "[3/8] Captions...";               python make-captions.py
[ -f music.mp3 ] || { echo "[4/8] Music..."; bash make-music.sh; }
echo "[5/8] Planning + recording scenes..."
python plan-scenes.py
bash build-scenes.sh
echo "[6/8] Assembling crossfade..."; bash assemble.sh
echo "[7/8] Mixing audio + captions..."; bash mix-final.sh; bash burn-captions.sh
echo "[8/8] Terminal-on-desk composite..."; node record-frame.mjs

# ─── Copy out ──────────────────────────────────────────────────────────
cd "$ROOT"; mkdir -p videos
cp "$BUILD/videos/final-framed.mp4" videos/
cp "$BUILD/videos/final-with-captions.mp4" videos/ 2>/dev/null || true
cp "$BUILD/captions.srt" videos/ 2>/dev/null || true

echo ""
echo "Done → videos/final-framed.mp4"
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 videos/final-framed.mp4 | awk '{printf "Duration: %.1fs\n", $1}'
