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

    def test_zoompan_into_output_size(self):
        f = md.build_camera_filter(self.SEGS, 3840, 2160, 1920, 1080, fps=30)
        self.assertIn("zoompan=", f)
        self.assertIn("s=1920x1080", f)
        # input pinned to fps so zoompan's on/fps time base maps to seconds
        self.assertIn("[0:v]fps=30,", f)

    def test_no_unsupported_crop_eval(self):
        # crop's `eval` option is absent on some ffmpeg builds (and animated crop
        # can't change output size anyway) — must not regress to it
        f = md.build_camera_filter(self.SEGS, 3840, 2160, 1920, 1080, fps=30)
        self.assertNotIn("eval=frame", f)

    def test_expression_covers_each_segment_on_frame_time(self):
        f = md.build_camera_filter(self.SEGS, 3840, 2160, 1920, 1080, fps=30)
        # zoompan exposes the output-frame counter `on`, not `t`
        self.assertIn("between((on/30.000),0.000,2.000)", f)
        self.assertIn("between((on/30.000),2.000,3.000)", f)

    def test_zoom_derived_from_canvas_width(self):
        f = md.build_camera_filter(self.SEGS, 3840, 2160, 1920, 1080, fps=30)
        # zoom factor = canvas_width / viewport_width, clamped so it never zooms
        # out past the full canvas
        self.assertIn("max(1,3840/(", f)

    def test_transition_uses_smoothstep(self):
        f = md.build_camera_filter(self.SEGS, 3840, 2160, 1920, 1080, fps=30)
        # the moving segment eases x from 0 toward 800 with a smoothstep p*p*(3-2*p)
        self.assertIn("(3-2*", f)


class TestDioramaTimeline(unittest.TestCase):
    KEYFRAMES = [{"at": 0, "emotion": "idle", "at_window": "a", "anchor": "top"},
                 {"at": 5, "emotion": "point", "at_window": "b", "anchor": "beside"}]

    def test_two_windows_insert_walk_with_base_and_tail(self):
        tl = md.diorama_timeline(self.KEYFRAMES, 10)
        # base segment (first keyframe, on window a)
        self.assertEqual(tl[0]["at"], 0)
        self.assertEqual(tl[0]["at_window"], "a")
        self.assertNotIn("move", tl[0])
        # walk move segment a -> b
        moves = [s for s in tl if "move" in s]
        self.assertEqual(len(moves), 1)
        self.assertEqual(moves[0]["emotion"], "walk")
        self.assertEqual(moves[0]["move"]["from_window"], "a")
        self.assertEqual(moves[0]["move"]["to_window"], "b")
        # tail segment lands on window b and reaches the duration
        self.assertEqual(tl[-1]["at_window"], "b")
        self.assertEqual(tl[-1]["until"], 10)
        # contiguous from 0 to duration
        self.assertEqual(tl[0]["at"], 0)
        for p, q in zip(tl, tl[1:]):
            self.assertAlmostEqual(p["until"], q["at"])
        self.assertAlmostEqual(tl[-1]["until"], 10)


class TestCanvasPositions(unittest.TestCase):
    WINS = [{"id": "a", "x": 100, "y": 200, "w": 1280, "h": 720},
            {"id": "b", "x": 2300, "y": 1100, "w": 1280, "h": 720}]
    CANVAS = {"width": 3840, "height": 2160}

    def test_static_segment_uses_window_anchor(self):
        tl = [{"at": 0, "until": 3, "emotion": "idle", "at_window": "a", "anchor": "top"}]
        pos = md.resolve_canvas_positions(tl, self.WINS, (160, 140), self.CANVAS)
        self.assertEqual(pos[0], (100 + (1280 - 160) // 2, 200 - 140))

    def test_move_segment_resolves_both_windows(self):
        tl = [{"at": 0, "until": 0.8, "emotion": "walk",
               "move": {"from_window": "a", "from_anchor": "top",
                        "to_window": "b", "to_anchor": "beside"}}]
        pos = md.resolve_canvas_positions(tl, self.WINS, (160, 140), self.CANVAS)
        self.assertEqual(pos[0][0], (100 + (1280 - 160) // 2, 200 - 140))
        self.assertEqual(pos[0][1], (2300 + 1280 + 8, 1100 + (720 - 140) // 2))

    def test_anchor_clamped_into_canvas(self):
        # window 'b' is at the right/bottom edge; a 'beside' anchor would land the
        # sprite off-canvas — it must clamp to within [0, canvas - sprite]
        small = {"width": 3300, "height": 1300}
        tl = [{"at": 0, "until": 3, "emotion": "point", "at_window": "b", "anchor": "beside"}]
        x, y = md.resolve_canvas_positions(tl, self.WINS, (160, 140), small)[0]
        self.assertLessEqual(x + 160, small["width"])
        self.assertLessEqual(y + 140, small["height"])
        self.assertGreaterEqual(x, 0)
        self.assertGreaterEqual(y, 0)


class TestChromeHelpers(unittest.TestCase):
    def test_ffcolor_normalizes_hex(self):
        self.assertEqual(md._ffcolor("#1e1714"), "0x1e1714")
        self.assertEqual(md._ffcolor("2c2c32"), "0x2c2c32")
        self.assertEqual(md._ffcolor("0xabcdef"), "0xabcdef")

    def test_chrome_metrics_scale_from_bar_height(self):
        m = md.chrome_metrics(40)
        self.assertEqual(m["strip_w"], 3 * m["d"] + 2 * m["gap"])
        self.assertEqual(m["strip_h"], m["d"])
        self.assertGreater(m["title_x"], m["pad"] + m["strip_w"])  # title right of dots
        for k in ("d", "gap", "pad", "title_x", "title_fs"):
            self.assertGreater(m[k], 0)

    def test_window_h_adds_bar_only_for_chrome(self):
        clip_only = round(1000 * 1080 / 1920)
        self.assertEqual(md.window_h(1000, 1920, 1080, False), clip_only)
        self.assertEqual(md.window_h(1000, 1920, 1080, True), clip_only + md.BAR_H)


if __name__ == "__main__":
    unittest.main()
