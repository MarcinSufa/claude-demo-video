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


def resolve_source(path):
    """Resolve a user-supplied scene clip path so it's reachable from the .build
    cwd the pipeline runs in. A relative path is taken relative to the project root
    (DEMO_ROOT, set by build.sh) — the same base the user wrote it against and the
    same base build.sh resolves the backdrop against. Absolute paths pass through.
    When DEMO_ROOT is unset (standalone/tests) the path is returned unchanged."""
    root = os.environ.get("DEMO_ROOT")
    if root and not os.path.isabs(path):
        return os.path.join(root, path).replace("\\", "/")
    return path


# Default whole-scene emotion per scene type (stage-1; exact timing is resolved
# at build time by resolve-mascot-timeline.py against the real clip).
MASCOT_TYPE_DEFAULTS = {
    "terminal": "type",
    "multi_agent": "type",
    "graph": "idle",
    "browser_capture": "idle",
    "html_mockup": "idle",
    "screen_recording": "idle",
}


def mascot_stub(mascot_cfg, entry, scene_override):
    """Stage-1 mascot resolution: defaults + overrides, no timing.
    mascot_cfg is config.json's `mascot` block; scene_override is the scene's
    `mascot:` dict (or None). Returns the mascot_plan stub for this entry."""
    ov = scene_override or {}
    enabled = bool(mascot_cfg.get("enabled", bool(mascot_cfg)))
    if entry.get("type") == "endcards" and "enabled" not in ov:
        enabled = False  # off by default on endcards (spec)
    if "enabled" in ov:
        enabled = bool(ov["enabled"])
    stub = {
        "enabled": enabled,
        "character": mascot_cfg.get("character", "octopus"),
        "position": ov.get("position", mascot_cfg.get("position", "bottom-right")),
        "scale": mascot_cfg.get("scale", 1.0),
    }
    if not enabled:
        return stub
    t = entry.get("type")
    if t == "before_after" and entry.get("layout", "sequential") == "sequential":
        stub["before"] = ov.get("before", "panic")
        stub["after"] = ov.get("after", "celebrate")
    elif t == "before_after":  # side_by_side: one emotion, no half split (spec)
        stub["emotion"] = ov.get("emotion", "point")
    else:
        stub["emotion"] = ov.get("emotion", MASCOT_TYPE_DEFAULTS.get(t, "idle"))
    return stub


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
    This is the single mechanism for ANY scene count + order.

    Note: built-in string scene names (e.g. "hero", "graph") don't support per-scene
    ``mascot:`` overrides — use the dict form ``{"type": ..., "mascot": {...}}`` for that.
    The global ``mascot:`` block in brand.yaml still applies to all scenes."""
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
                # P2-1: reuse the saved login session (storageState from the auth block)
                "auth": bool(sc.get("auth", False)),
                # Trim the head of the clip (ms) — skip a slow app boot/auth splash.
                # Unset → record-browser auto-trims to ~1s before the app was ready.
                "trim_start_ms": sc.get("trim_start_ms"),
                # Frame the change: crop+zoom the output to a selector / explicit rect.
                "clip": sc.get("clip"),
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
            entry["source"] = resolve_source(sc["source"])  # existing mp4, no build needed
            entry["mp4"] = entry["source"]
        elif t == "terminal":
            entry["scene"] = sc.get("scene", "hero")
            entry["mp4"] = f"{sid}_terminal.mp4"
        elif t in ("graph", "endcards", "multi_agent"):
            entry["mp4"] = f"videos/{t}.mp4"
        elif t == "before_after":
            # A labeled BEFORE/AFTER comparison scene. Each half is a path string,
            # a {"source": mp4}, or a browser_capture spec {"url", "actions", ...}.
            # build-scenes.sh records any capture halves, then make-before-after.py
            # labels + composes them (sequential concat or side_by_side hstack).
            entry["mp4"] = f"videos/{sid}.mp4"
            entry["layout"] = sc.get("layout", "sequential")
            if sc.get("half_duration") is not None:
                entry["half_duration"] = float(sc["half_duration"])
            for role, default_label in (("before", "BEFORE"), ("after", "AFTER")):
                if role not in sc:
                    sys.exit(f"before_after scene needs a '{role}' half")
                h = sc[role]
                if isinstance(h, str):
                    h = {"source": h}
                half = {"label": h.get("label", sc.get(f"{role}_label", default_label))}
                if h.get("source"):
                    half["source"] = resolve_source(h["source"])
                elif h.get("url"):
                    half["capture"] = {
                        "url": h["url"], "output": f"videos/{sid}_{role}.mp4",
                        "cursor": h.get("cursor", True),
                        "settle_ms": h.get("settle_ms", 1200),
                        "tail_ms": h.get("tail_ms", 1500),
                        "viewport": h.get("viewport", {"width": 1920, "height": 1080}),
                        "actions": h.get("actions", []),
                        "warmup": should_warmup(h["url"], h.get("warmup")),
                        "auth": bool(h.get("auth", False)),
                        "trim_start_ms": h.get("trim_start_ms"),
                        "clip": h.get("clip"),
                    }
                else:
                    sys.exit(f"before_after '{role}' needs a path string, 'source', or 'url'")
                entry[role] = half
        else:
            sys.exit(f"Unknown custom scene type: {t}")
        # P0-3: optional explicit duration — build-scenes.sh normalizes the clip to
        # this exact length (trim/freeze-pad) so VO<->video alignment is deterministic.
        # Not applied to screen_recording (would mutate the user's source file).
        if sc.get("duration") is not None and t != "screen_recording":
            entry["duration"] = float(sc["duration"])
        if sc.get("mascot") is not None:
            entry["_mascot_override"] = sc["mascot"]
        plan.append(entry)
    return plan


def retarget_screen_recording(entry):
    """screen_recording: never let the pipeline write onto the user's source
    footage. When the mascot will overlay this scene, retarget the entry's
    mp4 to a build-local copy (build-scenes.sh makes the copy)."""
    if entry.get("type") == "screen_recording" and entry["mascot_plan"].get("enabled"):
        entry["mp4"] = f"videos/{entry['id']}_screen.mp4"


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

    mascot_cfg = cfg.get("mascot", {})
    for entry in plan:
        ov = entry.pop("_mascot_override", None)
        entry["mascot_plan"] = mascot_stub(mascot_cfg, entry, ov)
        retarget_screen_recording(entry)

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"arc": label, "scenes": plan}, f, indent=2)

    print(f"Scene plan ({label}): {len(plan)} scenes -> {OUT}")
    for s in plan:
        print(f"  {s['id']}: {s['type']} -> {s['mp4']}")


if __name__ == "__main__":
    main()
