import tempfile
import unittest
from pathlib import Path

from test_report_publication import report_fixture
from validate_report import validate_report


class ValidateReportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.content = report_fixture(self.root)
        self.path = self.root / "research/2026-09-28-600519-贵州茅台.md"

    def test_preflight_reads_text_without_creating_report(self):
        result = validate_report(self.path, self.root, content=self.content)
        self.assertEqual(result["errors"], [])
        self.assertFalse(self.path.exists())

    def test_merged_metadata_is_equivalent_to_separate_lines(self):
        text = self.content.replace("\n> 股票代码：600519\n> 股票简称：贵州茅台",
                                    "；股票代码：600519；股票简称：贵州茅台")
        result = validate_report(self.path, self.root, content=text)
        self.assertEqual(result["errors"], [])

    def test_inequality_bands_pass_rated_contract(self):
        text = self.content.replace("数据不足，暂不评级。缺少可采用估值，未给出买入区间和持有区间。", """评级：持有
评级适用期限：2026-09-28至2027-09-28
买入参考区间：900≤P≤1000元/股
持有区间：1000＜P＜1400元/股
估值计算公式：利润×倍数／股本；经营假设失效触发重估。
[原始公告](https://static.cninfo.com.cn/finalpage/example.PDF)
""")
        import json
        evidence = self.root / "research/evidence/2026-09-28-600519.json"
        data = json.loads(evidence.read_text(encoding="utf-8"))
        data["observations"][0]["market_phase"] = "postmarket"
        evidence.write_text(json.dumps(data), encoding="utf-8")
        result = validate_report(self.path, self.root, content=text)
        self.assertEqual(result["errors"], [])

    def test_unrated_report_rejects_executable_inequality_bands(self):
        result = validate_report(self.path, self.root,
                                 content=self.content + "\n买入区间：900≤P≤1000元/股\n")
        self.assertIn("Unrated report must leave executable price bands empty", result["errors"])

    def test_numeric_band_is_still_required_for_rated_report(self):
        result = validate_report(self.path, self.root,
                                 content=self.content.replace("数据不足，暂不评级。", "评级：持有。"))
        self.assertIn("Positive/hold rating needs numeric buy and hold bands", result["errors"])


if __name__ == "__main__":
    unittest.main()
