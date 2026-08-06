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


if __name__ == "__main__":
    unittest.main()
