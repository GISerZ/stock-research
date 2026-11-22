"""Collect versioned market or stock sentiment evidence."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, time
from pathlib import Path

from evidence_core import normalize_target
from sentiment_core import BJ_TZ, load_market_five_days, save_sentiment_snapshot
from sentiment_cross_market import validate_cross_market_review
from sentiment_market import CALENDAR_URL, NonTradingDay, collect_market_day
from sentiment_stock import collect_stock_day, summarize_analysis_coverage
from source_runtime import RUNTIME_VERSION, SourceError, SourceRuntime


def _read_review(path: str | None) -> tuple[dict | None, str | None]:
    if path is None:
        return None, None
    try:
        def reject_nonfinite(value: str):
            raise ValueError(f"Non-finite JSON number: {value}")

        value = json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=reject_nonfinite)
        if not isinstance(value, dict):
            raise ValueError("Review file must contain a JSON object")
        return value, None
    except (OSError, ValueError) as exc:
        return None, f"{path}: {exc}"


def _completed_date(now: datetime, ak_api, runtime: SourceRuntime | None = None) -> date:
    now = now.astimezone(BJ_TZ)
    runtime = runtime or SourceRuntime()
    runtime.calendar_verified = False
    runtime.calendar = []
    frame = runtime.call("sina_trade_calendar", ak_api.tool_trade_date_hist_sina)
    if frame is None or frame.empty or "trade_date" not in frame.columns:
        raise ValueError("Trade calendar is empty or unrecognized")
    days = sorted({date.fromisoformat(str(value)[:10]) for value in frame["trade_date"]})
    runtime.calendar = days
    if days[-1] < now.date():
        raise ValueError(f"Trade calendar is stale: ends at {days[-1]}, research date is {now.date()}")
    eligible = [day for day in days if day < now.date() or (day == now.date() and now.time() >= time(15))]
    if not eligible:
        raise ValueError("No completed trading day in the source calendar")
    runtime.calendar_verified = True
    return eligible[-1]


def _target(raw: str, ak_api, runtime: SourceRuntime) -> tuple[str, str]:
    if re.search(r"(?:^BJ|\.BJ$)", raw, re.I) or re.search(r"^(?:4|8|92)\d{5}$", raw):
        frame = runtime.call("bse_directory", ak_api.stock_info_bj_name_code)
        if frame is None or frame.empty or "证券代码" not in frame.columns:
            raise ValueError("BSE listed-stock directory unavailable")
        active = {str(value).strip().zfill(6) for value in frame["证券代码"]}
        return normalize_target(raw, active_bse_codes=active)
    return normalize_target(raw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--market", action="store_true", help="Collect today's post-close 沪深 market snapshot")
    choice.add_argument("--code", help="Collect one A-share stock sentiment snapshot")
    parser.add_argument("--output-dir", default=".", help="Workspace containing research/")
    parser.add_argument("--social-review-file", help="Optional manually reviewed social-post JSON")
    parser.add_argument("--cross-market-file", help="Optional curated international-reference JSON")
    args = parser.parse_args(argv)
    now = datetime.now(BJ_TZ)
    workspace = Path(args.output_dir).expanduser().resolve()
    try:
        import akshare
        import requests
        runtime = SourceRuntime(cooldown_seconds=900)
        if args.market:
            if now.time() < time(15):
                raise ValueError("Market snapshot requires a completed A-share session")
            previous = load_market_five_days(workspace, [now.date()])[0]
            if previous["completeness"] == "complete":
                print((workspace / previous["snapshot_path"]).resolve())
                return 0
            try:
                packet = collect_market_day(now.date(), now=now, ak_api=akshare, runtime=runtime)
            except NonTradingDay as exc:
                print(f"Skipped non-trading day: {exc}")
                return 0
        else:
            code, market = _target(args.code, akshare, runtime)
            packet = {"schema_version": 1, "kind": "stock", "target": {"code": code, "market": market},
                      "collected_at": now.isoformat(), "as_of_trade_date": None,
                      "runtime_version": RUNTIME_VERSION, "run_id": runtime.run_id,
                      "scope": f"{market.upper()}{code} and 沪深 market context",
                      "completeness": "partial", "collection_status": "failed", "market_phase": "unknown",
                      "coverage": {"calendar_verified": False, "calendar_status": "not_requested"},
                      "source_results": [], "observations": [], "issues": []}
            try:
                completed = _completed_date(now, akshare, runtime)
            except Exception as exc:
                packet["coverage"]["calendar_status"] = "failed"
                packet["issues"].append("calendar_unavailable")
                packet["source_results"].append(runtime.result({"source": "sina_trade_calendar",
                    "source_url": CALENDAR_URL, "status": "source_failure",
                    "coverage": dict(packet["coverage"])}, error=exc))
                packet["analysis_coverage"] = summarize_analysis_coverage(packet)
                path = save_sentiment_snapshot(packet, workspace)
                print(path)
                print(f"Sentiment calendar unavailable; diagnostic snapshot saved: {exc}", file=sys.stderr)
                return 2
            social, social_error = _read_review(args.social_review_file)
            cross, cross_error = _read_review(args.cross_market_file)
            packet = collect_stock_day(code, market, completed, now=now, ak_api=akshare,
                                       http_get=requests.get, social_review=social, workspace=workspace,
                                       runtime=runtime)
            if social_error:
                packet["social_review"] = {"status": "unverifiable", "posts": [], "reason": social_error}
                packet["issues"].append(f"social_review: {social_error}")
                packet["completeness"] = "partial"
            packet["cross_market"] = validate_cross_market_review(cross, research_as_of=now)
            if cross_error:
                packet["cross_market"] = {"selection_status": "unavailable", "references": [],
                                          "issues": [cross_error]}
            packet["issues"].extend(f"cross_market: {issue}" for issue in packet["cross_market"]["issues"])
            if packet["cross_market"]["selection_status"] in {"unavailable", "not_reviewed"}:
                packet["completeness"] = "partial"
            packet["analysis_coverage"] = summarize_analysis_coverage(packet)
        path = save_sentiment_snapshot(packet, workspace)
        print(path)
        if packet["issues"]:
            print("Sentiment gaps: " + "; ".join(packet["issues"]), file=sys.stderr)
        if packet.get("collection_status") == "failed":
            return 2
        return 0 if packet["completeness"] == "complete" or packet["kind"] == "stock" else 1
    except (ImportError, OSError, TypeError, ValueError, KeyError, SourceError) as exc:
        print(f"Sentiment collection failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
