"""Collect and persist a versioned single A-share evidence packet."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from evidence_core import CODE_PATTERN, empty_fragment, normalize_target, save_packet
from evidence_disclosure import collect_disclosures
from evidence_documents import TRADE_TITLE, collect_documents
from evidence_financial import collect_financial
from evidence_market import collect_market
from evidence_valuation import collect_valuation
from source_runtime import RUNTIME_VERSION, SourceRuntime


BJ_TZ = timezone(timedelta(hours=8))


def _active_bse_codes(ak_api, runtime: SourceRuntime) -> set[str]:
    try:
        frame = runtime.call("bse_directory", ak_api.stock_info_bj_name_code)
        if frame is None or frame.empty or "证券代码" not in frame.columns:
            raise ValueError("empty or unrecognized listed-stock directory")
        codes = {str(value).strip().zfill(6) for value in frame["证券代码"]}
        if not codes or any(re.fullmatch(r"\d{6}", code) is None for code in codes):
            raise ValueError("invalid stock codes in listed-stock directory")
        return codes
    except Exception as exc:
        raise ValueError(f"BSE listed-stock directory is unavailable: {exc}") from exc


def _requested_range(adapter: str, source: str, now: datetime) -> str:
    day = now.astimezone(BJ_TZ).date()
    if adapter == "market_adapter":
        if "valuation" in source:
            return f"{day - timedelta(days=365 * 5 + 2)}..{day}"
        if "history" in source:
            return f"{day - timedelta(days=370)}..{day}"
        return f"latest quote as of {day}"
    if adapter == "financial_adapter":
        return f"latest 8 reporting periods as of {day}"
    if adapter == "valuation_adapter" and "peer" in source:
        return f"latest peer quote as of {day}"
    return f"past 2 years through {day}"


def _valuation_gaps(packet: dict, peer_specs: list[tuple[str, str, str]]) -> list[dict]:
    gaps = []
    material = [item for item in packet["announcements"] if TRADE_TITLE.search(item["title"])]
    if material:
        official_urls = [item["source_url"] for item in material[:10]]
        material_ids = {item["announcement_id"] for item in material}
        readable_material = [item for item in packet["documents"]
                             if item["announcement_id"] in material_ids
                             and item["extraction_status"] == "ok"]
        excerpts = [excerpt for document in packet["documents"]
                    if document["extraction_status"] == "ok"
                    for excerpt in document["excerpts"]]
        failed_material = any(item["source"] == f"cninfo_document:{announcement_id}"
                              and item["status"] in {"source_failure", "rate_limited", "malformed", "partial", "stale"}
                              for announcement_id in material_ids
                              for item in packet["source_results"])
        for kind, topic in (("closing_status", "closing"), ("post_transaction_profit", "pro_forma")):
            found = [item for item in excerpts if item["topic"] == topic]
            status = ("source_failure" if failed_material else "not_examined") if not readable_material else (
                "requires_manual_verification" if found else "not_found_in_collected_documents")
            detail = ("Transaction PDFs were not readable; no text search was possible" if failed_material else
                      "No transaction PDF was selected for text review") if not readable_material else (
                f"{len(found)} candidate passages require reading the official PDF" if found else
                "No matching passage in downloaded text; this does not establish absence of disclosure")
            gaps.append({"kind": kind,
                         "status": status, "detail": detail,
                         "source_urls": official_urls})
    forecast = next((item for item in packet["source_results"]
                     if item["source"] == "broker_forecast_eps"), None)
    gaps.append({"kind": "broker_forecast", "status": forecast["status"] if forecast else "source_failure",
                 "detail": forecast.get("detail", "Forecast query unavailable") if forecast else "Forecast query unavailable",
                 "source_urls": [forecast["source_url"]] if forecast else []})
    peers = packet["peer_snapshots"]
    comparable = sum(item["comparability"] == "comparable" for item in peers)
    gaps.append({"kind": "peer_quote_sync",
                 "status": "ok" if peer_specs and comparable == len(peer_specs) else (
                     "not_requested" if not peer_specs else "not_comparable"),
                 "detail": f"{comparable}/{len(peer_specs)} peers share the target quote date and market phase",
                 "source_urls": [item["source_url"] for item in peers]})
    return gaps


def collect(code: str, workspace: Path, *, now: datetime, http_get, http_post,
            ak_api, baostock_api, peers: list[tuple[str, str]] = (),
            valuation_reset_date: date | None = None,
            document_urls: list[str] | None = None,
            max_documents: int = 24, runtime: SourceRuntime | None = None) -> tuple[Path, bool]:
    """Save all available sources; return whether any research source succeeded."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must have a timezone")
    runtime = runtime or SourceRuntime()
    match = CODE_PATTERN.fullmatch((code or "").strip())
    active = None
    if not isinstance(max_documents, int) or not 1 <= max_documents <= 100:
        raise ValueError("max_documents must be between 1 and 100")
    if valuation_reset_date is not None and valuation_reset_date > now.astimezone(BJ_TZ).date():
        raise ValueError("valuation_reset_date cannot be in the future")
    if (match and match.group(2).startswith(("4", "8", "92"))) or any(
        CODE_PATTERN.fullmatch(raw) and CODE_PATTERN.fullmatch(raw).group(2).startswith(("4", "8", "92"))
        for raw, _ in peers
    ):
        active = _active_bse_codes(ak_api, runtime)
    ticker, market = normalize_target(code, active_bse_codes=active)
    peer_specs = []
    seen_peers = set()
    for raw, reason in peers:
        peer_code, peer_market = normalize_target(raw, active_bse_codes=active)
        if not reason.strip() or peer_code == ticker or peer_code in seen_peers:
            raise ValueError("Each peer needs a nonempty reason and a unique code distinct from the target")
        seen_peers.add(peer_code)
        peer_specs.append((peer_code, peer_market, reason.strip()))
    packet = {"schema_version": 2, "target": {"code": ticker, "market": market},
              "collected_at": now.astimezone(BJ_TZ).isoformat(),
              "runtime_version": RUNTIME_VERSION, "run_id": runtime.run_id,
              **empty_fragment(schema_version=2)}

    def documents_fragment():
        disclosure = next((item for item in packet["source_results"]
                           if item["source"] == "cninfo_announcements"), None)
        if disclosure is None or disclosure["status"] != "ok":
            fragment = empty_fragment(schema_version=2)
            status = "no_record" if disclosure and disclosure["status"] == "no_record" else "source_failure"
            fragment["source_results"].append({"source": "cninfo_documents", "status": status,
                "method": "requires complete CNINFO index", "source_url": "https://www.cninfo.com.cn/",
                "detail": "Complete index is empty" if status == "no_record" else "Announcement index unavailable"})
            return fragment
        import pymupdf
        return collect_documents(ticker, packet["announcements"], now, workspace,
                                 http_get=http_get, pymupdf_api=pymupdf,
                                 document_urls=document_urls or [], max_documents=max_documents, runtime=runtime)

    collectors = (
        ("market_adapter", lambda: collect_market(ticker, market, now,
            http_get=http_get, ak_api=ak_api, baostock_api=baostock_api, runtime=runtime)),
        ("financial_adapter", lambda: collect_financial(ticker, market, now, ak_api=ak_api, runtime=runtime)),
        ("disclosure_adapter", lambda: collect_disclosures(ticker, market, now,
            ak_api=ak_api, http_get=http_get, http_post=http_post, runtime=runtime)),
        ("documents_adapter", documents_fragment),
        ("valuation_adapter", lambda: collect_valuation(ticker, market, now,
            http_get=http_get, peer_specs=peer_specs,
            target_observations=packet["observations"],
            target_source_results=packet["source_results"],
            valuation_reset_date=valuation_reset_date, runtime=runtime)),
    )
    for name, run in collectors:
        event_offsets = {source: len(events) for source, events in runtime.events.items()}
        try:
            fragment = run()
            for result in fragment["source_results"]:
                result.setdefault("market", market)
                result.setdefault("query_range", _requested_range(name, result["source"], now))
                runtime.result(result)
                if isinstance(result.get("coverage"), dict) and result["coverage"].get("query_range") in {None, "source-defined"}:
                    result["coverage"]["query_range"] = result["query_range"]
            for key in empty_fragment(schema_version=2):
                packet[key].extend(fragment.get(key, []))
        except Exception as exc:
            events = [event for source, history in runtime.events.items()
                      for event in history[event_offsets.get(source, 0):]]
            result = runtime.result({"source": name, "status": "source_failure", "method": "adapter",
                "source_url": f"adapter:{name}", "market": market,
                "query_range": _requested_range(name, name, now)}, error=exc, events=events)
            if result["error_type"] == "unknown":
                result["error_type"] = "adapter_error"
            packet["source_results"].append(result)
            packet["issues"].append(f"{name} 意外失败：{exc}")
    packet["valuation_gaps"] = _valuation_gaps(packet, peer_specs)
    success = any(item["status"] == "ok" and item["source"] != "sina_trade_calendar"
                  for item in packet["source_results"])
    packet["overall_status"] = "partial_or_complete" if success else "all_sources_failed"
    packet["collection_completed_at"] = runtime.observation_time(now).isoformat()
    return save_packet(packet, workspace), success


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code", required=True, help="Six-digit A-share code, optionally qualified by SH/SZ/BJ")
    parser.add_argument("--output-dir", default=".", help="Workspace containing the research/ directory")
    parser.add_argument("--peer", action="append", default=[], metavar="CODE=REASON",
                        help="Repeat for analyst-selected peers, e.g. 300666=semiconductor-targets")
    parser.add_argument("--valuation-reset-date", type=date.fromisoformat, metavar="YYYY-MM-DD",
                        help="Verified material-event date; older forecasts are stale")
    parser.add_argument("--document-url", action="append", default=[], metavar="URL",
                        help="Official PDF URL present in the company's verified CNINFO index")
    parser.add_argument("--max-documents", type=int, default=24,
                        help="Maximum official PDFs to fetch (1-100; default 24)")
    args = parser.parse_args(argv)
    try:
        peers = []
        for spec in args.peer:
            if "=" not in spec:
                raise ValueError("--peer must have CODE=REASON form")
            raw, reason = spec.split("=", 1)
            peers.append((raw.strip(), reason.strip()))
        import akshare
        import baostock
        import requests

        path, success = collect(args.code, Path(args.output_dir),
                                now=datetime.now(BJ_TZ), http_get=requests.get,
                                http_post=requests.post, ak_api=akshare,
                                baostock_api=baostock, peers=peers,
                                valuation_reset_date=args.valuation_reset_date,
                                document_urls=args.document_url, max_documents=args.max_documents,
                                runtime=SourceRuntime())
        print(path)
        if not success:
            print("All research sources failed; diagnostic packet was saved.", file=sys.stderr)
        return 0 if success else 1
    except (ImportError, OSError, ValueError) as exc:
        print(f"Evidence collection failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
