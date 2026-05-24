"""Tests for scene_cache — capture caching (P0-2).

cache_key is a deterministic hash of the scene's plan entry + the contents of its
dependent input files (tape/html) + a version salt. is_fresh decides whether a
cached clip can be reused. Run: python -m unittest discover -s tests
"""
import importlib.util
import os
import sys
import tempfile
import unittest

_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "scripts", "scene_cache.py")
_spec = importlib.util.spec_from_file_location("scene_cache", _PATH)
scene_cache = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scene_cache)


class CacheKey(unittest.TestCase):
    def test_deterministic_for_same_entry(self):
        e = {"id": "c1", "type": "browser_capture", "scene_spec": {"url": "x", "actions": [1, 2]}}
        self.assertEqual(scene_cache.cache_key(e), scene_cache.cache_key(e))

    def test_key_order_independent(self):
        a = {"id": "c1", "type": "browser_capture", "mp4": "v.mp4"}
        b = {"mp4": "v.mp4", "type": "browser_capture", "id": "c1"}
        self.assertEqual(scene_cache.cache_key(a), scene_cache.cache_key(b))

    def test_changes_when_entry_changes(self):
        e1 = {"id": "c1", "scene_spec": {"url": "x"}}
        e2 = {"id": "c1", "scene_spec": {"url": "y"}}
        self.assertNotEqual(scene_cache.cache_key(e1), scene_cache.cache_key(e2))

    def test_changes_when_dep_file_content_changes(self):
        with tempfile.TemporaryDirectory() as d:
            tape = os.path.join(d, "s.tape")
            entry = {"id": "s1", "type": "terminal", "tape": "s.tape"}
            open(tape, "w").write("Type 'hello'")
            k1 = scene_cache.cache_key(entry, [tape])
            open(tape, "w").write("Type 'goodbye'")
            k2 = scene_cache.cache_key(entry, [tape])
            self.assertNotEqual(k1, k2)


class IsFresh(unittest.TestCase):
    def test_false_when_mp4_missing(self):
        with tempfile.TemporaryDirectory() as d:
            sha = os.path.join(d, "v.mp4.spec.sha")
            open(sha, "w").write("abc")
            self.assertFalse(scene_cache.is_fresh(os.path.join(d, "v.mp4"), sha, "abc"))

    def test_false_when_sha_missing(self):
        with tempfile.TemporaryDirectory() as d:
            mp4 = os.path.join(d, "v.mp4")
            open(mp4, "w").write("x")
            self.assertFalse(scene_cache.is_fresh(mp4, os.path.join(d, "v.mp4.spec.sha"), "abc"))

    def test_true_when_sha_matches_and_mp4_exists(self):
        with tempfile.TemporaryDirectory() as d:
            mp4 = os.path.join(d, "v.mp4"); sha = mp4 + ".spec.sha"
            open(mp4, "w").write("x"); open(sha, "w").write("abc\n")
            self.assertTrue(scene_cache.is_fresh(mp4, sha, "abc"))

    def test_false_when_sha_mismatches(self):
        with tempfile.TemporaryDirectory() as d:
            mp4 = os.path.join(d, "v.mp4"); sha = mp4 + ".spec.sha"
            open(mp4, "w").write("x"); open(sha, "w").write("stale")
            self.assertFalse(scene_cache.is_fresh(mp4, sha, "fresh"))


if __name__ == "__main__":
    unittest.main()
