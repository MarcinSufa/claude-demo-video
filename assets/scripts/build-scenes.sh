#!/usr/bin/env bash
# build-scenes.sh — build every scene mp4 listed in scene-plan.json, by type.
# Run from the .build working dir (after apply-brand.py + plan-scenes.py).
set -e
cd "$(dirname "$0")"
mkdir -p videos

PLAN="scene-plan.json"
[ -f "$PLAN" ] || { echo "Missing $PLAN — run plan-scenes.py first"; exit 1; }

run_vhs() {
  if command -v vhs >/dev/null; then vhs "$1"
  else MSYS_NO_PATHCONV=1 docker run --rm -v "$(pwd):/vhs" -w /vhs ghcr.io/charmbracelet/vhs "$1"; fi
}

# Iterate plan entries as TSV: id<TAB>type<TAB>mp4<TAB>extra(json)
python - "$PLAN" > .scene-rows.tsv <<'PY'
import json, sys
plan = json.load(open(sys.argv[1]))["scenes"]
for s in plan:
    extra = json.dumps({k: v for k, v in s.items() if k not in ("id", "type", "mp4")})
    print("\t".join([s["id"], s["type"], s["mp4"], extra]))
PY

while IFS=$'\t' read -r id type mp4 extra; do
  echo "[scene] $id ($type) -> $mp4"
  case "$type" in
    terminal)
      tape=$(echo "$extra" | python -c "import json,sys;print(json.load(sys.stdin).get('tape',''))")
      if [ -n "$tape" ]; then run_vhs "$tape"; else echo "  (custom terminal scenes need a tape; skipping)"; fi
      ;;
    graph)
      node record-graph.mjs ;;
    endcards)
      node record-endcards.mjs ;;
    multi_agent)
      run_vhs 05a_agent_claude.tape
      run_vhs 05b_agent_cursor.tape
      run_vhs 05c_agent_cli.tape
      ffmpeg -y -hide_banner -loglevel error \
        -i 05a_agent_claude.mp4 -i 05b_agent_cursor.mp4 -i 05c_agent_cli.mp4 \
        -filter_complex "[0:v][1:v][2:v]hstack=inputs=3,pad=ceil(iw/2)*2:ceil(ih/2)*2" \
        -c:v libx264 -crf 20 -pix_fmt yuv420p "$mp4" ;;
    browser_capture)
      echo "$extra" | python -c "import json,sys;json.dump(json.load(sys.stdin)['scene_spec'],open('.scene-$id.json','w'))"
      node record-browser.mjs ".scene-$id.json" ;;
    html_mockup)
      # html_source already rendered into .build by apply-brand OR copied by build.sh
      echo "$extra" | python -c "import json,sys;json.dump(json.load(sys.stdin)['scene_spec'],open('.scene-$id.json','w'))"
      node record-browser.mjs ".scene-$id.json" ;;
    screen_recording)
      src=$(echo "$extra" | python -c "import json,sys;print(json.load(sys.stdin)['source'])")
      [ -f "$src" ] || { echo "  missing screen_recording source: $src"; exit 1; }
      echo "  using existing: $src" ;;
    *)
      echo "  unknown scene type: $type"; exit 1 ;;
  esac
done < .scene-rows.tsv

rm -f .scene-rows.tsv
echo "[scenes] all built"
