"""dry-run-plan: built-in endcards have a known 15 s length (record-endcards.mjs),
so a plan whose other scenes are pinned gets a verdict instead of "indeterminate"."""
import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "assets", "scripts"))

_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "scripts", "dry-run-plan.py")
_spec = importlib.util.spec_from_file_location("dry_run_plan_endcards", _PATH)
drp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(drp)


class EndcardsDefault(unittest.TestCase):
    def test_pinned_duration_wins(self):
        self.assertEqual(drp.scene_duration({"type": "endcards", "duration": 8}), (8.0, False))

    def test_endcards_without_duration_uses_recorder_length(self):
        self.assertEqual(drp.scene_duration({"type": "endcards"}), (15.0, True))

    def test_other_unpinned_scene_stays_unknown(self):
        self.assertEqual(drp.scene_duration({"type": "terminal"}), (None, False))

    def test_plan_with_endcards_gets_a_verdict(self):
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with open("config.json", "w") as f:
                    json.dump({"voiceover": [{"text": "one two three four five"}],
                               "subs": {"speedup": 1.0, "crossfade": 0.6}}, f)
                with open("scene-plan.json", "w") as f:
                    json.dump({"scenes": [
                        {"id": "c1", "type": "html_mockup", "duration": 4},
                        {"id": "s2", "name": "endcards", "type": "endcards"}]}, f)
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    drp.CONFIG, drp.PLAN = "config.json", "scene-plan.json"
                    drp.main()
            finally:
                os.chdir(cwd)
        text = out.getvalue()
        self.assertNotIn("indeterminate", text)
        self.assertIn("Predicted video length", text)
        self.assertIn("recorder default", text)


if __name__ == "__main__":
    unittest.main()
