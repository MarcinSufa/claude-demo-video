# assets/scripts/make-diorama.py
"""make-diorama.py — build a diorama scene: composite N windows on a big canvas,
overlay the mascot at canvas coords, then move an eased camera over it.

  python make-diorama.py <plan.json> <out.mp4>

plan.json (written by build-scenes.sh): {canvas, backdrop, windows:[{id,x,y,w,clip}],
camera:[...], mascot:{frames_dir, timeline}|null, duration, fps}.

build_canvas_filter()/build_camera_filter() are the pure, unit-tested ffmpeg
builders; diorama_layout.py holds the geometry. The graph is verified end-to-end
by tests/smoke_build.sh's diorama tier.
"""
import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from diorama_layout import (  # noqa: E402
    assert_canvas_16_9, camera_duration, camera_timeline, viewport_at, window_anchor)

BAR_H = 40   # title-bar height in canvas px (constant — real title bars are ~fixed)


def _ffcolor(c):
    """'#1e1714' / '1e1714' / '0x1e1714' -> '0x1e1714' for ffmpeg drawbox/drawtext."""
    c = str(c)
    if c.startswith("0x"):
        return c
    return "0x" + c.lstrip("#")


def chrome_metrics(bar_h):
    """Derived chrome sizes from the bar height (so they scale together and are
    unit-testable): dot diameter/gap, left pad, dots-strip size, title x + font."""
    d = max(8, round(bar_h * 0.30))
    gap = max(4, round(d * 0.6))
    pad = round(bar_h * 0.5)
    strip_w = 3 * d + 2 * gap
    return {"d": d, "gap": gap, "pad": pad, "strip_w": strip_w, "strip_h": d,
            "title_x": pad + strip_w + round(bar_h * 0.5),
            "title_fs": max(10, round(bar_h * 0.42))}


DOT_COLORS = [(0xff, 0x5f, 0x57), (0xfe, 0xbc, 0x2e), (0x7f, 0xbf, 0x7f)]  # red/amber/green


def dots_rgba(metrics):
    """Raw RGBA bytes for the three traffic-light dots on a transparent strip
    (strip_w x strip_h). Filled circles with a 1px anti-aliased edge. No Pillow —
    the bytes are piped to ffmpeg as rawvideo, like render-mascot.py."""
    w, h = metrics["strip_w"], metrics["strip_h"]
    d, gap = metrics["d"], metrics["gap"]
    r = d / 2.0
    buf = bytearray(w * h * 4)                      # zero-filled = transparent
    for i, (cr, cg, cb) in enumerate(DOT_COLORS):
        cx = i * (d + gap) + r
        cy = r
        for y in range(h):
            for x in range(w):
                dist = ((x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2) ** 0.5
                cov = max(0.0, min(1.0, r - dist + 0.5))   # coverage at the edge
                a = int(round(cov * 255))
                if a == 0:
                    continue
                o = (y * w + x) * 4
                if a <= buf[o + 3]:
                    continue
                buf[o], buf[o + 1], buf[o + 2], buf[o + 3] = cr, cg, cb, a
    return bytes(buf)


def window_h(w_px, clip_cw, clip_ch, chrome):
    """A window's full canvas height: the clip scaled to width w_px, plus the title
    bar (BAR_H) when the window has chrome. focus_rect/camera/anchors use this."""
    return round(w_px * clip_ch / clip_cw) + (BAR_H if chrome else 0)


def build_canvas_filter(windows, canvas):
    """Backdrop ([0:v]) scaled to canvas, then each window clip ([i:v], i>=1)
    scaled to its width and overlaid at (x, y) — chrome windows' clips are pushed
    down by BAR_H to leave room for the title bar drawn later. Ends at [canvas]."""
    parts = [f"[0:v]scale={canvas['width']}:{canvas['height']},setsar=1[bg]"]
    src = "[bg]"
    for i, w in enumerate(windows, 1):
        parts.append(f"[{i}:v]scale={w['w']}:-2,setsar=1[w{i}]")
        label = "[canvas]" if i == len(windows) else f"[c{i}]"
        wy = w["y"] + (BAR_H if w.get("chrome") else 0)
        parts.append(f"{src}[w{i}]overlay={w['x']}:{wy}{label}")
        src = f"[c{i}]"
    return ";".join(parts)


# make-before-after helpers (find_font / _esc_path / ascii_label), loaded at MODULE
# level so module-level chrome_filter can escape paths without re-importing (main()
# reuses find_font / ascii_label too).
_mba_spec = importlib.util.spec_from_file_location(
    "make_before_after", os.path.join(os.path.dirname(os.path.abspath(__file__)), "make-before-after.py"))
_mba = importlib.util.module_from_spec(_mba_spec); _mba_spec.loader.exec_module(_mba)


def chrome_filter(windows, in_label, out_label, dots_index, style, font):
    """Draw the title bar (drawbox), traffic-light dots (overlay of input
    [dots_index]) and title (drawtext, textfile) on `in_label` for each chrome
    window, producing `out_label`. A no-op `null` when no window has chrome."""
    chrome = [w for w in windows if w.get("chrome")]
    if not chrome:
        return f"[{in_label}]null[{out_label}]"
    m = chrome_metrics(BAR_H)
    fontclause = f"fontfile='{_mba._esc_path(font)}':" if font else ""
    parts = [f"[{dots_index}:v]split={len(chrome)}" + "".join(f"[dots{i}]" for i in range(len(chrome)))]
    src = in_label
    for i, w in enumerate(chrome):
        x, y, ww = w["x"], w["y"], w["w"]
        nxt = out_label if i == len(chrome) - 1 else f"chr{i}"
        bar = (f"drawbox=x={x}:y={y}:w={ww}:h={BAR_H}:color={style['bar_bg']}:t=fill,"
               f"drawbox=x={x}:y={y + BAR_H - 2}:w={ww}:h=2:color={style['rule']}:t=fill")
        dots_x, dots_y = x + m["pad"], y + (BAR_H - m["strip_h"]) // 2
        title = (f"drawtext={fontclause}textfile='{_mba._esc_path(w['title_file'])}':"
                 f"x={x + m['title_x']}:y={y}+({BAR_H}-text_h)/2:"
                 f"fontsize={m['title_fs']}:fontcolor={style['fg']}")
        parts.append(f"[{src}]{bar}[chrb{i}]")
        parts.append(f"[chrb{i}][dots{i}]overlay={dots_x}:{dots_y}[chrd{i}]")
        parts.append(f"[chrd{i}]{title}[{nxt}]")
        src = nxt
    return ";".join(parts)


def _coord_expr(segs, idx, tvar="t"):
    """Piecewise ffmpeg expression for viewport coordinate `idx`
    (0=x,1=y,2=w,3=h) over the camera segments: smoothstep within each segment,
    constant for holds (a==b makes the eased term collapse to the value). `tvar`
    is the time expression (default "t"; zoompan has no `t`, so it passes on/fps)."""
    expr = f"{segs[-1][3][idx]}"  # default = last segment's end value
    for (s, e, a, b) in reversed(segs):
        dur = e - s
        if dur <= 0:
            continue
        p = f"clip(({tvar}-{s:.3f})/{dur:.3f},0,1)"
        pe = f"({p}*{p}*(3-2*{p}))"
        val = f"({a[idx]}+({b[idx]}-{a[idx]})*{pe})"
        expr = f"if(between({tvar},{s:.3f},{e:.3f}),{val},{expr})"
    return expr


def build_camera_filter(segs, canvas_w, canvas_h, out_w, out_h, fps):
    """Eased camera over the canvas via zoompan — smooth pan+zoom into a fixed
    out_w x out_h frame. Consumes [0:v] (the canvas/mascot mp4 read as input 0),
    produces [vout].

    Not crop+scale: crop's `eval` option is absent on some ffmpeg builds, and a
    filter's output size is fixed at init so an animated crop window can't zoom.
    zoompan always scales its crop to a fixed `s`, so it animates cleanly. It has
    no `t`, only the output-frame counter `on`, so the input is first pinned to
    `fps` CFR and time is on/fps. Zoom = canvas_w/viewport_w (clamped >= 1, i.e.
    never wider than the canvas); x/y are the viewport top-left, clamped in-bounds.
    Requires a canvas whose aspect matches the output (zoompan's crop is
    canvas-aspect), which focus_rect guarantees."""
    tv = f"(on/{float(fps):.3f})"
    xe = _coord_expr(segs, 0, tv)
    ye = _coord_expr(segs, 1, tv)
    we = _coord_expr(segs, 2, tv)
    z = f"max(1,{canvas_w}/({we}))"
    x = f"max(0,min({xe},iw-iw/zoom))"
    y = f"max(0,min({ye},ih-ih/zoom))"
    return (f"[0:v]fps={fps},zoompan=z='{z}':x='{x}':y='{y}':"
            f"d=1:s={out_w}x{out_h}:fps={fps},setsar=1[vout]")


MOVE_SECONDS = 0.8


def diorama_timeline(keyframes, duration):
    """Sorted window-keyframes -> contiguous segments to `duration`, with a `walk`
    move inserted when consecutive keyframes target different windows."""
    kf = [k for k in sorted(keyframes, key=lambda k: k["at"]) if k["at"] < duration]
    segs = []
    for i, k in enumerate(kf):
        start = k["at"]
        end = kf[i + 1]["at"] if i + 1 < len(kf) else duration
        if i > 0 and kf[i]["at_window"] != kf[i - 1]["at_window"]:
            mv = min(MOVE_SECONDS, (end - start) / 2)
            segs.append({"at": start, "until": start + mv, "emotion": "walk",
                         "move": {"from_window": kf[i - 1]["at_window"],
                                  "from_anchor": kf[i - 1]["anchor"],
                                  "to_window": k["at_window"], "to_anchor": k["anchor"]}})
            start += mv
        segs.append({"at": start, "until": end, "emotion": k["emotion"],
                     "at_window": k["at_window"], "anchor": k["anchor"]})
    return segs


def _clamp_xy(xy, sprite_wh, canvas):
    """Keep a sprite anchor inside the canvas: x in [0, W-sw], y in [0, H-sh]."""
    x, y = xy
    sw, sh = sprite_wh
    return (min(max(0, x), canvas["width"] - sw),
            min(max(0, y), canvas["height"] - sh))


def resolve_canvas_positions(timeline, windows, sprite_wh, canvas):
    """Per-segment canvas anchors for the mascot, clamped into the canvas. Static
    segs carry at_window+anchor; move segs carry move.{from,to}_{window,anchor}."""
    by_id = {w["id"]: w for w in windows}
    sw, sh = sprite_wh
    out = []
    for seg in timeline:
        if "move" in seg:
            mv = seg["move"]
            out.append((_clamp_xy(window_anchor(by_id[mv["from_window"]], mv["from_anchor"], sw, sh), sprite_wh, canvas),
                        _clamp_xy(window_anchor(by_id[mv["to_window"]], mv["to_anchor"], sw, sh), sprite_wh, canvas)))
        else:
            out.append(_clamp_xy(window_anchor(by_id[seg["at_window"]], seg["anchor"], sw, sh), sprite_wh, canvas))
    return out


def _probe(path, entries):
    out = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", entries, "-of", "csv=p=0", path]).decode().strip()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plan_json"); ap.add_argument("out")
    a = ap.parse_args()
    with open(a.plan_json, encoding="utf-8") as f:
        plan = json.load(f)
    canvas, windows = plan["canvas"], plan["windows"]
    assert_canvas_16_9(canvas)          # fail loud, not silent zoompan distortion
    # Duration is the camera tour's length unless the scene pins one explicitly.
    dur = plan["duration"] if plan.get("duration") is not None else camera_duration(plan["camera"])
    dur, fps = float(dur), int(plan.get("fps", 30))
    workdir = os.path.dirname(os.path.abspath(a.out)) or "."

    # 1. canvas composite (each window clip normalized to DUR first)
    import importlib.util
    nc = importlib.util.spec_from_file_location(
        "normalize_clip", os.path.join(os.path.dirname(__file__), "normalize-clip.py"))
    normmod = importlib.util.module_from_spec(nc); nc.loader.exec_module(normmod)
    backdrop = plan["backdrop"]
    if backdrop.startswith("color="):
        # lavfi solid-colour backdrop: synthesize a canvas-sized source for DUR
        inputs = ["-f", "lavfi", "-i",
                  f"{backdrop}:s={canvas['width']}x{canvas['height']}:d={dur:.3f}"]
    else:
        inputs = ["-i", backdrop]
    # Per window: probe the ORIGINAL for aspect (fills the canvas height h the
    # layout/camera need — plan-scenes only set x/y/w), then normalize a COPY in
    # the workdir to DUR. normalize-clip.py replaces in place, so normalizing
    # w["clip"] directly would trim/pad the user's SOURCE footage — copy first.
    for i, w in enumerate(windows):
        cw, ch = (int(v) for v in _probe(w["clip"], "stream=width,height").split(","))
        w["h"] = window_h(w["w"], cw, ch, w.get("chrome"))   # incl. BAR_H for chrome windows
        win_clip = os.path.join(workdir, f".diorama-win-{i}.mp4")
        shutil.copyfile(w["clip"], win_clip)
        normmod.main(["normalize-clip.py", win_clip, str(dur)])  # pin the COPY to DUR
        inputs += ["-i", win_clip]
    chrome_wins = [w for w in windows if w.get("chrome")]
    style, font, dots_index = None, None, None
    if chrome_wins:
        cs = plan["chrome_style"]
        style = {"bar_bg": _ffcolor(cs["bar_bg"]), "rule": _ffcolor(cs["rule"]),
                 "fg": _ffcolor(cs["fg"])}
        font = _mba.find_font()
        for w in chrome_wins:                       # one UTF-8 textfile per chrome title
            tf = os.path.join(workdir, f".diorama-title-{w['id']}.txt")
            with open(tf, "w", encoding="utf-8", newline="") as f:
                f.write(_mba.ascii_label(str(w.get("title", w["id"]))))
            w["title_file"] = tf
        dots_png = os.path.join(workdir, ".diorama-dots.png")
        m = chrome_metrics(BAR_H)
        buf = dots_rgba(m)
        proc = subprocess.Popen(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{m['strip_w']}x{m['strip_h']}",
             "-i", "-", "-frames:v", "1", dots_png], stdin=subprocess.PIPE)
        proc.communicate(buf)
        if proc.returncode != 0:
            sys.exit("make-diorama: dots PNG generation failed")
        dots_index = len(windows) + 1               # [0]=backdrop, [1..N]=clips, [N+1]=dots
        inputs += ["-i", dots_png]
    canvas_mp4 = os.path.join(workdir, ".diorama-canvas.mp4")
    fc = build_canvas_filter(windows, canvas)
    if chrome_wins:
        fc += ";" + chrome_filter(windows, "canvas", "canvasc", dots_index, style, font)
        last = "canvasc"
    else:
        last = "canvas"
    fc += f";[{last}]trim=duration={dur:.3f},setpts=PTS-STARTPTS[v]"
    subprocess.check_call(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *inputs,
        "-filter_complex", fc, "-map", "[v]", "-t", f"{dur:.3f}", "-r", str(fps),
        "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", canvas_mp4])

    # 2. mascot on the canvas (optional)
    src = canvas_mp4
    if plan.get("mascot"):
        from importlib import util as _u
        om = _u.spec_from_file_location("overlay_mascot",
            os.path.join(os.path.dirname(__file__), "overlay-mascot.py"))
        ovl = _u.module_from_spec(om); om.loader.exec_module(ovl)
        m = plan["mascot"]
        sprite_wh = tuple(int(v) for v in _probe(
            os.path.join(m["frames_dir"], "idle", "f_001.png"), "stream=width,height").split(","))
        timeline = diorama_timeline(m["keyframes"], dur)            # keyframes -> segments+walks
        positions = resolve_canvas_positions(timeline, windows, sprite_wh, canvas)
        cmd = ovl.build_overlay_cmd(canvas_mp4, os.path.join(workdir, ".diorama-m.mp4"),
            m["frames_dir"], timeline, positions, m["fps"], 1.0)
        if cmd:
            subprocess.check_call(cmd); src = os.path.join(workdir, ".diorama-m.mp4")

    # 3. camera
    segs, cam_total = camera_timeline(plan["camera"], {w["id"]: w for w in windows}, canvas)
    cf = build_camera_filter(segs, canvas["width"], canvas["height"], 1920, 1080, fps)
    subprocess.check_call(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", src,
        "-filter_complex", cf, "-map", "[vout]", "-r", str(fps),
        "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", a.out])
    print(f"  diorama -> {a.out}")


if __name__ == "__main__":
    main()
