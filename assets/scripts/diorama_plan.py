# assets/scripts/diorama_plan.py
"""diorama_plan.py — build the make-diorama plan dict from a resolved diorama
scene. Pure (no I/O): build-scenes.sh records the url windows + reads the palette,
then calls build_plan(). Kept separate from recording so it is unit-testable.
"""


def build_plan(scene, clips, chrome_style, mascot=None, fps=30):
    """scene (the diorama entry minus id/type/mp4) + clips {win_id: clip_path} +
    chrome_style {bar_bg, rule, fg} -> the make-diorama plan dict.

    Carries chrome/title per window; attaches chrome_style only when some window
    has chrome. `mascot` is the already-resolved RUNTIME dict (keyframes +
    frames_dir + fps) the caller builds — it is filesystem-derived (needs
    ./mascot + mascot-meta.json), so it is passed in, not read from `scene` here.
    backdrop falls back to a dark solid; duration passes through.
    """
    windows = []
    has_chrome = False
    for w in scene["windows"]:
        win = {"id": w["id"], "x": w["x"], "y": w["y"], "w": w["w"], "clip": clips[w["id"]]}
        if w.get("chrome"):
            win["chrome"] = True
            win["title"] = w.get("title", w["id"])
            has_chrome = True
        windows.append(win)
    plan = {
        "canvas": scene["canvas"],
        "camera": scene["camera"],
        "windows": windows,
        "fps": fps,
        "backdrop": (scene.get("canvas") or {}).get("backdrop") or "color=c=0x0a0705",
        "mascot": mascot,
    }
    if scene.get("duration") is not None:
        plan["duration"] = scene["duration"]
    if has_chrome:
        plan["chrome_style"] = chrome_style
    return plan
