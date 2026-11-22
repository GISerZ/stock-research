"""Validate analyst-selected international references without inventing market data."""

from __future__ import annotations

import math
from datetime import date, datetime

from sentiment_core import checked_time, checked_url


KINDS = {"foreign_peer", "tech_index", "volatility", "put_call", "yield",
         "policy_probability", "credit_spread", "commodity", "fx"}
PUT_CALL_SCOPES = {"total", "equity", "index", "etp"}


def _text(item: dict, key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value.strip()


def _number(value, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{field} must be a finite number")
    return float(value)


def _point(point: dict, item: dict, as_of: datetime) -> dict:
    for key in ("instrument", "unit", "basis", "currency", "session", "source_name"):
        if _text(point, key) != item[key]:
            raise ValueError(f"History {key} differs from current reference")
    source_url = checked_url(_text(point, "source_url"), "history.source_url")
    day = date.fromisoformat(_text(point, "trade_date"))
    observed = checked_time(_text(point, "observed_at"), "observed_at")
    published = checked_time(_text(point, "published_at"), "published_at")
    available = checked_time(_text(point, "available_at"), "available_at")
    if observed > available or published > available or available > as_of:
        raise ValueError("Point was not available by research_as_of")
    if observed.date() != day:
        raise ValueError("Point observation and local trade date disagree")
    if point["session"] == "final_close":
        close = checked_time(_text(point, "session_close_at"), "history.session_close_at")
        if close > available or close.date() != day:
            raise ValueError("History final close is later than availability or on another day")
    return {"trade_date": day.isoformat(), "value": _number(point.get("value"), "point.value"),
            "observed_at": observed.isoformat(), "published_at": published.isoformat(),
            "available_at": available.isoformat(), "source_url": source_url,
            "instrument": item["instrument"], "unit": item["unit"], "basis": item["basis"],
            "currency": item["currency"], "session": item["session"], "source_name": item["source_name"]}


def _reference(item: dict, as_of: datetime) -> dict:
    kind = _text(item, "kind")
    if kind not in KINDS:
        raise ValueError(f"Unsupported reference kind: {kind}")
    for key in ("instrument", "selection_reason", "transmission", "countercase", "unit", "basis",
                "market", "currency", "session", "source_name"):
        _text(item, key)
    checked_url(_text(item, "source_url"), "source_url")
    if kind == "foreign_peer":
        _text(item, "comparability")
        _text(item, "difference")
    if kind in {"yield", "credit_spread"}:
        _text(item, "tenor_or_index")
        if item["unit"] not in {"%", "percent", "bp"}:
            raise ValueError("Yield and spread levels must use percent or bp")
    if kind == "put_call" and item.get("option_scope") not in PUT_CALL_SCOPES:
        raise ValueError("put_call needs a Cboe option_scope")
    if kind == "commodity":
        if item.get("price_type") not in {"spot", "futures"}:
            raise ValueError("commodity needs spot or futures price_type")
        _text(item, "contract_or_grade")
        _text(item, "publication_lag")
    if kind == "policy_probability":
        date.fromisoformat(_text(item, "meeting_date"))
        _text(item, "outcome")
        if item["unit"] not in {"%", "percent"}:
            raise ValueError("FedWatch probability must use percent")
    if item["session"] not in {"final_close", "intraday", "published_daily"}:
        raise ValueError("session must describe final_close, intraday or published_daily")
    _text(item, "market_timezone")
    observed = checked_time(_text(item, "observed_at"), "observed_at")
    published = checked_time(_text(item, "published_at"), "published_at")
    available = checked_time(_text(item, "available_at"), "available_at")
    retrieved = checked_time(_text(item, "retrieved_at"), "retrieved_at")
    if observed > available or published > available or available > as_of or retrieved > as_of:
        raise ValueError("Reference was not available by research_as_of")
    if item["session"] == "final_close":
        close = checked_time(_text(item, "session_close_at"), "session_close_at")
        if close > as_of or close > available:
            raise ValueError("Future close cannot explain earlier A-share trading")
    value = _number(item.get("value"), "value")
    if kind == "policy_probability" and not 0 <= value <= 100:
        raise ValueError("FedWatch probability must be between 0 and 100")
    if kind == "put_call" and value < 0:
        raise ValueError("put/call ratio must be nonnegative")
    if kind in {"foreign_peer", "tech_index", "volatility", "commodity", "fx"} and value < 0:
        raise ValueError("Price/index level or volatility must be nonnegative")
    result = dict(item)
    result.update({"value": value, "observed_at": observed.isoformat(),
                   "published_at": published.isoformat(), "available_at": available.isoformat(),
                   "retrieved_at": retrieved.isoformat(), "status": "ok"})
    expected = item.get("expected_trade_dates", [])
    history = item.get("history", [])
    if not isinstance(expected, list) or not isinstance(history, list):
        raise ValueError("expected_trade_dates and history must be lists")
    expected = [date.fromisoformat(str(day)).isoformat() for day in expected]
    if expected and (len(expected) != 5 or len(set(expected)) != 5 or expected != sorted(expected)):
        raise ValueError("expected_trade_dates must contain five distinct ascending local trading days")
    calendar = item.get("calendar_evidence")
    if expected:
        if not isinstance(calendar, dict) or calendar.get("verification") != "analyst_checked":
            raise ValueError("Five-day window needs manually checked market calendar evidence")
        if _text(calendar, "market") != item["market"] or _text(calendar, "market_timezone") != item["market_timezone"]:
            raise ValueError("Calendar market or timezone differs from reference")
        checked_url(_text(calendar, "source_url"), "calendar.source_url")
        verified = checked_time(_text(calendar, "verified_at"), "calendar.verified_at")
        if verified > as_of or calendar.get("dates") != expected:
            raise ValueError("Calendar dates or verification time do not match the five-day window")
        result["calendar_verification"] = "analyst_checked_source_backed"
    points = [_point(point, item, as_of) for point in history]
    points.sort(key=lambda point: point["trade_date"])
    if kind == "policy_probability" and any(not 0 <= point["value"] <= 100 for point in points):
        raise ValueError("FedWatch history probabilities must be between 0 and 100")
    if kind in {"foreign_peer", "tech_index", "volatility", "put_call", "commodity", "fx"} and any(
            point["value"] < 0 for point in points):
        raise ValueError("Reference history has a negative price, level or ratio")
    if len({point["trade_date"] for point in points}) != len(points):
        raise ValueError("Duplicate trade dates in history")
    if kind == "policy_probability" and any(
            point.get("meeting_date") != item["meeting_date"] or point.get("outcome") != item["outcome"]
            for point in history):
        raise ValueError("Every FedWatch history point needs the same meeting and outcome")
    result["history"] = points
    result["expected_trade_dates"] = expected
    result["valid_points"] = len([point for point in points if point["trade_date"] in expected]) if expected else len(points)
    result["five_day_status"] = "incomplete"
    selected_points = [point for point in points if point["trade_date"] in expected]
    if (expected and item["session"] != "intraday" and
            [point["trade_date"] for point in selected_points] == expected):
        if selected_points[-1]["value"] != value or selected_points[-1]["observed_at"] != observed.isoformat():
            raise ValueError("Current value/time differs from final five-day history point")
        first, last = selected_points[0]["value"], selected_points[-1]["value"]
        if kind == "policy_probability":
            result["five_day_change"] = round(last - first, 4)
            result["five_day_change_unit"] = "percentage_points"
        elif kind in {"yield", "credit_spread"}:
            result["five_day_change"] = round((last - first) * (100 if item["unit"] in {"%", "percent"} else 1), 4)
            result["five_day_change_unit"] = "basis_points"
        elif kind == "volatility":
            result["five_day_change"] = round(last - first, 4)
            result["five_day_change_unit"] = "index_points"
        elif kind == "put_call":
            result["five_day_change"] = round(last - first, 4)
            result["five_day_change_unit"] = "ratio_points"
        elif first != 0:
            result["five_day_change"] = round((last / first - 1) * 100, 4)
            result["five_day_change_unit"] = "percent"
        if "five_day_change" in result:
            result["five_day_status"] = "complete_manual_calendar_review"
    if kind in {"foreign_peer", "tech_index"} and item.get("relative_to"):
        _text(item, "relative_to")
        if item.get("relative_window") != expected or result["five_day_status"] != "complete_manual_calendar_review":
            raise ValueError("Relative performance needs the same verified five-day window")
        checked_url(_text(item, "benchmark_source_url"), "benchmark_source_url")
        benchmark_available = checked_time(_text(item, "benchmark_available_at"), "benchmark_available_at")
        if benchmark_available > as_of:
            raise ValueError("Benchmark was unavailable by research_as_of")
        _text(item, "benchmark_basis")
        result["benchmark_five_day_change"] = _number(item.get("benchmark_five_day_change"),
                                                         "benchmark_five_day_change")
        result["relative_five_day_change"] = round(result["five_day_change"] - result["benchmark_five_day_change"], 4)
        result["relative_change_unit"] = "percentage_points"
        result["relative_change_status"] = "analyst_supplied_benchmark_requires_source_review"
    return result


def validate_cross_market_review(review: dict | None, *, research_as_of: datetime) -> dict:
    if review is None:
        return {"selection_status": "not_reviewed", "references": [], "issues": ["No review file supplied"]}
    try:
        if not isinstance(review, dict):
            raise ValueError("Review must be a JSON object")
        declared = checked_time(_text(review, "research_as_of"), "research_as_of")
        if declared > research_as_of:
            raise ValueError("Review cutoff is later than collection time")
        status = _text(review, "selection_status")
        if status not in {"selected", "none_material", "unavailable"}:
            raise ValueError("Invalid selection_status")
        reason = _text(review, "selection_reason")
        items = review.get("references", [])
        if not isinstance(items, list) or (status != "selected" and items):
            raise ValueError("Only selected reviews may contain references")
        if status != "selected":
            return {"selection_status": status, "selection_reason": reason,
                    "research_as_of": declared.isoformat(), "references": [], "issues": []}
        references, issues = [], []
        for index, item in enumerate(items, 1):
            try:
                references.append(_reference(item, declared))
            except (AttributeError, KeyError, TypeError, ValueError) as exc:
                issues.append(f"reference {index}: {exc}")
        return {"selection_status": "selected" if references else "unavailable",
                "selection_reason": reason, "research_as_of": declared.isoformat(),
                "references": references, "issues": issues}
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        return {"selection_status": "unavailable", "references": [], "issues": [str(exc)]}
