"""Broker EPS leads and analyst-selected peer quote snapshots."""

from __future__ import annotations

import math
import re
from datetime import date, datetime, timedelta, timezone

from evidence_core import empty_fragment
from evidence_market import collect_quote
from source_runtime import SourceRuntime


BJ_TZ = timezone(timedelta(hours=8))
REPORT_URL = "https://reportapi.eastmoney.com/report/list"
REPORT_PDF = "https://pdf.dfcfw.com/pdf/H3_{info_code}_1.pdf"
REPORT_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}
EPS_KEYS = ("predictThisYearEps", "predictNextYearEps", "predictNextTwoYearEps")


def _eps(raw) -> float | None:
    if raw in (None, "") or isinstance(raw, bool):
        return None
    value = float(raw)
    return value if math.isfinite(value) else None


def _report_date(raw: str) -> datetime:
    value = datetime.fromisoformat(str(raw).strip().replace(" ", "T"))
    return value.replace(tzinfo=BJ_TZ) if value.tzinfo is None else value.astimezone(BJ_TZ)


def _report_params(code: str, start: date, end: date, page: int) -> dict:
    return {
        "industryCode": "*", "pageSize": "100", "industry": "*",
        "rating": "*", "ratingChange": "*", "beginTime": start.isoformat(),
        "endTime": end.isoformat(), "pageNo": str(page), "fields": "", "qType": "0",
        "orgCode": "", "code": code, "rcode": "", "p": str(page),
        "pageNum": str(page), "pageNumber": str(page),
    }


def _collect_reports(fragment: dict, code: str, retrieved_at: datetime,
                     http_get, valuation_reset_date: date | None, runtime: SourceRuntime) -> None:
    end = retrieved_at.astimezone(BJ_TZ).date()
    start = end - timedelta(days=730)
    source = {"source": "eastmoney_reports", "status": "source_failure",
              "method": "reportapi.eastmoney.com/report/list", "source_url": REPORT_URL,
              "query_range": f"{start}..{end}", "detail": ""}
    forecast_source = {"source": "broker_forecast_eps", "status": "source_failure",
                       "method": "Eastmoney report EPS fields", "source_url": REPORT_URL,
                       "query_range": f"{start}..{end}", "detail": ""}
    try:
        http_get = runtime.http("eastmoney_reports", http_get)
        rows = []
        expected_hits = None
        expected_pages = None
        for page in range(1, 101):
            response = http_get(REPORT_URL, params=_report_params(code, start, end, page),
                                headers=REPORT_HEADERS, timeout=20)
            response.raise_for_status()
            data = response.json()
            hits, pages, batch = data.get("hits"), data.get("TotalPage"), data.get("data")
            if (isinstance(hits, bool) or not isinstance(hits, int) or hits < 0
                    or isinstance(pages, bool) or not isinstance(pages, int) or pages < 0
                    or not isinstance(batch, list) or not all(isinstance(row, dict) for row in batch)
                    or (hits > 0 and not batch) or (hits == 0 and batch)):
                raise ValueError("Eastmoney report response has invalid count or rows")
            if expected_hits is None:
                expected_hits, expected_pages = hits, pages
                if hits > 0 and pages < 1:
                    raise ValueError("Eastmoney report response lacks pages")
                if pages > 100:
                    raise ValueError("Eastmoney report query exceeds 100 pages")
            elif hits != expected_hits or pages != expected_pages:
                raise ValueError("Eastmoney report count changed during pagination")
            rows.extend(batch)
            if page >= pages:
                break
        if len(rows) != expected_hits:
            raise ValueError(f"Eastmoney report pagination incomplete: {len(rows)} of {expected_hits}")
        if not rows:
            source.update(status="no_record", detail="Complete two-year query returned zero reports")
            forecast_source.update(status="no_record", detail="No reports with EPS")
        else:
            reports = []
            seen_reports = set()
            for row in rows:
                if str(row.get("stockCode", "")).zfill(6) != code:
                    raise ValueError("Eastmoney report stock code mismatch")
                published = _report_date(row.get("publishDate", ""))
                if published.date() < start or published.date() > end:
                    raise ValueError("Eastmoney report publication outside queried range")
                info_code = str(row.get("infoCode", "")).strip()
                if info_code and not re.fullmatch(r"[A-Za-z0-9]+", info_code):
                    raise ValueError("Eastmoney report infoCode is invalid")
                title = str(row.get("title") or "").strip()
                org_code = str(row.get("orgCode") or "").strip()
                identity = ("infoCode", info_code) if info_code else (
                    "metadata", code, published.isoformat(), org_code, title)
                if identity in seen_reports or (not info_code and (not org_code or not title)):
                    raise ValueError("Eastmoney report identity is missing or duplicated")
                seen_reports.add(identity)
                values = {key: _eps(row.get(key)) for key in EPS_KEYS}
                has_eps = any(value is not None for value in values.values())
                age_days = (end - published.date()).days
                reason = ("eps_missing" if not has_eps else
                          "predates_valuation_reset" if valuation_reset_date and published.date() < valuation_reset_date else
                          "older_than_180_days" if age_days > 180 else None)
                pdf_url = REPORT_PDF.format(info_code=info_code) if info_code else None
                reports.append({
                    "code": code, "title": title,
                    "org_name": str(row.get("orgSName") or row.get("orgName") or "").strip(),
                    "publish_date": published.date().isoformat(), "publication_time": published.isoformat(),
                    "retrieved_time": retrieved_at.astimezone(BJ_TZ).isoformat(),
                    "info_code": info_code, "pdf_url": pdf_url,
                    "source_url": pdf_url or REPORT_URL,
                    "eps_relative_years": values,
                    "candidate_for_manual_review": reason is None,
                    "usable_for_current_valuation": False,
                    "unusable_reason": reason or "requires_original_report_fiscal_year_and_share_verification",
                    "verification": "broker_vendor_index",
                })
            fragment["broker_reports"].extend(reports)
            source.update(status="ok", detail=f"{len(reports)} reports in two years")
            candidates = sum(item["candidate_for_manual_review"] for item in reports)
            any_eps = any(any(value is not None for value in item["eps_relative_years"].values())
                          for item in reports)
            forecast_source.update(
                status="partial" if candidates else "stale" if any_eps else "no_record",
                detail=f"{candidates} current EPS leads; {len(reports)} indexed reports; "
                       "original report, fiscal year and share basis require manual verification")
    except Exception as exc:
        source = runtime.result(source, error=exc)
        forecast_source.update(status=source["status"], error_type=source["error_type"],
                               detail="Report query failed; EPS availability unknown")
        fragment["issues"].append(f"东方财富研报查询失败：{exc}")
    if source["status"] != "ok":
        source["manual_review"] = {"sina": "https://stock.finance.sina.com.cn/stock/go.php/vReport_List/kind/search/index.phtml",
                                 "ths": "https://basic.10jqka.com.cn/", "eps_verified": False}
    runtime.result(source)
    forecast_source.update({key: source[key] for key in ("attempts", "elapsed_ms", "retrieved_at", "coverage",
        "http_status", "request_log", "runtime_version", "run_id")})
    fragment["source_results"].extend((source, forecast_source))


def _quote_values(observations: list[dict]) -> tuple[dict, dict | None]:
    values = {item["field"]: item["value"] for item in observations
              if item["field"] in {"price", "pe_ttm", "pb", "market_cap"}
              and item.get("source_name") in {"腾讯财经", "东方财富"}}
    price = next((item for item in observations
                  if item["field"] == "price" and item.get("source_name") in {"腾讯财经", "东方财富"}), None)
    return values, price


def _collect_peers(fragment: dict, peer_specs: list[tuple[str, str, str]],
                   target_observations: list[dict], retrieved_at: datetime, http_get, runtime: SourceRuntime,
                   *, target_source_results: list[dict] | None = None) -> None:
    target_values, target_price = _quote_values(target_observations)
    def selected_result(price, results):
        if price is None:
            return None
        source = {"腾讯财经": "tencent_quote", "东方财富": "eastmoney_quote"}.get(price.get("source_name"))
        return next((item for item in results or [] if item.get("source") == source
                     and item.get("selected_for_payload") is True
                     and item.get("source_url") == price.get("source_url")
                     and item.get("coverage", {}).get("quote_time") == price.get("period_or_market_time")), None)
    target_result = selected_result(target_price, target_source_results)
    for code, market, reason in peer_specs:
        quote = collect_quote(code, market, retrieved_at, http_get=http_get, runtime=runtime)
        peer_names = {"tencent_quote": f"tencent_peer_quote:{code}", "eastmoney_quote": f"eastmoney_peer_quote:{code}"}
        for quote_result in quote["source_results"]:
            peer_result = {**quote_result, "source": peer_names[quote_result["source"]], "code": code, "market": market}
            if quote_result.get("fallback_from"):
                peer_result["fallback_from"] = [peer_names[name] for name in quote_result["fallback_from"]]
            fragment["source_results"].append(peer_result)
        fragment["issues"].extend(quote["issues"])
        values, price = _quote_values(quote["observations"])
        peer_result = selected_result(price, quote["source_results"])
        if target_price is None or price is None:
            comparability, detail = "not_comparable", "target or peer quote unavailable"
        elif any(item is None or item.get("status") != "ok" or
                 item.get("coverage", {}).get("calendar_verified") is not True or
                 item.get("coverage", {}).get("quote_phase") in {None, "unknown"} or
                 item.get("coverage", {}).get("freshness_cutoff") is None
                 for item in (target_result, peer_result)):
            comparability, detail = "not_comparable", "selected target or peer source freshness unverified"
        elif target_price["period_or_market_time"][:10] != price["period_or_market_time"][:10]:
            comparability, detail = "not_comparable", "different trading dates"
        elif any(item.get("market_phase") in {None, "unknown"} for item in (target_price, price)):
            comparability, detail = "not_comparable", "unverified market phase"
        elif target_price.get("market_phase") != price.get("market_phase"):
            comparability, detail = "not_comparable", "different market phases"
        elif (not target_result["coverage"].get("close_confirmed") and
              datetime.fromisoformat(target_price["period_or_market_time"]) <
              datetime.fromisoformat(peer_result["coverage"]["freshness_cutoff"]) or
              not peer_result["coverage"].get("close_confirmed") and
              datetime.fromisoformat(price["period_or_market_time"]) <
              datetime.fromisoformat(target_result["coverage"]["freshness_cutoff"])):
            comparability, detail = "not_comparable", "quotes do not share the verified freshness window"
        else:
            comparability, detail = "comparable", "verified selected sources; same trading date and collection phase"
        fragment["peer_snapshots"].append({
            "code": code, "market": market, "selection_reason": reason,
            "source_url": price["source_url"] if price else f"https://qt.gtimg.cn/q={market}{code}",
            "retrieved_time": price["retrieved_time"] if price else runtime.observation_time(retrieved_at).isoformat(),
            "quote_time": price["period_or_market_time"] if price else None,
            "market_phase": price.get("market_phase", "unknown") if price else "unknown",
            "price": values.get("price"), "pe_ttm": values.get("pe_ttm"),
            "pb": values.get("pb"), "market_cap": values.get("market_cap"),
            "target_quote_time": target_price["period_or_market_time"] if target_price else None,
            "target_pe_ttm": target_values.get("pe_ttm"),
            "comparability": comparability, "comparability_detail": detail,
            "verification": "market_vendor",
        })


def collect_valuation(code: str, market: str, retrieved_at: datetime, *, http_get,
                      peer_specs: list[tuple[str, str, str]], target_observations: list[dict],
                      valuation_reset_date: date | None, runtime: SourceRuntime | None = None,
                      target_source_results: list[dict] | None = None) -> dict:
    """Collect broker forecast leads and compact explicit-peer snapshots."""
    fragment = empty_fragment(schema_version=2)
    runtime = runtime or SourceRuntime()
    _collect_reports(fragment, code, retrieved_at, http_get, valuation_reset_date, runtime)
    _collect_peers(fragment, peer_specs, target_observations, retrieved_at, http_get, runtime,
                   target_source_results=target_source_results)
    return fragment
