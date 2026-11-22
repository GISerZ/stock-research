"""Shared contract and versioned storage for a single-stock evidence snapshot."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timedelta
from itertools import count
from pathlib import Path

from market_phase import MARKET_PHASES
from source_runtime import SOURCE_STATUSES, checked_source_url, validate_source_result


CODE_PATTERN = re.compile(r"^(?:(SH|SZ|BJ))?(\d{6})(?:\.(SH|SZ|BJ))?$", re.I)
BEIJING_OFFSET = timedelta(hours=8)
OBSERVATION_FIELDS = {
    "field", "value", "unit", "period_or_market_time", "publication_time",
    "retrieved_time", "basis", "source_name", "source_url", "verification",
}


def normalize_target(raw: str, *, active_bse_codes: set[str] | None = None) -> tuple[str, str]:
    """Resolve an A-share code without treating a legacy BSE code as current."""
    match = CODE_PATTERN.fullmatch((raw or "").strip())
    if match is None:
        raise ValueError("A-share code must be six digits, with an optional SH/SZ/BJ prefix or suffix")
    prefix, code, suffix = match.groups()
    if prefix and suffix:
        raise ValueError("Use one market qualifier, not both a prefix and suffix")
    if code.startswith(("60", "68")):
        market = "sh"
    elif code.startswith(("00", "30")):
        market = "sz"
    elif code.startswith(("4", "8", "92")):
        market = "bj"
        if active_bse_codes is None or code not in active_bse_codes:
            raise ValueError(f"BSE code {code} is not verified in the current listed-stock directory")
    else:
        raise ValueError(f"Unsupported or ambiguous A-share code: {code}")
    qualifier = (prefix or suffix or "").lower()
    if qualifier and qualifier != market:
        raise ValueError(f"Market qualifier {qualifier} conflicts with code {code} ({market})")
    return code, market


def empty_fragment(*, schema_version: int = 1) -> dict:
    fragment = {"source_results": [], "observations": [], "announcements": [], "issues": []}
    if schema_version == 2:
        fragment.update({key: [] for key in (
            "documents", "broker_reports", "peer_snapshots", "valuation_gaps")})
    return fragment


def _beijing_time(value: str, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO timestamp with +08:00")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO timestamp with +08:00") from exc
    if parsed.utcoffset() != BEIJING_OFFSET:
        raise ValueError(f"{field} must use Beijing time (+08:00)")
    return parsed


def validate_packet(packet: dict, *, current: bool = False) -> None:
    """Reject malformed or untraceable evidence before it reaches a report."""
    if not isinstance(packet, dict) or packet.get("schema_version") not in (1, 2):
        raise ValueError("Unsupported evidence schema")
    target = packet.get("target")
    if not isinstance(target, dict):
        raise ValueError("Missing target")
    code, market = target.get("code"), target.get("market")
    if not isinstance(code, str) or not re.fullmatch(r"\d{6}", code) or market not in {"sh", "sz", "bj"}:
        raise ValueError("Invalid target code or market")
    if market == "sh" and not code.startswith(("60", "68")):
        raise ValueError("Target code conflicts with Shanghai market")
    if market == "sz" and not code.startswith(("00", "30")):
        raise ValueError("Target code conflicts with Shenzhen market")
    if market == "bj" and not code.startswith(("4", "8", "92")):
        raise ValueError("Target code conflicts with Beijing market")
    _beijing_time(packet.get("collected_at"), "collected_at")
    for key in ("source_results", "observations", "announcements", "issues"):
        if not isinstance(packet.get(key), list):
            raise ValueError(f"{key} must be a list")
    for result in packet["source_results"]:
        validate_source_result(result, require_source_url=current or "runtime_version" in packet)
    for item in packet["observations"]:
        if not isinstance(item, dict) or not OBSERVATION_FIELDS.issubset(item):
            raise ValueError("Observation is missing required provenance fields")
        for key in ("field", "unit", "period_or_market_time", "retrieved_time", "basis", "source_name", "source_url", "verification"):
            if not item[key] or not isinstance(item[key], str):
                raise ValueError(f"Observation {key} is missing")
        _beijing_time(item["retrieved_time"], "retrieved_time")
        if not item["source_url"].startswith(("https://", "http://")):
            raise ValueError("Observation source_url must be an HTTP(S) URL")
        if current or "runtime_version" in packet:
            checked_source_url(item["source_url"])
        if (current or "runtime_version" in packet) and "market_phase" in item:
            if not isinstance(item["market_phase"], str) or item["market_phase"] not in MARKET_PHASES:
                raise ValueError("New observations need a canonical market_phase")
        value = item["value"]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("Observation value must be a finite number")
    for item in packet["announcements"]:
        if not isinstance(item, dict) or item.get("code") != code or not item.get("source_url"):
            raise ValueError("Announcement must match the target and link to its source")
    if packet["schema_version"] == 2:
        for key in ("documents", "broker_reports", "peer_snapshots", "valuation_gaps"):
            if not isinstance(packet.get(key), list):
                raise ValueError(f"{key} must be a list")
        for item in packet["documents"]:
            if item.get("code") != code or not item.get("source_url", "").startswith("https://static.cninfo.com.cn/"):
                raise ValueError("Document must link to the target's official PDF")
            if not re.fullmatch(r"[0-9a-f]{64}", item.get("pdf_sha256", "")):
                raise ValueError("Document lacks a SHA-256 PDF hash")
            for field in ("pdf_path", "text_path"):
                path = item.get(field)
                if path is not None and (not isinstance(path, str) or Path(path).is_absolute()
                                         or ".." in Path(path).parts):
                    raise ValueError(f"Document {field} must be a safe relative path")
            _beijing_time(item.get("retrieved_time"), "document retrieved_time")
        for key in ("broker_reports", "peer_snapshots"):
            for item in packet[key]:
                if not isinstance(item, dict) or not re.fullmatch(r"\d{6}", item.get("code", "")):
                    raise ValueError(f"Invalid {key} code")
                if not str(item.get("source_url", "")).startswith("https://"):
                    raise ValueError(f"Invalid {key} source URL")
                if (current or "runtime_version" in packet) and "market_phase" in item:
                    if not isinstance(item["market_phase"], str) or item["market_phase"] not in MARKET_PHASES:
                        raise ValueError(f"New {key} need a canonical market_phase")
                _beijing_time(item.get("retrieved_time"), f"{key} retrieved_time")
        for item in packet["valuation_gaps"]:
            if not isinstance(item, dict) or not all(k in item for k in ("kind", "status", "detail", "source_urls")):
                raise ValueError("Invalid valuation gap")


def save_packet(packet: dict, workspace: Path) -> Path:
    """Persist an immutable JSON snapshot, preserving earlier same-day runs."""
    validate_packet(packet, current=True)
    base = Path(workspace).expanduser().resolve() / "research" / "evidence"
    date_text = _beijing_time(packet["collected_at"], "collected_at").date().isoformat()
    stem = f"{date_text}-{packet['target']['code']}"
    serialized = json.dumps(packet, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    base.mkdir(parents=True, exist_ok=True)
    for version in count(1):
        name = f"{stem}.json" if version == 1 else f"{stem}-v{version}.json"
        path = base / name
        try:
            with path.open("x", encoding="utf-8") as output:
                output.write(serialized)
        except FileExistsError:
            continue
        except OSError:
            path.unlink(missing_ok=True)
            raise
        try:
            if json.loads(path.read_text(encoding="utf-8")) != packet:
                raise OSError("Saved evidence packet did not read back unchanged")
        except (OSError, ValueError):
            path.unlink(missing_ok=True)
            raise
        return path
