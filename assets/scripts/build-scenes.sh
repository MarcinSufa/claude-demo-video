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

# P0-2 cache controls (passed through by build.sh)
NO_CACHE="${DEMO_NO_CACHE:-0}"
ONLY="${DEMO_ONLY:-}"

while IFS=$'\t' read -r id type mp4 extra; do
  echo "[scene] $id ($type) -> $mp4"

  # P0-2: reuse a scene's clip when nothing affecting it changed (skip capture).
  # --no-cache forces all; --only <id> forces just that scene. screen_recording is
  # never cached (it just references the user's external file).
  force=0
  [ "$NO_CACHE" = "1" ] && force=1
  [ -n "$ONLY" ] && [ "$ONLY" = "$id" ] && force=1
  if [ "$type" != "screen_recording" ] && [ "$force" = "0" ] \
     && python scene_cache.py check "$PLAN" "$id" 2>/dev/null; then
    echo "  -> cached (unchanged), skipping capture"
    continue
  fi

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

  # P0-3: pin the clip to an explicit duration when the scene declares one.
  dur=$(echo "$extra" | python -c "import json,sys;d=json.load(sys.stdin).get('duration');print(d if d is not None else '')")
  if [ -n "$dur" ]; then
    python normalize-clip.py "$mp4" "$dur"
  fi

  # P0-2: record the cache fingerprint of the finished (normalized) clip.
  [ "$type" != "screen_recording" ] && python scene_cache.py save "$PLAN" "$id"
done < .scene-rows.tsv

rm -f .scene-rows.tsv
echo "[scenes] all built"
