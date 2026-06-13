"""Tests for shade_sprite.py procedural shading (pure, no ffmpeg)."""
import importlib.util
import os
import sys
import unittest

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "assets", "scripts")
sys.path.insert(0, SCRIPTS)
spec = importlib.util.spec_from_file_location(
    "shade_sprite", os.path.join(SCRIPTS, "shade_sprite.py"))
ss = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ss)

# A 4x4 body block with a 1-cell outline ring would be ideal, but a flat body
# square is enough to exercise top-rim / bottom-rim / interior logic.
FLAT = {
    "name": "blk",
    "cell_px": 4,
    "fps": 6,
    "legend": {".": None, "b": "body", "e": "eyes", "o": "outline"},
    "palette": {"body": "#d97757", "eyes": "#141414", "outline": "#3a352c"},
    "animations": {
        "idle": [["bb", "bb"]],
        "type": [["bb", "bb"]], "panic": [["bb", "bb"]], "celebrate": [["bb", "bb"]],
        "sleep": [["bb", "bb"]], "point": [["bb", "bb"]], "walk": [["bb", "bb"]],
        "enter": [["bb", "bb"]], "exit": [["bb", "bb"]],
    },
}


class TestColorMath(unittest.TestCase):
    def test_lighten_toward_white(self):
        self.assertEqual(ss.lighten("#000000", 0.5), "#808080")

    def test_darken_toward_black(self):
        self.assertEqual(ss.darken("#ffffff", 0.5), "#808080")


class TestShade(unittest.TestCase):
    def setUp(self):
        self.out = ss.shade_mascot(FLAT)

    def test_input_not_mutated(self):
        self.assertEqual(FLAT["animations"]["idle"][0], ["bb", "bb"])

    def test_adds_hi_shade_glow_slots(self):
        for slot in ("hi", "shade", "glow"):
            self.assertIn(slot, self.out["palette"])

    def test_top_row_becomes_hi_bottom_becomes_shade(self):
        # 2x2 body on transparent bg: top row has open sky -> hi, bottom -> shade
        f = self.out["animations"]["idle"][0]
        legend = self.out["legend"]
        top_slots = {legend[ch] for ch in f[0]}
        bot_slots = {legend[ch] for ch in f[1]}
        self.assertIn("hi", top_slots)
        self.assertIn("shade", bot_slots)

    def test_hi_color_lighter_than_body(self):
        self.assertEqual(self.out["palette"]["hi"], ss.lighten("#d97757", 0.30))
        self.assertEqual(self.out["palette"]["shade"], ss.darken("#d97757", 0.18))

    def test_eye_catchlight(self):
        m = {
            "name": "eye", "cell_px": 4, "fps": 6,
            "legend": {".": None, "b": "body", "e": "eyes", "o": "outline"},
            "palette": {"body": "#d97757", "eyes": "#141414", "outline": "#3a352c"},
            "animations": {n: [["bbbb", "beeb", "beeb", "bbbb"]]
                           for n in ("idle", "type", "panic", "celebrate", "sleep",
                                     "point", "walk", "enter", "exit")},
        }
        out = ss.shade_mascot(m)
        glow_char = next(ch for ch, s in out["legend"].items() if s == "glow")
        # top-left of the 2x2 eye blob (row1,col1) becomes glow
        self.assertEqual(out["animations"]["idle"][0][1][1], glow_char)

    def test_missing_body_slot_raises(self):
        bad = {"name": "x", "cell_px": 4, "fps": 6,
               "legend": {".": None}, "palette": {}, "animations": {}}
        with self.assertRaises(ValueError):
            ss.shade_mascot(bad)

    def test_result_still_validates(self):
        md = importlib.util.spec_from_file_location(
            "mascot_data", os.path.join(SCRIPTS, "mascot_data.py"))
        mod = importlib.util.module_from_spec(md)
        md.loader.exec_module(mod)
        mod.validate_mascot(self.out)  # must not raise


if __name__ == "__main__":
    unittest.main()
