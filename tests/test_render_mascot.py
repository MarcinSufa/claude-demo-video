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


def _rendered_idle_sha256(mascot_filename):
    """Render a mascot and return sha256 of decoded RGBA of idle/f_001.png."""
    import hashlib
    import subprocess
    import sys
    import tempfile
    scripts = os.path.join(os.path.dirname(__file__), "..", "assets", "scripts")
    with tempfile.TemporaryDirectory() as d:
        subprocess.check_call([
            sys.executable,
            os.path.join(scripts, "render-mascot.py"),
            os.path.join(scripts, "..", "mascots", mascot_filename), d,
        ], stdout=subprocess.DEVNULL)
        raw = subprocess.check_output([
            "ffmpeg", "-v", "error", "-i", os.path.join(d, "idle", "f_001.png"),
            "-f", "rawvideo", "-pix_fmt", "rgba", "-"])
        return hashlib.sha256(raw).hexdigest()


def _require_ffmpeg(test):
    import shutil
    if not shutil.which("ffmpeg"):
        test.skipTest("ffmpeg not installed")


class TestGoldenFrame(unittest.TestCase):
    def test_octopus_idle_frame0_is_stable(self):
        _require_ffmpeg(self)
        self.assertEqual(
            _rendered_idle_sha256("octopus.json"),
            "9d09707504268b30e039d6154715c5fdcf8ddf60606ab4ef908d3246984f00cc")


class TestGoldenFrameKangaroo(unittest.TestCase):
    def test_kangaroo_idle_frame0_is_stable(self):
        _require_ffmpeg(self)
        self.assertEqual(
            _rendered_idle_sha256("kangaroo.json"),
            "048add4a13a03e9eaeb0ee8b1bc8250c59c02f9a48ac3e5123abd9e914bad164")


class TestGoldenFrameTessel(unittest.TestCase):
    def test_tessel_idle_frame0_is_stable(self):
        _require_ffmpeg(self)
        self.assertEqual(
            _rendered_idle_sha256("tessel.json"),
            "379e42f282055582a03f6d0c42944605c481ff5329b6435ed957f09ca26cfea9")


class TestStaleFrameClearing(unittest.TestCase):
    def test_rerender_with_fewer_frames_removes_stale_pngs(self):
        import shutil as _sh, subprocess as _sp, tempfile as _tf
        if not _sh.which("ffmpeg"):
            self.skipTest("ffmpeg not installed")
        mascot = {"name": "t", "cell_px": 2, "fps": 4, "scale": 1.0,
                  "legend": {".": None, "b": "body"},
                  "palette": {"body": "#ff0000"}}
        with _tf.TemporaryDirectory() as d:
            out = os.path.join(d, "idle")
            rm.render_animation(mascot, "idle", [["b"], ["b"], ["b"]], out)
            self.assertTrue(os.path.exists(os.path.join(out, "f_003.png")))
            rm.render_animation(mascot, "idle", [["b"], ["b"]], out)
            self.assertTrue(os.path.exists(os.path.join(out, "f_002.png")))
            self.assertFalse(os.path.exists(os.path.join(out, "f_003.png")))
