"""plan-scenes.py — resolve the scene sequence into an ordered build plan.

Reads .build/config.json, emits .build/scene-plan.json: an ordered list of scene
descriptors that build-scenes.sh builds and assemble.sh crossfades.

Each plan entry: { "id", "type", "mp4", ...type-specific build args }
- mp4 is the path (relative to .build/) the scene will be rendered to.

Arcs:
  memory-product-default  → fixed 7-scene terminal narrative
  custom                  → translate config.scenes.custom_scenes 1:1
"""
import json
import os
import sys

CONFIG = os.environ.get("DEMO_CONFIG", "config.json")
OUT = "scene-plan.json"


def should_warmup(url, explicit=None):
    """Warm a route before recording? (P2-2) Dev servers (Next etc.) compile routes on
    first hit, so the first capture can catch a 'Rendering...' overlay. Explicit per-scene
    `warmup:` wins; else default ON for localhost/127.0.0.1, OFF for public sites."""
    if explicit is not None:
        return bool(explicit)
    u = (url or "").lower()
    return "localhost" in u or "127.0.0.1" in u


# Built-in scene names → how to build them. Use any subset, any order, via
# scenes.sequence. This is what gives full control over scene COUNT.
BUILTINS = {
    "hero":        {"type": "terminal", "tape": "01_hero_blank.tape",     "mp4": "01_hero_blank.mp4"},
    "typing":      {"type": "terminal", "tape": "02_typing_context.tape", "mp4": "02_typing_context.mp4"},
    "amnesia":     {"type": "terminal", "tape": "03_amnesia.tape",        "mp4": "03_amnesia.mp4"},
    "graph":       {"type": "graph",                                       "mp4": "videos/graph.mp4"},
    "recall":      {"type": "terminal", "tape": "04_memory_recall.tape",  "mp4": "04_memory_recall.mp4"},
    "multi-agent": {"type": "multi_agent",                                 "mp4": "videos/multi_agent_preview.mp4"},
    "multi_agent": {"type": "multi_agent",                                 "mp4": "videos/multi_agent_preview.mp4"},
    "endcards":    {"type": "endcards",                                    "mp4": "videos/endcards.mp4"},
}

# Named arc presets expand to a sequence of built-in names.
ARCS = {
    "memory-product-default": ["hero", "typing", "amnesia", "graph", "recall", "multi-agent", "endcards"],
    "short":                  ["hero", "graph", "endcards"],
    "problem-solution":       ["hero", "amnesia", "graph", "recall", "endcards"],
}


def resolve_sequence(seq, ctx=None):
    """Resolve an ordered list of (built-in name | custom scene dict) into plan entries.
    This is the single mechanism for ANY scene count + order."""
    ctx = ctx or {}
    plan = []
    for i, item in enumerate(seq):
        sid = f"s{i+1}"
        if isinstance(item, str):
            if item not in BUILTINS:
                sys.exit(f"Unknown built-in scene '{item}'. Valid: {sorted(set(BUILTINS) - {'multi_agent'})}")
            entry = dict(BUILTINS[item]); entry["id"] = sid; entry["name"] = item
            plan.append(entry)
        elif isinstance(item, dict):
            plan.extend(custom_arc([item], start_index=i, ctx=ctx))
        else:
            sys.exit(f"Bad sequence item: {item!r}")
    return plan


def custom_arc(custom_scenes, start_index=0, ctx=None):
    """Translate user-defined custom_scenes into plan entries."""
    ctx = ctx or {}
    plan = []
    for i, sc in enumerate(custom_scenes):
        t = sc.get("type")
        sid = f"c{start_index + i + 1}"
        entry = {"id": sid, "type": t, "mp4": f"videos/{sid}.mp4"}
        if t == "browser_capture":
            entry["scene_spec"] = {
                "url": sc["url"],
                "output": entry["mp4"],
                "cursor": sc.get("cursor", True),
                "settle_ms": sc.get("settle_ms", 1200),
                "tail_ms": sc.get("tail_ms", 1500),
                "viewport": sc.get("viewport", {"width": 1920, "height": 1080}),
                "actions": sc.get("actions", []),
                # P2-2: warm dev-server routes before recording (avoids "Rendering..." frame)
                "warmup": should_warmup(sc["url"], sc.get("warmup")),
            }
        elif t == "html_mockup":
            # Render a local HTML via the same browser engine, served by the http server
            src = sc["source"]
            entry["scene_spec"] = {
                "url": f"http://localhost:8765/{os.path.basename(src)}",
                "output": entry["mp4"],
                "cursor": sc.get("cursor", False),
                "settle_ms": sc.get("settle_ms", 800),
                "tail_ms": sc.get("tail_ms", 1000),
                "actions": sc.get("actions", []),
                # P2-3: paint the palette bg before first paint so a mockup that forgets
                # an inline <html> background never records as a white flash.
                "bg": sc.get("bg", ctx.get("bg")),
            }
            entry["html_source"] = src
        elif t == "screen_recording":
            entry["source"] = sc["source"]  # existing mp4, no build needed
            entry["mp4"] = sc["source"]
        elif t == "terminal":
            entry["scene"] = sc.get("scene", "hero")
            entry["mp4"] = f"{sid}_terminal.mp4"
        elif t in ("graph", "endcards", "multi_agent"):
            entry["mp4"] = f"videos/{t}.mp4"
        else:
            sys.exit(f"Unknown custom scene type: {t}")
        # P0-3: optional explicit duration — build-scenes.sh normalizes the clip to
        # this exact length (trim/freeze-pad) so VO<->video alignment is deterministic.
        # Not applied to screen_recording (would mutate the user's source file).
        if sc.get("duration") is not None and t != "screen_recording":
            entry["duration"] = float(sc["duration"])
        plan.append(entry)
    return plan


def main():
    if not os.path.exists(CONFIG):
        sys.exit(f"Missing {CONFIG} — run apply-brand.py first")
    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)

    scenes = cfg.get("scenes", {})
    arc = scenes.get("arc", "memory-product-default")

    # Context threaded into scene specs (e.g. palette bg for html_mockup flash guard).
    ctx = {"bg": cfg.get("subs", {}).get("palette_bg", "#0a0705")}

    # Resolution priority (most explicit wins):
    #   1. scenes.sequence  — exact ordered list, full scene-COUNT control
    #   2. arc: custom       — scenes.custom_scenes
    #   3. arc: <preset>     — expands to a built-in sequence
    if scenes.get("sequence"):
        plan = resolve_sequence(scenes["sequence"], ctx)
        label = f"sequence[{len(plan)}]"
    elif arc == "custom":
        custom = scenes.get("custom_scenes", [])
        if not custom:
            sys.exit("arc: custom but scenes.custom_scenes is empty (or use scenes.sequence)")
        plan = custom_arc(custom, ctx=ctx)
        label = "custom"
    elif arc in ARCS:
        plan = resolve_sequence(ARCS[arc], ctx)
        label = arc
    else:
        sys.exit(f"Unknown arc '{arc}'. Use a preset {list(ARCS)}, 'custom', or scenes.sequence")

    if len(plan) < 2:
        sys.exit(f"Need >=2 scenes for crossfades, got {len(plan)}")

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"arc": label, "scenes": plan}, f, indent=2)

    print(f"Scene plan ({label}): {len(plan)} scenes -> {OUT}")
    for s in plan:
        print(f"  {s['id']}: {s['type']} -> {s['mp4']}")


if __name__ == "__main__":
    main()
