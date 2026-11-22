"""Financial statement and per-share observations with explicit period basis."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit

from evidence_core import empty_fragment
from source_runtime import SourceRuntime


BJ_TZ = timezone(timedelta(hours=8))
STATEMENTS = (
    ("sina_income", "利润表", {
        "revenue": ("营业收入", "营业总收入"),
        "attributable_profit": ("归属于母公司所有者的净利润", "归属于母公司的净利润", "归母净利润", "归属于母公司股东的净利润"),
        "operating_cost": ("营业成本",),
        "investment_income": ("投资收益",),
        "fair_value_income": ("公允价值变动收益",),
    }, "consolidated cumulative"),
    ("sina_balance", "资产负债表", {
        "total_assets": ("资产总计", "资产总额"),
        "total_liabilities": ("负债合计", "负债总计"),
        "cash": ("货币资金",),
        "accounts_receivable": ("应收账款",),
        "inventory": ("存货",),
        "short_term_borrowings": ("短期借款",),
        "current_noncurrent_liabilities": ("一年内到期的非流动负债",),
        "long_term_borrowings": ("长期借款",),
    }, "consolidated period-end"),
    ("sina_cashflow", "现金流量表", {
        "operating_cash_flow": ("经营活动产生的现金流量净额", "经营活动现金流量净额"),
        "capex_cash_paid": ("购建固定资产、无形资产和其他长期资产支付的现金",),
    }, "consolidated cumulative"),
)


def _finite(raw: Any) -> float | None:
    if raw is None or raw == "" or isinstance(raw, bool):
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _period(raw: Any) -> str:
    text = str(raw).strip()
    if len(text) >= 10 and text[4] == "-":
        day = text[:10]
    elif len(text) >= 8 and text[:8].isdigit():
        day = f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    else:
        raise ValueError(f"Invalid financial report period: {raw!r}")
    datetime.strptime(day, "%Y-%m-%d")
    return day


def _source(source: str, status: str, method: str, url: str, detail: str = "") -> dict:
    return {"source": source, "status": status, "method": method,
            "source_url": url, "detail": detail}


def _observation(field: str, value: float, unit: str, period: str, basis: str,
                 source_name: str, source_url: str, retrieved_at: datetime) -> dict:
    return {
        "field": field, "value": value, "unit": unit,
        "period_or_market_time": period, "publication_time": None,
        "retrieved_time": retrieved_at.astimezone(BJ_TZ).isoformat(),
        "basis": basis, "source_name": source_name, "source_url": source_url,
        "verification": "unverified",
    }


def _collect_statement(fragment: dict, code: str, market: str, retrieved_at: datetime,
                       ak_api, source: str, statement: str, aliases: dict,
                       basis: str, runtime: SourceRuntime) -> None:
    url = f"https://vip.stock.finance.sina.com.cn/corp/go.php/vFD_FinanceSummary/stockid/{code}.phtml"
    method = "akshare.stock_financial_report_sina"
    result = _source(source, "source_failure", method, url)
    coverage = result["coverage"] = {"alignment_verified": False, "currency_verified": False,
                                     "field_diagnostics": []}
    original = {}
    def validate_response(request_url, response, kwargs):
        parsed = urlsplit(request_url)
        if parsed.hostname != "quotes.sina.cn" or not parsed.path.endswith(
                "/CompanyFinanceService.getFinanceReport2022"):
            return
        params = kwargs.get("params") or {}
        if (params.get("paperCode") != f"{market}{code}" or
                params.get("source") != {"资产负债表": "fzb", "利润表": "lrb", "现金流量表": "llb"}[statement]
                or str(params.get("type")) != "0" or str(params.get("page")) != "1"):
            raise ValueError("Sina raw statement request target/type mismatch")
        data = response.json()["result"]["data"]
        periods = [item["date_value"] for item in data["report_date"]]
        if not periods or original:
            raise ValueError("Sina raw statement is empty or route was called more than once")
        reports = {}
        for key in periods:
            report = data["report_list"][key]
            entries = report["data"]
            titles = [item["item_title"] for item in entries]
            if not titles or not all(isinstance(name, str) and name for name in titles):
                raise ValueError("Sina raw item titles are missing")
            period = _period(key)
            if period in reports:
                raise ValueError("Sina raw report periods duplicated")
            reports[period] = {"titles": titles, "entries": entries,
                               "currency": report["rCurrency"], "type": report["rType"]}
        original.update(reports=reports, sdk_titles=titles, sdk_period=_period(periods[-1]))
        coverage["sdk_column_period"] = original["sdk_period"]
    try:
        frame = runtime.call(source, ak_api.stock_financial_report_sina, stock=f"{market}{code}", symbol=statement,
                             response_validator=validate_response)
        if frame is None or frame.empty:
            raise ValueError("Empty statement response does not establish absence of financial records")
        if "报告日" not in frame.columns:
            raise ValueError("Sina statement has no 报告日 column")
        records = []
        for _, row in frame.iterrows():
            report_type = str(row.get("类型") or "")
            if "合并" not in report_type:
                continue
            period = _period(row["报告日"])
            if period > retrieved_at.astimezone(BJ_TZ).date().isoformat():
                raise ValueError(f"Future financial report period: {period}")
            records.append((period, row))
        records.sort(key=lambda item: item[0], reverse=True)
        seen = set()
        chosen = []
        for period, row in records:
            if period not in seen:
                chosen.append((period, row))
                seen.add(period)
            if len(chosen) == 8:
                break
        if not chosen:
            raise ValueError("Sina statement has no consolidated records")
        if original:
            expected_columns = list(dict.fromkeys(["报告日", *original["sdk_titles"],
                "数据源", "是否审计", "公告日期", "币种", "类型", "更新日期"]))
            if list(frame.columns) != expected_columns:
                raise ValueError("Sina SDK columns differ from final raw period item titles")
            for period, row in chosen:
                report = original["reports"].get(period)
                if report is None or report["titles"] != original["sdk_titles"]:
                    raise ValueError(f"Sina item alignment differs from SDK column period: {period}")
                unique = {}
                for item in report["entries"]:
                    name, raw_value = item["item_title"], item["item_value"]
                    if name in unique and unique[name] != raw_value:
                        raise ValueError(f"Sina duplicate item has conflicting values: {period} {name}")
                    unique[name] = raw_value
                if "合并" not in str(report["type"]) or str(row.get("类型")) != str(report["type"]):
                    raise ValueError(f"Sina consolidated report type mismatch: {period}")
                if report["currency"] not in {"CNY", "人民币", "人民币元"}:
                    raise ValueError(f"Sina currency is not verified CNY: {period} {report['currency']}")
                if row.get("币种") != report["currency"]:
                    raise ValueError(f"Sina SDK currency differs from raw report: {period}")
            coverage.update(alignment_verified=True, currency_verified=True)
        observations = []
        for period, row in chosen:
            for field, names in aliases.items():
                found = next(((name, _finite(row[name])) for name in names
                              if name in row and _finite(row[name]) is not None), None)
                present = next((name for name in names if name in row), None)
                state = ("alignment_unverified" if not original else "mapping_missing" if not names else
                         "source_field_missing" if present is None else "source_value_invalid" if found is None else "matched")
                diagnostic = {"period": period, "field": field, "state": state,
                              "raw_name": found[0] if found else present,
                              "reason": {"alignment_unverified": "raw route/SDK alignment and currency not verified",
                                         "mapping_missing": "no mapping implemented",
                                         "source_field_missing": "none of the implemented aliases is in this response",
                                         "source_value_invalid": "field exists but value is blank/non-numeric/non-finite",
                                         "matched": "raw order, SDK columns and CNY checked; filing remains unverified"}[state]}
                if found and state == "alignment_unverified":
                    diagnostic["raw_value"] = found[1]
                coverage["field_diagnostics"].append(diagnostic)
                if state != "matched":
                    fragment["issues"].append(f"{statement} {period} {field}: {state}；不能补0或猜原文归属")
                    continue
                name, value = found
                observations.append(_observation(field, value, "CNY", period,
                                                 f"{basis}; {name}", "新浪财经", url, retrieved_at))
        fragment["observations"].extend(observations)
        incomplete = any(item["state"] != "matched" for item in coverage["field_diagnostics"])
        result.update(status="partial" if incomplete else "ok",
                      detail=f"{len(chosen)} consolidated periods; {basis}; raw alignment {bool(original)}; "
                             "financial observations remain unverified against filings")
        fragment["source_results"].append(runtime.result(result))
    except Exception as exc:
        coverage["alignment_issue"] = str(exc)
        fragment["source_results"].append(runtime.result(result, error=exc))
        fragment["issues"].append(f"{statement} 取数失败：{exc}")


def _collect_per_share(fragment: dict, code: str, market: str, retrieved_at: datetime, ak_api,
                       runtime: SourceRuntime) -> None:
    url = ("https://emweb.securities.eastmoney.com/pc_hsf10/pages/index.html"
           f"?type=web&code={market.upper()}{code}&color=b#/cwfx")
    method = "akshare.stock_financial_analysis_indicator_em"
    source = "eastmoney_per_share"
    try:
        frame = runtime.call(source, ak_api.stock_financial_analysis_indicator_em,
            symbol=f"{code}.{market.upper()}", indicator="按报告期")
        if frame is None or frame.empty:
            raise ValueError("Empty per-share response does not establish absence of financial records")
        if "REPORT_DATE" not in frame.columns or "SECURITY_CODE" not in frame.columns:
            raise ValueError("Eastmoney indicators lack report date or security code")
        records = []
        for _, row in frame.iterrows():
            if str(row["SECURITY_CODE"]).zfill(6) != code:
                raise ValueError("Eastmoney indicator code mismatch")
            period = _period(row["REPORT_DATE"])
            if period > retrieved_at.astimezone(BJ_TZ).date().isoformat():
                raise ValueError(f"Future per-share indicator period: {period}")
            records.append((period, row))
        records.sort(key=lambda item: item[0], reverse=True)
        observations = []
        seen = set()
        for period, row in records:
            if period in seen:
                continue
            seen.add(period)
            for field, key in (("basic_eps", "EPSJB"), ("book_value_per_share", "BPS")):
                value = _finite(row.get(key))
                if value is not None:
                    observations.append(_observation(field, value, "CNY/share", period,
                                                     f"provider reported {key}", "东方财富", url,
                                                     retrieved_at))
                else:
                    fragment["issues"].append(f"东方财富 {period} 缺少{key}，不能由价格和 PE 倒推")
            if len(seen) == 8:
                break
        if not observations:
            raise ValueError("Eastmoney indicators have no EPSJB or BPS values")
        fragment["observations"].extend(observations)
        fragment["source_results"].append(_source(source, "ok", method, url, f"{len(seen)} report periods"))
    except Exception as exc:
        fragment["source_results"].append(runtime.result(_source(source, "source_failure", method, url), error=exc))
        fragment["issues"].append(f"东方财富每股指标失败：{exc}")


def collect_financial(code: str, market: str, retrieved_at: datetime, *, ak_api,
                      runtime: SourceRuntime | None = None) -> dict:
    """Collect independent financial statements and optional per-share metrics."""
    fragment = empty_fragment()
    runtime = runtime or SourceRuntime()
    for source, statement, aliases, basis in STATEMENTS:
        _collect_statement(fragment, code, market, retrieved_at, ak_api,
                           source, statement, aliases, basis, runtime)
    _collect_per_share(fragment, code, market, retrieved_at, ak_api, runtime)
    for result in fragment["source_results"]:
        runtime.result(result)
    return fragment
