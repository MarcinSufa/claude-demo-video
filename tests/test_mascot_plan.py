"""Tests for plan-scenes.mascot_stub — stage-1 mascot_plan resolution."""
import importlib.util
import os
import unittest

_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "scripts", "plan-scenes.py")
_spec = importlib.util.spec_from_file_location("plan_scenes", _PATH)
ps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ps)

CFG = {"character": "octopus", "enabled": True, "position": "bottom-right", "scale": 1.0}


class TestMascotStub(unittest.TestCase):
    def test_disabled_globally(self):
        stub = ps.mascot_stub({"enabled": False}, {"type": "terminal"}, scene_override=None)
        self.assertFalse(stub["enabled"])

    def test_default_emotion_by_type(self):
        self.assertEqual(ps.mascot_stub(CFG, {"type": "terminal"}, None)["emotion"], "type")
        self.assertEqual(ps.mascot_stub(CFG, {"type": "graph"}, None)["emotion"], "idle")
        self.assertEqual(ps.mascot_stub(CFG, {"type": "multi_agent"}, None)["emotion"], "type")
        self.assertEqual(ps.mascot_stub(CFG, {"type": "browser_capture"}, None)["emotion"], "idle")

    def test_endcards_disabled_by_default(self):
        self.assertFalse(ps.mascot_stub(CFG, {"type": "endcards"}, None)["enabled"])

    def test_endcards_can_be_forced_on(self):
        stub = ps.mascot_stub(CFG, {"type": "endcards"}, {"enabled": True})
        self.assertTrue(stub["enabled"])

    def test_scene_override_emotion_and_position(self):
        stub = ps.mascot_stub(CFG, {"type": "browser_capture"},
                              {"emotion": "celebrate", "position": "bottom-left"})
        self.assertEqual(stub["emotion"], "celebrate")
        self.assertEqual(stub["position"], "bottom-left")

    def test_before_after_halves(self):
        stub = ps.mascot_stub(CFG, {"type": "before_after", "layout": "sequential"}, None)
        self.assertEqual(stub["before"], "panic")
        self.assertEqual(stub["after"], "celebrate")

    def test_before_after_side_by_side_single_emotion(self):
        stub = ps.mascot_stub(CFG, {"type": "before_after", "layout": "side_by_side"}, None)
        self.assertEqual(stub["emotion"], "point")
        self.assertNotIn("before", stub)

    def test_scene_override_disable(self):
        stub = ps.mascot_stub(CFG, {"type": "terminal"}, {"enabled": False})
        self.assertFalse(stub["enabled"])

    def test_no_mascot_config_means_disabled(self):
        stub = ps.mascot_stub({}, {"type": "terminal"}, None)
        self.assertFalse(stub["enabled"])


class TestScreenRecordingSafety(unittest.TestCase):
    def test_mascot_enabled_retargets_mp4_away_from_source(self):
        # entry as produced by custom_arc for screen_recording
        entry = {"id": "c1", "type": "screen_recording",
                 "source": "footage/raw.mp4", "mp4": "footage/raw.mp4",
                 "mascot_plan": {"enabled": True}}
        ps.retarget_screen_recording(entry)
        self.assertNotEqual(entry["mp4"], entry["source"])
        self.assertEqual(entry["source"], "footage/raw.mp4")

    def test_mascot_disabled_keeps_source_path(self):
        entry = {"id": "c1", "type": "screen_recording",
                 "source": "footage/raw.mp4", "mp4": "footage/raw.mp4",
                 "mascot_plan": {"enabled": False}}
        ps.retarget_screen_recording(entry)
        self.assertEqual(entry["mp4"], "footage/raw.mp4")


if __name__ == "__main__":
    unittest.main()
