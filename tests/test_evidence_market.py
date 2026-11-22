import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace

import pandas as pd


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

try:
    from evidence_market import collect_market
except ImportError:
    collect_market = None


NOW = datetime(2026, 9, 28, 16, 20, tzinfo=timezone(timedelta(hours=8)))


def quote_body(code="600519", stamp="20260928161451", amount_wan="3000"):
    parts = [""] * 88
    parts[1], parts[2], parts[3], parts[4] = "贵州茅台", code, "1243.88", "1240.00"
    parts[30], parts[37], parts[39], parts[45], parts[46] = stamp, amount_wan, "20.5", "15600", "8.1"
    return ('v_sh600519="' + "~".join(parts) + '";').encode("gbk")


def http_get_for(body):
    def get(url, **kwargs):
        return SimpleNamespace(content=body, raise_for_status=lambda: None)
    return get


def history_api(code="600519"):
    tx = pd.DataFrame([{
        "date": "2026-09-28", "open": 1240.0, "high": 1250.0, "low": 1230.0,
        "close": 1243.88, "volume": 1000.0, "amount": 1243880.0, "turnover": 0.01,
    }])
    em = pd.DataFrame([{
        "日期": "2026-09-28", "股票代码": code, "开盘": 1240.0, "最高": 1250.0,
        "最低": 1230.0, "收盘": 1243.88, "成交量": 10.0, "成交额": 1243880.0,
    }])
    return SimpleNamespace(
        stock_zh_a_hist_tx=lambda **kwargs: tx.copy(),
        stock_zh_a_hist=lambda **kwargs: em.copy(),
    )


class FakeResult:
    fields = ["date", "code", "close", "peTTM", "pbMRQ", "psTTM", "pcfNcfTTM", "turn", "tradestatus", "isST"]

    def __init__(self, error_code="0"):
        self.error_code, self.error_msg = error_code, "upstream error"
        self.rows = [["2026-09-28", "sh.600519", "1243.88", "20.5", "8.1", "", "", "0.7", "1", "0"]]
        self.index = 0

    def next(self):
        if self.index >= len(self.rows):
            return False
        self.index += 1
        return True

    def get_row_data(self):
        return self.rows[self.index - 1]


class FakeBaoStock:
    def __init__(self, result=None):
        self.result = result or FakeResult()
        self.logged_out = False

    def login(self):
        return SimpleNamespace(error_code="0", error_msg="")

    def query_history_k_data_plus(self, *args, **kwargs):
        return self.result

    def logout(self):
        self.logged_out = True


class EvidenceMarketTests(unittest.TestCase):
    def test_baostock_keeps_daily_trading_status_and_turnover(self):
        self.assertIsNotNone(collect_market, "evidence_market is missing")
        result = collect_market("600519", "sh", NOW, http_get=http_get_for(quote_body()),
                                ak_api=history_api(), baostock_api=FakeBaoStock())
        observations = {x["field"]: x for x in result["observations"]
                        if x["field"] in {"trading_status_history", "is_st_history", "turnover_rate_history"}}
        self.assertEqual((observations["trading_status_history"]["value"],
                          observations["trading_status_history"]["unit"]), (1, "flag"))
        self.assertEqual(observations["is_st_history"]["value"], 0)
        self.assertEqual((observations["turnover_rate_history"]["value"],
                          observations["turnover_rate_history"]["unit"]), (0.7, "percent"))

    def test_daily_bars_reject_out_of_order_or_future_dates(self):
        self.assertIsNotNone(collect_market, "evidence_market is missing")
        api = history_api()
        rows = pd.DataFrame([
            {"date": day, "open": 1240.0, "high": 1250.0, "low": 1230.0,
             "close": 1243.88, "volume": 1000.0, "amount": 1243880.0}
            for day in ("2026-09-28", "2026-09-25")
        ])
        api.stock_zh_a_hist_tx = lambda **kwargs: rows.copy()
        reversed_result = collect_market("600519", "sh", NOW, http_get=http_get_for(quote_body()),
                                         ak_api=api, baostock_api=FakeBaoStock())
        self.assertEqual(next(x for x in reversed_result["source_results"]
                              if x["source"] == "akshare_tx_history")["status"], "source_failure")
        self.assertEqual(next(x for x in reversed_result["source_results"]
                              if x["source"] == "akshare_em_history")["status"], "ok")
        rows.loc[0, "date"] = "2026-09-29"
        future_result = collect_market("600519", "sh", NOW, http_get=http_get_for(quote_body()),
                                       ak_api=api, baostock_api=FakeBaoStock())
        self.assertEqual(next(x for x in future_result["source_results"]
                              if x["source"] == "akshare_tx_history")["status"], "source_failure")

    def test_quote_uses_vendor_time_and_rejects_other_ticker(self):
        self.assertIsNotNone(collect_market, "evidence_market is missing")
        result = collect_market("600519", "sh", NOW, http_get=http_get_for(quote_body()),
                                ak_api=history_api(), baostock_api=FakeBaoStock())
        price = next(x for x in result["observations"] if x["field"] == "price")
        self.assertEqual(price["value"], 1243.88)
        self.assertEqual(price["period_or_market_time"], "2026-09-28T16:14:51+08:00")
        self.assertEqual(price["source_url"], "https://qt.gtimg.cn/q=sh600519")
        other = collect_market("600519", "sh", NOW, http_get=http_get_for(quote_body(code="000001")),
                               ak_api=history_api(), baostock_api=FakeBaoStock())
        self.assertFalse(any(x["field"] == "price" for x in other["observations"]))
        self.assertEqual(next(x for x in other["source_results"] if x["source"] == "tencent_quote")["status"],
                         "source_failure")

    def test_legacy_bse_quote_is_stale_and_valuation_not_supported(self):
        self.assertIsNotNone(collect_market, "evidence_market is missing")
        result = collect_market("832982", "bj", NOW,
                                http_get=http_get_for(quote_body(code="832982", stamp="20260731150000", amount_wan="0")),
                                ak_api=history_api(code="832982"), baostock_api=FakeBaoStock())
        statuses = {x["source"]: x["status"] for x in result["source_results"]}
        self.assertEqual(statuses["tencent_quote"], "stale")
        self.assertEqual(statuses["baostock_valuation"], "not_supported")
        self.assertFalse(any(x["field"] == "price" for x in result["observations"]))

    def test_daily_bar_keeps_adjustment_and_volume_unit(self):
        self.assertIsNotNone(collect_market, "evidence_market is missing")
        result = collect_market("600519", "sh", NOW, http_get=http_get_for(quote_body()),
                                ak_api=history_api(), baostock_api=FakeBaoStock())
        close = next(x for x in result["observations"] if x["field"] == "daily_close")
        volume = next(x for x in result["observations"] if x["field"] == "daily_volume")
        self.assertEqual((close["value"], close["basis"]), (1243.88, "unadjusted"))
        self.assertEqual((volume["value"], volume["unit"]), (1000.0, "shares"))

    def test_baostock_logs_out_after_query_error(self):
        self.assertIsNotNone(collect_market, "evidence_market is missing")
        bs = FakeBaoStock(FakeResult(error_code="10004011"))
        result = collect_market("600519", "sh", NOW, http_get=http_get_for(quote_body()),
                                ak_api=history_api(), baostock_api=bs)
        self.assertTrue(bs.logged_out)
        self.assertEqual(next(x for x in result["source_results"] if x["source"] == "baostock_valuation")["status"],
                         "source_failure")

    def test_history_runtime_error_records_failure_and_uses_fallback(self):
        self.assertIsNotNone(collect_market, "evidence_market is missing")
        api = history_api()
        api.stock_zh_a_hist_tx = lambda **kwargs: (_ for _ in ()).throw(RuntimeError("upstream changed"))
        result = collect_market("600519", "sh", NOW, http_get=http_get_for(quote_body()),
                                ak_api=api, baostock_api=FakeBaoStock())
        statuses = {x["source"]: x["status"] for x in result["source_results"]}
        self.assertEqual(statuses["akshare_tx_history"], "source_failure")
        self.assertEqual(statuses["akshare_em_history"], "ok")
        volume = next(x for x in result["observations"] if x["field"] == "daily_volume")
        self.assertEqual((volume["value"], volume["unit"]), (1000.0, "shares"))

    def test_baostock_mismatched_code_does_not_leak_earlier_values(self):
        self.assertIsNotNone(collect_market, "evidence_market is missing")
        rows = FakeResult()
        rows.rows.append(["2026-09-29", "sz.000001", "11.0", "9.0", "1.1", "", "", "0.1", "1", "0"])
        result = collect_market("600519", "sh", NOW, http_get=http_get_for(quote_body()),
                                ak_api=history_api(), baostock_api=FakeBaoStock(rows))
        self.assertEqual(next(x for x in result["source_results"] if x["source"] == "baostock_valuation")["status"],
                         "source_failure")
        self.assertFalse(any(x["field"].endswith("_history") for x in result["observations"]))


if __name__ == "__main__":
    unittest.main()
