import json
import subprocess
import sys
import tempfile
import unittest
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))
from create_report import create_report
from test_evidence_core import packet


def report_fixture(directory):
    evidence = Path(directory) / "research/evidence/2026-09-28-600519.json"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json.dumps(packet(), ensure_ascii=False), encoding="utf-8")
    return """# 贵州茅台（600519）研究报告

> 研究日期：2026-09-28
> 股票代码：600519
> 股票简称：贵州茅台
> 研究资料截至时间：2026-09-28 16:30+08:00
> 行情时间与交易状态：1243.88元/股，2026-09-28 16:14:51，盘后
> 证据包路径与采集时间：[核心证据](evidence/2026-09-28-600519.json)，16:20
> 情绪快照路径与采集时间：未采集，缺失
> 最近完整A股交易日：2026-09-28

## 1. 核心结论

数据不足，暂不评级。缺少可采用估值，未给出买入区间和持有区间。

## 筹码峰与成本分布

筹码峰数据不足，需恢复可核分布。
"""


class ReportPublicationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.content = report_fixture(self.root)

    def save(self, content=None, **kwargs):
        return create_report("600519", "贵州茅台", "2026-09-28", self.root,
                             self.content if content is None else content, **kwargs)

    def published(self):
        return list((self.root / "research").glob("*.md"))

    def test_default_edits_one_draft_and_leaves_no_formal_versions(self):
        first = self.save()
        second = self.save(self.content + "\n修复说明。\n")
        self.assertEqual(first, second)
        self.assertEqual(first.parent, self.root / "research/.drafts")
        self.assertIn("修复说明", second.read_text(encoding="utf-8"))
        self.assertEqual(self.published(), [])

    def test_template_cannot_be_published(self):
        with self.assertRaises(ValueError):
            create_report("600519", "贵州茅台", "2026-09-28", self.root, publish=True)
        self.assertEqual(self.published(), [])

    def test_internal_repairs_publish_once_after_preflight(self):
        for broken in ["# 草稿", self.content + "\n[附件](evidence/missing.md)\n"]:
            with self.assertRaises(ValueError):
                self.save(broken, publish=True)
            self.assertEqual(self.published(), [])
            self.assertEqual(len(list((self.root / "research/.drafts").glob("*.md"))), 1)
        report = self.save(publish=True)
        self.assertEqual(report.name, "2026-09-28-600519-贵州茅台.md")
        self.assertIn("发布状态：已发布", report.read_text(encoding="utf-8"))
        self.assertEqual(len(self.published()), 1)

    def test_identical_publish_retry_reuses_existing_report(self):
        first = self.save(publish=True)
        original = first.read_bytes()
        self.assertEqual(self.save(publish=True), first)
        self.assertEqual(len(self.published()), 1)
        self.assertEqual(first.read_bytes(), original)

    def test_changed_publication_requires_reason_and_preserves_predecessor(self):
        first = self.save(publish=True)
        original = first.read_bytes()
        changed = self.content + "\n更正此前说明，决定不变。\n"
        with self.assertRaisesRegex(ValueError, "change-reason"):
            self.save(changed, publish=True)
        second = self.save(changed, publish=True, change_reason="发布后更正：说明文字有误")
        self.assertEqual(second.name, "2026-09-28-600519-贵州茅台-v2.md")
        self.assertIn(first.name, second.read_text(encoding="utf-8"))
        self.assertIn("发布后更正", second.read_text(encoding="utf-8"))
        self.assertEqual(first.read_bytes(), original)
        self.assertEqual(self.save(changed, publish=True), second)

    def test_version_follows_numeric_maximum_without_filling_gap(self):
        first = self.save(publish=True)
        first.with_name(first.stem + "-v9.md").write_bytes(first.read_bytes())
        result = self.save(self.content + "\n新证据。\n", publish=True, change_reason="真实更新")
        self.assertTrue(result.name.endswith("-v10.md"))

    def test_preflight_resolves_final_relative_links_and_own_link(self):
        result = self.save(self.content + "\n[本报告](2026-09-28-600519-贵州茅台.md)\n", publish=True)
        self.assertTrue(result.is_file())

    def test_cross_date_update_records_exact_predecessor(self):
        first = self.save(publish=True)
        changed = self.content.replace("研究日期：2026-09-28", "研究日期：2026-09-29")
        with self.assertRaisesRegex(ValueError, "change-reason"):
            create_report("600519", "贵州茅台", "2026-09-29", self.root, changed,
                          publish=True, supersedes=first)
        result = create_report("600519", "贵州茅台", "2026-09-29", self.root, changed,
                               publish=True, supersedes=first, change_reason="核验新的经营资料")
        self.assertIn(first.name, result.read_text(encoding="utf-8"))

    def test_cross_date_update_rejects_superseded_predecessor(self):
        first = self.save(publish=True)
        self.save(self.content + "\n已发布更正。\n", publish=True, change_reason="发布后更正")
        changed = self.content.replace("研究日期：2026-09-28", "研究日期：2026-09-29")
        with self.assertRaisesRegex(ValueError, "latest"):
            create_report("600519", "贵州茅台", "2026-09-29", self.root, changed,
                          publish=True, supersedes=first, change_reason="新的经营资料")

    def test_legacy_supplement_reserves_number_but_is_not_predecessor(self):
        first = self.save(publish=True)
        note = first.with_name(first.stem + "-v5.md")
        note.write_text("# 贵州茅台补充\n> 补充日期：2026-09-28\n本补充继承完整报告。\n", encoding="utf-8")
        result = self.save(self.content + "\n经营信息更新。\n", publish=True,
                           supersedes=first, change_reason="核验新材料")
        self.assertTrue(result.name.endswith("-v6.md"))
        self.assertIn(f"]({first.name})", result.read_text(encoding="utf-8"))

    def test_legacy_draft_does_not_become_predecessor(self):
        first = self.save(publish=True)
        draft = first.with_name(first.stem + "-v3.md")
        draft.write_text("# 贵州茅台研究报告\n> 报告验收状态：草稿\n## 核心结论\n待核对\n", encoding="utf-8")
        result = self.save(self.content + "\n经营信息更新。\n", publish=True,
                           supersedes=first, change_reason="核验新材料")
        self.assertTrue(result.name.endswith("-v4.md"))

    def test_invalid_predecessor_is_rejected(self):
        with self.assertRaises(ValueError):
            self.save(publish=True, supersedes=self.root / "missing.md", change_reason="更新")
        self.assertEqual(self.published(), [])

    def test_later_day_publication_requires_explicit_predecessor(self):
        self.save(publish=True)
        changed = self.content.replace("研究日期：2026-09-28", "研究日期：2026-09-29")
        with self.assertRaisesRegex(ValueError, "supersedes"):
            create_report("600519", "贵州茅台", "2026-09-29", self.root, changed,
                          publish=True, change_reason="核验新事实")
        self.assertEqual(len(self.published()), 1)

    def test_concurrent_different_publisher_is_not_overwritten_or_given_extra_version(self):
        other = self.content + "\n另一个发布者的完整文件。\n"

        def other_publishes(staged, destination):
            Path(destination).write_text(other, encoding="utf-8")
            raise FileExistsError("publisher won")

        with patch("create_report.os.link", side_effect=other_publishes):
            with self.assertRaises(FileExistsError):
                self.save(publish=True)
        self.assertEqual(len(self.published()), 1)
        self.assertEqual(self.published()[0].read_text(encoding="utf-8"), other)

    def test_concurrent_names_cannot_publish_two_initial_reports_for_one_ticker(self):
        import validate_report as validator
        original = validator.validate_report
        entered = threading.Event()
        release = threading.Event()

        def hold_first(report_path, workspace, **kwargs):
            if report_path.name == "2026-09-28-600519.md":
                entered.set()
                if not release.wait(5):
                    raise RuntimeError("test timed out")
            return original(report_path, workspace, **kwargs)

        def publish(name):
            try:
                return create_report("600519", name, "2026-09-28", self.root,
                                     self.content, publish=True)
            except OSError as exc:
                return exc

        with patch("validate_report.validate_report", side_effect=hold_first), ThreadPoolExecutor(2) as pool:
            first = pool.submit(publish, None)
            try:
                self.assertTrue(entered.wait(5))
                second_result = pool.submit(publish, "贵州茅台").result(timeout=5)
            finally:
                release.set()
            first_result = first.result(timeout=5)
        self.assertTrue(isinstance(first_result, Path))
        self.assertIsInstance(second_result, FileExistsError)
        self.assertEqual(len(self.published()), 1)

    def test_validate_only_keeps_draft_without_formal_report(self):
        result = self.save(validate=True)
        self.assertEqual(result.parent.name, ".drafts")
        self.assertEqual(self.published(), [])

    def test_atomic_publication_failure_leaves_no_formal_file(self):
        with patch("create_report.os.link", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                self.save(publish=True)
        self.assertEqual(self.published(), [])
        self.assertTrue((self.root / "research/.drafts/2026-09-28-600519-贵州茅台.md").is_file())

    def test_cli_explicit_publish_and_invalid_preflight_exit(self):
        draft = self.root / "input.md"
        draft.write_text("# 草稿", encoding="utf-8")
        command = [sys.executable, "-X", "utf8", str(SKILL_DIR / "scripts/create_report.py"),
                   "--code", "600519", "--name", "贵州茅台", "--date", "2026-09-28",
                   "--output-dir", str(self.root), "--content-file", str(draft), "--publish"]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(self.published(), [])
        draft.write_text(self.content, encoding="utf-8")
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.published()), 1)


if __name__ == "__main__":
    unittest.main()
