# tests/test_make_diorama.py
import importlib.util, os, sys, unittest
SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "assets", "scripts")
sys.path.insert(0, SCRIPTS)
spec = importlib.util.spec_from_file_location("make_diorama", os.path.join(SCRIPTS, "make-diorama.py"))
md = importlib.util.module_from_spec(spec); spec.loader.exec_module(md)

CANVAS = {"width": 3840, "height": 2160}
WINDOWS = [
    {"id": "a", "x": 200, "y": 200, "w": 1280},
    {"id": "b", "x": 2300, "y": 1100, "w": 1280},
]


class TestCanvasFilter(unittest.TestCase):
    def test_scales_backdrop_to_canvas(self):
        fc = md.build_canvas_filter(WINDOWS, CANVAS)
        self.assertIn("[0:v]scale=3840:2160", fc)

    def test_one_overlay_per_window_at_its_offset(self):
        fc = md.build_canvas_filter(WINDOWS, CANVAS)
        self.assertEqual(fc.count("overlay="), 2)
        self.assertIn("overlay=200:200", fc)
        self.assertIn("overlay=2300:1100", fc)

    def test_window_scaled_to_its_width(self):
        fc = md.build_canvas_filter(WINDOWS, CANVAS)
        self.assertIn("[1:v]scale=1280:-2", fc)   # window 'a' to width 1280
        self.assertIn("[2:v]scale=1280:-2", fc)
