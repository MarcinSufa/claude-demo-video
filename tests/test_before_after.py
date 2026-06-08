"""Tests for the before_after scene type: make-before-after.py's pure filter/
label logic and plan-scenes.py's before_after resolution.

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


mba = _load("make_before_after", "make-before-after.py")
plan = _load("plan_scenes", "plan-scenes.py")


class AsciiLabel(unittest.TestCase):
    def test_em_dash_to_hyphen(self):
        self.assertEqual(mba.ascii_label("BEFORE — the bug"), "BEFORE - the bug")

    def test_smart_quotes_and_ellipsis(self):
        self.assertEqual(mba.ascii_label("“hi” …"), '"hi" ...')

    def test_drops_remaining_unicode(self):
        self.assertEqual(mba.ascii_label("ok✓"), "ok")


class HalfClipPath(unittest.TestCase):
    def test_source(self):
        self.assertEqual(mba.half_clip_path({"source": "x.mp4"}), "x.mp4")

    def test_capture_output(self):
        self.assertEqual(mba.half_clip_path({"capture": {"output": "v/c.mp4"}}), "v/c.mp4")

    def test_missing_raises(self):
        with self.assertRaises(SystemExit):
            mba.half_clip_path({"label": "x"})


class BuildFilter(unittest.TestCase):
    def test_sequential_concats_and_labels_both(self):
        fc, out = mba.build_filter("sequential", 1920, 1080, "b.txt", "a.txt")
        self.assertEqual(out, "[v]")
        self.assertIn("concat=n=2:v=1:a=0", fc)
        self.assertNotIn("hstack", fc)
        self.assertIn("textfile='b.txt'", fc)
        self.assertIn("textfile='a.txt'", fc)
        self.assertIn(mba.BEFORE_COLOR, fc)
        self.assertIn(mba.AFTER_COLOR, fc)

    def test_side_by_side_hstacks_at_half_width(self):
        fc, _ = mba.build_filter("side_by_side", 1920, 1080, "b.txt", "a.txt")
        self.assertIn("hstack=inputs=2", fc)
        self.assertIn("scale=960:1080", fc)  # 1920 // 2

    def test_half_duration_trims_each(self):
        fc, _ = mba.build_filter("sequential", 1920, 1080, "b.txt", "a.txt", half_duration=6)
        self.assertEqual(fc.count("trim=duration=6.0"), 2)

    def test_no_trim_without_half_duration(self):
        fc, _ = mba.build_filter("sequential", 1920, 1080, "b.txt", "a.txt")
        self.assertNotIn("trim=duration", fc)

    def test_unknown_layout_raises(self):
        with self.assertRaises(SystemExit):
            mba.build_filter("nope", 1920, 1080, "b.txt", "a.txt")

    def test_windows_fontfile_colon_escaped(self):
        fc, _ = mba.build_filter("sequential", 1920, 1080, "b.txt", "a.txt", font="C:/F/x.ttf")
        self.assertIn("fontfile='C\\:/F/x.ttf'", fc)


class PlanBeforeAfter(unittest.TestCase):
    def test_source_halves_and_options(self):
        seq = [
            {"type": "html_mockup", "source": "t.html"},
            {
                "type": "before_after",
                "before": "b.mp4",
                "after": {"source": "a.mp4", "label": "fixed"},
                "before_label": "BUG",
                "layout": "side_by_side",
                "half_duration": 8,
            },
        ]
        ba = plan.resolve_sequence(seq)[1]
        self.assertEqual(ba["type"], "before_after")
        self.assertEqual(ba["layout"], "side_by_side")
        self.assertEqual(ba["half_duration"], 8.0)
        self.assertEqual(ba["before"]["source"], "b.mp4")
        self.assertEqual(ba["before"]["label"], "BUG")
        self.assertEqual(ba["after"]["source"], "a.mp4")
        self.assertEqual(ba["after"]["label"], "fixed")
        self.assertEqual(ba["mp4"], f"videos/{ba['id']}.mp4")

    def test_default_layout_and_labels(self):
        ba = plan.resolve_sequence(
            [
                {"type": "before_after", "before": "b.mp4", "after": "a.mp4"},
                {"type": "html_mockup", "source": "t.html"},
            ]
        )[0]
        self.assertEqual(ba["layout"], "sequential")
        self.assertEqual(ba["before"]["label"], "BEFORE")
        self.assertEqual(ba["after"]["label"], "AFTER")
        self.assertNotIn("half_duration", ba)

    def test_url_half_becomes_capture_spec(self):
        seq = [
            {
                "type": "before_after",
                "before": {"url": "https://staging.example/x", "actions": [{"click": ".b"}], "auth": True},
                "after": "a.mp4",
            },
            {"type": "html_mockup", "source": "t.html"},
        ]
        cap = plan.resolve_sequence(seq)[0]["before"]["capture"]
        self.assertEqual(cap["url"], "https://staging.example/x")
        self.assertTrue(cap["auth"])
        self.assertEqual(cap["actions"], [{"click": ".b"}])
        self.assertTrue(cap["output"].endswith("_before.mp4"))

    def test_missing_half_raises(self):
        with self.assertRaises(SystemExit):
            plan.resolve_sequence(
                [
                    {"type": "before_after", "before": "b.mp4"},
                    {"type": "html_mockup", "source": "t.html"},
                ]
            )


if __name__ == "__main__":
    unittest.main()
