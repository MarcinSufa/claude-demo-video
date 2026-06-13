#!/usr/bin/env bash
# tests/smoke_build.sh — end-to-end integration smoke for /demo-video.
#
# Unit tests cover pure logic; this catches INTEGRATION breaks they can't —
# mockups not copied into .build (404 frames), a vendored-script arg skew that
# ships a mascot-less video, white-flash blank frames, etc.
#
# Two tiers, gracefully degrading:
#   * plan smoke  (always; needs only ffmpeg + python + pyyaml): scaffolds a tiny
#     project and runs `build.sh --plan` — exercises config parse, scene-plan
#     resolution and the drift guard.
#   * full smoke  (when node + edge-tts + a Playwright node_modules are present):
#     a real render of 2 html_mockup scenes + endcards + a shaded mascot, then
#     asserts a non-blank video came out.
#
#   bash tests/smoke_build.sh
#   DEMO_SMOKE_NODE_MODULES=/path/to/node_modules bash tests/smoke_build.sh
set -uo pipefail
SKILL="$(cd "$(dirname "$0")/.." && pwd)"
ASSETS="$SKILL/assets"

have() { command -v "$1" >/dev/null 2>&1; }
fail() { echo "SMOKE FAIL: $1"; exit 1; }

# nonblank <video> <t1> [t2 ...] — pass (0) if ANY sampled frame has real colour
# variety (>20 distinct colours at 64x36). Sampling several frames and taking the
# richest catches a genuinely blank / white-flash render without flaking on a
# single dark beat (e.g. a long end-card scene that dominates the timeline).
nonblank() {
  local vid="$1"; shift
  local t best=0 n
  for t in "$@"; do
    ffmpeg -y -v error -ss "$t" -i "$vid" -frames:v 1 "$TMP/nb.png" 2>/dev/null || continue
    n=$(python - "$TMP/nb.png" <<'PY'
import subprocess, sys
try:
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", sys.argv[1],
        "-vf", "scale=64:36", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
    print(len({raw[i:i + 3] for i in range(0, len(raw), 3)}))
except Exception:
    print(0)
PY
)
    [ "${n:-0}" -gt "$best" ] && best="$n"
  done
  [ "$best" -gt 20 ]
}

have python || fail "python not found"
have ffmpeg || fail "ffmpeg not found"
python -c "import yaml" 2>/dev/null || fail "pyyaml not found (pip install pyyaml)"

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
PROJ="$TMP/demo-video"; mkdir -p "$PROJ"/{scripts,templates,mascots,mockups,footage}
cp "$ASSETS"/scripts/* "$PROJ/scripts/" 2>/dev/null || true
cp -r "$ASSETS"/templates/* "$PROJ/templates/" 2>/dev/null || true
cp "$ASSETS"/mascots/*.json "$PROJ/mascots/" 2>/dev/null || true
cp "$ASSETS/package.example.json" "$PROJ/package.json"

cat > "$PROJ/mockups/a.html" <<'H'
<!DOCTYPE html><html style="background:#0a0705"><body style="background:#0a0705;margin:0">
<div style="color:#dbaf71;font:48px sans-serif;padding:80px">Smoke scene A</div></body></html>
H
cat > "$PROJ/mockups/b.html" <<'H'
<!DOCTYPE html><html style="background:#0a0705"><body style="background:#0a0705;margin:0">
<div style="color:#dcd7cf;font:48px sans-serif;padding:80px">Smoke scene B</div></body></html>
H

# Diorama source-window clips: colourful testsrc2 → guaranteed non-blank windows.
ffmpeg -y -v error -f lavfi -i "testsrc2=s=1280x720:d=4" "$PROJ/footage/da.mp4"
ffmpeg -y -v error -f lavfi -i "testsrc2=s=1280x720:d=4,hue=h=140" "$PROJ/footage/db.mp4"

cat > "$PROJ/brand.yaml" <<'Y'
project: { name: "Smoke", url: "smoke.test", version_tag: "v0" }
palette: { bg: "#0a0705", fg: "#dcd7cf", accent: "#dbaf71", rule: "#29231f", end_card_bg: "#1e1714" }
logo: { wordmark_italic: "Smo", wordmark_roman: "ke" }
typography: { display: "Newsreader", body: "Inter", mono: "JetBrains Mono" }
voice: { provider: "edge-tts", voice_id: "en-US-AndrewNeural" }
music: { mode: "none" }
backdrop: { type: "color", color: "#0a0705" }
scenes:
  speedup: 1.0
  sequence:
    - { type: html_mockup, source: "mockups/a.html", duration: 4 }
    - { type: html_mockup, source: "mockups/b.html", duration: 4 }
    - type: diorama
      duration: 6
      canvas: { width: 2560, height: 1440, backdrop: "color=c=0x0a0705" }
      windows:
        - { id: a, source: "footage/da.mp4", x: 120, y: 300, w: 1000 }
        - { id: b, source: "footage/db.mp4", x: 1440, y: 600, w: 1000 }
      camera:
        - { focus: a, zoom: 1.7, hold: 2.5 }
        - { focus: b, zoom: 1.7, hold: 2.5, transition: 1.0 }
      mascot:
        keyframes:
          - { at: 0, emotion: idle,  at_window: a, anchor: top }
          - { at: 3, emotion: point, at_window: b, anchor: beside }
    - endcards
voiceover:
  - { text: "Smoke test scene one.", pause_after: 0.4 }
  - { text: "Smoke test scene two.", pause_after: 0.4 }
  - { text: "Windows on a canvas, one camera.", pause_after: 0.4 }
end_cards: { tagline: "Smoke.", spec_line: "a - b - c", url_pill: "smoke.test" }
mascot: { character: octopus, enabled: true, shade: true }
Y

cd "$PROJ"

echo "== plan smoke =="
if ! bash scripts/build.sh --plan > "$TMP/plan.log" 2>&1; then
  cat "$TMP/plan.log"; fail "--plan exited non-zero"
fi
grep -q "html_mockup" "$TMP/plan.log" || { cat "$TMP/plan.log"; fail "--plan did not resolve scenes"; }
echo "   plan OK"

NM="${DEMO_SMOKE_NODE_MODULES:-}"
[ -z "$NM" ] && [ -d "$SKILL/node_modules/playwright" ] && NM="$SKILL/node_modules"
if ! have node || ! python -c "import edge_tts" 2>/dev/null || [ -z "$NM" ] || [ ! -d "$NM/playwright" ]; then
  echo "== full build smoke: SKIP =="
  echo "   (needs node + edge-tts + a Playwright node_modules; set DEMO_SMOKE_NODE_MODULES=/path)"
  echo "SMOKE PASS (plan only)"; exit 0
fi

echo "== full build smoke =="
ln -s "$NM" node_modules 2>/dev/null || cp -r "$NM" node_modules
if ! bash scripts/build.sh > "$TMP/build.log" 2>&1; then
  tail -30 "$TMP/build.log"; fail "full build exited non-zero"
fi
OUT="videos/final-with-captions.mp4"
[ -f "$OUT" ] || { tail -30 "$TMP/build.log"; fail "no $OUT produced"; }
DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT" 2>/dev/null)
python -c "import sys; sys.exit(0 if float('${DUR:-0}') > 2 else 1)" || fail "video too short ($DUR s)"
# non-blank render: sample frames across the timeline (fractions of DUR) and
# require at least one with real colour variety. Multi-sample so a long dark
# end-card scene can't blank the single midpoint sample (catches white-flash /
# blank renders without flaking on scene composition).
SAMPLES=$(python -c "d=float('${DUR:-0}');print(' '.join(f'{d*f:.2f}' for f in (0.1,0.25,0.4,0.55,0.7)))")
nonblank "$OUT" $SAMPLES || fail "render looks blank (no colourful frame across the video)"
echo "   full build OK ($OUT, ${DUR}s)"

# Diorama tier: the diorama scene clip must be a non-blank 1920x1080 canvas+camera
# render with the mascot composited on it (the one path the mascot:null isolation
# tests can't reach). Locate it from the plan — sequence dict-items get c<N> ids.
DIO=".build/$(python -c "import json;print(next(s['mp4'] for s in json.load(open('.build/scene-plan.json'))['scenes'] if s['type']=='diorama'))" 2>/dev/null)"
[ -f "$DIO" ] || { tail -30 "$TMP/build.log"; fail "no diorama clip built ($DIO)"; }
DW=$(ffprobe -v error -select_streams v:0 -show_entries stream=width -of csv=p=0 "$DIO")
DH=$(ffprobe -v error -select_streams v:0 -show_entries stream=height -of csv=p=0 "$DIO")
{ [ "$DW" = "1920" ] && [ "$DH" = "1080" ]; } || fail "diorama clip not 1920x1080 (${DW}x${DH})"
nonblank "$DIO" 1 3 5 || fail "diorama clip looks blank (canvas/camera/mascot composite produced no colour)"
# The diorama must normalize window clips on workdir COPIES, never the user's
# source footage in place. The smoke's source windows were generated at 4s and
# the scene is 6s — if make-diorama pad-normalized them in place they'd now be 6s.
for f in footage/da.mp4 footage/db.mp4; do
  fdur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$f" 2>/dev/null)
  python -c "import sys;sys.exit(0 if abs(float('${fdur:-0}')-4.0)<0.3 else 1)" \
    || fail "diorama mutated source footage in place ($f is ${fdur}s, expected ~4s)"
done
echo "   diorama OK ($DIO, ${DW}x${DH}); source footage intact"
echo "SMOKE PASS"
