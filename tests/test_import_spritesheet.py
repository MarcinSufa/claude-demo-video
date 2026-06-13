"""Tests for import-spritesheet.py — pure sheet-plan parsing (no ffmpeg)."""
import importlib.util
import os
import sys
import unittest

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "assets", "scripts")
sys.path.insert(0, SCRIPTS)
spec = importlib.util.spec_from_file_location(
    "import_spritesheet", os.path.join(SCRIPTS, "import-spritesheet.py"))
isp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(isp)

FR = [
    {"frame": {"x": 0, "y": 0, "w": 16, "h": 16}, "duration": 100},
    {"frame": {"x": 16, "y": 0, "w": 16, "h": 16}, "duration": 100},
    {"frame": {"x": 32, "y": 0, "w": 16, "h": 16}, "duration": 100},
]


def doc(frames, tags):
    return {"frames": frames, "meta": {"frameTags": tags, "image": "x"}}


class TestParse(unittest.TestCase):
    def test_fps_from_duration(self):
        plan = isp.parse_sheet_plan(doc(FR, [{"name": "idle", "from": 0, "to": 2}]))
        self.assertEqual(plan["fps"], 10.0)  # 1000/100ms

    def test_rects_and_anims(self):
        plan = isp.parse_sheet_plan(doc(FR, [
            {"name": "idle", "from": 0, "to": 1},
            {"name": "walk", "from": 0, "to": 2}]))
        self.assertEqual(len(plan["anims"]["idle"]), 2)
        self.assertEqual(plan["anims"]["walk"][2], (32, 0, 16, 16))

    def test_hash_frames_supported(self):
        hashed = {"f0": FR[0], "f1": FR[1], "f2": FR[2]}
        plan = isp.parse_sheet_plan(
            {"frames": hashed, "meta": {"frameTags": [{"name": "idle", "from": 0, "to": 2}]}})
        self.assertEqual(len(plan["anims"]["idle"]), 3)

    def test_fps_override(self):
        plan = isp.parse_sheet_plan(
            doc(FR, [{"name": "idle", "from": 0, "to": 0}]), fps_override=12)
        self.assertEqual(plan["fps"], 12.0)

    def test_missing_tags_raises(self):
        with self.assertRaises(ValueError):
            isp.parse_sheet_plan({"frames": FR, "meta": {}})

    def test_out_of_bounds_tag_raises(self):
        with self.assertRaises(ValueError):
            isp.parse_sheet_plan(doc(FR, [{"name": "idle", "from": 0, "to": 5}]))


if __name__ == "__main__":
    unittest.main()
