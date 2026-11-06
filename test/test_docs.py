"""Documentation checks: pointers resolve, criteria exist, stale commands are gone."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / ".dsh" / "skills" / "chess-diagram-to-fen"


class SkillFileTests(unittest.TestCase):
    def test_required_files_exist(self):
        for name in (
            "SKILL.md", "requirements.txt", "THIRD_PARTY_NOTICES.md",
            "LICENSES/2d-chess-ocr-MIT.txt",
            "references/ocr.md", "references/manual.md",
            "references/recognition.md", "references/verification.md",
            "scripts/boardtool.py", "scripts/download_model.py",
            "scripts/selftest.py", "scripts/chessdiagram/pipeline.py",
        ):
            with self.subTest(name=name):
                self.assertTrue((SKILL / name).is_file(), name)

    def test_frontmatter(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        front = text.split("---", 2)[1]
        self.assertIn("name: chess-diagram-to-fen", front)
        self.assertIn("description:", front)
        self.assertIn("license:", front)
        description = next(line for line in front.splitlines()
                           if line.startswith("description:"))
        self.assertLess(len(description), 240,
                        "description is an always-loaded pointer; keep it tight")
        self.assertIn("FEN", description)
        self.assertIn("diagram", description)
        value = description.split(":", 1)[1].strip()
        if not value.startswith(("'", '"')):
            self.assertNotIn(": ", value,
                             "unquoted YAML description with ': ' silently breaks skill loading")

    def test_completion_criteria(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertGreaterEqual(text.count("**Done when**"), 6,
                                "every step needs a checkable completion criterion")

    def test_reference_pointers_resolve(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        for rel in sorted(set(re.findall(r"references/[a-z-]+\.md", text))):
            with self.subTest(ref=rel):
                self.assertTrue((SKILL / rel).is_file(), rel)

    def test_no_stale_prepare_command(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("boardtool.py prepare", text)
        self.assertNotIn("prepare --bbox", text)


class RepoDocTests(unittest.TestCase):
    def test_agents_pointer(self):
        text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("INSTALL.md", text)
        self.assertIn("selftest.py", text)
        self.assertIn("download_model.py", text)
        self.assertIn("THIRD_PARTY_NOTICES.md", text)

    def test_requirements(self):
        lines = (SKILL / "requirements.txt").read_text(encoding="utf-8").splitlines()
        active = [ln.strip() for ln in lines
                  if ln.strip() and not ln.lstrip().startswith("#")]
        self.assertTrue(any(ln.lower().startswith("onnxruntime") for ln in active))
        self.assertFalse(any(ln.lower().startswith("python-chess") for ln in active),
                         "python-chess is optional GPL-3.0, keep it out of the hard requirements")

    def test_notices(self):
        text = (SKILL / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        for needle in ("2d-chess-ocr", "Andreas Spanopoulos", "MIT",
                       "AGPL-3.0", "Ultralytics"):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)

    def test_readme_points_at_model(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("2d-chess-ocr", text)
        self.assertIn("download_model.py", text)

    def test_test_folder_present(self):
        self.assertTrue((ROOT / "test" / "run_tests.py").is_file())


if __name__ == "__main__":
    unittest.main()
