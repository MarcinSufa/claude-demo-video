"""Tests for gen-pixellab.py — offline parts (action map + placeholder PNG).

The live API path needs PIXELLAB_API_KEY + network and is not unit-tested; the
build wires it behind mascot.source=pixellab and falls back mascot-less without
a key. These tests pin the offline contract the dry-run/build rely on.
"""
import importlib.util
import os
import sys
import tempfile
import unittest

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "assets", "scripts")
sys.path.insert(0, SCRIPTS)
spec = importlib.util.spec_from_file_location(
    "gen_pixellab", os.path.join(SCRIPTS, "gen-pixellab.py"))
gp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gp)

REQUIRED = ("idle", "type", "walk", "panic", "celebrate", "sleep", "point", "enter", "exit")


class TestPixelLab(unittest.TestCase):
    def test_action_map_covers_required_anims(self):
        for a in REQUIRED:
            self.assertIn(a, gp.DEFAULT_ACTIONS)

    def test_placeholder_writes_valid_png(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "f.png")
            gp._placeholder(p, 8, 8)
            with open(p, "rb") as f:
                self.assertEqual(f.read(8), b"\x89PNG\r\n\x1a\n")  # PNG signature


if __name__ == "__main__":
    unittest.main()


class TestKeyResolution(unittest.TestCase):
    def test_env_var_wins_and_strips(self):
        old = os.environ.get("PIXELLAB_API_KEY")
        os.environ["PIXELLAB_API_KEY"] = "  abc123  "
        try:
            self.assertEqual(gp._load_key(), "abc123")
        finally:
            if old is None:
                os.environ.pop("PIXELLAB_API_KEY", None)
            else:
                os.environ["PIXELLAB_API_KEY"] = old

    def test_credentials_file_fallback(self):
        import json as _json
        from unittest import mock
        old = os.environ.pop("PIXELLAB_API_KEY", None)
        with tempfile.TemporaryDirectory() as home:
            os.makedirs(os.path.join(home, ".pixellab"))
            with open(os.path.join(home, ".pixellab", "credentials.json"), "w") as f:
                _json.dump({"api_key": "filekey"}, f)
            try:
                with mock.patch("os.path.expanduser", return_value=home):
                    self.assertEqual(gp._load_key(), "filekey")
            finally:
                if old is not None:
                    os.environ["PIXELLAB_API_KEY"] = old
