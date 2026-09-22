"""Lightweight consistency checks for the remotion-el docs/scaffold deliverables
(T4): plugin version, gitignore example, and the cost-gate protocol being
documented where the agent (and the user) will actually read it.
Run: python -m unittest discover -s tests
"""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class PluginMetadata(unittest.TestCase):
    def test_plugin_version_is_0_11_0(self):
        data = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(data["version"], "0.11.0")

    def test_marketplace_description_mentions_optional_paid_elevenlabs(self):
        data = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        text = data["plugins"][0]["description"]
        self.assertIn("paid", text.lower())
        self.assertIn("cost-gate", text.lower())


class GitignoreExample(unittest.TestCase):
    def test_covers_all_required_entries(self):
        text = (ROOT / "assets" / "gitignore.example").read_text(encoding="utf-8")
        for entry in (".build/", ".env", ".tts-cache/", ".music-cache/",
                      ".spend-ledger.jsonl", "remotion/node_modules/"):
            self.assertIn(entry, text)


class SkillDocsMentionCostGate(unittest.TestCase):
    def test_skill_md_documents_the_cost_gate_protocol(self):
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Cost-gate protocol", text)
        self.assertIn("--approve-spend", text)
        self.assertIn("APPROVAL CODE", text)
        self.assertIn("never generate", text.lower())

    def test_skill_md_documents_remotion_licence(self):
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("NOT MIT", text)


class RemotionTemplateFiles(unittest.TestCase):
    def test_pinned_versions_present(self):
        pkg = json.loads((ROOT / "assets" / "remotion" / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(pkg["dependencies"]["remotion"], "4.0.527")
        self.assertEqual(pkg["devDependencies"]["@remotion/cli"], "4.0.527")
        self.assertTrue(pkg["dependencies"]["react"].startswith("19."))

    def test_readme_states_the_licence_is_not_mit(self):
        text = (ROOT / "assets" / "remotion" / "README.md").read_text(encoding="utf-8")
        self.assertIn("NOT MIT", text)


if __name__ == "__main__":
    unittest.main()
