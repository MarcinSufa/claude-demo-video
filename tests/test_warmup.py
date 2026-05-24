"""Tests for plan-scenes.should_warmup — dev-server route warmup (P2-2).

Next-style dev servers compile routes on first hit, so the first capture can catch a
"Rendering..." overlay. Warmup defaults ON for localhost URLs, OFF for public sites,
and an explicit per-scene `warmup:` always wins. Run: python -m unittest discover -s tests
"""
import importlib.util
import os
import unittest

_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "scripts", "plan-scenes.py")
_spec = importlib.util.spec_from_file_location("plan_scenes", _PATH)
plan_scenes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(plan_scenes)


class ShouldWarmup(unittest.TestCase):
    def test_default_on_for_localhost(self):
        self.assertTrue(plan_scenes.should_warmup("http://localhost:3000/calls", None))

    def test_default_on_for_127_0_0_1(self):
        self.assertTrue(plan_scenes.should_warmup("http://127.0.0.1:8080/", None))

    def test_default_off_for_public_site(self):
        self.assertFalse(plan_scenes.should_warmup("https://example.com/pricing", None))

    def test_explicit_true_overrides_public(self):
        self.assertTrue(plan_scenes.should_warmup("https://example.com", True))

    def test_explicit_false_overrides_localhost(self):
        self.assertFalse(plan_scenes.should_warmup("http://localhost:3000", False))


if __name__ == "__main__":
    unittest.main()
