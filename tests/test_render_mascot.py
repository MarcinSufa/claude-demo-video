"""Tests for render-mascot.py pure grid/RGBA/scale logic (no ffmpeg needed).

Run: python -m unittest discover tests
"""
import importlib.util
import os
import unittest


def _load(name, filename):
    path = os.path.join(os.path.dirname(__file__), "..", "assets", "scripts", filename)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rm = _load("render_mascot", "render-mascot.py")

LEGEND = {".": None, "b": "body"}
PALETTE = {"body": "#ff0000"}


class TestGridToRgba(unittest.TestCase):
    def test_dimensions(self):
        buf, w, h = rm.grid_to_rgba(["b.", ".b"], LEGEND, PALETTE, cell_px=3)
        self.assertEqual((w, h), (6, 6))
        self.assertEqual(len(buf), 6 * 6 * 4)

    def test_filled_cell_is_opaque_color(self):
        buf, w, h = rm.grid_to_rgba(["b"], LEGEND, PALETTE, cell_px=2)
        for px in range(w * h):
            self.assertEqual(tuple(buf[px * 4:px * 4 + 4]), (255, 0, 0, 255))

    def test_transparent_cell_has_zero_alpha(self):
        buf, w, h = rm.grid_to_rgba(["."], LEGEND, PALETTE, cell_px=1)
        self.assertEqual(buf[3], 0)

    def test_palette_override_wins(self):
        buf, _, _ = rm.grid_to_rgba(["b"], LEGEND, PALETTE, cell_px=1,
                                    overrides={"body": "#00ff00"})
        self.assertEqual(tuple(buf[0:4]), (0, 255, 0, 255))

    def test_hex_to_rgb(self):
        self.assertEqual(rm.hex_to_rgb("#dbaf71"), (219, 175, 113))


class TestTargetHeight(unittest.TestCase):
    def test_scale_pins_output_height(self):
        self.assertEqual(rm.upscale_factor(native_h=96, target_h=140, scale=1.0), 1)
        self.assertEqual(rm.upscale_factor(native_h=96, target_h=280, scale=1.0), 3)
        self.assertEqual(rm.upscale_factor(native_h=96, target_h=140, scale=2.0), 3)
