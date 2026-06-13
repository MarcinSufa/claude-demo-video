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

have python || fail "python not found"
have ffmpeg || fail "ffmpeg not found"
python -c "import yaml" 2>/dev/null || fail "pyyaml not found (pip install pyyaml)"

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
PROJ="$TMP/demo-video"; mkdir -p "$PROJ"/{scripts,templates,mascots,mockups}
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
    - endcards
voiceover:
  - { text: "Smoke test scene one.", pause_after: 0.4 }
  - { text: "Smoke test scene two.", pause_after: 0.4 }
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
# non-blank: a mid frame must have real colour variety (catches white-flash / blank render)
ffmpeg -v error -ss 5 -i "$OUT" -frames:v 1 "$TMP/f.png"
python - "$TMP/f.png" <<'PY' || fail "mid frame looks blank (one solid colour)"
import subprocess, sys
raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", sys.argv[1],
                               "-vf", "scale=64:36", "-f", "rawvideo",
                               "-pix_fmt", "rgb24", "-"])
colors = {raw[i:i + 3] for i in range(0, len(raw), 3)}
sys.exit(0 if len(colors) > 20 else 1)
PY
echo "   full build OK ($OUT, ${DUR}s)"
echo "SMOKE PASS"
