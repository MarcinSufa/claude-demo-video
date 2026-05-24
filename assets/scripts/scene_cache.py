"""scene_cache.py — skip re-capturing unchanged scenes (P0-2).

Each scene's clip is cached with a sidecar `<mp4>.spec.sha` holding a hash of its
plan entry + the contents of its dependent input files (tape / html) + a version
salt. On rebuild, an unchanged scene is reused — so editing only the voiceover
re-runs TTS+mix but skips every capture, and scene durations stay identical
run-to-run (which is what makes the P0-1/P3-1 timing math exact).

  python scene_cache.py check <scene-plan.json> <id>   # exit 0 = fresh (reuse), 1 = stale
  python scene_cache.py save  <scene-plan.json> <id>   # write the sidecar after building

cache_key() / is_fresh() are the pure, unit-tested core; main() is the plan/file glue.
"""
import hashlib
import json
import os
import sys

# Bump to invalidate ALL caches when a recorder/normalizer change makes old clips wrong.
VERSION = "1"


def cache_key(entry, dep_files=()):
    """Deterministic sha256 over the plan entry + dependent file contents + VERSION."""
    h = hashlib.sha256()
    h.update(("scene-cache-v" + VERSION).encode())
    h.update(json.dumps(entry, sort_keys=True).encode())
    for p in sorted(dep_files):
        try:
            with open(p, "rb") as f:
                h.update(b"\x00")
                h.update(os.path.basename(p).encode())
                h.update(b"\x00")
                h.update(f.read())
        except FileNotFoundError:
            h.update(b"\x00MISSING:" + os.path.basename(p).encode() + b"\x00")
    return h.hexdigest()


def is_fresh(mp4_path, sha_path, key):
    """A cached clip is reusable only if the clip exists AND its sidecar matches `key`."""
    if not os.path.exists(mp4_path) or not os.path.exists(sha_path):
        return False
    with open(sha_path, encoding="utf-8") as f:
        return f.read().strip() == key


def dep_files_for(entry):
    """Input files whose CONTENT should bust the cache for this scene type.
    (browser_capture has none — remote content can't be hashed; use --force.)"""
    t = entry.get("type")
    if t == "terminal":
        tape = entry.get("tape")
        return [tape] if tape else []
    if t == "multi_agent":
        return ["05a_agent_claude.tape", "05b_agent_cursor.tape", "05c_agent_cli.tape"]
    if t == "graph":
        return ["graph.html"]
    if t == "endcards":
        return ["endcards.html"]
    if t == "html_mockup":
        src = entry.get("html_source")
        return [os.path.basename(src)] if src else []
    return []


def _find_entry(plan_path, sid):
    with open(plan_path, encoding="utf-8") as f:
        for s in json.load(f).get("scenes", []):
            if s.get("id") == sid:
                return s
    sys.exit(f"scene_cache: no scene '{sid}' in {plan_path}")


def main(argv):
    if len(argv) != 4 or argv[1] not in ("check", "save"):
        sys.exit("usage: python scene_cache.py check|save <scene-plan.json> <id>")
    cmd, plan_path, sid = argv[1], argv[2], argv[3]
    entry = _find_entry(plan_path, sid)
    mp4 = entry["mp4"]
    sha = mp4 + ".spec.sha"
    key = cache_key(entry, dep_files_for(entry))
    if cmd == "check":
        return 0 if is_fresh(mp4, sha, key) else 1
    # save
    os.makedirs(os.path.dirname(sha) or ".", exist_ok=True)
    with open(sha, "w", encoding="utf-8", newline="\n") as f:
        f.write(key + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
