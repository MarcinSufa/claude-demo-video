"""Wiring coverage for check-timing.py's composite_speedup= argument.

grok-review2.md residual 3: if someone drops `composite_speedup=speedup` from
the `timing_util.scene_spans(...)` call in `_check_scene_alignment`, no
existing test fails -- the pure timing_util tests exercise scene_spans
directly (always passing composite_speedup themselves) and never go through
check-timing.py's own call site. This test drives _check_scene_alignment
end-to-end at a real project speedup != 1.0, so a dropped kwarg silently
misplaces the composite cut and this test catches it.
"""
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "assets", "scripts"))

_SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "assets", "scripts")


def _load_check_timing():
    # timing_util must resolve as a real top-level import inside check-timing.py
    spec = importlib.util.spec_from_file_location(
        "timing_util", os.path.join(_SCRIPTS, "timing_util.py"))
    timing_util = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(timing_util)
    sys.modules["timing_util"] = timing_util

    spec = importlib.util.spec_from_file_location(
        "check_timing_wiring", os.path.join(_SCRIPTS, "check-timing.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CompositeSpeedupWiring(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def test_composite_cut_uses_real_project_speedup_not_1_0(self):
        # Real project speedup 1.5, crossfade 0.6, 3 raw scenes [8, 28, 12],
        # a before_after (sequential) middle scene with half_duration=14.0
        # (always authored in PRE-speedup seconds). Probed .normalized/*.mp4
        # durations are ALREADY post-speedup (raw/speedup), matching what
        # assemble.sh and check-timing.py's own probing produce.
        speedup = 1.5
        crossfade = 0.6
        raw = [8.0, 28.0, 12.0]
        half_duration = 14.0
        probed = [r / speedup for r in raw]

        start_1 = raw[0] / speedup - crossfade  # 4.7333...
        correct_cut = start_1 + half_duration / speedup  # 4.7333 + 9.3333 = 14.0667
        wrong_cut_if_kwarg_dropped = start_1 + half_duration  # 18.7333 (unconverted)
        self.assertNotAlmostEqual(correct_cut, wrong_cut_if_kwarg_dropped, places=1)

        scenes = [{"type": "html_mockup"},
                  {"type": "before_after", "layout": "sequential",
                   "half_duration": half_duration},
                  {"type": "endcards"}]
        with open("scene-plan.json", "w", encoding="utf-8") as f:
            json.dump({"scenes": scenes}, f)
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump({"subs": {"speedup": speedup, "crossfade": crossfade}}, f)
        os.makedirs(".normalized", exist_ok=True)
        for i in range(1, len(scenes) + 1):
            open(f".normalized/s{i}.mp4", "wb").close()

        module = _load_check_timing()
        durations = iter(probed)
        module._probe_duration = lambda path: next(durations)

        # A line starting well before the correct cut and ending well after
        # it: correctly wired, this overruns the "before" window and gets
        # flagged. If composite_speedup were dropped (cut placed at 18.73
        # instead of 14.07), this same line would sit entirely inside the
        # (wrongly enlarged) "before" window and NOT be flagged.
        words = {"lines": [{"line_start": 10.0, "line_end": 17.0, "text": "x"}]}
        buf = io.StringIO()
        with redirect_stdout(buf):
            module._check_scene_alignment(words)
        output = buf.getvalue()
        self.assertIn("WARNING scene alignment", output,
                       f"expected a scene-alignment violation using the real "
                       f"project speedup ({speedup}) for the composite cut; "
                       f"got:\n{output}")
        # finding 5: a bare "WARNING" substring match would also pass if the
        # kwarg WERE dropped -- check_scene_alignment still fires a violation
        # against the wrong (unconverted) cut, just at the wrong overrun.
        # Pin the actual numbers so this test fails if composite_speedup
        # stops being wired through, not just if the warning path breaks
        # entirely. correct_cut=14.07 -> window_end rounds to 14.1, overrun
        # = 17.0 - 14.0667 = 2.93 -> 2.9s. wrong_cut (18.73) would instead
        # report window_end 18.7 and overrun -1.7 (i.e. no violation at all,
        # since the line would sit inside the wrongly enlarged window).
        expected_overrun = 17.0 - correct_cut
        self.assertIn(f"{correct_cut:.1f}s)", output)
        self.assertIn(f"by {expected_overrun:.1f}s", output)
        self.assertNotIn(f"{wrong_cut_if_kwarg_dropped:.1f}s)", output)


class StaleWordsHardFail(unittest.TestCase):
    """finding 5: check-timing.py's stale-mtime guard (main(), gap >
    STALE_WORDS_GAP_SECONDS) had no unit coverage -- only the two green
    paths (missing files) and the scene-alignment warn-only path were
    tested. This pins the hard-fail path itself: a vo-words.json far older
    than the video it's being checked against must FAIL the build (exit 1),
    not warn-and-continue like the scene-alignment check does.
    """

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def test_words_file_far_older_than_video_fails_the_build(self):
        words = {"leading_offset": 0.0, "lines": [
            {"line_start": 0.0, "line_end": 5.0, "text": "hello world"}]}
        with open("vo-words.json", "w", encoding="utf-8") as f:
            json.dump(words, f)
        open("video.mp4", "wb").close()

        now = 2_000_000_000  # arbitrary fixed epoch, far past STALE gap math
        os.utime("vo-words.json", (now, now))
        os.utime("video.mp4", (now + 7200, now + 7200))  # 2h newer -> stale

        module = _load_check_timing()
        module._probe_duration = lambda path: (_ for _ in ()).throw(
            AssertionError("must not probe video duration once already stale"))
        rc = module.main(["check-timing.py", "video.mp4", "vo-words.json"])
        self.assertEqual(rc, 1)

    def test_words_file_close_in_age_to_video_does_not_trigger_stale_fail(self):
        words = {"leading_offset": 0.0, "lines": [
            {"line_start": 0.0, "line_end": 5.0, "text": "hello world"}]}
        with open("vo-words.json", "w", encoding="utf-8") as f:
            json.dump(words, f)
        open("video.mp4", "wb").close()

        now = 2_000_000_000
        os.utime("vo-words.json", (now, now))
        os.utime("video.mp4", (now + 60, now + 60))  # normal pipeline ordering

        module = _load_check_timing()
        module._probe_duration = lambda path: 5.0  # fits, no scene-plan/config -> no alignment check
        rc = module.main(["check-timing.py", "video.mp4", "vo-words.json"])
        self.assertEqual(rc, 0)


class SceneAlignmentObservability(unittest.TestCase):
    """Two silent paths in _check_scene_alignment made a passing check
    indistinguishable from a check that never ran:

    1. A clean project (no violations) printed nothing on success -- the
       whole point of this feature is to catch a misalignment that once
       slipped through silently, so shipping the confirmation itself
       invisible defeats the purpose.
    2. Missing scene-plan.json/config.json returned with no output at all,
       unlike the sibling missing-.normalized-clip skip a few lines below
       which already prints its reason.
    """

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def _write_clean_3scene_project(self):
        scenes = [{"type": "html_mockup"}, {"type": "html_mockup"},
                  {"type": "endcards"}]
        with open("scene-plan.json", "w", encoding="utf-8") as f:
            json.dump({"scenes": scenes}, f)
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump({"subs": {"speedup": 1.0, "crossfade": 0.6}}, f)
        os.makedirs(".normalized", exist_ok=True)
        for i in range(1, len(scenes) + 1):
            open(f".normalized/s{i}.mp4", "wb").close()
        return scenes

    def test_clean_project_prints_confirmation_with_real_counts(self):
        self._write_clean_3scene_project()
        module = _load_check_timing()
        durations = iter([8.0, 8.0, 8.0])
        module._probe_duration = lambda path: next(durations)

        # Two lines, both comfortably inside their scene's window -- no
        # overruns expected.
        words = {"lines": [
            {"line_start": 1.0, "line_end": 3.0, "text": "a"},
            {"line_start": 10.0, "line_end": 12.0, "text": "b"},
        ]}
        buf = io.StringIO()
        with redirect_stdout(buf):
            module._check_scene_alignment(words)
        output = buf.getvalue()

        self.assertNotIn("WARNING", output)
        # 3 scenes, no composite splits -> 3 ownership windows.
        self.assertIn("2 voiceover line", output)
        self.assertIn("3 scene boundar", output)
        self.assertIn("no overruns", output)

    def test_missing_scene_plan_prints_skip_reason_naming_the_file(self):
        # config.json present, scene-plan.json missing.
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump({"subs": {"speedup": 1.0, "crossfade": 0.6}}, f)
        module = _load_check_timing()

        words = {"lines": []}
        buf = io.StringIO()
        with redirect_stdout(buf):
            module._check_scene_alignment(words)
        output = buf.getvalue()

        self.assertIn("timing: scene alignment check skipped", output)
        self.assertIn("scene-plan.json", output)

    def test_missing_config_prints_skip_reason_naming_the_file(self):
        # scene-plan.json present, config.json missing.
        with open("scene-plan.json", "w", encoding="utf-8") as f:
            json.dump({"scenes": []}, f)
        module = _load_check_timing()

        words = {"lines": []}
        buf = io.StringIO()
        with redirect_stdout(buf):
            module._check_scene_alignment(words)
        output = buf.getvalue()

        self.assertIn("timing: scene alignment check skipped", output)
        self.assertIn("config.json", output)


if __name__ == "__main__":
    unittest.main()
