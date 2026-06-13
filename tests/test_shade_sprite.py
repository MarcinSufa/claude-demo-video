"""Tests for shade_sprite.py procedural shading v2 (pure, no ffmpeg).

Shader v2 = hue-shifted ramp (warm highlight / cool shadow), a two-step shadow
(`shade2`), and a subtle body/shade boundary dither. These tests pin the colour
*direction* (warmer/cooler), not exact hexes where it would be brittle.
"""
import colorsys
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


def hsv(hex_color):
    """#rrggbb -> (hue_deg, sat, val)."""
    r, g, b = (int(hex_color[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return h * 360.0, s, v


def warmth(hex_color):
    """Signed warmth: + = closer to yellow(60), - = closer to cool(270).

    Measured as -(shortest angular distance to the warm hue 60deg); a warmer
    colour is a *larger* value. Lets us assert hi > body > shade without caring
    about the exact wheel position.
    """
    h = hsv(hex_color)[0]
    dist_to_warm = abs((h - 60.0 + 180.0) % 360.0 - 180.0)
    return -dist_to_warm


# A flat body square exercises top-rim / bottom-rim / interior logic. A taller
# block (BLOCK3) is used to exercise the deep-shadow floor + dither.
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


def _block(rows):
    return {
        "name": "tall", "cell_px": 4, "fps": 6,
        "legend": {".": None, "b": "body", "e": "eyes", "o": "outline"},
        "palette": {"body": "#d97757", "eyes": "#141414", "outline": "#3a352c"},
        "animations": {n: [rows] for n in (
            "idle", "type", "panic", "celebrate", "sleep", "point", "walk",
            "enter", "exit")},
    }


class TestColorMath(unittest.TestCase):
    def test_lighten_toward_white(self):
        self.assertEqual(ss.lighten("#000000", 0.5), "#808080")

    def test_darken_toward_black(self):
        self.assertEqual(ss.darken("#ffffff", 0.5), "#808080")

    def test_hi_is_lighter_than_body(self):
        body = "#d97757"
        self.assertGreater(hsv(ss.hi_color(body))[2], hsv(body)[2])

    def test_shade_is_darker_than_body_and_shade2_darkest(self):
        body = "#d97757"
        self.assertLess(hsv(ss.shade_color(body))[2], hsv(body)[2])
        self.assertLess(hsv(ss.shade2_color(body))[2], hsv(ss.shade_color(body))[2])

    def test_hue_shift_directions(self):
        # The headline v2 behaviour: light reads WARMER, shadow reads COOLER.
        body = "#d97757"
        self.assertGreater(warmth(ss.hi_color(body)), warmth(body),
                           "highlight must be warmer (toward yellow) than body")
        self.assertLess(warmth(ss.shade_color(body)), warmth(body),
                        "shadow must be cooler (toward blue/purple) than body")
        self.assertLess(warmth(ss.shade2_color(body)), warmth(ss.shade_color(body)),
                        "deep shadow must be cooler still than shade")

    def test_highlight_slightly_desaturated_shadow_more_saturated(self):
        body = "#d97757"
        self.assertLess(hsv(ss.hi_color(body))[1], hsv(body)[1])
        self.assertGreater(hsv(ss.shade_color(body))[1], hsv(body)[1])

    def test_greyish_color_not_hue_tinted(self):
        # Near-neutral colours should ramp by value only (no colour cast).
        grey = "#808080"
        for fn in (ss.hi_color, ss.shade_color, ss.shade2_color):
            r, g, b = (int(fn(grey)[i:i + 2], 16) for i in (1, 3, 5))
            self.assertEqual(r, g)
            self.assertEqual(g, b)


class TestShade(unittest.TestCase):
    def setUp(self):
        self.out = ss.shade_mascot(FLAT)

    def test_input_not_mutated(self):
        self.assertEqual(FLAT["animations"]["idle"][0], ["bb", "bb"])
        # palette/legend dicts of the input are untouched too
        self.assertNotIn("hi", FLAT["palette"])
        self.assertNotIn("shade2", FLAT["palette"])

    def test_adds_hi_shade_shade2_glow_slots(self):
        for slot in ("hi", "shade", "shade2", "glow"):
            self.assertIn(slot, self.out["palette"])

    def test_top_row_becomes_hi_bottom_becomes_shade(self):
        # 2x2 body on transparent bg: top row has open sky -> hi, bottom -> shade
        f = self.out["animations"]["idle"][0]
        legend = self.out["legend"]
        top_slots = {legend[ch] for ch in f[0]}
        bot_slots = {legend[ch] for ch in f[1]}
        self.assertIn("hi", top_slots)
        # bottom row is the silhouette floor with body directly above -> shade2
        self.assertIn("shade2", bot_slots)

    def test_hi_shade_palette_match_helpers(self):
        body = self.out["palette"]["body"]
        self.assertEqual(self.out["palette"]["hi"], ss.hi_color(body))
        self.assertEqual(self.out["palette"]["shade"], ss.shade_color(body))
        self.assertEqual(self.out["palette"]["shade2"], ss.shade2_color(body))

    def test_deep_shadow_on_floor_under_overhang(self):
        # Tall 3-row body: top->hi, middle->body, bottom row has body above it and
        # open space below -> deepest shade2 (the floor).
        out = ss.shade_mascot(_block(["bb", "bb", "bb"]), dither=False)
        f = out["animations"]["idle"][0]
        legend = out["legend"]
        self.assertEqual({legend[ch] for ch in f[0]}, {"hi"})
        self.assertEqual({legend[ch] for ch in f[2]}, {"shade2"})

    def test_dither_produces_mixed_boundary_row(self):
        # With dither ON, the interior row above a shade rim gets a body/shade
        # checker -> at least one row contains BOTH body and a shadow slot.
        rows = ["bbbb", "bbbb", "bbbb", "bbbb"]
        on = ss.shade_mascot(_block(rows), dither=True)["animations"]["idle"][0]
        off = ss.shade_mascot(_block(rows), dither=False)["animations"]["idle"][0]
        legend_on = ss.shade_mascot(_block(rows), dither=True)["legend"]

        def slots(frame):
            return [[legend_on.get(ch) for ch in row] for row in frame]

        # dither changes the grid...
        self.assertNotEqual(on, off, "dither=True must change the frame")
        # ...and creates a row mixing body with a shadow slot (textured boundary)
        mixed = any(
            ("body" in r and ("shade" in r or "shade2" in r))
            for r in slots(on))
        self.assertTrue(mixed, "expected a mixed body/shade dither row")

    def test_dither_off_leaves_clean_bands(self):
        rows = ["bbbb", "bbbb", "bbbb", "bbbb"]
        off = ss.shade_mascot(_block(rows), dither=False)
        legend = off["legend"]
        f = off["animations"]["idle"][0]
        # no interior row should mix body with shade when dither is off
        for row in f:
            slots = {legend[ch] for ch in row}
            self.assertFalse(
                "body" in slots and ("shade" in slots or "shade2" in slots),
                f"unexpected mixed row without dither: {row}")

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

    def test_graceful_without_belly_or_eyes(self):
        # body-only character (no belly/eyes slots) must still shade + validate
        m = {
            "name": "bodyonly", "cell_px": 4, "fps": 6,
            "legend": {".": None, "b": "body", "o": "outline"},
            "palette": {"body": "#6ea0e0", "outline": "#3a352c"},
            "animations": {n: [["bb", "bb"]] for n in (
                "idle", "type", "panic", "celebrate", "sleep", "point", "walk",
                "enter", "exit")},
        }
        out = ss.shade_mascot(m)
        for slot in ("hi", "shade", "shade2"):
            self.assertIn(slot, out["palette"])

    def test_result_still_validates(self):
        md = importlib.util.spec_from_file_location(
            "mascot_data", os.path.join(SCRIPTS, "mascot_data.py"))
        mod = importlib.util.module_from_spec(md)
        md.loader.exec_module(mod)
        mod.validate_mascot(self.out)  # must not raise
        # the real roster character must validate after shading too
        kpath = os.path.join(SCRIPTS, "..", "mascots", "kangaroo.json")
        import json
        with open(kpath, encoding="utf-8") as f:
            kangaroo = json.load(f)
        mod.validate_mascot(ss.shade_mascot(kangaroo))
        mod.validate_mascot(ss.shade_mascot(kangaroo, dither=False))


if __name__ == "__main__":
    unittest.main()
