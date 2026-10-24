"""Keep runtime script copy lists complete for their sibling imports."""
import os
import re
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPTS = os.path.join(ROOT, "assets", "scripts")


def build_copy_list():
    with open(os.path.join(SCRIPTS, "build.sh"), encoding="utf-8") as f:
        source = f.read()
    match = re.search(r'cp "\$SKILL_SCRIPTS"/\{([^}]*)\} "\$BUILD/"', source)
    if not match:
        raise AssertionError("could not find build.sh runtime script copy list")
    return {name.strip() for name in match.group(1).split(",") if name.strip()}


def sibling_imports(path):
    """Return sibling .mjs/.py imports referenced by one copied script."""
    with open(path, encoding="utf-8") as f:
        source = f.read()
    if path.endswith(".mjs"):
        names = re.findall(r'\bfrom\s+["\']\./([^"\']+\.mjs)["\']', source)
    elif path.endswith(".py"):
        names = re.findall(r"^\s*(?:import\s+([A-Za-z_]\w*)|from\s+([A-Za-z_]\w*)\s+import\s)", source, re.M)
        names = [a or b for a, b in names]
        names = [name + ".py" for name in names
                 if os.path.isfile(os.path.join(SCRIPTS, name + ".py"))]
    else:
        return []
    return [name for name in names if os.path.isfile(os.path.join(SCRIPTS, name))]


class TestBuildCopyList(unittest.TestCase):
    def test_build_list_includes_sibling_imports(self):
        copied = build_copy_list()
        missing = []
        for importer in sorted(copied):
            full_path = os.path.join(SCRIPTS, importer)
            if not os.path.isfile(full_path):
                continue
            for imported in sibling_imports(full_path):
                if imported not in copied:
                    missing.append((imported, importer))
        self.assertEqual(
            missing, [],
            "build copy list is missing sibling imports: " + ", ".join(
                f"{name} (imported by {importer})" for name, importer in missing))

    def test_quick_capture_list_includes_record_browser_imports(self):
        with open(os.path.join(ROOT, "SKILL.md"), encoding="utf-8") as f:
            source = f.read()
        match = re.search(
            r'cp "\$\{CLAUDE_SKILL_DIR\}"/assets/scripts/\{([^}]*)\}\.mjs\s+\.',
            source)
        self.assertIsNotNone(match, "could not find SKILL.md quick-capture script copy list")
        copied = {name.strip() + ".mjs" for name in match.group(1).split(",")}
        missing = [name for name in sibling_imports(os.path.join(SCRIPTS, "record-browser.mjs"))
                   if name not in copied]
        self.assertEqual(missing, [],
                         "quick-capture copy list is missing record-browser imports: " +
                         ", ".join(missing))


if __name__ == "__main__":
    unittest.main()
