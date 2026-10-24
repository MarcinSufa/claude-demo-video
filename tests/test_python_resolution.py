"""Shell scripts must not call a bare `python` (audit 2026-10-24).

Stock Linux ships only `python3`, so a bare `python` exits 127 there. build.sh
resolves the interpreter once ($PYTHON, else python3, else python) and exports
it as $PY; every sub-script falls back to the same probe when run standalone.
Run: python3 -m unittest discover -s tests
"""
import os
import re
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
SHELL = [os.path.join(ROOT, "assets", "scripts", f)
         for f in sorted(os.listdir(os.path.join(ROOT, "assets", "scripts"))) if f.endswith(".sh")]
SHELL.append(os.path.join(ROOT, "tests", "smoke_build.sh"))

# `python` used as a command: line start, after ( ; | && or whitespace, followed by an argument.
BARE = re.compile(r"(^|[\s(;|&])python\s+(-[cm]\b|-\s|[\w\"$.])")


class NoBarePython(unittest.TestCase):
    def test_no_bare_python_command(self):
        hits = []
        for path in SHELL:
            with open(path, encoding="utf-8") as f:
                for n, line in enumerate(f, 1):
                    code = line.split("#", 1)[0] if line.lstrip().startswith("#") else line
                    if "echo" in code or "fail " in code or "python3 python" in code:
                        continue    # user-facing messages and the resolver candidate list
                    if BARE.search(code):
                        hits.append(f"{os.path.basename(path)}:{n}: {line.strip()}")
        self.assertEqual(hits, [], "bare `python` call (use \"$PY\"):\n" + "\n".join(hits))

    def test_build_sh_exports_py(self):
        with open(os.path.join(ROOT, "assets", "scripts", "build.sh"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn("export PY", src)
        self.assertIn("python3", src)


if __name__ == "__main__":
    unittest.main()
