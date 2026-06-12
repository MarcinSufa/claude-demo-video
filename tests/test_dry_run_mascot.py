"""Tests for dry-run-plan.mascot_note_for helper."""
import importlib.util
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "assets", "scripts"))

_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "scripts", "dry-run-plan.py")
_spec = importlib.util.spec_from_file_location("dry_run_plan", _PATH)
drp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(drp)


class TestMascotNoteFor(unittest.TestCase):
    def test_enabled_with_emotion(self):
        entry = {"mascot_plan": {"enabled": True, "character": "octopus", "emotion": "celebrate"}}
        self.assertEqual(drp.mascot_note_for(entry), "  mascot: octopus (celebrate)")

    def test_disabled_returns_empty_string(self):
        entry = {"mascot_plan": {"enabled": False, "character": "octopus"}}
        self.assertEqual(drp.mascot_note_for(entry), "")

    def test_no_mascot_plan_returns_empty_string(self):
        self.assertEqual(drp.mascot_note_for({}), "")

    def test_before_after_halves(self):
        entry = {"mascot_plan": {"enabled": True, "character": "octopus", "before": "panic", "after": "celebrate"}}
        self.assertEqual(drp.mascot_note_for(entry), "  mascot: octopus (panic->celebrate)")


if __name__ == "__main__":
    unittest.main()
