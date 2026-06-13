"""gen-pixellab.py — generate a mascot's animation frames with the PixelLab API.

An optional, PAID art source. Generates a character from a text prompt
(pixflux), then animates it per emotion (animate-with-text, 64x64), and writes
the results straight into the mascot frames_dir contract the overlay reads
(<out>/<anim>/f_%03d.png + mascot-meta.json) — same target as render-mascot.py
and import-spritesheet.py.

  PIXELLAB_API_KEY=... python gen-pixellab.py <out_dir> --prompt "a coral kangaroo, cream pouch" \
       [--actions idle,type,walk,panic,celebrate,sleep,point,enter,exit] [--n-frames 6] [--fps 7] [--dry-run]

Auth (Bearer): the key is read from the PIXELLAB_API_KEY env var, or failing
that from ~/.pixellab/credentials.json ({"api_key": "..."}). Calls are paid
(response carries usage.usd); GET /balance is checked first. --dry-run writes
flat placeholder frames so the build wiring can be exercised without a key or
spend. stdlib only (urllib).
"""
import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mascot_data import ensure_emotion_dirs  # noqa: E402

BASE = "https://api.pixellab.ai/v1"

# our emotion -> a PixelLab free-text `action` prompt. Generic, override-able.
DEFAULT_ACTIONS = {
    "idle": "idle, gentle breathing",
    "type": "tapping hands quickly, working",
    "walk": "hopping forward",
    "panic": "panicking, arms up, scared",
    "celebrate": "celebrating, both arms raised, cheering",
    "sleep": "sleeping, eyes closed",
    "point": "pointing to the side with one arm",
    "enter": "jumping into frame from below",
    "exit": "jumping away out of frame",
}


def _load_key():
    """Resolve the API key: PIXELLAB_API_KEY env var first, then a credentials
    file at ~/.pixellab/credentials.json ({"api_key": "..."}). Returns None if
    neither is set."""
    key = os.environ.get("PIXELLAB_API_KEY")
    if key:
        return key.strip()
    cred = os.path.join(os.path.expanduser("~"), ".pixellab", "credentials.json")
    try:
        with open(cred, encoding="utf-8") as f:
            data = json.load(f)
        return (data.get("api_key") or data.get("token") or "").strip() or None
    except (OSError, ValueError):
        return None


def _post(path, payload, key):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def _get(path, key):
    req = urllib.request.Request(BASE + path, headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def _write_png_b64(b64, out_png):
    with open(out_png, "wb") as f:
        f.write(base64.b64decode(b64))


def _placeholder(out_png, w=64, h=64):
    """A tiny solid PNG (no deps) so --dry-run can populate the frames dir."""
    import struct
    import zlib
    raw = b"".join(b"\x00" + bytes((220, 135, 110)) * w for _ in range(h))  # coral rows
    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    png = sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    with open(out_png, "wb") as f:
        f.write(png)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("--prompt", required=True, help="character description")
    ap.add_argument("--actions", default=",".join(DEFAULT_ACTIONS))
    ap.add_argument("--n-frames", type=int, default=6)
    ap.add_argument("--fps", type=float, default=7.0)
    ap.add_argument("--size", type=int, default=64,
                    help="sprite size for base + animation (PixelLab animate-with-text "
                         "currently supports 64; other sizes may be rejected by the API)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    actions = [x.strip() for x in a.actions.split(",") if x.strip()]
    os.makedirs(a.out_dir, exist_ok=True)

    def write_anim(anim, pngs_b64=None):
        d = os.path.join(a.out_dir, anim)
        os.makedirs(d, exist_ok=True)
        if pngs_b64 is None:  # dry-run
            for i in range(1, a.n_frames + 1):
                _placeholder(os.path.join(d, f"f_{i:03d}.png"), a.size, a.size)
            n = a.n_frames
        else:
            for i, b in enumerate(pngs_b64, 1):
                _write_png_b64(b, os.path.join(d, f"f_{i:03d}.png"))
            n = len(pngs_b64)
        print(f"  pixellab {anim}: {n} frames")

    if a.dry_run:
        for anim in actions:
            write_anim(anim)
        ensure_emotion_dirs(a.out_dir)  # fill any emotion the scenes need from idle
        with open(os.path.join(a.out_dir, "mascot-meta.json"), "w", encoding="utf-8") as f:
            json.dump({"fps": a.fps, "name": "pixellab-dry"}, f)
        print(f"  (dry-run) -> {a.out_dir}")
        return

    key = _load_key()
    if not key:
        sys.exit("No PixelLab key. Set PIXELLAB_API_KEY env var, or save "
                 "~/.pixellab/credentials.json = {\"api_key\": \"...\"}. "
                 "Get one at pixellab.ai (paid). Or use --dry-run.")
    try:
        bal = _get("/balance", key)
        print(f"  pixellab balance: {bal}")
        # 1) base character (reference image)
        base = _post("/generate-image-pixflux", {
            "description": a.prompt, "image_size": {"width": a.size, "height": a.size},
            "no_background": True}, key)
        ref = base["image"]["base64"]
        spent = base.get("usage", {}).get("usd", 0) or 0
        # 2) animate per emotion
        for anim in actions:
            action_prompt = DEFAULT_ACTIONS.get(anim, anim)
            res = _post("/animate-with-text", {
                "description": a.prompt, "action": action_prompt,
                "reference_image": {"type": "base64", "base64": ref},
                "image_size": {"width": a.size, "height": a.size},  # match base
                "n_frames": a.n_frames}, key)
            write_anim(anim, [im["base64"] for im in res["images"]])
            spent += res.get("usage", {}).get("usd", 0) or 0
        ensure_emotion_dirs(a.out_dir)  # fill any emotion the scenes need from idle
        with open(os.path.join(a.out_dir, "mascot-meta.json"), "w", encoding="utf-8") as f:
            json.dump({"fps": a.fps, "name": "pixellab"}, f)
        print(f"  pixellab done -> {a.out_dir} (~${spent:.3f})")
    except urllib.error.HTTPError as e:
        sys.exit(f"pixellab API error {e.code}: {e.read().decode()[:200]}")


if __name__ == "__main__":
    main()
