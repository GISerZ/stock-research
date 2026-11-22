"""Daily A-share market breadth and limit-board snapshots."""

from __future__ import annotations

import re
from datetime import date, datetime, time

from sentiment_core import BJ_TZ
from market_phase import classify_market_phase
from source_runtime import RUNTIME_VERSION, SourceRuntime


CALENDAR_URL = "https://finance.sina.com.cn/realstock/company/klc_td_sh.txt"
ACTIVITY_URL = "https://legulegu.com/stockdata/market-activity"
POOL_URL = "https://quote.eastmoney.com/ztb/detail#type={}"
ACTIVITY_FIELDS = {"上涨": "rising", "下跌": "falling", "平盘": "flat", "停牌": "suspended"}
POOLS = (("limit_up", "stock_zt_pool_em", "ztgc"),
         ("limit_down", "stock_zt_pool_dtgc_em", "dtgc"),
         ("failed_board", "stock_zt_pool_zbgc_em", "zbgc"))
POOL_SCOPE = "Eastmoney limit-board topic pools; excludes ST and STAR stocks; other coverage follows source definition"


class NonTradingDay(ValueError):
    """The source calendar explicitly excludes the requested day."""


def last_five_trade_dates(as_of_date: date, ak_api, runtime: SourceRuntime | None = None) -> list[date]:
    runtime = runtime or SourceRuntime()
    calendar_cached = runtime.calendar_verified is True and bool(runtime.calendar)
    runtime.calendar_verified = False
    frame = runtime.call("sina_trade_calendar", ak_api.tool_trade_date_hist_sina) if not calendar_cached else None
    if calendar_cached:
        dates = runtime.calendar
    else:
        if frame is None or frame.empty or "trade_date" not in frame.columns:
            raise ValueError("Trade calendar is empty or unrecognized")
        dates = sorted({date.fromisoformat(str(value)[:10]) for value in frame["trade_date"]})
        runtime.calendar = dates
    if not dates:
        raise ValueError("Trade calendar has no dates")
    if dates[-1] < as_of_date:
        raise ValueError(f"Trade calendar ends at {dates[-1]}, before {as_of_date}")
    runtime.calendar_verified = True
    if as_of_date not in dates:
        raise NonTradingDay(f"{as_of_date} is not in the source trade calendar")
    previous = [day for day in dates if day <= as_of_date]
    if len(previous) < 5:
        raise ValueError("Trade calendar has fewer than five dates through target day")
    return previous[-5:]


def _result(source: str, status: str, url: str, detail: str = "", *, runtime=None, error=None) -> dict:
    result = {"source": source, "status": status, "source_url": url, "detail": detail}
    return runtime.result(result, error=error) if runtime else result


def _observation(field: str, value: int | None, *, status: str, source: str, url: str,
                 observed_at: str, retrieved_at: str, basis: str, finality: str, scope: str,
                 time_basis: str) -> dict:
    return {"field": field, "value": value, "unit": "家", "basis": basis,
            "source_name": source, "source_url": url, "observed_at": observed_at,
            "retrieved_at": retrieved_at, "scope": scope, "status": status,
            "finality": finality, "observation_time_basis": time_basis}


def _count(value) -> int:
    number = float(str(value).replace(",", ""))
    if number < 0 or not number.is_integer():
        raise ValueError(f"Invalid stock count: {value}")
    return int(number)


def _activity(packet: dict, target_date: date, now: datetime, ak_api, runtime: SourceRuntime) -> None:
    retrieved = now.isoformat()
    values = {}
    observed = retrieved
    status = "source_failure"
    detail = ""
    error = None
    try:
        if target_date != now.date():
            status, detail = "not_supported", "Current-only activity cannot backfill a past day"
        else:
            frame = runtime.call("legulegu_market_activity", ak_api.stock_market_activity_legu)
            if frame is None or frame.empty or not {"item", "value"}.issubset(frame.columns):
                raise ValueError("Empty or unrecognized market activity response")
            rows = {str(row["item"]).strip(): row["value"] for _, row in frame.iterrows()}
            match = re.search(r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})\s+(\d{1,2}:\d{2}(?::\d{2})?)",
                              str(rows.get("统计日期", "")))
            if not match:
                raise ValueError("Source did not provide a dated market-statistics time")
            source_time = datetime.fromisoformat(" ".join(match.groups()).replace("/", "-")).replace(tzinfo=BJ_TZ)
            observed = source_time.isoformat()
            if source_time.date() != target_date or source_time.time() < time(15, 0):
                status, detail = "stale", f"Source statistics time is {observed}, not target close"
            else:
                values = {field: _count(rows[label]) for label, field in ACTIVITY_FIELDS.items()}
                status = "ok"
    except Exception as exc:
        error = exc
        detail = f"{type(exc).__name__}: {exc}"
    result = _result("legulegu_market_activity", status, ACTIVITY_URL, detail, runtime=runtime, error=error)
    result["coverage"] = {"requested_trade_date": target_date.isoformat(), "observed_at": observed,
                          "scope": "沪深两市; current only"}
    status = result["status"]
    packet["source_results"].append(result)
    if detail:
        packet["issues"].append(f"legulegu_market_activity: {detail}")
    for field in ACTIVITY_FIELDS.values():
        packet["observations"].append(_observation(field, values.get(field), status=status,
            source="legulegu_market_activity", url=ACTIVITY_URL, observed_at=observed,
            retrieved_at=retrieved, basis="source statistics date; 沪深两市",
            finality="source_confirmed_close" if status == "ok" else "unconfirmed", scope="沪深两市",
            time_basis="source_statistics" if observed != retrieved else "retrieval_only"))


def _pool(packet: dict, field: str, method: str, pool_type: str, target_date: date,
          now: datetime, ak_api, runtime: SourceRuntime) -> None:
    url = POOL_URL.format(pool_type)
    status, value, detail = "source_failure", None, ""
    error = None
    try:
        frame = runtime.call(method, getattr(ak_api, method), date=target_date.strftime("%Y%m%d"))
        if frame is None:
            raise ValueError("Pool response is unavailable")
        if frame.empty and field == "limit_down":
            value, status, detail = 0, "ok", "AKShare 1.18.97 returned its explicit empty down-limit pool"
        elif frame.empty:
            raise ValueError("Empty pool frame; a valid zero cannot be confirmed")
        elif "代码" not in frame.columns:
            raise ValueError("Pool response lacks stock codes")
        else:
            codes = [str(code).zfill(6) for code in frame["代码"]]
            if len(codes) != len(set(codes)) or any(not re.fullmatch(r"\d{6}", code) for code in codes):
                raise ValueError("Pool contains invalid or duplicate codes")
            value, status = len(frame), "ok"
    except Exception as exc:
        error = exc
        detail = f"{type(exc).__name__}: {exc}"
    result = _result(method, status, url, detail, runtime=runtime, error=error)
    result["coverage"] = {"requested_trade_date": target_date.isoformat(), "scope": POOL_SCOPE,
                          "source_date_confirmed": False}
    status = result["status"]
    packet["source_results"].append(result)
    if detail and status != "ok":
        packet["issues"].append(f"{method}: {detail}")
    packet["observations"].append(_observation(field, value, status=status, source=method,
        url=url, observed_at=now.isoformat(), retrieved_at=now.isoformat(),
        basis=f"requested_trade_date={target_date}; count of returned pool; source date not separately confirmed"
              + ("; limit-up excludes uninterrupted one-price new listings" if field == "limit_up" else ""),
        finality="post_close_fetch", scope=POOL_SCOPE,
        time_basis="retrieval_only; provider observation time unavailable"))


def collect_market_day(target_date: date, *, now: datetime, ak_api,
                       runtime: SourceRuntime | None = None) -> dict:
    now = now.astimezone(BJ_TZ)
    runtime = runtime or SourceRuntime()
    if target_date > now.date() or (target_date == now.date() and now.time() < time(15, 0)):
        raise ValueError("A closing snapshot cannot be collected before the target close")
    packet = {"schema_version": 1, "kind": "market", "as_of_trade_date": target_date.isoformat(),
              "collected_at": now.isoformat(), "scope": "乐咕广度为沪深两市；东财涨跌停专题池排除 ST 与科创板，分别列示",
              "runtime_version": RUNTIME_VERSION, "run_id": runtime.run_id,
              "market_phase": "unknown", "coverage": {"calendar_verified": False},
              "source_results": [], "observations": [], "issues": [], "completeness": "partial"}
    try:
        last_five_trade_dates(target_date, ak_api, runtime)
        packet["coverage"].update(calendar_verified=True, calendar_status="verified")
        packet["market_phase"] = classify_market_phase(now, is_trading_day=(now.date() in runtime.calendar)
            if runtime.calendar[-1] >= now.date() else None)
        packet["source_results"].append(_result("sina_trade_calendar", "ok", CALENDAR_URL, runtime=runtime))
    except NonTradingDay:
        raise
    except Exception as exc:
        packet.update(as_of_trade_date=None, requested_trade_date=target_date.isoformat(), collection_status="failed")
        packet["coverage"].update(calendar_verified=False, calendar_status="failed")
        result = _result("sina_trade_calendar", "source_failure", CALENDAR_URL, runtime=runtime, error=exc)
        result["coverage"] = dict(packet["coverage"])
        packet["source_results"].append(result)
        packet["issues"].append(f"calendar_unavailable: {exc}")
        return packet
    _activity(packet, target_date, now, ak_api, runtime)
    for field, method, pool_type in POOLS:
        _pool(packet, field, method, pool_type, target_date, now, ak_api, runtime)
    packet["completeness"] = ("complete" if all(item["status"] == "ok" for item in packet["source_results"])
                              else "partial")
    return packet
