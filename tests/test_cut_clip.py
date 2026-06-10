"""Tests for cut-clip.py's pure timeline/filter logic (no ffmpeg needed).

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


cc = _load("cut_clip", "cut-clip.py")


class HasWork(unittest.TestCase):
    def test_plain_events_are_noop(self):
        self.assertFalse(cc.has_work([{"start": 0, "end": 1, "speed": 1, "zoom": None}]))

    def test_speed_is_work(self):
        self.assertTrue(cc.has_work([{"start": 0, "end": 1, "speed": 4, "zoom": None}]))

    def test_zoom_is_work(self):
        self.assertTrue(cc.has_work([{"start": 0, "end": 1, "speed": 1,
                                      "zoom": {"fx": 0.5, "fy": 0.5, "z": 1.3}}]))

    def test_empty_is_noop(self):
        self.assertFalse(cc.has_work([]))

    def test_malformed_zoom_is_noop(self):
        # a zoom that isn't a usable dict (missing z, or not a dict) is no work
        self.assertFalse(cc.has_work([{"start": 0, "end": 1, "speed": 1, "zoom": {"fx": 0.5}}]))
        self.assertFalse(cc.has_work([{"start": 0, "end": 1, "speed": 1, "zoom": "corner"}]))

    def test_bad_speed_is_noop(self):
        # non-positive / non-numeric speed is sanitized to 1x → no work
        self.assertFalse(cc.has_work([{"start": 0, "end": 1, "speed": 0, "zoom": None}]))
        self.assertFalse(cc.has_work([{"start": 0, "end": 1, "speed": "fast", "zoom": None}]))


class BuildTimeline(unittest.TestCase):
    def test_fills_gap_before_and_after(self):
        segs = cc.build_timeline([{"start": 2, "end": 4, "speed": 4, "zoom": None}], 6)
        self.assertEqual(segs, [
            (0.0, 2.0, 1.0, None),
            (2.0, 4.0, 4.0, None),
            (4.0, 6.0, 1.0, None),
        ])

    def test_is_contiguous_and_covers_full_duration(self):
        segs = cc.build_timeline(
            [{"start": 1, "end": 2, "speed": 2, "zoom": None},
             {"start": 3, "end": 5, "speed": 1, "zoom": {"fx": 0.8, "fy": 0.1, "z": 1.3}}], 6)
        self.assertEqual(segs[0][0], 0.0)
        self.assertEqual(segs[-1][1], 6.0)
        for a, b in zip(segs, segs[1:]):
            self.assertAlmostEqual(a[1], b[0])  # end of one == start of next

    def test_clamps_overlap(self):
        segs = cc.build_timeline(
            [{"start": 0, "end": 3, "speed": 2, "zoom": None},
             {"start": 2, "end": 4, "speed": 4, "zoom": None}], 4)
        # second event's start is clamped to the first's end (no overlap, no gap)
        self.assertEqual(segs, [(0.0, 3.0, 2.0, None), (3.0, 4.0, 4.0, None)])

    def test_no_events_is_single_passthrough(self):
        self.assertEqual(cc.build_timeline([], 5), [(0.0, 5.0, 1.0, None)])

    def test_clamps_event_past_duration(self):
        segs = cc.build_timeline([{"start": 1, "end": 99, "speed": 3, "zoom": None}], 4)
        self.assertEqual(segs, [(0.0, 1.0, 1.0, None), (1.0, 4.0, 3.0, None)])


class BuildFilter(unittest.TestCase):
    def test_segment_count_and_concat(self):
        segs = [(0.0, 2.0, 1.0, None), (2.0, 4.0, 4.0, None)]
        fc, out = cc.build_filter(segs, 1920, 1080, fps=30)
        self.assertEqual(out, "[outv]")
        self.assertEqual(fc.count("[0:v]"), 2)
        self.assertIn("concat=n=2:v=1:a=0[outv]", fc)
        self.assertIn("setsar=1", fc)

    def test_speed_changes_setpts(self):
        fc, _ = cc.build_filter([(0.0, 2.0, 4.0, None)], 1920, 1080)
        self.assertIn("setpts=(PTS-STARTPTS)/4", fc)

    def test_passthrough_setpts(self):
        fc, _ = cc.build_filter([(0.0, 2.0, 1.0, None)], 1920, 1080)
        self.assertIn("setpts=(PTS-STARTPTS)", fc)
        self.assertNotIn("STARTPTS)/", fc)

    def test_zoom_adds_crop_scale(self):
        fc, _ = cc.build_filter([(0.0, 2.0, 1.0, {"fx": 0.5, "fy": 0.5, "z": 2.0})], 1920, 1080)
        self.assertIn("crop=", fc)
        self.assertIn("scale=1920:1080", fc)

    def test_malformed_zoom_is_ignored(self):
        # zoom dict missing z (or not a dict) must not crash or emit a crop filter
        for bad in ({"fx": 0.5, "fy": 0.5}, {"z": float("nan"), "fx": 0.5, "fy": 0.5}, "corner", 7):
            fc, _ = cc.build_filter([(0.0, 2.0, 1.0, bad)], 1920, 1080)
            self.assertNotIn("crop=", fc)

    def test_bad_speed_falls_back_to_passthrough(self):
        # non-positive / NaN / inf speed must not emit a divide (invalid setpts)
        for bad in (0, -3, float("nan"), float("inf")):
            fc, _ = cc.build_filter([(0.0, 2.0, bad, None)], 1920, 1080)
            self.assertNotIn("STARTPTS)/", fc)


class ZoomChain(unittest.TestCase):
    def test_centered_full_zoom_window(self):
        # z=2 centered → half-size window centered at (480, 270) for 1920x1080
        chain = cc.zoom_chain(1920, 1080, 2.0, 0.5, 0.5)
        self.assertEqual(chain, "crop=960:540:480:270,scale=1920:1080")

    def test_focal_clamped_into_bounds(self):
        # focal at the far corner must not produce a negative / overflowing crop origin
        chain = cc.zoom_chain(1920, 1080, 2.0, 1.0, 1.0)
        self.assertEqual(chain, "crop=960:540:960:540,scale=1920:1080")

    def test_zoom_le_1_is_full_frame(self):
        # z<=1 must clamp the window to the full frame (never a window larger than it)
        self.assertEqual(cc.zoom_chain(1920, 1080, 0.5, 0.5, 0.5),
                         "crop=1920:1080:0:0,scale=1920:1080")

    def test_huge_zoom_keeps_a_valid_window(self):
        # an extreme z must floor the window at 2px (even), origin inside the frame
        chain = cc.zoom_chain(1920, 1080, 99999.0, 0.5, 0.5)
        self.assertTrue(chain.startswith("crop=2:2:"))
        self.assertIn(",scale=1920:1080", chain)


if __name__ == "__main__":
    unittest.main()
