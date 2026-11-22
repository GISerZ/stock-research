"""Summarize saved source history without fetching or changing any snapshot."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from source_runtime import BJ_TZ, SOURCE_STATUSES, validate_source_result
from validate_report import read_json

FAILURES = {"source_failure", "rate_limited", "malformed", "stale", "partial"}
REQUEST_SUMMARY_FIELDS = ("source", "status", "error_type", "attempts", "http_status", "elapsed_ms", "retrieved_at")
COVERAGE_FIELDS = {"code", "target", "market", "query_range", "scope", "start", "end", "first_date", "last_date", "bars", "gap_dates",
                   "effective_daily_bar_date", "latest_complete_trade_date", "calendar_verified", "calendar_status",
                   "market_phase", "expected_quote_date", "quote_time", "quote_phase", "freshness_cutoff",
                   "quote_time_basis", "raw_quote_time", "as_of_trade_date", "requested_trade_date",
                   "raw_pagination_verified", "raw_pages_checked", "iteration_status", "history_coverage",
                   "calendar_covers_start", "unexpected_dates", "sdk_deadline_seconds", "volume_unit_verified",
                   "alignment_verified", "currency_verified", "sdk_column_period", "alignment_issue",
                   "quote_time_evidence", "provider_state", "provider_phase", "close_confirmed",
                   "volume_rows_corrected", "volume_basis", "volume_unit_evidence",
                   "adapter_module", "adapter_path", "python_executable"}


def _diagnostics(result: dict) -> dict:
    summary = {key: result.get(key) for key in
               ("error_type", "attempts", "http_status", "elapsed_ms", "fallback_from")}
    events = result.get("request_log")
    summary["request_log"] = None if not isinstance(events, list) else [
        {**{key: event.get(key) for key in REQUEST_SUMMARY_FIELDS},
         "attempt_log": [{key: attempt.get(key) for key in ("attempt", "status", "error_type", "http_status")}
                         for attempt in event.get("attempt_log", []) if isinstance(attempt, dict)]}
        for event in events if isinstance(event, dict)]
    return summary


def source_health(workspace: Path) -> dict:
    base = Path(workspace).expanduser().resolve() / "research/evidence"
    summary = {"snapshot_count": 0, "sources": {}, "read_errors": [],
               "count_basis": "counts include all immutable records; failure_rate deduplicates by source and run_id, "
                              "falling back to retrieved_at or collected_at for legacy records (not confirmed outages)",
               "cooldown_scope": "process-local; saved cooldown_until is historical only"}
    events_by_source = {}
    now = datetime.now(BJ_TZ)
    for path in sorted(base.rglob("*.json")):
        try:
            packet = read_json(path, allow_list=True)
            if not isinstance(packet, dict) or "source_results" not in packet:
                continue
            stamp = datetime.fromisoformat(packet["collected_at"])
            if stamp.utcoffset() is None or not isinstance(packet["source_results"], list):
                raise ValueError("Snapshot lacks timestamp or source list")
            summary["snapshot_count"] += 1
            for result in packet["source_results"]:
                validate_source_result(result)
                source, status = result["source"], result["status"]
                event_key = result.get("run_id") or packet.get("run_id") or result.get("retrieved_at") or stamp.isoformat()
                if not isinstance(event_key, str):
                    raise ValueError("Source run identifier must be a string")
                entry = summary["sources"].setdefault(source, {"counts": {key: 0 for key in sorted(SOURCE_STATUSES)},
                    "latest_success": None, "latest_failure": None, "latest_result_at": None,
                    "latest_status": None, "coverage": None, "datasets": [], "latest_failure_diagnostics": None})
                entry["counts"][status] += 1
                source_events = events_by_source.setdefault(source, {})
                source_events[event_key] = source_events.get(event_key, False) or status in FAILURES
                dataset = ("chip_analysis" if packet.get("kind") == "chips" else
                           "sentiment_" + packet["kind"] if packet.get("kind") else "core_evidence")
                if dataset not in entry["datasets"]:
                    entry["datasets"].append(dataset)
                for key, eligible in (("latest_success", status == "ok"), ("latest_failure", status in FAILURES)):
                    if eligible and (entry[key] is None or stamp >= datetime.fromisoformat(entry[key])):
                        entry[key] = stamp.isoformat()
                        if key == "latest_failure":
                            entry["latest_failure_diagnostics"] = {**_diagnostics(result), "status": status,
                                                                   "snapshot_path": str(path)}
                if entry["latest_result_at"] is None or stamp >= datetime.fromisoformat(entry["latest_result_at"]):
                    coverage = result.get("coverage")
                    displayed_coverage = ({key: value for key, value in coverage.items() if key in COVERAGE_FIELDS}
                                          if isinstance(coverage, dict) else None)
                    if isinstance(coverage, dict) and isinstance(coverage.get("field_diagnostics"), list):
                        problems = [item for item in coverage["field_diagnostics"] if item.get("state") != "matched"]
                        displayed_coverage.update(field_issue_count=len(problems), field_issues=problems[:12])
                    entry.update(latest_result_at=stamp.isoformat(), latest_status=status,
                                 coverage=displayed_coverage,
                                 **_diagnostics(result),
                                 snapshot_path=str(path), saved_cooldown_until=result.get("cooldown_until"))
        except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
            summary["read_errors"].append({"path": str(path), "error": str(exc)})
    for source, entry in summary["sources"].items():
        status = entry["latest_status"]
        if status in {"no_record", "not_supported"}:
            action = "正常空查询/覆盖边界；按 detail 解释，不当作接口故障重试"
        elif status == "rate_limited":
            action = "等待冷却；不要重复撞击来源，必要时走已定义备源或人工复核"
        elif status == "malformed":
            action = "检查返回结构、代码与日期；修复解析前不要重复请求"
        elif status in {"stale", "partial"}:
            action = "核对交易阶段与实际覆盖日期；补核缺口，不倒填成完整"
        elif status == "source_failure":
            action = "检查错误分类与网络；保留失败链，披露事实转官方人工复核"
        else:
            action = "最近来源成功；仍需核对原始披露与覆盖范围"
        entry["record_count"] = sum(entry["counts"].values())
        entry["failure_record_count"] = sum(entry["counts"][key] for key in FAILURES)
        entry["event_count"] = len(events_by_source[source])
        entry["failure_event_count"] = sum(events_by_source[source].values())
        entry["repeated_failure"] = entry["failure_event_count"] > 1
        entry["failure_rate"] = round(entry["failure_event_count"] / entry["event_count"], 4)
        entry["snapshot_failure_rate"] = round(entry["failure_record_count"] / entry["record_count"], 4)
        entry["suggested_action"] = action
    summary["generated_at"] = now.isoformat()
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=".", type=Path)
    args = parser.parse_args(argv)
    summary = source_health(args.output_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if summary["read_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
