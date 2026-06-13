# tests/test_diorama_plan_build.py
import importlib.util, os, sys, unittest
SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "assets", "scripts")
spec = importlib.util.spec_from_file_location("diorama_plan", os.path.join(SCRIPTS, "diorama_plan.py"))
dp = importlib.util.module_from_spec(spec); spec.loader.exec_module(dp)

SCENE = {"canvas": {"width": 2560, "height": 1440, "backdrop": "color=c=0x121214"},
         "camera": [{"focus": "a", "hold": 2}, {"focus": "b", "hold": 2, "transition": 1}],
         "windows": [{"id": "a", "x": 1, "y": 2, "w": 900, "chrome": True, "title": "worker"},
                     {"id": "b", "x": 3, "y": 4, "w": 900}],
         "mascot": {"keyframes": [{"at": 0, "emotion": "idle", "at_window": "a", "anchor": "top"}]},
         "duration": 12}
CLIPS = {"a": "videos/da.mp4", "b": "footage/b.mp4"}
STYLE = {"bar_bg": "#17171a", "rule": "#2c2c32", "fg": "#f4efe3"}  # raw brand hex; make-diorama _ffcolor's it


class TestBuildPlan(unittest.TestCase):
    def test_carries_chrome_and_title(self):
        plan = dp.build_plan(SCENE, CLIPS, STYLE)
        a, b = plan["windows"]
        self.assertTrue(a["chrome"]); self.assertEqual(a["title"], "worker")
        self.assertEqual(a["clip"], "videos/da.mp4")
        self.assertFalse(b.get("chrome", False))   # b has no chrome
        self.assertEqual(b["clip"], "footage/b.mp4")

    def test_chrome_style_present_only_when_a_window_has_chrome(self):
        self.assertEqual(dp.build_plan(SCENE, CLIPS, STYLE)["chrome_style"], STYLE)
        plain = {**SCENE, "windows": [{"id": "a", "x": 1, "y": 2, "w": 900}]}
        self.assertIsNone(dp.build_plan(plain, {"a": "x.mp4"}, STYLE).get("chrome_style"))

    def test_backdrop_and_duration_pass_through(self):
        plan = dp.build_plan(SCENE, CLIPS, STYLE)
        self.assertEqual(plan["backdrop"], "color=c=0x121214")
        self.assertEqual(plan["duration"], 12)
        self.assertEqual(plan["fps"], 30)

    def test_default_backdrop_when_canvas_has_none(self):
        s = {**SCENE, "canvas": {"width": 2560, "height": 1440}}
        self.assertEqual(dp.build_plan(s, CLIPS, STYLE)["backdrop"], "color=c=0x0a0705")

    def test_mascot_runtime_passed_through_else_none(self):
        # mascot is the resolved runtime dict (keyframes + frames_dir + fps), built
        # by the caller from ./mascot — build_plan just stores it (None when absent)
        self.assertIsNone(dp.build_plan(SCENE, CLIPS, STYLE)["mascot"])
        m = {"keyframes": SCENE["mascot"]["keyframes"], "frames_dir": "mascot", "fps": 12}
        self.assertEqual(dp.build_plan(SCENE, CLIPS, STYLE, mascot=m)["mascot"], m)
