"""fetch-music.py: fetch one CC0 / public-domain track for a music mood.

Reads assets/music/manifest.yaml (per mood: primary and alternate track with a
url and sha256), downloads into a per-user cache keyed by sha256, verifies the
checksum on download and on every cache hit, and copies the track to --output.

  python fetch-music.py --manifest manifest.yaml --style calm --output music-src.mp3

Exit 1 with a message on stderr when no track of the mood could be verified.
"""
import argparse
import hashlib
import os
import pathlib
import shutil
import sys
import tempfile
import urllib.request

import yaml


class FetchError(Exception):
    pass


class OutputError(Exception):
    pass


def cache_dir(env=None, platform=None):
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    explicit = env.get("DEMO_MUSIC_CACHE")
    if explicit:
        return pathlib.Path(explicit)
    if platform == "win32" and env.get("LOCALAPPDATA"):
        base = pathlib.Path(env["LOCALAPPDATA"])
    elif env.get("XDG_CACHE_HOME"):
        base = pathlib.Path(env["XDG_CACHE_HOME"])
    else:
        base = pathlib.Path(env.get("HOME") or pathlib.Path.home()) / ".cache"
    return base / "demo-video" / "music"


def load_manifest(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def licence_ok(licence):
    text = str(licence or "").strip().lower()
    return text.startswith("cc0") or "public domain" in text


def _extension(url):
    ext = pathlib.Path(url.split("?")[0]).suffix.lower()
    return ext if ext in (".mp3", ".ogg", ".oga", ".flac", ".wav", ".m4a", ".opus") else ".mp3"


def _download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": "demo-video fetch-music"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as out:
        shutil.copyfileobj(resp, out)


def ensure_cached(track, cache):
    want = str(track.get("sha256", "")).lower()
    if len(want) != 64:
        raise FetchError(f"{track.get('title', '?')}: manifest sha256 is not 64 hex chars")
    cache.mkdir(parents=True, exist_ok=True)
    cached = cache / f"{want}{_extension(track['url'])}"
    if cached.exists():
        if sha256_of(cached) == want:
            return cached
        cached.unlink()
    fd, tmp = tempfile.mkstemp(dir=cache, suffix=".part")
    os.close(fd)
    try:
        _download(track["url"], tmp)
        got = sha256_of(tmp)
        if got != want:
            raise FetchError(
                f"{track.get('title', '?')}: sha256 mismatch (manifest {want[:12]}, got {got[:12]})")
        os.replace(tmp, cached)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return cached


def fetch(manifest, style, output, cache):
    mood = manifest.get(style)
    if not mood:
        raise FetchError(f"no '{style}' mood in the manifest ({', '.join(sorted(manifest))})")
    if mood.get("procedural_only"):
        raise FetchError(f"mood '{style}' is procedural only (no verified CC0 track yet)")
    errors = []
    for role in ("primary", "alternate"):
        track = mood.get(role)
        if not track or not track.get("url"):
            continue
        if not licence_ok(track.get("licence")):
            errors.append(f"{role}: licence '{track.get('licence')}' is not CC0 or public domain")
            continue
        try:
            cached = ensure_cached(track, cache)
        except (OSError, ValueError, FetchError) as e:
            errors.append(f"{role}: {e}")
            continue
        try:
            shutil.copyfile(cached, output)
        except OSError as e:
            raise OutputError(f"cannot write {output}: {e}") from e
        return track
    raise FetchError(f"no track of mood '{style}' could be fetched: " + "; ".join(errors))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--style", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--cache-dir", default=None)
    args = ap.parse_args(argv)
    cache = pathlib.Path(args.cache_dir) if args.cache_dir else cache_dir()
    try:
        track = fetch(load_manifest(args.manifest), args.style, args.output, cache)
    except OutputError as e:
        print(f"fetch-music: FATAL: {e}", file=sys.stderr)
        return 3
    except (FetchError, OSError) as e:
        print(f"fetch-music: WARNING: {e}", file=sys.stderr)
        return 1
    print(f"fetch-music: {args.style} -> {track.get('title')} by {track.get('artist')} "
          f"({track.get('licence')}, {track.get('source_page')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
