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


class TestCameraFilter(unittest.TestCase):
    SEGS = [(0.0, 2.0, (0, 0, 1920, 1080), (0, 0, 1920, 1080)),
            (2.0, 3.0, (0, 0, 1920, 1080), (800, 400, 960, 540))]

    def test_crops_then_scales_to_output(self):
        f = md.build_camera_filter(self.SEGS, 3840, 2160, 1920, 1080, fps=30)
        self.assertIn("crop=", f)
        self.assertIn("eval=frame", f)
        self.assertIn("scale=1920:1080", f)

    def test_expression_covers_each_segment_window(self):
        f = md.build_camera_filter(self.SEGS, 3840, 2160, 1920, 1080, fps=30)
        self.assertIn("between(t,0.000,2.000)", f)
        self.assertIn("between(t,2.000,3.000)", f)

    def test_transition_uses_smoothstep(self):
        f = md.build_camera_filter(self.SEGS, 3840, 2160, 1920, 1080, fps=30)
        # the moving segment eases x from 0 toward 800 with a smoothstep p*p*(3-2*p)
        self.assertIn("(3-2*", f)
