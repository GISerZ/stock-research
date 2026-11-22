import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

try:
    from evidence_financial import collect_financial
except ImportError:
    collect_financial = None


NOW = datetime(2026, 9, 28, 16, 20, tzinfo=timezone(timedelta(hours=8)))


def financial_api(*, missing_cash=False, empty_income=False, income_error=False):
    dates = ["20260630", "20260331", "20251231", "20250930", "20250630",
             "20250331", "20241231", "20240930", "20240630"]
    income = pd.DataFrame([{
        "报告日": day, "类型": "合并本期", "营业总收入": 100_000_000.0 + i,
        "归属于母公司所有者的净利润": 20_000_000.0 + i,
        "更新日期": "2026-08-29 T18:05:05",
    } for i, day in enumerate(dates)])
    balance = pd.DataFrame([{
        "报告日": "20260630", "类型": "合并期末", "资产总计": 500_000_000.0,
        "负债合计": 200_000_000.0, "货币资金": 50_000_000.0,
    }])
    cash = pd.DataFrame([{
        "报告日": "20260630", "类型": "合并本期",
        "经营活动产生的现金流量净额": None if missing_cash else 30_000_000.0,
    }])
    per_share = pd.DataFrame([{
        "REPORT_DATE": "2026-06-30", "SECURITY_CODE": "600519",
        "EPSJB": 12.5, "BPS": 110.0,
    }])

    def report(*, stock, symbol):
        if symbol == "利润表":
            if income_error:
                raise RuntimeError("Sina unavailable")
            return pd.DataFrame() if empty_income else income.copy()
        if symbol == "资产负债表":
            return balance.copy()
        return cash.copy()

    return SimpleNamespace(stock_financial_report_sina=report,
                           stock_financial_analysis_indicator_em=lambda **kwargs: per_share.copy())


class EvidenceFinancialTests(unittest.TestCase):
    def test_revenue_prefers_reported_operating_revenue_over_total_income(self):
        self.assertIsNotNone(collect_financial, "evidence_financial is missing")
        api = financial_api()
        original = api.stock_financial_report_sina

        def report(*, stock, symbol):
            if symbol == "利润表":
                return pd.DataFrame([{"报告日": "20260630", "类型": "合并期末",
                                      "营业总收入": 92_278.0, "营业收入": 90_703.0,
                                      "归属于母公司所有者的净利润": 44_516.0}])
            return original(stock=stock, symbol=symbol)

        api.stock_financial_report_sina = report
        result = collect_financial("600519", "sh", NOW, ak_api=api)
        revenue = next(x for x in result["observations"] if x["field"] == "revenue")
        self.assertEqual(revenue["value"], 90_703.0)
        self.assertIn("营业收入", revenue["basis"])

    def test_bank_income_uses_reported_parent_profit_alias(self):
        self.assertIsNotNone(collect_financial, "evidence_financial is missing")
        api = financial_api()
        original = api.stock_financial_report_sina

        def report(*, stock, symbol):
            if symbol == "利润表":
                return pd.DataFrame([{"报告日": "20260630", "类型": "合并期末",
                                      "营业收入": 10_000.0, "归属于母公司的净利润": 2_000.0}])
            return original(stock=stock, symbol=symbol)

        api.stock_financial_report_sina = report
        result = collect_financial("000001", "sz", NOW, ak_api=api)
        profits = [x for x in result["observations"] if x["field"] == "attributable_profit"]
        self.assertEqual(len(profits), 1)
        self.assertEqual(profits[0]["value"], 2_000.0)
        self.assertIn("归属于母公司的净利润", profits[0]["basis"])

    def test_financial_periods_are_limited_and_cumulative_values_keep_units(self):
        self.assertIsNotNone(collect_financial, "evidence_financial is missing")
        result = collect_financial("600519", "sh", NOW, ak_api=financial_api())
        revenue = [x for x in result["observations"] if x["field"] == "revenue"]
        self.assertEqual(len(revenue), 8)
        self.assertEqual(revenue[0]["period_or_market_time"], "2026-06-30")
        self.assertEqual(revenue[0]["value"], 100_000_000.0)
        self.assertEqual((revenue[0]["unit"], revenue[0]["basis"]), ("CNY", "consolidated cumulative; 营业总收入"))
        self.assertEqual(revenue[0]["verification"], "unverified")
        self.assertIsNone(revenue[0]["publication_time"])

    def test_missing_cash_flow_is_not_zero(self):
        self.assertIsNotNone(collect_financial, "evidence_financial is missing")
        result = collect_financial("600519", "sh", NOW, ak_api=financial_api(missing_cash=True))
        self.assertFalse(any(x["field"] == "operating_cash_flow" for x in result["observations"]))
        self.assertTrue(any("经营现金流" in issue for issue in result["issues"]))

    def test_empty_statement_differs_from_source_exception(self):
        self.assertIsNotNone(collect_financial, "evidence_financial is missing")
        empty = collect_financial("600519", "sh", NOW, ak_api=financial_api(empty_income=True))
        failed = collect_financial("600519", "sh", NOW, ak_api=financial_api(income_error=True))
        self.assertEqual(next(x for x in empty["source_results"] if x["source"] == "sina_income")["status"],
                         "no_record")
        self.assertEqual(next(x for x in failed["source_results"] if x["source"] == "sina_income")["status"],
                         "source_failure")
        self.assertTrue(any(x["field"] == "total_assets" for x in failed["observations"]))

    def test_eps_bps_have_per_share_unit_and_are_unverified(self):
        self.assertIsNotNone(collect_financial, "evidence_financial is missing")
        result = collect_financial("600519", "sh", NOW, ak_api=financial_api())
        per_share = {x["field"]: x for x in result["observations"] if x["field"] in {"basic_eps", "book_value_per_share"}}
        self.assertEqual((per_share["basic_eps"]["value"], per_share["basic_eps"]["unit"]),
                         (12.5, "CNY/share"))
        self.assertEqual((per_share["book_value_per_share"]["value"], per_share["book_value_per_share"]["unit"]),
                         (110.0, "CNY/share"))
        self.assertEqual(per_share["basic_eps"]["verification"], "unverified")
        self.assertTrue(per_share["basic_eps"]["source_url"].startswith("https://"))


if __name__ == "__main__":
    unittest.main()
