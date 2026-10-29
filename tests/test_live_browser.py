"""Tests for live browser prerequisite reporting."""
import os
import unittest
from unittest.mock import patch

from tests import live_browser


class LiveBrowserTests(unittest.TestCase):
    def _run_dummy(self, required):
        reason = "Chromium failed to launch: missing libnspr4.so"

        class Dummy(unittest.TestCase):
            def test_runs(self):
                pass

        with patch.dict(os.environ, {"DEMO_REQUIRE_LIVE": "1" if required else "0"}):
            with patch.object(live_browser, "_probe_live_browser", return_value=reason):
                live_browser.live_browser_reason.cache_clear()
                decorated = live_browser.requires_live_browser(Dummy)
                result = unittest.TestResult()
                unittest.defaultTestLoader.loadTestsFromTestCase(decorated).run(result)
                live_browser.live_browser_reason.cache_clear()
        return result, reason

    def test_missing_browser_is_skipped(self):
        result, reason = self._run_dummy(False)
        self.assertEqual(len(result.skipped), 1)
        self.assertIn(reason, result.skipped[0][1])
        self.assertEqual(result.errors, [])

    def test_required_browser_failure_is_an_error(self):
        result, reason = self._run_dummy(True)
        self.assertEqual(result.skipped, [])
        self.assertEqual(len(result.errors), 1)
        self.assertIn(reason, result.errors[0][1])

    def test_shared_library_reason_names_library_and_documentation(self):
        reason = live_browser._launch_failure_reason(
            "Error: error while loading shared libraries: libnss3.so: cannot open file")
        self.assertIn("libnss3.so", reason)
        self.assertIn("references/troubleshooting.md", reason)
        self.assertIn("Chromium: error while loading shared libraries", reason)


if __name__ == "__main__":
    unittest.main()
