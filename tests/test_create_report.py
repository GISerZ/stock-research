import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from create_report import create_report  # noqa: E402


class CreateReportTests(unittest.TestCase):
    def test_same_day_research_preserves_prior_report(self):
        with tempfile.TemporaryDirectory() as directory:
            first = create_report("600519", "贵州茅台", "2026-09-28", directory)
            first.write_text("第一份完整报告", encoding="utf-8")

            second = create_report("600519", "贵州茅台", "2026-09-28", directory)

            self.assertEqual(first.name, "2026-09-28-600519-贵州茅台.md")
            self.assertEqual(second.name, "2026-09-28-600519-贵州茅台-v2.md")
            self.assertEqual(first.read_text(encoding="utf-8"), "第一份完整报告")
            self.assertTrue(second.is_file())

    def test_cli_saves_finished_content_in_workspace_research_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            draft = Path(directory) / "draft.md"
            draft.write_text("# 深研报告\n\n已核验数据与来源。\n", encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(SKILL_DIR / "scripts" / "create_report.py"),
                    "--code", "600519",
                    "--name", "贵州茅台",
                    "--date", "2026-09-28",
                    "--output-dir", directory,
                    "--content-file", str(draft),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            report = Path(directory) / "research" / "2026-09-28-600519-贵州茅台.md"
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(Path(result.stdout.strip()), report)
            self.assertEqual(report.read_text(encoding="utf-8"), draft.read_text(encoding="utf-8"))

    def test_empty_finished_report_is_not_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "cannot be empty"):
                create_report("600519", "贵州茅台", "2026-09-28", directory, "  \n")
            self.assertFalse((Path(directory) / "research" / "2026-09-28-600519-贵州茅台.md").exists())


if __name__ == "__main__":
    unittest.main()
