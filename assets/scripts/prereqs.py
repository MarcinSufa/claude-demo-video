"""prereqs.py — arc-aware prerequisite logic (P1-2).

A full build always needs ffmpeg/python/node/edge-tts and Playwright (the end-card,
graph, and terminal-on-desk composite scenes all use headless Chromium). VHS/Docker,
however, is ONLY needed to record terminal or multi-agent scenes — so a pure
browser_capture + endcards arc must not be blocked on a missing VHS. Likewise the
(non-MIT, opt-in) Remotion package is only needed for `type: remotion` scenes.

  python prereqs.py needs-vhs <scene-plan.json>       # exit 0 if VHS/Docker required
  python prereqs.py needs-remotion <scene-plan.json>  # exit 0 if remotion/ is required
"""
import json
import sys

VHS_TYPES = ("terminal", "multi_agent")
REMOTION_TYPES = ("remotion",)


def needs_vhs(scene_types):
    """True if any scene in the plan must be rendered with VHS (terminal/multi_agent)."""
    return any(t in VHS_TYPES for t in scene_types)


def needs_remotion(scene_types):
    """True if any scene in the plan must be rendered by the Remotion package."""
    return any(t in REMOTION_TYPES for t in scene_types)


def _types_from_plan(path):
    with open(path, encoding="utf-8") as f:
        return [s.get("type") for s in json.load(f).get("scenes", [])]


def main(argv):
    if len(argv) >= 3 and argv[1] == "needs-vhs":
        return 0 if needs_vhs(_types_from_plan(argv[2])) else 1
    if len(argv) >= 3 and argv[1] == "needs-remotion":
        return 0 if needs_remotion(_types_from_plan(argv[2])) else 1
    sys.exit("usage: python prereqs.py needs-vhs|needs-remotion <scene-plan.json>")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
