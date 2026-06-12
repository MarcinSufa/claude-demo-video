# tests/test_mascot_data.py
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "assets", "scripts"))
from mascot_data import load_mascot, validate_mascot, MascotError  # noqa: E402

MINIMAL = {
    "name": "blob",
    "cell_px": 6,
    "scale": 1.0,
    "fps": 8,
    "legend": {".": None, "b": "body", "e": "eyes"},
    "palette": {"body": "#e07a5f", "eyes": "#1a1a1a"},
    "animations": {
        "idle": [[".b.", "beb", ".b."], [".b.", "bbb", ".b."]],
        "type": [[".b.", "beb", "b.b"]],
        "walk": [[".b.", "beb", "b.."], [".b.", "beb", "..b"]],
        "panic": [["e.e", ".b.", "b.b"]],
        "celebrate": [["b.b", ".b.", "..."]],
        "sleep": [["...", ".b.", "bbb"]],
        "point": [["..b", ".bb", ".b."]],
        "enter": [["...", "...", ".b."]],
        "exit": [[".b.", "...", "..."]],
    },
}


class TestValidate(unittest.TestCase):
    def test_minimal_valid(self):
        validate_mascot(MINIMAL)  # should not raise

    def test_missing_animation_rejected(self):
        bad = json.loads(json.dumps(MINIMAL))
        del bad["animations"]["panic"]
        with self.assertRaisesRegex(MascotError, "panic"):
            validate_mascot(bad)

    def test_unknown_legend_char_rejected(self):
        bad = json.loads(json.dumps(MINIMAL))
        bad["animations"]["idle"][0][0] = "xb."
        with self.assertRaisesRegex(MascotError, "idle.*frame 0.*'x'"):
            validate_mascot(bad)

    def test_ragged_frame_rejected(self):
        bad = json.loads(json.dumps(MINIMAL))
        bad["animations"]["idle"][0][1] = "bb"
        with self.assertRaisesRegex(MascotError, "idle.*frame 0.*width"):
            validate_mascot(bad)

    def test_legend_slot_missing_from_palette_rejected(self):
        bad = json.loads(json.dumps(MINIMAL))
        bad["legend"]["h"] = "hat"  # no "hat" in palette
        with self.assertRaisesRegex(MascotError, "hat"):
            validate_mascot(bad)

    def test_bad_hex_rejected(self):
        bad = json.loads(json.dumps(MINIMAL))
        bad["palette"]["body"] = "tomato"
        with self.assertRaisesRegex(MascotError, "body"):
            validate_mascot(bad)

    def test_nonpositive_cell_px_rejected(self):
        bad = json.loads(json.dumps(MINIMAL))
        bad["cell_px"] = 0
        with self.assertRaisesRegex(MascotError, "cell_px"):
            validate_mascot(bad)

    def test_non_integer_fps_rejected(self):
        bad = json.loads(json.dumps(MINIMAL))
        bad["fps"] = "fast"
        with self.assertRaisesRegex(MascotError, "fps"):
            validate_mascot(bad)

    def test_bad_scale_rejected(self):
        bad = json.loads(json.dumps(MINIMAL))
        bad["scale"] = -1
        with self.assertRaisesRegex(MascotError, "scale"):
            validate_mascot(bad)


class TestLoad(unittest.TestCase):
    def test_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "m.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump(MINIMAL, f)
            m = load_mascot(p)
            self.assertEqual(m["name"], "blob")

    def test_load_missing_file(self):
        with self.assertRaises(MascotError):
            load_mascot("no/such/mascot.json")


class TestOctopusShips(unittest.TestCase):
    def test_bundled_octopus_validates(self):
        p = os.path.join(os.path.dirname(__file__), "..", "assets", "mascots", "octopus.json")
        validate_mascot(load_mascot(p))


if __name__ == "__main__":
    unittest.main()
