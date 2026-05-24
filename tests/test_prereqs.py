"""Tests for prereqs.needs_vhs — arc-aware prerequisite gate (P1-2).

VHS/Docker is only needed for terminal / multi_agent scenes. A pure
browser_capture + endcards arc must build without VHS.
Run: python -m unittest discover -s tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "assets", "scripts"))
import prereqs  # noqa: E402


class NeedsVhs(unittest.TestCase):
    def test_true_for_terminal_scene(self):
        self.assertTrue(prereqs.needs_vhs(["terminal", "graph", "endcards"]))

    def test_true_for_multi_agent(self):
        self.assertTrue(prereqs.needs_vhs(["multi_agent", "endcards"]))

    def test_false_for_pure_browser_arc(self):
        self.assertFalse(prereqs.needs_vhs(["browser_capture", "html_mockup", "endcards"]))

    def test_false_for_empty(self):
        self.assertFalse(prereqs.needs_vhs([]))


if __name__ == "__main__":
    unittest.main()
