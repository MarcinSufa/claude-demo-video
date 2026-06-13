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

# Read the plan on FD 3, NOT stdin: tools inside the loop (ffmpeg especially)
# read stdin and would otherwise swallow the remaining scene rows, silently
# building only the first scene. (Caught by the CI full-render smoke.)
while IFS=$'\t' read -r id type mp4 extra <&3; do
  echo "[scene] $id ($type) -> $mp4"

  # P0-2: reuse a scene's clip when nothing affecting it changed (skip capture).
  # --no-cache forces all; --only <id> forces just that scene. screen_recording is
  # never cached (it just references the user's external file).
  force=0
  [ "$NO_CACHE" = "1" ] && force=1
  [ -n "$ONLY" ] && [ "$ONLY" = "$id" ] && force=1

  # ── Capture phase ──
  # Cached when a pristine pre-mascot copy exists AND the capture fingerprint
  # matches (mascot_plan changes don't invalidate the capture layer).
  if [ "$type" != "screen_recording" ] && [ "$force" = "0" ] \
     && [ -f "$mp4.capture.mp4" ] \
     && python scene_cache.py check "$PLAN" "$id" 2>/dev/null; then
    echo "  -> capture cached (unchanged)"
  else
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
      node record-browser.mjs ".scene-$id.json"
      python cut-clip.py "$mp4" ;;        # focus: speed-ramp + zoom (no-op if unused)
    html_mockup)
      # html_source already rendered into .build by apply-brand OR copied by build.sh
      echo "$extra" | python -c "import json,sys;json.dump(json.load(sys.stdin)['scene_spec'],open('.scene-$id.json','w'))"
      node record-browser.mjs ".scene-$id.json"
      python cut-clip.py "$mp4" ;;
    screen_recording)
      src=$(echo "$extra" | python -c "import json,sys;print(json.load(sys.stdin)['source'])")
      [ -f "$src" ] || { echo "  missing screen_recording source: $src"; exit 1; }
      if [ "$src" != "$mp4" ]; then
        # Mascot retargeted this scene to a build-local clip. Keep the pristine
        # source as the .capture.mp4 sidecar (NOT as $mp4) so the overlay layer
        # can cache — copying onto $mp4 would clobber the previous overlaid clip
        # and bust the overlay cache on every run.
        cmp -s "$src" "$mp4.capture.mp4" 2>/dev/null || cp "$src" "$mp4.capture.mp4"
        echo "  pristine copy for overlay: $mp4.capture.mp4"
      else echo "  using existing: $src"; fi ;;
    before_after)
      # Record any capture halves (record-browser writes to each half's capture.output),
      # then make-before-after.py labels + composes the two clips into one scene mp4.
      echo "$extra" > ".scene-$id.json"
      for role in before after; do
        cap=$(python -c "import json;h=json.load(open('.scene-$id.json')).get('$role',{});print(json.dumps(h['capture']) if isinstance(h,dict) and 'capture' in h else '')")
        if [ -n "$cap" ]; then
          echo "  recording $role half..."
          echo "$cap" > ".scene-$id-$role.json"
          node record-browser.mjs ".scene-$id-$role.json"
          # focus the half before it is labeled + composed (no-op without speed/zoom)
          half_mp4=$(python -c "import json;print(json.load(open('.scene-$id-$role.json'))['output'])")
          python cut-clip.py "$half_mp4"
        fi
      done
      python make-before-after.py ".scene-$id.json" "$mp4"
      rm -f ".scene-$id.json" ".scene-$id-before.json" ".scene-$id-after.json" ;;
    diorama)
      # N windows composited on a big canvas + an eased camera tour + the mascot
      # moving window-to-window (composited in canvas space by make-diorama, NOT
      # the corner overlay phase). Record any url windows like before_after halves.
      echo "$extra" > ".scene-$id.json"
      python - "$id" <<'PY'
import importlib.util, json, os, subprocess, sys
sid = sys.argv[1]
dps = importlib.util.spec_from_file_location("diorama_plan", "diorama_plan.py")
dp = importlib.util.module_from_spec(dps); dps.loader.exec_module(dp)
e = json.load(open(f".scene-{sid}.json"))
clips = {}
for w in e["windows"]:
    if "capture" in w:                       # a live url window — record it now
        cap = w["capture"]
        json.dump(cap, open(f".scene-{sid}-{w['id']}.json", "w"))
        subprocess.check_call(["node", "record-browser.mjs", f".scene-{sid}-{w['id']}.json"])
        subprocess.check_call(["python", "cut-clip.py", cap["output"]])  # focus (no-op if unused)
        clips[w["id"]] = cap["output"]
    else:
        clips[w["id"]] = w["source"]
pal = json.load(open("config.json")).get("palette", {})   # raw brand palette (apply-brand emits it)
style = {"bar_bg": pal.get("end_card_bg", "#17171a"),
         "rule":   pal.get("rule", "#2c2c32"),
         "fg":     pal.get("fg", "#f4efe3")}               # raw #RRGGBB; make-diorama _ffcolor's it
# Mascot RUNTIME enrichment (filesystem-derived) stays here, not in pure build_plan:
mascot = None
if e.get("mascot") and os.path.isdir("mascot"):
    mfps = json.load(open("mascot/mascot-meta.json")).get("fps", 12)
    mascot = {"keyframes": e["mascot"]["keyframes"], "frames_dir": "mascot", "fps": mfps}
json.dump(dp.build_plan(e, clips, style, mascot=mascot), open(f".diorama-{sid}.json", "w"))
PY
      python make-diorama.py ".diorama-$id.json" "$mp4"
      rm -f ".scene-$id.json" ".scene-$id"-*.json ".diorama-$id.json" ;;
    *)
      echo "  unknown scene type: $type"; exit 1 ;;
  esac

  # P0-3: pin the clip to an explicit duration when the scene declares one.
  dur=$(echo "$extra" | python -c "import json,sys;d=json.load(sys.stdin).get('duration');print(d if d is not None else '')")
  if [ -n "$dur" ]; then
    python normalize-clip.py "$mp4" "$dur"
  fi

  # Keep a pristine pre-mascot copy + record the capture fingerprint of the
  # finished (normalized) clip. screen_recording is never cached/copied.
  if [ "$type" != "screen_recording" ]; then
    cp "$mp4" "$mp4.capture.mp4"
    python scene_cache.py save "$PLAN" "$id"
  fi
  fi  # end capture phase

  # ── Overlay phase (mascot) ──
  enabled=$(echo "$extra" | python -c "import json,sys;print(1 if json.load(sys.stdin).get('mascot_plan',{}).get('enabled') else 0)")
  if [ "$enabled" = "1" ] && [ -d mascot ]; then
    src="$mp4"; [ -f "$mp4.capture.mp4" ] && src="$mp4.capture.mp4"
    python resolve-mascot-timeline.py "$PLAN" "$id"
    if [ "$force" = "0" ] \
       && python scene_cache.py overlay-check "$mp4" "$src" mascot.json "$src.mascot.json" 2>/dev/null; then
      echo "  -> overlay cached"
    else
      python overlay-mascot.py "$src" "$mp4.tmp.mp4" mascot "$src.mascot.json" --speedup "${DEMO_SPEEDUP:-1.0}"
      if [ -f "$mp4.tmp.mp4" ]; then
        mv -f "$mp4.tmp.mp4" "$mp4"
      elif [ "$src" != "$mp4" ]; then
        cp "$src" "$mp4"   # empty timeline: ship the pristine clip, not last build's overlay
      fi
      python scene_cache.py overlay-save "$mp4" "$src" mascot.json "$src.mascot.json"
    fi
  elif [ -f "$mp4.capture.mp4" ]; then
    # Mascot disabled (possibly after a previous overlaid build) — ship pristine.
    cp "$mp4.capture.mp4" "$mp4"
  fi
done 3< .scene-rows.tsv

rm -f .scene-rows.tsv
echo "[scenes] all built"
