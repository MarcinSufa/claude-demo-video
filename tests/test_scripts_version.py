"""Keep assets/scripts/VERSION current and prove drift is detected.

If you change any runtime script, regenerate the stamp:
    python assets/scripts/scripts_fingerprint.py --write assets/scripts
"""
import importlib.util
import os
import shutil
import sys
import tempfile
import unittest

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "assets", "scripts")
spec = importlib.util.spec_from_file_location(
    "scripts_fingerprint", os.path.join(SCRIPTS, "scripts_fingerprint.py"))
sf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sf)


class TestScriptsVersion(unittest.TestCase):
    def test_committed_version_is_current(self):
        vpath = os.path.join(SCRIPTS, "VERSION")
        self.assertTrue(os.path.exists(vpath),
                        "assets/scripts/VERSION missing — run scripts_fingerprint.py --write")
        with open(vpath, encoding="utf-8") as f:
            committed = f.read().strip()
        self.assertEqual(
            committed, sf.compute(SCRIPTS),
            "assets/scripts/VERSION is STALE — run:\n"
            "  python assets/scripts/scripts_fingerprint.py --write assets/scripts")

    def test_drift_is_detected(self):
        """A partial sync (one stale script) must fail --check."""
        with tempfile.TemporaryDirectory() as d:
            for f in os.listdir(SCRIPTS):
                src = os.path.join(SCRIPTS, f)
                if os.path.isfile(src):
                    shutil.copy(src, os.path.join(d, f))
            # consistent copy -> check passes
            self.assertEqual(sf.main([sys.argv[0], "--check", d]), 0)
            # mutate one script (simulate a stale/partial sync) -> check fails
            with open(os.path.join(d, "build.sh"), "a", encoding="utf-8") as f:
                f.write("\n# drift\n")
            self.assertEqual(sf.main([sys.argv[0], "--check", d]), 1)

    def test_normalises_line_endings(self):
        """CRLF vs LF must not change the fingerprint (cross-platform stability)."""
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            with open(os.path.join(a, "x.py"), "wb") as f:
                f.write(b"print(1)\nprint(2)\n")
            with open(os.path.join(b, "x.py"), "wb") as f:
                f.write(b"print(1)\r\nprint(2)\r\n")
            self.assertEqual(sf.compute(a), sf.compute(b))


if __name__ == "__main__":
    unittest.main()
