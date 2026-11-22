"""Versioned sentiment evidence, separate from the financial evidence schema."""

from __future__ import annotations

import json
import math
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from market_phase import MARKET_PHASES
from source_runtime import SOURCE_STATUSES, validate_source_result


BJ_TZ = timezone(timedelta(hours=8))
_VOLATILE = {"collected_at", "retrieved_at", "elapsed_ms", "attempts", "attempt_log", "request_log", "cooldown_until", "run_id"}


def checked_time(value: str, field: str, *, beijing: bool = False) -> datetime:
    try:
        result = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an ISO timestamp") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"{field} needs a UTC offset")
    if beijing and result.utcoffset() != timedelta(hours=8):
        raise ValueError(f"{field} must use Beijing time (+08:00)")
    return result


def checked_url(value: str, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} needs an HTTP(S) URL")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{field} needs an HTTP(S) URL")
    return value


def validate_snapshot(packet: dict, *, current: bool = False) -> None:
    if not isinstance(packet, dict) or packet.get("schema_version") != 1:
        raise ValueError("Unsupported sentiment schema")
    if packet.get("kind") not in {"market", "stock"}:
        raise ValueError("Invalid sentiment kind")
    checked_time(packet.get("collected_at"), "collected_at", beijing=True)
    if not packet.get("scope") or packet.get("completeness") not in {"complete", "partial"}:
        raise ValueError("Snapshot scope or completeness missing")
    for key in ("source_results", "observations", "issues"):
        if not isinstance(packet.get(key), list):
            raise ValueError(f"{key} must be a list")
    if packet.get("collection_status") == "failed":
        coverage = packet.get("coverage")
        if (packet.get("as_of_trade_date") is not None or packet["completeness"] != "partial"
                or packet["observations"] or not packet["issues"]
                or not isinstance(coverage, dict) or coverage.get("calendar_verified") is not False
                or not any(isinstance(result, dict) and result.get("status") in
                           {"source_failure", "rate_limited", "malformed", "partial"}
                           for result in packet["source_results"])):
            raise ValueError("Calendar diagnostics need a null trade date, failure evidence and partial status")
    else:
        date.fromisoformat(packet["as_of_trade_date"])
    if current or "runtime_version" in packet:
        phase = packet.get("market_phase", "unknown")
        if not isinstance(phase, str) or phase not in MARKET_PHASES:
            raise ValueError("New sentiment snapshots need a canonical market_phase")
    if packet["kind"] == "stock":
        target = packet.get("target", {})
        if not re.fullmatch(r"\d{6}", str(target.get("code", ""))) or target.get("market") not in {"sh", "sz", "bj"}:
            raise ValueError("Invalid stock target")
    for result in packet["source_results"]:
        validate_source_result(result, require_source_url=current or "runtime_version" in packet)
        if not current and "runtime_version" not in packet:
            checked_url(result.get("source_url"), "source_result.source_url")
    for item in packet["observations"]:
        if not isinstance(item, dict) or not all(item.get(k) for k in
                ("field", "unit", "basis", "source_name", "observed_at", "retrieved_at", "scope")):
            raise ValueError("Observation lacks provenance")
        checked_url(item.get("source_url"), "observation.source_url")
        checked_time(item["observed_at"], "observation.observed_at")
        checked_time(item["retrieved_at"], "observation.retrieved_at", beijing=True)
        if item.get("status") not in SOURCE_STATUSES:
            raise ValueError("Invalid observation status")
        value = item.get("value")
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                  or not math.isfinite(value) or value < 0):
            raise ValueError("Observation value must be finite and nonnegative, or null")
        if value is None and item["status"] == "ok":
            raise ValueError("An ok observation needs a value")
        if value is not None and item["status"] != "ok":
            raise ValueError("A missing observation cannot have a value")


def _meaningful(value):
    """Ignore fetch-clock differences when deciding whether a new version is needed."""
    if isinstance(value, dict):
        clock_only = (str(value.get("observation_time_basis", "")).startswith("retrieval_only") or
                      value.get("finality") == "post_close_fetch" or
                      value.get("source_name") in {"eastmoney_top100", "xueqiu_discussion_rank"} or
                      value.get("scope") == "current top 100" or "list_name" in value)
        return {key: _meaningful(item) for key, item in value.items()
                if key not in _VOLATILE and not (key == "observed_at" and clock_only)}
    if isinstance(value, list):
        return [_meaningful(item) for item in value]
    return value


def _version(path: Path, stem: str) -> int:
    match = re.fullmatch(re.escape(stem) + r"(?:-v(\d+))?\.json", path.name)
    return 0 if match is None else int(match.group(1) or 1)


def _base(packet: dict, workspace: Path) -> tuple[Path, str]:
    if packet.get("collection_status") == "failed":
        stem = packet["collected_at"][:10]
        if packet["kind"] == "stock":
            stem += "-" + packet["target"]["code"]
        return Path(workspace).expanduser().resolve() / "research/evidence/sentiment/diagnostics" / packet["kind"], stem
    target = packet["as_of_trade_date"]
    if packet["kind"] == "market":
        return Path(workspace).expanduser().resolve() / "research/evidence/sentiment/market", target
    return (Path(workspace).expanduser().resolve() / "research/evidence/sentiment/stock",
            f"{target}-{packet['target']['code']}")


def save_sentiment_snapshot(packet: dict, workspace: Path) -> Path:
    validate_snapshot(packet, current=True)
    base, stem = _base(packet, workspace)
    base.mkdir(parents=True, exist_ok=True)
    existing = sorted((p for p in base.glob(f"{stem}*.json") if _version(p, stem)),
                      key=lambda p: _version(p, stem))
    for path in (existing[-1:] if packet.get("collection_status") != "failed" else []):
        try:
            if _meaningful(json.loads(path.read_text(encoding="utf-8"))) == _meaningful(packet):
                return path
        except (OSError, TypeError, ValueError):
            continue
    next_version = _version(existing[-1], stem) + 1 if existing else 1
    content = json.dumps(packet, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    while True:
        name = f"{stem}.json" if next_version == 1 else f"{stem}-v{next_version}.json"
        path = base / name
        try:
            with path.open("x", encoding="utf-8") as output:
                output.write(content)
            if json.loads(path.read_text(encoding="utf-8")) != packet:
                raise OSError("Sentiment snapshot read-back differs")
            return path
        except FileExistsError:
            next_version += 1
        except (OSError, ValueError):
            path.unlink(missing_ok=True)
            raise


def load_market_five_days(workspace: Path, trade_dates: list[date]) -> list[dict]:
    workspace = Path(workspace).expanduser().resolve()
    base = workspace / "research/evidence/sentiment/market"
    days = []
    for day in trade_dates:
        stem = day.isoformat()
        candidates = sorted((p for p in base.glob(f"{stem}*.json") if _version(p, stem)),
                            key=lambda p: _version(p, stem), reverse=True)
        selected = None
        for path in candidates:
            try:
                packet = json.loads(path.read_text(encoding="utf-8"))
                validate_snapshot(packet)
                if packet["kind"] != "market" or packet["as_of_trade_date"] != stem:
                    continue
            except (OSError, TypeError, ValueError, KeyError):
                continue
            if selected is None or packet["completeness"] == "complete":
                selected = (path, packet)
            if packet["completeness"] == "complete":
                break
        days.append({"trade_date": stem, "snapshot_path": selected[0].relative_to(workspace).as_posix() if selected else None,
                     "completeness": selected[1]["completeness"] if selected else "missing",
                     "observations": selected[1]["observations"] if selected else [],
                     "source_results": selected[1]["source_results"] if selected else [],
                     "valid_fields": [item["field"] for item in selected[1]["observations"]
                                      if item["status"] == "ok"] if selected else [],
                     "valid_points": sum(item["status"] == "ok" for item in selected[1]["observations"])
                                     if selected else 0,
                     "issues": selected[1]["issues"] if selected else ["no_saved_snapshot"]})
    return days
