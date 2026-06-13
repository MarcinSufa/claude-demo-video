"""scripts_fingerprint.py — detect vendored-script drift.

Each project keeps a COPY of the skill's scripts in demo-video/scripts/. When
the skill updates, a partial re-sync (some files refreshed, others left stale)
silently runs a mix of old + new scripts and breaks in confusing ways — e.g. a
new build.sh passing `--scale` to an old render-mascot.py that doesn't accept
it, which fails soft and ships a mascot-less video.

This computes ONE fingerprint over all runtime scripts (line-ending-normalised,
so it's stable across LF/CRLF and OSes) and compares it to the committed VERSION
file. The build calls `--check`; if the vendored set is internally inconsistent,
it warns the user to re-sync — turning a silent breakage into a clear message.

  python scripts_fingerprint.py --check <dir>   # exit 0 = consistent, 1 = drift
  python scripts_fingerprint.py --write <dir>   # (re)write <dir>/VERSION  (dev tool)

compute() is the pure core; the committed assets/scripts/VERSION is kept current
by tests/test_scripts_version.py (fails if you change a script without rewriting).
"""
import hashlib
import os
import sys

EXTS = (".py", ".sh", ".mjs")
VERSION_FILE = "VERSION"


def compute(scripts_dir):
    """Deterministic sha256 over every runtime script's name + normalised content.

    Line endings are collapsed to \\n so the fingerprint is identical whether the
    working tree checked out LF (Linux/CI) or CRLF (Windows). VERSION itself is
    excluded (it is the output, not an input)."""
    h = hashlib.sha256()
    files = sorted(
        f for f in os.listdir(scripts_dir)
        if f.endswith(EXTS) and os.path.isfile(os.path.join(scripts_dir, f)))
    for f in files:
        with open(os.path.join(scripts_dir, f), "rb") as fh:
            data = fh.read().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        h.update(f.encode())
        h.update(b"\x00")
        h.update(data)
        h.update(b"\x00")
    return h.hexdigest()


def main(argv):
    if len(argv) != 3 or argv[1] not in ("--check", "--write"):
        sys.exit("usage: scripts_fingerprint.py --check|--write <scripts_dir>")
    mode, d = argv[1], argv[2]
    fp = compute(d)
    vpath = os.path.join(d, VERSION_FILE)
    if mode == "--write":
        with open(vpath, "w", encoding="utf-8", newline="\n") as f:
            f.write(fp + "\n")
        print(f"scripts VERSION <- {fp[:12]}")
        return 0
    try:
        with open(vpath, encoding="utf-8") as f:
            want = f.read().strip()
    except FileNotFoundError:
        print(f"scripts drift: no VERSION file in {d} — re-copy assets/scripts/* from the skill")
        return 1
    if fp == want:
        return 0
    print("scripts drift: the vendored demo-video/scripts/ are INCONSISTENT "
          "(mixed/stale versions from a partial sync). Re-copy ALL of "
          "assets/scripts/* from the skill (or re-run /demo-video init). "
          "Building with mixed versions causes confusing soft failures.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
