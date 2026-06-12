import importlib.util
import os
import sys
import unittest

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "assets", "scripts")
sys.path.insert(0, SCRIPTS)
spec = importlib.util.spec_from_file_location(
    "overlay_mascot", os.path.join(SCRIPTS, "overlay-mascot.py"))
om = importlib.util.module_from_spec(spec)
spec.loader.exec_module(om)

TL = [
    {"at": 0.0, "until": 4.0, "emotion": "idle"},
    {"at": 4.0, "until": 6.0, "emotion": "panic"},
    {"at": 6.0, "until": 10.0, "emotion": "idle"},
]


class TestPosition(unittest.TestCase):
    def test_bottom_right_clears_captions(self):
        x, y = om.anchor_xy("bottom-right", video_w=1920, video_h=1080,
                            sprite_w=160, sprite_h=140)
        self.assertEqual(x, 1920 - 160 - om.MARGIN_PX)
        self.assertEqual(y, 1080 - 140 - om.CAPTION_CLEARANCE_PX)

    def test_bottom_left(self):
        x, y = om.anchor_xy("bottom-left", 1920, 1080, 160, 140)
        self.assertEqual(x, om.MARGIN_PX)

    def test_top_right(self):
        x, y = om.anchor_xy("top-right", 1920, 1080, 160, 140)
        self.assertEqual(y, om.MARGIN_PX)


class TestCmd(unittest.TestCase):
    def test_one_input_per_distinct_emotion(self):
        cmd = om.build_overlay_cmd("in.mp4", "out.mp4", "mascot", TL,
                                   pos=(1700, 740), fps=7, speedup=1.0)
        self.assertEqual(cmd.count("-i"), 3)
        joined = " ".join(cmd)
        self.assertIn("mascot/idle/f_%03d.png", joined)
        self.assertIn("mascot/panic/f_%03d.png", joined)

    def test_enable_windows_match_timeline(self):
        cmd = om.build_overlay_cmd("in.mp4", "out.mp4", "mascot", TL,
                                   pos=(1700, 740), fps=7, speedup=1.0)
        fc = cmd[cmd.index("-filter_complex") + 1]
        self.assertIn("between(t,0.000,4.000)", fc)
        self.assertIn("between(t,4.000,6.000)", fc)
        self.assertIn("between(t,6.000,10.000)", fc)

    def test_speedup_compensates_fps(self):
        cmd = om.build_overlay_cmd("in.mp4", "out.mp4", "mascot", TL,
                                   pos=(0, 0), fps=7, speedup=1.4)
        joined = " ".join(cmd)
        self.assertIn("-framerate 9.8", joined)

    def test_empty_timeline_returns_none(self):
        self.assertIsNone(om.build_overlay_cmd("in.mp4", "out.mp4", "mascot", [],
                                               pos=(0, 0), fps=7, speedup=1.0))


if __name__ == "__main__":
    unittest.main()
