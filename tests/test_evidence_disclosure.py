import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

try:
    from evidence_disclosure import collect_disclosures
except ImportError:
    collect_disclosures = None


NOW = datetime(2026, 9, 28, 16, 20, tzinfo=timezone(timedelta(hours=8)))


def official_get(url, **kwargs):
    return SimpleNamespace(json=lambda: {"stockList": [{"code": "600519", "orgId": "gssh0600519"}]},
                           raise_for_status=lambda: None)


def official_get_bse(url, **kwargs):
    return SimpleNamespace(json=lambda: {"stockList": [
        {"code": "920982", "orgId": "gfbj0832982"},
        {"code": "832982", "orgId": "gfbj0832982"},
    ]}, raise_for_status=lambda: None)


def official_post(total):
    def post(url, **kwargs):
        return SimpleNamespace(json=lambda: {"totalAnnouncement": total, "announcements": []},
                               raise_for_status=lambda: None)
    return post


def announcement_frame(*, wrong_code=False):
    return pd.DataFrame([
        {"代码": "000001" if wrong_code else "600519", "简称": "贵州茅台",
         "公告标题": "贵州茅台：2025年年度报告", "公告时间": "2026-03-30 16:00:00",
         "公告链接": "http://www.cninfo.com.cn/new/disclosure/detail?announcementId=A1"},
        {"代码": "600519", "简称": "贵州茅台",
         "公告标题": "<em>贵州茅台</em>：2025年年度报告", "公告时间": "2026-03-30 16:00:00",
         "公告链接": "http://www.cninfo.com.cn/new/disclosure/detail?announcementId=A1"},
        {"代码": "600519", "简称": "贵州茅台",
         "公告标题": "贵州茅台：董事会决议公告", "公告时间": "2026-09-20 16:00:00",
         "公告链接": "http://www.cninfo.com.cn/new/disclosure/detail?announcementId=A2"},
    ])


def ak_api(frame):
    return SimpleNamespace(stock_zh_a_disclosure_report_cninfo=lambda **kwargs: frame.copy())


class EvidenceDisclosureTests(unittest.TestCase):
    def test_bse_legacy_disclosure_code_is_retained_when_org_id_matches(self):
        self.assertIsNotNone(collect_disclosures, "evidence_disclosure is missing")
        frame = pd.DataFrame([
            {"代码": "832982", "公告标题": "2024年年度报告", "公告时间": "2025-03-30 16:00:00",
             "公告链接": "http://www.cninfo.com.cn/new/disclosure/detail?announcementId=B1"},
            {"代码": "920982", "公告标题": "董事会决议公告", "公告时间": "2026-09-20 16:00:00",
             "公告链接": "http://www.cninfo.com.cn/new/disclosure/detail?announcementId=B2"},
        ])
        result = collect_disclosures("920982", "bj", NOW, ak_api=ak_api(frame),
                                     http_get=official_get_bse, http_post=official_post(2))
        self.assertEqual(result["source_results"][0]["status"], "ok")
        old = next(x for x in result["announcements"] if x["disclosure_code"] == "832982")
        self.assertEqual(old["code"], "920982")
        self.assertEqual(old["identity_basis"], "same_cninfo_org_id")

    def test_official_links_are_retained_and_duplicates_removed(self):
        self.assertIsNotNone(collect_disclosures, "evidence_disclosure is missing")
        result = collect_disclosures("600519", "sh", NOW, ak_api=ak_api(announcement_frame()),
                                     http_get=official_get, http_post=official_post(3))
        self.assertEqual(len(result["announcements"]), 2)
        annual = next(x for x in result["announcements"] if "年度报告" in x["title"])
        self.assertEqual(annual["published_at"], "2026-03-30T16:00:00+08:00")
        self.assertTrue(annual["source_url"].startswith("https://www.cninfo.com.cn/"))
        self.assertNotIn("<em>", annual["title"])
        self.assertEqual(result["source_results"][0]["status"], "ok")
        self.assertEqual(result["source_results"][0]["query_range"], "2024-09-28..2026-09-28")

    def test_complete_empty_query_is_no_record(self):
        self.assertIsNotNone(collect_disclosures, "evidence_disclosure is missing")
        result = collect_disclosures("600519", "sh", NOW, ak_api=ak_api(pd.DataFrame()),
                                     http_get=official_get, http_post=official_post(0))
        self.assertEqual(result["source_results"][0]["status"], "no_record")
        self.assertEqual(result["announcements"], [])

    def test_truncation_or_other_ticker_is_source_failure(self):
        self.assertIsNotNone(collect_disclosures, "evidence_disclosure is missing")
        truncated = collect_disclosures("600519", "sh", NOW, ak_api=ak_api(announcement_frame().head(1)),
                                        http_get=official_get, http_post=official_post(3))
        wrong = collect_disclosures("600519", "sh", NOW, ak_api=ak_api(announcement_frame(wrong_code=True)),
                                    http_get=official_get, http_post=official_post(3))
        self.assertEqual(truncated["source_results"][0]["status"], "source_failure")
        self.assertNotEqual(truncated["source_results"][0]["status"], "no_record")
        self.assertEqual(wrong["source_results"][0]["status"], "source_failure")
        self.assertEqual(wrong["announcements"], [])


if __name__ == "__main__":
    unittest.main()
