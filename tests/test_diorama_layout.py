# tests/test_diorama_layout.py
import importlib.util, os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "assets", "scripts"))
from diorama_layout import window_anchor  # noqa: E402

WIN = {"x": 100, "y": 200, "w": 1280, "h": 720}  # a window's canvas rect


class TestWindowAnchor(unittest.TestCase):
    def test_top_perches_centered_on_top_edge(self):
        # sprite 160x140: centered horizontally on the window, sitting ON the top edge
        self.assertEqual(window_anchor(WIN, "top", 160, 140),
                         (100 + (1280 - 160) // 2, 200 - 140))

    def test_beside_is_right_of_window_vertically_centered(self):
        self.assertEqual(window_anchor(WIN, "beside", 160, 140),
                         (100 + 1280 + 8, 200 + (720 - 140) // 2))

    def test_on_is_centered_inside(self):
        self.assertEqual(window_anchor(WIN, "on", 160, 140),
                         (100 + (1280 - 160) // 2, 200 + (720 - 140) // 2))

    def test_unknown_anchor_raises(self):
        with self.assertRaises(ValueError):
            window_anchor(WIN, "sideways", 160, 140)


from diorama_layout import assert_canvas_16_9, focus_rect, camera_timeline, camera_duration, viewport_at  # noqa: E402

CANVAS = {"width": 3840, "height": 2160}
WINS = {
    "a": {"x": 200, "y": 200, "w": 1280, "h": 720},
    "b": {"x": 2300, "y": 1100, "w": 1280, "h": 720},
}


class TestFocusRect(unittest.TestCase):
    def test_zoom_one_is_full_width_16x9_centered(self):
        x, y, w, h = focus_rect({"focus": "a", "zoom": 1.0}, WINS, CANVAS)
        self.assertEqual(w, 3840)
        self.assertEqual(h, round(3840 * 9 / 16))   # 2160
        # clamped to canvas (can't center beyond edges)
        self.assertEqual((x, y), (0, 0))

    def test_zoom_in_halves_the_span_and_centers_on_window(self):
        x, y, w, h = focus_rect({"focus": "a", "zoom": 2.0}, WINS, CANVAS)
        self.assertEqual(w, 1920)
        self.assertEqual(h, 1080)
        cx, cy = 200 + 1280 / 2, 200 + 720 / 2          # window centre
        # unclamped x would be round(cx - 1920/2) = -120, but clamped to 0
        self.assertEqual(x, max(0, round(cx - 1920 / 2)))
        self.assertEqual(y, round(cy - 1080 / 2))

    def test_all_frames_bounding_box_of_windows(self):
        x, y, w, h = focus_rect({"focus": "all", "zoom": 1.0}, WINS, CANVAS)
        # viewport stays 16:9 and within canvas; centred on the windows' bbox centre
        self.assertEqual((w, h), (3840, 2160))
        self.assertEqual((x, y), (0, 0))

    def test_clamps_within_canvas_when_window_near_edge(self):
        x, y, w, h = focus_rect({"focus": "b", "zoom": 3.0}, WINS, CANVAS)
        self.assertGreaterEqual(x, 0)
        self.assertGreaterEqual(y, 0)
        self.assertLessEqual(x + w, CANVAS["width"])
        self.assertLessEqual(y + h, CANVAS["height"])

    def test_fractional_zoom_viewport_stays_within_canvas(self):
        # size and position are rounded independently — that must not push the rect
        # past the edge (regression: zoom 1.7 on a 2560 canvas yields a 1506px span)
        c = {"width": 2560, "height": 1440}
        wins = {"r": {"x": 1540, "y": 300, "w": 900, "h": 506}}
        x, y, w, h = focus_rect({"focus": "r", "zoom": 1.7}, wins, c)
        self.assertGreaterEqual(x, 0)
        self.assertGreaterEqual(y, 0)
        self.assertLessEqual(x + w, c["width"])
        self.assertLessEqual(y + h, c["height"])

    def test_mascot_focus_without_position_raises(self):
        # v1 can't follow the mascot (the tour is built before mascot positions are
        # known) — a focus:mascot stop must fail loud, not silently center on canvas
        with self.assertRaises(ValueError):
            focus_rect({"focus": "mascot", "zoom": 1.5}, WINS, CANVAS)

    def test_mascot_focus_with_explicit_position_centers_on_it(self):
        # the mascot_xy hook still works (future "camera follows mascot")
        x, y, w, h = focus_rect({"focus": "mascot", "zoom": 2.0}, WINS, CANVAS,
                                mascot_xy=(1920, 1080))
        self.assertLessEqual(x + w, CANVAS["width"])
        self.assertLessEqual(y + h, CANVAS["height"])


class TestCameraTimeline(unittest.TestCase):
    STOPS = [
        {"focus": "a", "zoom": 2.0, "hold": 3},
        {"focus": "b", "zoom": 2.0, "hold": 4, "transition": 1.0},
    ]

    def test_segments_cover_total_duration_contiguously(self):
        segs, total = camera_timeline(self.STOPS, WINS, CANVAS)
        self.assertEqual(segs[0][0], 0.0)
        for (s, e, a, b) in segs:
            self.assertLessEqual(s, e)
        for p, q in zip(segs, segs[1:]):
            self.assertAlmostEqual(p[1], q[0])           # contiguous
        self.assertAlmostEqual(segs[-1][1], total)
        self.assertAlmostEqual(total, 3 + 1 + 4)         # hold + transition + hold

    def test_hold_segment_is_static_transition_eases(self):
        segs, _ = camera_timeline(self.STOPS, WINS, CANVAS)
        holds = [s for s in segs if s[2] == s[3]]
        moves = [s for s in segs if s[2] != s[3]]
        self.assertEqual(len(holds), 2)
        self.assertEqual(len(moves), 1)                  # the 1s transition


class TestCameraDuration(unittest.TestCase):
    STOPS = [
        {"focus": "a", "zoom": 2.0, "hold": 3},
        {"focus": "b", "zoom": 2.0, "hold": 4, "transition": 1.0},
    ]

    def test_sums_holds_and_transitions(self):
        self.assertAlmostEqual(camera_duration(self.STOPS), 3 + 1 + 4)

    def test_first_stop_transition_ignored(self):
        # a transition on the first stop has nothing to ease from — it must not count
        stops = [{"focus": "a", "hold": 2, "transition": 5}, {"focus": "b", "hold": 3}]
        self.assertAlmostEqual(camera_duration(stops), 2 + 3)

    def test_default_hold_when_unspecified(self):
        self.assertAlmostEqual(camera_duration([{"focus": "a"}, {"focus": "b"}]), 2.0 + 2.0)

    def test_matches_camera_timeline_total(self):
        # the geometry-free duration MUST equal camera_timeline's accumulated total,
        # or a no-duration diorama would clip or pad its final hold
        _, total = camera_timeline(self.STOPS, WINS, CANVAS)
        self.assertAlmostEqual(camera_duration(self.STOPS), total)


class TestViewportAt(unittest.TestCase):
    def test_smoothstep_midpoint_is_halfway(self):
        segs = [(0.0, 1.0, (0, 0, 100, 56), (200, 0, 100, 56))]
        x, y, w, h = viewport_at(segs, 0.5)
        self.assertEqual(x, 100)                          # smoothstep(0.5)=0.5
        self.assertEqual(w, 100)

    def test_endpoints_exact(self):
        segs = [(0.0, 2.0, (0, 0, 100, 56), (200, 0, 100, 56))]
        self.assertEqual(viewport_at(segs, 0.0)[0], 0)
        self.assertEqual(viewport_at(segs, 2.0)[0], 200)

    def test_past_end_holds_last(self):
        segs = [(0.0, 2.0, (0, 0, 100, 56), (200, 0, 100, 56))]
        self.assertEqual(viewport_at(segs, 99)[0], 200)


class TestAssertCanvas16x9(unittest.TestCase):
    def test_accepts_16_9(self):
        assert_canvas_16_9({"width": 2560, "height": 1440})   # no raise
        assert_canvas_16_9({"width": 1920, "height": 1080})

    def test_rejects_other_aspect(self):
        with self.assertRaises(ValueError):
            assert_canvas_16_9({"width": 2560, "height": 1200})

    def test_error_names_the_dimensions(self):
        with self.assertRaises(ValueError) as cm:
            assert_canvas_16_9({"width": 2000, "height": 1000})
        self.assertIn("2000x1000", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
