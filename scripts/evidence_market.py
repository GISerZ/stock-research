"""Timestamped A-share quotes, daily bars, and historical valuation evidence."""

from __future__ import annotations

import math
import json
import subprocess
import sys
import time as clock
from datetime import datetime, timedelta, timezone, time
from inspect import unwrap
from typing import Any

from evidence_core import empty_fragment
from market_phase import classify_market_phase, effective_daily_bar_date
from source_runtime import SourceRuntime


BJ_TZ = timezone(timedelta(hours=8))
BS_FIELDS = "date,code,close,peTTM,pbMRQ,psTTM,pcfNcfTTM,turn,tradestatus,isST"


def _number(raw: Any, *, positive: bool = False) -> float | None:
    if raw is None or raw == "" or isinstance(raw, bool):
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or (positive and value <= 0):
        return None
    return value


def _observation(field: str, value: float, unit: str, when: str, basis: str,
                 source_name: str, source_url: str, retrieved_at: datetime,
                 market_phase: str | None = None) -> dict:
    item = {
        "field": field, "value": value, "unit": unit,
        "period_or_market_time": when, "publication_time": None,
        "retrieved_time": retrieved_at.astimezone(BJ_TZ).isoformat(),
        "basis": basis, "source_name": source_name, "source_url": source_url,
        "verification": "market_vendor",
    }
    if market_phase is not None:
        item["market_phase"] = market_phase
    return item


def _source(source: str, status: str, method: str, url: str, detail: str = "") -> dict:
    return {"source": source, "status": status, "method": method, "source_url": url,
            "detail": detail}


def _quote_attempt(source: str, code: str, market: str, retrieved_at: datetime,
                   http_get, runtime: SourceRuntime) -> tuple[list[dict], dict]:
    url = (f"https://qt.gtimg.cn/q={market}{code}" if source == "tencent_quote" else
           "https://push2.eastmoney.com/api/qt/stock/get")
    retrieved_at = runtime.observation_time(retrieved_at)
    local = retrieved_at.astimezone(BJ_TZ)
    calendar_known = bool(runtime.calendar_verified is True and runtime.calendar
                          and runtime.calendar[-1] >= local.date())
    result = _source(source, "source_failure", "timestamped unadjusted quote", url)
    result["coverage"] = {"code": code, "market": market, "calendar_verified": calendar_known,
                          "calendar_status": "verified" if calendar_known else
                          "not_requested" if runtime.calendar_verified is None else "failed",
                          "market_phase": "unknown", "quote_phase": "unknown",
                          "freshness_cutoff": None, "quote_time_basis": None}
    try:
        get = runtime.http(source, http_get)
        if source == "tencent_quote":
            response = get(url)
            body = response.content.decode("gbk")
            if not body.strip().startswith(f'v_{market}{code}=') or '"' not in body:
                raise ValueError("Tencent quote market prefix or payload mismatch")
            values = body.split('"', 2)[1].split("~")
            if len(values) < 53 or values[2] != code:
                raise ValueError("Tencent quote code or shape mismatch")
            stamp = datetime.strptime(values[30], "%Y%m%d%H%M%S").replace(tzinfo=BJ_TZ)
            raw_time = values[30]
            provider_state = values[40]
            time_basis = "provider_quote_time"
            time_evidence = "https://wzq.gtimg.com/resources/web-quota-page/SuperData_v20260825.js"
            price = _number(values[3], positive=True)
            previous = _number(values[4], positive=True)
            volume, amount = _number(values[6]), _number(values[37])
            amount = amount * 10000 if amount is not None else None
            metrics = [("pe_ttm", values[39], "ratio", 1), ("pb", values[46], "ratio", 1),
                       ("market_cap", values[45], "CNY", 100000000)]
            provider = "腾讯财经"
        else:
            response = get(url, params={"secid": f"{1 if market == 'sh' else 0}.{code}",
                "fltt": "2", "invt": "2", "fields": "f43,f57,f60,f47,f48,f86,f116,f292"})
            data = response.json().get("data")
            if not isinstance(data, dict) or data.get("f57") != code:
                raise ValueError("Eastmoney quote code or shape mismatch")
            stamp = datetime.fromtimestamp(float(data["f86"]), tz=BJ_TZ)
            raw_time = data["f86"]
            provider_state = data.get("f292")
            if provider_state is not None and (isinstance(provider_state, bool) or not isinstance(provider_state, int)):
                raise ValueError("Eastmoney quote trading state is not a numeric status")
            time_basis = "provider_trading_time"
            time_evidence = "https://quote.eastmoney.com/newstatic/build/vendor.js"
            price, previous = _number(data["f43"], positive=True), _number(data["f60"], positive=True)
            volume, amount = _number(data["f47"]), _number(data["f48"])
            metrics = [("market_cap", data.get("f116"), "CNY", 1)]
            provider = "东方财富"
        if price is None or previous is None or amount is None or volume is None or min(amount, volume) < 0:
            raise ValueError("Quote price, previous close, volume or amount invalid")
        phase = classify_market_phase(local, is_trading_day=local.date() in runtime.calendar,
                                      quote_time=stamp) if calendar_known else "unknown"
        eligible = [day for day in runtime.calendar if calendar_known and day <= local.date()
                    and (day < local.date() or local.time() >= time(9, 15))]
        expected = eligible[-1] if eligible else None
        quote_phase = classify_market_phase(stamp, is_trading_day=stamp.date() in runtime.calendar) if (
            calendar_known and runtime.calendar[0] <= stamp.date() <= runtime.calendar[-1]) else "unknown"
        cutoff = None
        if phase in {"intraday", "closing_auction"}:
            cutoff = local - timedelta(minutes=15)
        elif phase == "lunch_break":
            cutoff = local.replace(hour=11, minute=15, second=0, microsecond=0)
        elif expected is not None:
            cutoff = datetime.combine(expected, time(9, 15) if (
                expected == local.date() and phase == "premarket") else time(15), tzinfo=BJ_TZ)
        if source == "tencent_quote":
            state_compatible = provider_state in {"", "0"}
            inactive = not state_compatible
            close_confirmed = False
            if (phase in {"lunch_break", "postmarket", "premarket", "non_trading"}
                    and cutoff is not None and stamp < cutoff):
                cutoff = None
                quote_phase = "unknown"
        else:
            provider_phase = {1: "premarket", 2: "intraday", 3: "lunch_break", 4: "closing_auction",
                              5: "postmarket", 10: "premarket", 11: "premarket", 12: "postmarket",
                              13: "non_trading", 17: "postmarket", 18: "postmarket", 19: "postmarket"}.get(provider_state)
            inactive = provider_state in {6, 7, 8, 9, 14, 15, 16}
            state_compatible = provider_phase == phase or (
                phase in {"premarket", "non_trading"} and expected is not None
                and expected < local.date() and provider_state in {5, 10, 13})
            if provider_state == 10 and expected == local.date():
                state_compatible = False
            close_confirmed = provider_state == 5 and state_compatible and phase in {
                "postmarket", "premarket", "non_trading"}
            if close_confirmed and expected is not None:
                # f292=5 explicitly confirms a completed session; f86 need not be the final transaction at 15:00.
                cutoff = datetime.combine(expected, time(), tzinfo=BJ_TZ)
            elif (phase in {"lunch_break", "postmarket", "premarket", "non_trading"}
                  and cutoff is not None and stamp < cutoff):
                # Trading time can be an earlier last trade; without session confirmation retain only a partial quote.
                cutoff = None
                quote_phase = "unknown"
            result["coverage"]["provider_phase"] = provider_phase or "unknown"
        if inactive:
            cutoff = None
            quote_phase = "unknown"
        stale = (stamp > local + timedelta(minutes=5) or stamp < local - timedelta(days=15)
                 or (not inactive and expected is not None and stamp.date() != expected)
                 or (cutoff is not None and stamp < cutoff))
        current = bool(not stale and calendar_known and expected is not None and quote_phase != "unknown"
                       and state_compatible and not inactive and volume > 0 and amount > 0)
        result["coverage"].update(quote_time=stamp.isoformat(), market_phase=phase,
                                  raw_quote_time=raw_time, quote_phase=quote_phase,
                                  quote_time_basis=time_basis, quote_time_evidence=time_evidence,
                                  provider_state=provider_state, close_confirmed=close_confirmed,
                                  freshness_cutoff=cutoff.isoformat() if cutoff else None,
                                  expected_quote_date=expected.isoformat() if expected else None)
        result.update(status="stale" if stale else "ok" if current else "partial",
                      detail=f"供应商原时间 {stamp.isoformat()}；采集阶段 {phase}；"
                             f"时间口径 {time_basis}；供应商状态 {provider_state!r}；"
                             + ("时效和阶段已核；非交易日/盘前沿原交易日背景使用" if current else
                                "日历/交易状态/活动量额未闭合，候选不能锚定当前评级"))
        if stale:
            return [], runtime.result(result)
        when = stamp.isoformat()
        observations = [_observation("price", price, "CNY/share", when, "unadjusted",
                                     provider, url, retrieved_at, phase),
                        _observation("trading_amount", amount, "CNY", when, "vendor amount",
                                     provider, url, retrieved_at, phase)]
        for field, raw, unit, factor in metrics:
            number = _number(raw, positive=True)
            if number is not None:
                observations.append(_observation(field, number * factor, unit, when,
                    "vendor snapshot", provider, url, retrieved_at, phase))
        return observations, runtime.result(result)
    except Exception as exc:
        return [], runtime.result(result, error=exc)


def collect_quote(code: str, market: str, retrieved_at: datetime, *, http_get,
                  runtime: SourceRuntime | None = None) -> dict:
    """Return a quote-only fragment for the target or an explicitly selected peer."""
    runtime = runtime or SourceRuntime()
    fragment = empty_fragment()
    observations, results = runtime.run_chain(("tencent_quote", "eastmoney_quote"),
        lambda source: _quote_attempt(source, code, market, retrieved_at, http_get, runtime))
    fragment["observations"] = observations or []
    fragment["source_results"] = results
    fragment["issues"] = [f"{item['source']}: {item['status']}: {item.get('detail', '')}"
                          for item in results if item["status"] != "ok"]
    return fragment


def _bar_rows(frame, code: str, market: str, origin: str, retrieved_at: datetime) -> list[dict]:
    if frame is None or frame.empty:
        raise ValueError("Empty daily-bar response cannot establish no records")
    rows = []
    seen = set()
    previous_date = None
    source_name = "腾讯财经" if origin == "tx" else "东方财富"
    url = (f"https://gu.qq.com/{market}{code}" if origin == "tx"
           else f"https://quote.eastmoney.com/{market}{code}.html")
    for _, raw in frame.iterrows():
        when = str(raw["date"] if origin == "tx" else raw["日期"])[:10]
        datetime.strptime(when, "%Y-%m-%d")
        if when > retrieved_at.astimezone(BJ_TZ).date().isoformat():
            raise ValueError(f"Future daily bar: {when}")
        if when in seen:
            raise ValueError(f"Duplicate daily bar: {when}")
        if previous_date is not None and when < previous_date:
            raise ValueError(f"Daily bars are not in ascending date order: {when}")
        seen.add(when)
        previous_date = when
        if origin == "em" and str(raw["股票代码"]).zfill(6) != code:
            raise ValueError("Eastmoney daily bar code mismatch")
        keys = ("open", "high", "low", "close", "volume", "amount") if origin == "tx" else (
            "开盘", "最高", "最低", "收盘", "成交量", "成交额")
        opened, high, low, close = [_number(raw[key], positive=True) for key in keys[:4]]
        volume, amount = [_number(raw[key]) for key in keys[4:]]
        if None in (opened, high, low, close, volume, amount):
            raise ValueError(f"Invalid daily bar numbers: {when}")
        if high < max(opened, close) or low > min(opened, close) or volume < 0 or amount < 0:
            raise ValueError(f"Inconsistent daily bar: {when}")
        if effective_daily_bar_date(retrieved_at, latest_available=datetime.strptime(when, "%Y-%m-%d").date()) is None:
            continue
        shares = volume if origin == "tx" else volume * 100
        rows.extend([
            _observation("daily_close", close, "CNY/share", when, "unadjusted", source_name, url, retrieved_at),
            _observation("daily_volume", shares, "shares", when, "unadjusted", source_name, url, retrieved_at),
            _observation("daily_amount", amount, "CNY", when, "unadjusted", source_name, url, retrieved_at),
        ])
    return rows


def _raw_history_validator(code: str, market: str, origin: str, retrieved_at: datetime,
                           checked_pages: list, *, raw_bars: dict | None = None):
    seen = {}
    def validate(url, response, kwargs):
        if origin == "tx":
            # The listing-date helper also calls Tencent, sometimes with adjusted bars.
            parameter = (kwargs.get("params") or {}).get("param", "")
            if "newfqkline/get" not in url or not parameter.endswith(","):
                return
            parts = parameter.split(",")
            if len(parts) != 6 or parts[:2] != [f"{market}{code}", "day"]:
                raise ValueError("Tencent raw history request target or frequency mismatch")
            page_start = datetime.strptime(parts[2], "%Y-%m-%d").date()
            page_end = datetime.strptime(parts[3], "%Y-%m-%d").date()
            if page_start > page_end:
                raise ValueError("Tencent raw history request window reversed")
            body = response.text
            payload = json.loads(body[body.index("{"):].rstrip(";\r\n "))
            if payload.get("code", 0) != 0:
                raise ValueError("Tencent raw history service returned an error")
            rows = payload["data"][f"{market}{code}"]["day"]
        else:
            if "/kline/get" not in url:
                return
            payload = response.json()
            data = payload.get("data")
            if not isinstance(data, dict) or str(data.get("code", "")) != code:
                raise ValueError("Eastmoney raw history target code mismatch")
            if "market" in data and data["market"] != (1 if market == "sh" else 0):
                raise ValueError("Eastmoney raw history market mismatch")
            raw_rows = data.get("klines")
            if not isinstance(raw_rows, list) or not all(isinstance(row, str) for row in raw_rows):
                raise ValueError("Eastmoney raw history rows malformed")
            rows = [row.split(",") for row in raw_rows]
        if not isinstance(rows, list) or not rows:
            raise ValueError("Empty raw daily-bar page")
        previous = None
        page_dates = set()
        for row in rows:
            if not isinstance(row, (list, tuple)) or len(row) < (9 if origin == "tx" else 7):
                raise ValueError("Raw daily bar lacks fields")
            day = datetime.strptime(str(row[0]), "%Y-%m-%d").date()
            if day in page_dates or (previous is not None and day <= previous):
                raise ValueError("Raw daily dates duplicated or not ascending")
            if day > retrieved_at.astimezone(BJ_TZ).date():
                raise ValueError("Future raw daily bar")
            previous = day
            page_dates.add(day)
            opened, close, high, low = [_number(value, positive=True) for value in row[1:5]]
            volume = _number(row[5])
            amount = _number(row[8 if origin == "tx" else 6])
            if (None in (opened, close, high, low, volume, amount) or volume < 0 or amount < 0
                    or high < max(opened, close) or low > min(opened, close)):
                raise ValueError("Invalid raw daily-bar prices or volume/amount")
            numbers = (opened, close, high, low, volume, amount)
            if day in seen and (origin != "tx" or seen[day] != numbers):
                raise ValueError(f"Raw daily bar overlap conflict or disallowed duplicate: {day}")
            seen[day] = numbers
            if raw_bars is not None:
                raw_bars[day.isoformat()] = numbers
        checked_pages.append(len(rows))
    return validate


def _collect_history(fragment: dict, code: str, market: str, retrieved_at: datetime, ak_api,
                     runtime: SourceRuntime) -> None:
    end = retrieved_at.astimezone(BJ_TZ).date()
    start = end - timedelta(days=370)
    calendar_verified = bool(runtime.calendar_verified is True and runtime.calendar and runtime.calendar[-1] >= end)
    def invoke(origin):
        source = f"akshare_{origin}_history"
        url = (f"https://gu.qq.com/{market}{code}" if origin == "tx"
               else f"https://quote.eastmoney.com/{market}{code}.html")
        method = "stock_zh_a_hist_tx" if origin == "tx" else "stock_zh_a_hist"
        result = _source(source, "source_failure", f"akshare.{method}", url)
        result["coverage"] = {"code": code, "start": start.isoformat(), "end": end.isoformat(),
                              "calendar_verified": calendar_verified,
                              "calendar_status": "verified" if calendar_verified else
                              "not_requested" if runtime.calendar_verified is None else "failed"}
        try:
            params = {"symbol": f"{market}{code}" if origin == "tx" else code,
                      "start_date": start.strftime("%Y%m%d"), "end_date": end.strftime("%Y%m%d"), "adjust": ""}
            if origin == "em":
                params["period"] = "daily"
            checked_pages = []
            raw_bars = {}
            operation = getattr(ak_api, method)
            adapter = unwrap(operation)
            result["coverage"].update(adapter_module=getattr(adapter, "__module__", None),
                adapter_path=getattr(getattr(adapter, "__code__", None), "co_filename", None),
                python_executable=sys.executable)
            frame = runtime.call(source, operation, **params,
                response_validator=_raw_history_validator(code, market, origin, retrieved_at, checked_pages,
                                                          raw_bars=raw_bars))
            if origin == "tx" and checked_pages and frame is not None and not frame.empty:
                # The SDK's whole-row dedup can retain equal consumed bars with different auxiliary turnover.
                frame = frame.drop_duplicates(subset=["date", "open", "high", "low", "close", "volume", "amount"])
            needs_volume_check = origin == "tx" and market == "sz" and code.startswith("000")
            volume_unverified = needs_volume_check and not raw_bars
            if needs_volume_check and raw_bars and frame is not None and not frame.empty:
                volumes = []
                corrected = 0
                for _, row in frame.iterrows():
                    day = str(row["date"])[:10]
                    raw = raw_bars.get(day)
                    volume, amount = _number(row["volume"]), _number(row["amount"])
                    if raw is None or volume is None or amount is None:
                        raise ValueError(f"Tencent SDK row lacks verified raw volume/amount: {day}")
                    shares = raw[4] * 100
                    if (not (math.isclose(volume, raw[4], rel_tol=1e-9, abs_tol=1e-6) or
                             math.isclose(volume, shares, rel_tol=1e-9, abs_tol=1e-6)) or
                            not math.isclose(amount, raw[5] * 10000, rel_tol=1e-9, abs_tol=0.01)):
                        raise ValueError(f"Tencent SDK/raw volume or amount unit mismatch: {day}")
                    corrected += volume != shares
                    volumes.append(shares)
                frame = frame.assign(volume=volumes)
                result["coverage"].update(volume_unit_verified=True, volume_rows_corrected=corrected,
                    volume_basis="raw lots x 100; SDK lots/shares checked per date; amount CNY checked",
                    volume_unit_evidence="https://st.gtimg.com/quotes/hs-fund/bundle.13362df9.js")
            bars = _bar_rows(frame, code, market, origin, retrieved_at)
            if volume_unverified:
                bars = [item for item in bars if item["field"] != "daily_volume"]
            if not bars:
                raise ValueError("No completed daily bars in response")
            dates = [item["period_or_market_time"] for item in bars if item["field"] == "daily_close"]
            if dates[0] < start.isoformat():
                raise ValueError("Daily bars outside requested range")
            if calendar_verified and any(datetime.strptime(day, "%Y-%m-%d").date() not in runtime.calendar for day in dates):
                raise ValueError("Daily bar date is not in the source trading calendar")
            complete_dates = [day for day in runtime.calendar if calendar_verified and start <= day <= end and
                              effective_daily_bar_date(retrieved_at, latest_available=day) is not None]
            gaps = [day.isoformat() for day in complete_dates
                    if dates[0] <= day.isoformat() <= dates[-1] and day.isoformat() not in dates]
            behind = bool(complete_dates and dates[-1] != complete_dates[-1].isoformat())
            result["coverage"].update(first_date=dates[0], last_date=dates[-1], bars=len(dates),
                                      gap_dates=gaps,
                                      effective_daily_bar_date=dates[-1] if calendar_verified else None,
                                      latest_complete_trade_date=complete_dates[-1].isoformat() if complete_dates else None,
                                      raw_pagination_verified=bool(checked_pages),
                                      raw_pages_checked=len(checked_pages))
            if volume_unverified:
                result["coverage"]["volume_unit_verified"] = False
            result.update(status="partial" if not calendar_verified or gaps or volume_unverified else "stale" if behind else "ok",
                          detail=f"{start}..{end}; adjust=none; {len(dates)} bars; "
                                 f"calendar {'verified' if calendar_verified else 'unavailable; completeness unknown'}")
            if volume_unverified:
                result["detail"] += "; sz000 raw volume unit unverified; daily_volume omitted; trying fallback"
            return bars, runtime.result(result)
        except Exception as exc:
            return None, runtime.result(result, error=exc)
    bars, results = runtime.run_chain(["em"] if market == "bj" else ["tx", "em"], invoke)
    fragment["source_results"].extend(results)
    fragment["observations"].extend(bars or [])
    fragment["issues"].extend(f"{item['source']}: {item['status']}: {item.get('detail', '')}"
                              for item in results if item["status"] != "ok")


def _collect_valuation(fragment: dict, code: str, market: str, retrieved_at: datetime, baostock_api) -> None:
    url = "https://www.baostock.com/"
    method = "baostock.query_history_k_data_plus"
    if market == "bj":
        fragment["source_results"].append(_source("baostock_valuation", "not_supported", method, url,
                                                  "BaoStock 不覆盖北交所"))
        return
    end = retrieved_at.astimezone(BJ_TZ).date()
    start = end - timedelta(days=365 * 5 + 2)
    logged_in = False
    coverage = {"start": start.isoformat(), "end": end.isoformat(), "returned_dates": [],
                "first_date": None, "last_date": None, "bars": 0, "iteration_status": "not_started"}
    try:
        login = baostock_api.login()
        if login.error_code != "0":
            raise RuntimeError(f"BaoStock login: {login.error_code} {login.error_msg}")
        logged_in = True
        result = baostock_api.query_history_k_data_plus(
            f"{market}.{code}", BS_FIELDS, start_date=start.isoformat(), end_date=end.isoformat(),
            frequency="d", adjustflag="3")
        if result.error_code != "0":
            raise RuntimeError(f"BaoStock query: {result.error_code} {result.error_msg}")
        count = 0
        previous_day = None
        valuation_observations = []
        while result.next():
            if result.error_code != "0":
                raise RuntimeError(f"BaoStock iteration: {result.error_code} {result.error_msg}")
            values = result.get_row_data()
            if len(values) != len(result.fields):
                raise ValueError("BaoStock row/field lengths differ")
            row = dict(zip(result.fields, values))
            if row.get("code") != f"{market}.{code}":
                raise ValueError("BaoStock valuation code mismatch")
            day = row["date"]
            datetime.strptime(day, "%Y-%m-%d")
            if day < start.isoformat() or day > end.isoformat() or (previous_day is not None and day <= previous_day):
                raise ValueError("BaoStock dates outside range, duplicated or reversed")
            previous_day = day
            if effective_daily_bar_date(retrieved_at, latest_available=datetime.strptime(day, "%Y-%m-%d").date()) is None:
                continue
            count += 1
            coverage["returned_dates"].append(day)
            for field, key in (("pe_ttm_history", "peTTM"), ("pb_history", "pbMRQ"),
                               ("ps_ttm_history", "psTTM"), ("pcf_ttm_history", "pcfNcfTTM")):
                number = _number(row.get(key))
                if number is not None:
                    valuation_observations.append(_observation(field, number, "ratio", day,
                                                                key, "BaoStock", url, retrieved_at))
            turnover = _number(row.get("turn"))
            if turnover is not None and turnover >= 0:
                valuation_observations.append(_observation("turnover_rate_history", turnover,
                                                            "percent", day, "BaoStock turn",
                                                            "BaoStock", url, retrieved_at))
            for field, key in (("trading_status_history", "tradestatus"),
                               ("is_st_history", "isST")):
                flag = _number(row.get(key))
                if flag is not None:
                    if flag not in (0, 1):
                        raise ValueError(f"Invalid BaoStock {key}: {row.get(key)}")
                    valuation_observations.append(_observation(field, flag, "flag", day,
                                                                f"BaoStock {key}: 0/1", "BaoStock",
                                                                url, retrieved_at))
        if result.error_code != "0":
            raise RuntimeError(f"BaoStock terminal state: {result.error_code} {result.error_msg}")
        coverage.update(first_date=coverage["returned_dates"][0] if count else None,
                        last_date=coverage["returned_dates"][-1] if count else None,
                        bars=count, iteration_status="ended_without_reported_error")
        fragment["observations"].extend(valuation_observations)
        fragment["source_results"].append({**_source("baostock_valuation", "partial", method, url,
            f"{start}..{end}; adjustflag=3; {count} rows; calendar coverage pending"), "coverage": coverage})
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError) as exc:
        dates = coverage["returned_dates"]
        coverage.update(iteration_status="failed", bars=len(dates),
                        first_date=dates[0] if dates else None, last_date=dates[-1] if dates else None)
        fragment["source_results"].append({**_source("baostock_valuation", "source_failure", method, url,
                                                  str(exc)), "coverage": coverage})
        fragment["issues"].append(f"BaoStock 历史估值失败：{exc}")
    finally:
        if logged_in:
            try:
                logout = baostock_api.logout()
                if getattr(logout, "error_code", "0") != "0":
                    raise RuntimeError(f"{logout.error_code} {logout.error_msg}")
            except Exception as exc:
                fragment["issues"].append(f"BaoStock logout failed: {exc}")


def _bounded_valuation(fragment: dict, code: str, market: str, retrieved_at: datetime,
                       baostock_api, runtime: SourceRuntime) -> None:
    # BaoStock has blocking sockets without a timeout API; bound the whole SDK process.
    started = clock.monotonic()
    try:
        if market != "bj" and getattr(baostock_api, "__name__", "") == "baostock":
            process = subprocess.run([sys.executable, str(__file__), "--valuation-worker", code, market,
                                      retrieved_at.isoformat()], capture_output=True, encoding="utf-8",
                                     errors="replace", timeout=45, check=True)
            collected = json.loads(process.stdout)
            for key in ("source_results", "observations", "issues"):
                fragment[key].extend(collected[key])
        else:
            _collect_valuation(fragment, code, market, retrieved_at, baostock_api)
        for result in fragment["source_results"]:
            if result["source"] == "baostock_valuation":
                end = retrieved_at.astimezone(BJ_TZ).date()
                calendar_known = bool(runtime.calendar_verified is True and runtime.calendar
                                      and runtime.calendar[-1] >= end)
                coverage = result.setdefault("coverage", {})
                dates = coverage.pop("returned_dates", [])
                coverage.update(code=code, market=market, sdk_deadline_seconds=45,
                                calendar_verified=calendar_known,
                                calendar_status="verified" if calendar_known else "unavailable")
                if result["status"] == "partial":
                    start = datetime.fromisoformat(coverage["start"]).date()
                    calendar_covers_start = calendar_known and runtime.calendar[0] <= start
                    expected = [day.isoformat() for day in runtime.calendar if calendar_known
                                and start <= day <= end and
                                effective_daily_bar_date(retrieved_at, latest_available=day) is not None]
                    returned = set(dates)
                    gaps = [day for day in expected if day not in returned]
                    unexpected = [day for day in dates if calendar_known and
                                  datetime.fromisoformat(day).date() not in runtime.calendar]
                    complete = bool(dates and expected and calendar_covers_start and not gaps and not unexpected)
                    coverage.update(gap_dates=gaps if calendar_known else None,
                                    unexpected_dates=unexpected if calendar_known else None,
                                    latest_complete_trade_date=expected[-1] if expected else None,
                                    calendar_covers_start=calendar_covers_start,
                                    history_coverage="complete_requested_window" if complete else "incomplete_or_unknown")
                    result.update(status="ok" if complete else "partial",
                                  detail=result["detail"].removesuffix("; calendar coverage pending") +
                                  ("; requested window covered" if complete else
                                   "; incomplete/unknown coverage; listing/suspension/normal empty result not established"))
                    if not complete:
                        fragment["issues"].append(f"BaoStock 历史估值覆盖未完整确认：{result['detail']}")
                result.update(attempts=0 if market == "bj" else 1,
                              elapsed_ms=round((clock.monotonic() - started) * 1000, 2),
                              retrieved_at=datetime.now(BJ_TZ).isoformat())
                runtime.result(result)
    except Exception as exc:
        result = runtime.result(_source("baostock_valuation", "source_failure",
            "bounded SDK process", "https://www.baostock.com/"), error=exc)
        result.update(attempts=1, elapsed_ms=round((clock.monotonic() - started) * 1000, 2))
        fragment["source_results"].append(result)
        fragment["issues"].append(f"BaoStock SDK failed or exceeded 45 seconds: {exc}")


def collect_market(code: str, market: str, retrieved_at: datetime, *, http_get, ak_api,
                   baostock_api, runtime: SourceRuntime | None = None) -> dict:
    """Collect independent quote, daily-bar, and valuation evidence."""
    runtime = runtime or SourceRuntime()
    calendar_url = "https://finance.sina.com.cn/realstock/company/klc_td_sh.txt"
    runtime.calendar_verified = False
    try:
        frame = runtime.call("sina_trade_calendar", ak_api.tool_trade_date_hist_sina)
        if frame is None or frame.empty or "trade_date" not in frame.columns:
            raise ValueError("Trade calendar is empty or unrecognized")
        runtime.calendar = sorted({datetime.fromisoformat(str(day)[:10]).date() for day in frame["trade_date"]})
        if not runtime.calendar or runtime.calendar[-1] < retrieved_at.astimezone(BJ_TZ).date():
            raise ValueError("Trade calendar is empty or stale")
        runtime.calendar_verified = True
        calendar_result = runtime.result(_source("sina_trade_calendar", "ok", "AKShare", calendar_url))
    except Exception as exc:
        runtime.calendar = []
        calendar_result = runtime.result(_source("sina_trade_calendar", "source_failure", "AKShare", calendar_url), error=exc)
    calendar_result["coverage"] = {"calendar_verified": runtime.calendar_verified,
                                   "calendar_status": "verified" if runtime.calendar_verified else "failed"}
    fragment = collect_quote(code, market, retrieved_at, http_get=http_get, runtime=runtime)
    fragment["source_results"].append(calendar_result)
    _collect_history(fragment, code, market, retrieved_at, ak_api, runtime)
    _bounded_valuation(fragment, code, market, retrieved_at, baostock_api, runtime)
    return fragment


if __name__ == "__main__":
    from contextlib import redirect_stdout
    import baostock
    if len(sys.argv) != 5 or sys.argv[1] != "--valuation-worker":
        raise SystemExit("Internal BaoStock worker requires code, market, timestamp")
    packet = empty_fragment()
    with redirect_stdout(sys.stderr):
        _collect_valuation(packet, sys.argv[2], sys.argv[3], datetime.fromisoformat(sys.argv[4]), baostock)
    print(json.dumps(packet, ensure_ascii=True, allow_nan=False))
