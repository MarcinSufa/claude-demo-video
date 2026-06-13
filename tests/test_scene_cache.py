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


class DepFiles(unittest.TestCase):
    def test_diorama_hashes_local_source_windows_only(self):
        # local source clips bust the cache on content change; url/capture windows
        # carry their url+actions in the entry JSON (already hashed), so contribute none
        entry = {"id": "d1", "type": "diorama", "windows": [
            {"id": "a", "source": "footage/a.mp4", "x": 0, "y": 0, "w": 1280},
            {"id": "b", "capture": {"url": "http://x", "output": "videos/d1_b.mp4"},
             "x": 0, "y": 0, "w": 1280}]}
        self.assertEqual(scene_cache.dep_files_for(entry), ["footage/a.mp4"])


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


class TestMascotCacheLayers(unittest.TestCase):
    def test_capture_key_ignores_mascot_plan(self):
        entry = {"id": "s1", "type": "terminal", "mp4": "a.mp4", "tape": None}
        with_mascot = dict(entry, mascot_plan={"enabled": True, "emotion": "type"})
        self.assertEqual(scene_cache.cache_key(entry), scene_cache.cache_key(with_mascot))

    def test_capture_key_still_sensitive_to_entry(self):
        a = {"id": "s1", "type": "terminal", "mp4": "a.mp4"}
        b = {"id": "s1", "type": "terminal", "mp4": "b.mp4"}
        self.assertNotEqual(scene_cache.cache_key(a), scene_cache.cache_key(b))

    def test_overlay_key_changes_with_timeline(self):
        with tempfile.TemporaryDirectory() as d:
            clip = os.path.join(d, "c.mp4")
            mascot = os.path.join(d, "m.json")
            with open(clip, "wb") as f:
                f.write(b"fakevideo")
            with open(mascot, "w") as f:
                f.write('{"name":"octopus"}')
            t1 = {"stub": {"enabled": True}, "duration": 5.0,
                  "timeline": [{"at": 0, "until": 5, "emotion": "idle"}]}
            t2 = {"stub": {"enabled": True}, "duration": 5.0,
                  "timeline": [{"at": 0, "until": 5, "emotion": "panic"}]}
            k1 = scene_cache.overlay_key(clip, mascot, t1)
            k2 = scene_cache.overlay_key(clip, mascot, t2)
            self.assertNotEqual(k1, k2)

    def test_overlay_key_changes_with_clip_content(self):
        with tempfile.TemporaryDirectory() as d:
            clip = os.path.join(d, "c.mp4")
            mascot = os.path.join(d, "m.json")
            with open(mascot, "w") as f:
                f.write("{}")
            t = {"stub": {"enabled": True}, "duration": 5.0,
                 "timeline": [{"at": 0, "until": 5, "emotion": "idle"}]}
            with open(clip, "wb") as f:
                f.write(b"v1")
            k1 = scene_cache.overlay_key(clip, mascot, t)
            with open(clip, "wb") as f:
                f.write(b"v2")
            self.assertNotEqual(k1, scene_cache.overlay_key(clip, mascot, t))

    def test_version_bumped(self):
        self.assertEqual(scene_cache.VERSION, "4")


if __name__ == "__main__":
    unittest.main()
