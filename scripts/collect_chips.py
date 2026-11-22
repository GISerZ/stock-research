"""Collect a stock's completed-day chip model or explicit source diagnostics."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from chips_core import calculate_chips, save_chips_snapshot
# shortcut: reuse the established identity/calendar policy; extract it if either CLI changes that contract.
from collect_sentiment import _completed_date, _target
from evidence_chips import collect_chip_sources
from market_phase import classify_market_phase
from source_runtime import BJ_TZ, RUNTIME_VERSION, SourceRuntime


def collect_chips(code: str, workspace: Path, *, now: datetime, ak_api, baostock_api,
                  runtime: SourceRuntime | None = None) -> tuple[Path, str]:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Chip collection requires a timezone-aware reference time")
    now = now.astimezone(BJ_TZ)
    runtime = runtime or SourceRuntime()
    ticker, market = _target(code, ak_api, runtime)
    packet = {"schema_version": 1, "kind": "chips", "target": {"code": ticker, "market": market},
        "collected_at": now.isoformat(), "runtime_version": RUNTIME_VERSION, "run_id": runtime.run_id,
        "market_phase": "unknown", "expected_trade_date": None, "as_of_trade_date": None,
        "collection_status": "failed", "data_mode": "unavailable", "input_bars": [],
        "adjustment_anchor": None, "model": None, "distribution": [], "metrics": None,
        "vendor_summary": None, "chart_path": None, "observations": [], "source_results": [],
        "coverage": {"calendar_verified": False}, "issues": []}
    if market == "bj":
        packet["source_results"].extend([
            runtime.result({"source": "bse_directory", "source_url": "https://www.bse.cn/",
                            "method": "AKShare current BSE directory", "status": "ok"}),
            runtime.result({"source": "chip_market_coverage", "source_url": "adapter:chip_market_coverage",
                            "status": "not_supported", "attempts": 0, "detail": "First version covers SH/SZ only"})])
        packet.update(collection_status="not_supported", issues=["BSE chip models are not supported"])
        path = save_chips_snapshot(packet, workspace)
        return path, packet["collection_status"]
    calendar_result = {"source": "sina_trade_calendar",
        "source_url": "https://finance.sina.com.cn/realstock/company/klc_td_sh.txt",
        "method": "AKShare verified trading calendar", "status": "ok"}
    try:
        expected = _completed_date(now, ak_api, runtime)
        calendar_result = runtime.result(calendar_result)
        packet["expected_trade_date"] = expected.isoformat()
        packet["market_phase"] = classify_market_phase(now, is_trading_day=now.date() in runtime.calendar)
        packet["coverage"]["calendar_verified"] = True
    except Exception as exc:
        calendar_result = runtime.result(calendar_result, error=exc)
        packet["issues"].append(f"calendar_unavailable: {exc}")
        packet["source_results"].append(calendar_result)
        path = save_chips_snapshot(packet, workspace)
        return path, packet["collection_status"]
    packet["source_results"].append(calendar_result)
    sources = collect_chip_sources(ticker, market, expected, now=now, ak_api=ak_api,
                                   baostock_api=baostock_api, runtime=runtime)
    packet["source_results"].extend(sources["source_results"])
    packet["coverage"].update(sources["coverage"])
    packet["issues"].extend(sources["issues"])
    if sources["input_bars"]:
        try:
            calculated = calculate_chips(sources["input_bars"], sources["adjustment_anchor"]["raw_ohlc"]["close"])
            packet.update(input_bars=sources["input_bars"], adjustment_anchor=sources["adjustment_anchor"],
                model=calculated["model"], distribution=calculated["distribution"], metrics=calculated["metrics"],
                data_mode="local_distribution", as_of_trade_date=sources["input_bars"][-1]["date"])
            packet["issues"].extend(calculated["issues"])
            packet["collection_status"] = "complete" if (
                not packet["issues"] and packet["as_of_trade_date"] == expected.isoformat()) else "partial"
        except (KeyError, ValueError, TypeError, ArithmeticError) as exc:
            # shortcut: keep calculation errors explicit; add a summary fallback if valid-bar failures are observed.
            packet["source_results"].append(runtime.result({"source": "chip_model",
                "source_url": "adapter:chip_model", "method": "local triangular-turnover model",
                "status": "malformed", "attempts": 0}, error=exc))
            packet["issues"].append(f"chip_model_unavailable: {exc}")
            for source in sources["source_results"]:
                source["selected_for_output"] = False
    elif sources["vendor_summary"] is not None:
        packet.update(data_mode="vendor_summary", collection_status="partial",
                      vendor_summary=sources["vendor_summary"],
                      as_of_trade_date=sources["vendor_summary"]["as_of_trade_date"])
        packet["issues"].append("vendor_summary_only: no histogram, main peak or weighted average cost")
    if packet["data_mode"] == "unavailable" and not packet["issues"]:
        packet["issues"].append("chip_sources_unavailable")
    path = save_chips_snapshot(packet, workspace)
    return path, packet["collection_status"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code", required=True, help="A-share code, optionally qualified by SH/SZ/BJ")
    parser.add_argument("--output-dir", default=".", help="Workspace containing research/")
    args = parser.parse_args(argv)
    try:
        import akshare
        import baostock
        path, status = collect_chips(args.code, Path(args.output_dir), now=datetime.now(BJ_TZ),
                                    ak_api=akshare, baostock_api=baostock, runtime=SourceRuntime())
        print(path)
        if status != "complete":
            print(f"Chip result is {status}; inspect the snapshot's actual date and issues.", file=sys.stderr)
        return 0 if status == "complete" else 1 if status in {"partial", "not_supported"} else 2
    except (ImportError, OSError, KeyError, ValueError, TypeError, ArithmeticError) as exc:
        print(f"Chip collection failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
