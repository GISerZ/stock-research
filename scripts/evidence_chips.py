"""Bounded BaoStock chip inputs, with a separate AKShare summary fallback."""

from __future__ import annotations

import json
import math
import subprocess
import sys
import time
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta
from pathlib import Path

from evidence_core import normalize_target
from source_runtime import BJ_TZ, SourceRuntime, classify_exception


BS_SOURCE = "baostock_chip_history"
AK_SOURCE = "akshare_chip_summary"
BS_URL = "https://www.baostock.com/"
BS_FIELDS = "date,code,open,high,low,close,volume,amount,turn,tradestatus,adjustflag"
PRICE_KEYS = ("open", "high", "low", "close")
AK_FIELDS = {
    "平均成本": "reported_avg_cost", "获利比例": "reported_profit_ratio",
    "90成本-低": "cost_90_low", "90成本-高": "cost_90_high", "90集中度": "concentration_90",
    "70成本-低": "cost_70_low", "70成本-高": "cost_70_high", "70集中度": "concentration_70",
}


def number(value) -> float:
    if isinstance(value, bool):
        raise ValueError("Boolean is not a market-data number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Non-finite market-data number")
    return result


def _baostock_rows(code: str, market: str, expected: date, api) -> dict:
    logged_in = False
    try:
        login = api.login()
        if login.error_code != "0":
            raise RuntimeError(f"BaoStock login: {login.error_code} {login.error_msg}")
        logged_in = True

        def query(start: date, end: date, adjust: str) -> list[dict]:
            result = api.query_history_k_data_plus(
                f"{market}.{code}", BS_FIELDS, start_date=start.isoformat(),
                end_date=end.isoformat(), frequency="d", adjustflag=adjust)
            rows = []
            if result.error_code != "0":
                raise RuntimeError(f"BaoStock query: {result.error_code} {result.error_msg}")
            while result.next():
                if result.error_code != "0":
                    raise RuntimeError(f"BaoStock page: {result.error_code} {result.error_msg}")
                values = result.get_row_data()
                if len(values) != len(result.fields):
                    raise ValueError("BaoStock row/field lengths differ")
                rows.append(dict(zip(result.fields, values)))
            if result.error_code != "0":
                raise RuntimeError(f"BaoStock incomplete query: {result.error_code} {result.error_msg}")
            if not rows:
                raise ValueError("Empty BaoStock response cannot establish no records")
            return rows

        history = query(expected - timedelta(days=365 * 5 + 2), expected, "2")
        last = date.fromisoformat(history[-1]["date"])
        return {"history": history, "anchor": query(last, last, "3")}
    finally:
        if logged_in:
            api.logout()


def _parse_bar(raw: dict, code: str, market: str, adjust: str) -> dict:
    if not set(BS_FIELDS.split(",")).issubset(raw) or raw["code"] != f"{market}.{code}":
        raise ValueError("BaoStock chip row lacks fields or has the wrong code")
    day = date.fromisoformat(raw["date"]).isoformat()
    if str(raw["adjustflag"]) != adjust:
        raise ValueError("BaoStock price-adjustment flag differs from the request")
    bar = {"date": day, "code": raw["code"], "adjustflag": adjust}
    for key in ("tradestatus", *PRICE_KEYS, "volume", "amount"):
        try:
            # BaoStock can leave volume and amount empty on explicitly suspended days.
            suspended_empty = (key in ("volume", "amount") and bar["tradestatus"] == 0
                               and raw[key] in (None, ""))
            bar[key] = 0.0 if suspended_empty else number(raw[key])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid BaoStock chip value: {day} {key}={raw[key]!r}") from exc
    if bar["tradestatus"] not in (0, 1):
        raise ValueError("Invalid BaoStock trading status")
    bar["tradestatus"] = int(bar["tradestatus"])
    try:
        bar["turn"] = None if raw["turn"] in (None, "") else number(raw["turn"])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid BaoStock chip value: {day} turn={raw['turn']!r}") from exc
    if (min(bar[key] for key in PRICE_KEYS) <= 0 or bar["low"] > min(bar["open"], bar["close"])
            or bar["high"] < max(bar["open"], bar["close"]) or bar["low"] > bar["high"]
            or min(bar["volume"], bar["amount"]) < 0
            or (bar["volume"] == 0) != (bar["amount"] == 0)):
        raise ValueError(f"Inconsistent BaoStock chip prices/volume: {day}")
    if bar["turn"] is not None and bar["turn"] < 0:
        raise ValueError("Negative chip turnover")
    if bar["tradestatus"] == 0:
        if bar["volume"] != 0 or bar["amount"] != 0 or bar["turn"] not in (None, 0):
            raise ValueError("Suspended chip row has activity")
    elif bar["turn"] is None or (bar["volume"] == 0 and bar["turn"] != 0):
        raise ValueError("Trading chip row lacks valid turnover")
    return bar


def _prepare_input(payload: dict, code: str, market: str, expected: date, calendar: list) -> dict:
    start = expected - timedelta(days=365 * 5 + 2)
    bars = []
    previous = None
    for raw in payload["history"]:
        bar = _parse_bar(raw, code, market, "2")
        day = date.fromisoformat(bar["date"])
        if day < start or day > expected or (previous is not None and day <= previous):
            raise ValueError("Chip history is outside range, duplicated or reversed")
        previous = day
        bars.append(bar)
    if not bars:
        raise ValueError("No chip history")
    active = [i for i, bar in enumerate(bars) if bar["tradestatus"] == 1 and bar["volume"] > 0]
    if not active:
        raise ValueError("No traded chip input")
    bars = bars[active[max(0, len(active) - 500)]:]
    last = date.fromisoformat(bars[-1]["date"])
    wanted = {day.isoformat() for day in calendar if bars[0]["date"] <= day.isoformat() <= last.isoformat()}
    actual = {bar["date"] for bar in bars}
    if wanted != actual:
        raise ValueError(f"Chip calendar mismatch; missing={sorted(wanted - actual)[:10]}, "
                         f"unexpected={sorted(actual - wanted)[:10]}")
    if len(payload["anchor"]) != 1:
        raise ValueError("Chip anchor must contain exactly one unadjusted day")
    raw = _parse_bar(payload["anchor"][0], code, market, "3")
    if raw["date"] != bars[-1]["date"]:
        raise ValueError("Chip anchor date differs from the final adjusted bar")
    scale = raw["close"] / bars[-1]["close"]
    for bar in bars:
        for key in PRICE_KEYS:
            bar[f"model_{key}"] = bar[key] * scale
            if not math.isfinite(bar[f"model_{key}"]):
                raise ValueError("Non-finite aligned chip price")
    if any(abs(bars[-1][f"model_{key}"] - raw[key]) > 0.01 + 1e-9 for key in PRICE_KEYS):
        raise ValueError("Adjusted/unadjusted chip OHLC cannot be aligned within 0.01 CNY")
    return {"input_bars": bars,
            "adjustment_anchor": {"trade_date": raw["date"], "scale": scale, "tolerance_cny": 0.01,
                "qfq_ohlc": {key: bars[-1][key] for key in PRICE_KEYS},
                "raw_ohlc": {key: raw[key] for key in PRICE_KEYS}},
            "coverage": {"code": code, "market": market, "calendar_verified": True,
                "query_range": f"{start.isoformat()}..{expected.isoformat()}",
                "first_date": bars[0]["date"], "last_date": last.isoformat(),
                "sdk_deadline_seconds": 45, "missing_dates": []}}


def _summary(code: str, expected: date, now: datetime, ak_api, runtime: SourceRuntime) -> dict:
    frame = runtime.call(AK_SOURCE, ak_api.stock_cyq_em, symbol=code, adjust="")
    if frame is None or frame.empty or not {"日期", *AK_FIELDS}.issubset(frame.columns):
        raise ValueError("Empty or unrecognized AKShare chip summary")
    retained, skipped = [], []
    previous = None
    for _, row in frame.iterrows():
        day = date.fromisoformat(str(row["日期"])[:10])
        if day > now.astimezone(BJ_TZ).date() or (previous is not None and day <= previous):
            raise ValueError("AKShare chip summary dates are future, repeated or reversed")
        previous = day
        if day > expected:
            continue
        if day not in runtime.calendar:
            raise ValueError("AKShare chip date is not in the verified calendar")
        try:
            values = {name: number(row[raw]) for raw, name in AK_FIELDS.items()}
            for key, value in values.items():
                if (key.startswith("concentration_") or key == "reported_profit_ratio"):
                    if not 0 <= value <= 1:
                        raise ValueError("Invalid fractional chip summary value")
                elif value <= 0:
                    raise ValueError("Invalid chip summary cost")
            if not (values["cost_90_low"] <= values["cost_70_low"] <= values["cost_70_high"]
                    <= values["cost_90_high"]):
                raise ValueError("AKShare chip intervals are inconsistent")
        except (KeyError, ValueError, TypeError, OverflowError) as exc:
            skipped.append({"date": day.isoformat(), "reason": str(exc)})
            continue
        retained.append({"as_of_trade_date": day.isoformat(), **values,
            "reported_avg_cost_basis": "median_p50" if getattr(ak_api, "__version__", "") == "1.18.97"
                else "vendor_label_unverified", "basis": "vendor_unadjusted",
            "raw_fields": {raw: values[name] for raw, name in AK_FIELDS.items()}})
    if not retained:
        raise ValueError("No valid completed AKShare chip summary day; rejected=" + json.dumps(skipped, ensure_ascii=False))
    retained[-1]["skipped_invalid_rows"] = skipped
    return retained[-1]


def collect_chip_sources(code: str, market: str, expected_trade_date: date, *, now: datetime,
                         ak_api, baostock_api, runtime: SourceRuntime) -> dict:
    result = {"input_bars": [], "adjustment_anchor": None, "vendor_summary": None,
              "source_results": [], "coverage": {}, "issues": []}
    started = time.monotonic()
    primary = {"source": BS_SOURCE, "source_url": BS_URL, "method": "bounded BaoStock qfq and raw OHLC",
               "status": "ok", "attempts": 1}
    try:
        if market not in {"sh", "sz"} or runtime.calendar_verified is not True:
            raise ValueError("Chip inputs require a supported market and a verified calendar")
        if getattr(baostock_api, "__name__", "") == "baostock":
            process = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--baostock-worker",
                code, market, expected_trade_date.isoformat(), now.isoformat()],
                capture_output=True, encoding="utf-8", errors="replace", timeout=45, check=True)
            payload = json.loads(process.stdout)
            if "error" in payload:
                error_class = ValueError if payload["error_type"] == "parse_error" else RuntimeError
                raise error_class(payload["error"])
        else:
            payload = _baostock_rows(code, market, expected_trade_date, baostock_api)
        result.update(_prepare_input(payload, code, market, expected_trade_date, runtime.calendar))
        primary["coverage"] = dict(result["coverage"])
        primary["status"] = "ok" if result["coverage"]["last_date"] == expected_trade_date.isoformat() else "stale"
        primary["detail"] = "Prices anchored to the final unadjusted close; vendor float turnover model"
        primary = runtime.result(primary)
    except Exception as exc:
        primary = runtime.result(primary, error=exc)
    primary["elapsed_ms"] = round((time.monotonic() - started) * 1000, 2)
    primary["selected_for_output"] = bool(result["input_bars"])
    result["source_results"].append(primary)
    if primary["status"] == "ok":
        return result
    result["issues"].append(f"{BS_SOURCE}: {primary['status']}: {primary.get('detail', '')}")
    backup = {"source": AK_SOURCE, "source_url": f"https://quote.eastmoney.com/{market}{code}.html",
              "method": "akshare.stock_cyq_em(adjust='')", "status": "ok", "fallback_from": [BS_SOURCE]}
    try:
        summary = _summary(code, expected_trade_date, now, ak_api, runtime)
        day = summary["as_of_trade_date"]
        backup.update(status="ok" if day == expected_trade_date.isoformat() else "stale",
                      coverage={"last_date": day, "identity_basis": "requested_symbol",
                                "query_range": "vendor last 90 sessions", "histogram_available": False,
                                "skipped_invalid_rows": summary["skipped_invalid_rows"]},
                      detail=f"Selected {day}; skipped {len(summary['skipped_invalid_rows'])} invalid rows; no histogram")
        if summary["skipped_invalid_rows"]:
            result["issues"].append(f"{AK_SOURCE}: invalid rows excluded; see source coverage for dates/reasons")
        if not result["input_bars"] or day > result["input_bars"][-1]["date"]:
            result.update(input_bars=[], adjustment_anchor=None, vendor_summary=summary,
                          coverage={"calendar_verified": True, **backup["coverage"]})
            primary["selected_for_output"] = False
            backup["selected_for_output"] = True
        else:
            backup["selected_for_output"] = False
        backup = runtime.result(backup)
    except Exception as exc:
        backup = runtime.result(backup, error=exc)
    result["source_results"].append(backup)
    if backup["status"] != "ok":
        result["issues"].append(f"{AK_SOURCE}: {backup['status']}: {backup.get('detail', '')}")
    return result


if __name__ == "__main__":
    if len(sys.argv) != 6 or sys.argv[1] != "--baostock-worker":
        raise SystemExit("Internal worker requires CODE MARKET EXPECTED_DATE NOW")
    try:
        import baostock
        code, market = normalize_target(sys.argv[2])
        expected, now = date.fromisoformat(sys.argv[4]), datetime.fromisoformat(sys.argv[5])
        if market != sys.argv[3] or market not in {"sh", "sz"} or now.utcoffset() != timedelta(hours=8):
            raise ValueError("Invalid worker market or timezone")
        if expected > now.date() or (expected == now.date() and now.hour < 15):
            raise ValueError("Worker requires a completed day")
        with redirect_stdout(sys.stderr):
            payload = _baostock_rows(code, market, expected, baostock)
    except Exception as exc:
        payload = {"error": f"{type(exc).__name__}: {exc}", "error_type": classify_exception(exc)}
    print(json.dumps(payload, ensure_ascii=True, allow_nan=False))
