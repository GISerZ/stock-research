"""Explainable chip model, production snapshot contract, and immutable artifacts."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date, datetime, timedelta
from html import escape
from itertools import count
from pathlib import Path

from evidence_core import normalize_target
from market_phase import MARKET_PHASES, effective_daily_bar_date
from source_runtime import validate_source_result


ALGORITHM_VERSION = "triangular-turnover-v1"
WINDOW = 500
MIN_DAYS = 120
MAX_BINS = 400
PROB_TOL = 1e-8
PRICE_KEYS = ("open", "high", "low", "close")


def _finite(value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Chip value must be a finite number")
    return value


def _prices(bar: dict, prefix: str = "") -> tuple:
    opened, high, low, close = (_finite(bar[prefix + key]) for key in PRICE_KEYS)
    if min(opened, high, low, close) <= 0 or low > min(opened, close) or high < max(opened, close):
        raise ValueError("Inconsistent chip OHLC")
    return opened, high, low, close


def _check_bars(bars: list[dict]) -> None:
    if not isinstance(bars, list) or not bars:
        raise ValueError("Chip model requires nonempty input bars")
    previous = None
    for bar in bars:
        day = date.fromisoformat(bar["date"])
        if previous is not None and day <= previous:
            raise ValueError("Chip model dates repeated or reversed")
        previous = day
        _prices(bar, "model_")
        volume, amount = _finite(bar["volume"]), _finite(bar["amount"])
        state, turn = bar["tradestatus"], bar["turn"]
        if isinstance(state, bool) or state not in (0, 1) or min(volume, amount) < 0:
            raise ValueError("Invalid chip activity")
        if (volume == 0) != (amount == 0):
            raise ValueError("Chip volume and amount disagree")
        if turn is not None and _finite(turn) < 0:
            raise ValueError("Negative turnover")
        if state == 0:
            if volume != 0 or amount != 0 or turn not in (None, 0):
                raise ValueError("Suspended chip row has activity")
        elif turn is None or (volume == 0 and turn != 0):
            raise ValueError("Trading chip row lacks valid turnover")


def _metrics(distribution: list[dict], reference_price: float) -> dict:
    if _finite(reference_price) <= 0:
        raise ValueError("Chip reference price must be positive")
    probabilities = [item["probability"] for item in distribution]
    average = math.fsum(item["price"] * item["probability"] for item in distribution)

    def quantile(fraction: float) -> float:
        cumulative = 0.0
        for item in distribution:
            cumulative += item["probability"]
            if cumulative >= fraction - 1e-12:
                return item["price"]
        return distribution[-1]["price"]

    maximum = max(probabilities)
    peaks = [item["price"] for item in distribution if abs(item["probability"] - maximum) <= 1e-12]
    result = {"reference_price": reference_price, "weighted_avg_cost": average,
              "median_cost": quantile(0.5), "main_peak_price": peaks[0], "main_peak_tied": len(peaks) > 1,
              "profit_ratio": math.fsum(item["probability"] for item in distribution
                                         if item["price"] <= reference_price),
              "price_vs_weighted_avg_cost": reference_price / average - 1}
    for percentage, low_fraction, high_fraction in ((70, 0.15, 0.85), (90, 0.05, 0.95)):
        low, high = quantile(low_fraction), quantile(high_fraction)
        result.update({f"cost_{percentage}_low": low, f"cost_{percentage}_high": high,
                       f"concentration_{percentage}": (high - low) / (high + low)})
    return result


def calculate_chips(bars: list[dict], reference_price: float) -> dict:
    _check_bars(bars)
    active = [bar for bar in bars if bar["tradestatus"] == 1 and bar["volume"] > 0]
    if not active or len(active) > WINDOW:
        raise ValueError("Chip model needs 1..500 traded input days")
    minimum = min(bar["model_low"] for bar in bars)
    maximum = max(bar["model_high"] for bar in bars)
    if minimum == maximum:
        lower, upper, size = minimum, maximum, 1
    else:
        lower, upper = math.floor(minimum * 100) / 100, math.ceil(maximum * 100) / 100
        size = min(MAX_BINS, max(1, round((upper - lower) / 0.01)))
    width = (upper - lower) / size
    distribution = [{"low": lower + i * width,
                     "high": upper if i == size - 1 else lower + (i + 1) * width,
                     "price": lower + (i + 0.5) * width, "probability": 0.0} for i in range(size)]
    weights = None
    residual = 1.0
    clipped, zero_turn = [], []
    for bar in active:
        opened, high, low, close = _prices(bar, "model_")
        daily = [0.0] * size
        if high == low:
            index = 0 if width == 0 else min(size - 1, max(0, int((low - lower) / width)))
            daily[index] = 1.0
        else:
            mode = (opened + high + low + close) / 4

            def cdf(price):
                if price <= low:
                    return 0.0
                if price >= high:
                    return 1.0
                if price <= mode:
                    return (price - low) / (high - low) * (price - low) / (mode - low)
                return 1 - (high - price) / (high - low) * (high - price) / (high - mode)

            daily = [cdf(item["high"]) - cdf(item["low"]) for item in distribution]
            if min(daily) < 0 or abs(math.fsum(daily) - 1) > PROB_TOL:
                raise ValueError("Invalid daily chip probability mass")
            total = math.fsum(daily)
            daily = [value / total for value in daily]
        turnover = min(bar["turn"] / 100, 1.0)
        if bar["turn"] > 100:
            clipped.append(bar["date"])
        if bar["turn"] == 0:
            zero_turn.append(bar["date"])
        if weights is None:
            weights = daily
        else:
            weights = [(1 - turnover) * old + turnover * new for old, new in zip(weights, daily)]
            residual *= 1 - turnover
    total = math.fsum(weights)
    if min(weights) < 0 or abs(total - 1) > PROB_TOL:
        raise ValueError("Invalid final chip probability mass")
    for item, value in zip(distribution, weights):
        item["probability"] = value / total
    issues = []
    if len(active) < MIN_DAYS:
        issues.append(f"short_history: {len(active)} traded days < {MIN_DAYS}")
    if residual > 0.05:
        issues.append(f"initial_state_sensitive: residual={residual:.8g} > 0.05")
    if zero_turn:
        issues.append("zero_turnover_with_volume: " + ",".join(zero_turn))
    if clipped:
        issues.append("turnover_clipped_at_100_percent: " + ",".join(clipped))
    return {"model": {"algorithm_version": ALGORITHM_VERSION, "window": WINDOW,
        "effective_days": len(active), "minimum_days": MIN_DAYS, "bin_count": size, "bin_width": width,
        "initialization": "first_traded_day_distribution", "initial_residual_weight": residual,
        "turnover_clipped_dates": clipped, "zero_turnover_dates": zero_turn,
        "as_of_trade_date": bars[-1]["date"], "price_basis": "last_raw_close_anchored_qfq",
        "limitations": ["model_not_account_inventory", "vendor_float_turnover",
                        "corporate_actions_not_account_level", "taxes_and_fees_excluded"]},
        "distribution": distribution, "metrics": _metrics(distribution, reference_price), "issues": issues}


def validate_chips_snapshot(packet: dict) -> None:
    if not isinstance(packet, dict) or packet.get("schema_version") != 1 or packet.get("kind") != "chips":
        raise ValueError("Unsupported chip snapshot schema")
    json.dumps(packet, allow_nan=False)
    if {"rating", "research_confidence", "new_money_status", "unrated_reason", "buy_range", "hold_range"} & packet.keys():
        raise ValueError("Chip snapshots cannot produce investment judgments")
    target = packet["target"]
    code, market = normalize_target(target["code"], active_bse_codes={target["code"]} if target["market"] == "bj" else None)
    if code != target["code"] or market != target["market"]:
        raise ValueError("Chip snapshot code/market mismatch")
    collected = datetime.fromisoformat(packet["collected_at"])
    if collected.utcoffset() != timedelta(hours=8) or packet["market_phase"] not in MARKET_PHASES:
        raise ValueError("Chip snapshot needs Beijing time and a canonical market phase")
    expected = date.fromisoformat(packet["expected_trade_date"]) if packet["expected_trade_date"] else None
    observed = date.fromisoformat(packet["as_of_trade_date"]) if packet["as_of_trade_date"] else None
    if expected and effective_daily_bar_date(collected, latest_available=expected) is None:
        raise ValueError("Chip expected date is not completed")
    if observed and (expected is None or observed > expected):
        raise ValueError("Chip data date exceeds expected completed date")
    status, mode = packet["collection_status"], packet["data_mode"]
    if status not in {"complete", "partial", "failed", "not_supported"}:
        raise ValueError("Invalid chip collection status")
    for key in ("input_bars", "distribution", "source_results", "observations", "issues"):
        if not isinstance(packet[key], list):
            raise ValueError(f"Chip {key} must be a list")
    if packet["observations"] or not all(isinstance(issue, str) and issue for issue in packet["issues"]):
        raise ValueError("Chip observations must be empty and issues must be text")
    if not isinstance(packet["coverage"], dict) or not packet["source_results"]:
        raise ValueError("Chip snapshot lacks coverage/source diagnostics")
    for source in packet["source_results"]:
        validate_source_result(source, require_source_url=True)
    chart = packet["chart_path"]
    if chart is not None and (not isinstance(chart, str) or not re.fullmatch(
            r"research/evidence/chips/charts/[0-9a-f]{64}\.svg", chart)):
        raise ValueError("Chip chart path must be a content-addressed safe relative SVG path")
    if mode == "unavailable":
        if (status not in {"failed", "not_supported"} or observed is not None or packet["input_bars"]
                or packet["distribution"] or any(packet[key] is not None for key in
                    ("adjustment_anchor", "model", "metrics", "vendor_summary", "chart_path"))
                or not packet["issues"]):
            raise ValueError("Unavailable chips cannot contain inferred values")
        if status == "not_supported" and market != "bj":
            raise ValueError("Only BSE is outside the chip market scope")
        required = {"not_supported"} if status == "not_supported" else {
            "source_failure", "rate_limited", "malformed", "partial"}
        if not any(source["status"] in required for source in packet["source_results"]):
            raise ValueError("Unavailable chips require matching source diagnostics")
        return
    if observed is None or expected is None or status not in {"complete", "partial"}:
        raise ValueError("Available chip results need valid dates and status")
    if packet["coverage"].get("calendar_verified") is not True:
        raise ValueError("Available chip results require a verified calendar")
    source_name = "baostock_chip_history" if mode == "local_distribution" else "akshare_chip_summary"
    if not any(source["source"] == source_name and source.get("selected_for_output") is True
               and source["status"] in {"ok", "stale", "partial"} for source in packet["source_results"]):
        raise ValueError("Chip result lacks its selected source")
    if mode == "vendor_summary":
        summary = packet["vendor_summary"]
        if (status != "partial" or packet["input_bars"] or packet["distribution"]
                or any(packet[key] is not None for key in ("adjustment_anchor", "model", "metrics", "chart_path"))
                or not isinstance(summary, dict) or summary["as_of_trade_date"] != observed.isoformat()):
            raise ValueError("Vendor summary cannot fabricate a local chip distribution")
        for key in ("reported_avg_cost", "cost_70_low", "cost_70_high", "cost_90_low", "cost_90_high"):
            if _finite(summary[key]) <= 0:
                raise ValueError("Invalid vendor chip cost")
        for key in ("reported_profit_ratio", "concentration_70", "concentration_90"):
            if not 0 <= _finite(summary[key]) <= 1:
                raise ValueError("Invalid vendor chip fraction")
        if not summary["cost_90_low"] <= summary["cost_70_low"] <= summary["cost_70_high"] <= summary["cost_90_high"]:
            raise ValueError("Invalid vendor chip intervals")
        if summary["reported_avg_cost_basis"] not in {"median_p50", "vendor_label_unverified"}:
            raise ValueError("Missing vendor cost method")
        return
    if mode != "local_distribution" or packet["vendor_summary"] is not None or market == "bj":
        raise ValueError("Invalid local chip mode")
    bars, anchor, model, bins = packet["input_bars"], packet["adjustment_anchor"], packet["model"], packet["distribution"]
    _check_bars(bars)
    if bars[-1]["date"] != observed.isoformat() or anchor["trade_date"] != observed.isoformat():
        raise ValueError("Chip model/anchor date mismatch")
    scale = _finite(anchor["scale"])
    if scale <= 0 or anchor["tolerance_cny"] != 0.01:
        raise ValueError("Invalid chip adjustment anchor")
    _prices(anchor["qfq_ohlc"])
    _prices(anchor["raw_ohlc"])
    for bar in bars:
        _prices(bar)
        if bar["code"] != f"{market}.{code}" or bar["adjustflag"] != "2":
            raise ValueError("Chip input code or adjustment mismatch")
        if any(not math.isclose(bar[f"model_{key}"], bar[key] * scale, rel_tol=1e-12, abs_tol=1e-8)
               for key in PRICE_KEYS):
            raise ValueError("Chip input price basis mismatch")
    if any(not math.isclose(bars[-1][key], anchor["qfq_ohlc"][key], rel_tol=1e-12, abs_tol=1e-8)
           or abs(bars[-1][f"model_{key}"] - anchor["raw_ohlc"][key]) > 0.01 + 1e-9 for key in PRICE_KEYS):
        raise ValueError("Chip anchor cannot reconcile adjusted and raw OHLC")
    if not 1 <= len(bins) <= MAX_BINS or model["bin_count"] != len(bins):
        raise ValueError("Invalid chip bin count")
    minimum, maximum = min(bar["model_low"] for bar in bars), max(bar["model_high"] for bar in bars)
    lower = minimum if minimum == maximum else math.floor(minimum * 100) / 100
    upper = maximum if minimum == maximum else math.ceil(maximum * 100) / 100
    if (not math.isclose(bins[0]["low"], lower, rel_tol=1e-12, abs_tol=1e-8)
            or not math.isclose(bins[-1]["high"], upper, rel_tol=1e-12, abs_tol=1e-8)
            or (minimum != maximum and _finite(model["bin_width"]) < 0.01 - 1e-8)):
        raise ValueError("Chip grid disagrees with the input price range")
    previous = None
    for item in bins:
        low, high, price, probability = (_finite(item[key]) for key in ("low", "high", "price", "probability"))
        if low < 0 or price <= 0 or high < low or not low <= price <= high or not 0 <= probability <= 1:
            raise ValueError("Invalid chip bin")
        if not math.isclose(price, (low + high) / 2, rel_tol=1e-12, abs_tol=1e-8):
            raise ValueError("Chip representative price is not the bin midpoint")
        if previous is not None and not math.isclose(low, previous, rel_tol=1e-12, abs_tol=1e-8):
            raise ValueError("Chip bins overlap or have gaps")
        if not math.isclose(high - low, model["bin_width"], rel_tol=1e-10, abs_tol=1e-8):
            raise ValueError("Chip bins do not use the declared width")
        previous = high
    if abs(math.fsum(item["probability"] for item in bins) - 1) > PROB_TOL:
        raise ValueError("Chip probability sum is not one")
    active = [bar for bar in bars if bar["tradestatus"] == 1 and bar["volume"] > 0]
    residual = math.prod(1 - min(bar["turn"] / 100, 1) for bar in active[1:])
    if (not 1 <= len(active) <= WINDOW or model["effective_days"] != len(active)
            or model["algorithm_version"] != ALGORITHM_VERSION or model["window"] != WINDOW
            or model["minimum_days"] != MIN_DAYS or model["as_of_trade_date"] != observed.isoformat()
            or not math.isclose(_finite(model["initial_residual_weight"]), residual, abs_tol=1e-12)):
        raise ValueError("Chip model metadata disagrees with input")
    expected_metrics = _metrics(bins, anchor["raw_ohlc"]["close"])
    for key, value in expected_metrics.items():
        actual = packet["metrics"][key]
        if isinstance(value, bool):
            if not isinstance(actual, bool) or value != actual:
                raise ValueError("Chip peak tie flag disagrees with distribution")
        elif not math.isclose(_finite(actual), value, rel_tol=1e-10, abs_tol=1e-8):
            raise ValueError(f"Chip metric disagrees with distribution: {key}")
    if status == "complete" and (observed != expected or len(active) < MIN_DAYS or residual > 0.05
                                  or packet["issues"]):
        raise ValueError("Incomplete chip model cannot be marked complete")


def render_chip_svg(packet: dict) -> str:
    if packet["data_mode"] != "local_distribution" or not packet["distribution"]:
        raise ValueError("A vendor summary has no chip chart")
    bins, metrics = packet["distribution"], packet["metrics"]
    minimum, maximum = bins[0]["low"], bins[-1]["high"]
    if minimum == maximum:
        margin = max(0.01, minimum * 0.01)
        minimum, maximum = minimum - margin, maximum + margin
    y = lambda price: 610 - (price - minimum) / (maximum - minimum) * 500
    peak = max(item["probability"] for item in bins)
    title = escape(f"{packet['target']['code']} 筹码分布 · {packet['as_of_trade_date']} · 模型估算")
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1060" height="760" viewBox="0 0 1060 760" role="img">',
        f'<title>{title}</title><desc>横轴为单档估计权重，纵轴为价格。模型不识别主力账户。</desc>',
        '<rect width="1060" height="760" fill="white"/><g font-family="sans-serif" fill="#263238">',
        f'<text x="40" y="40" font-size="22">{title}</text>',
        '<text x="40" y="72" font-size="14">参考价以下：红色（模型获利部分）；参考价以上：绿色（模型套牢部分）</text>']
    for item in bins:
        height = max(0.8, y(item["low"]) - y(item["high"]))
        color = "#c63c3c" if item["price"] <= metrics["reference_price"] else "#2d8553"
        parts.append(f'<rect x="140" y="{y(item["price"]) - height / 2:.3f}" '
                     f'width="{item["probability"] / peak * 560:.3f}" height="{height:.3f}" fill="{color}"/>')
    for i in range(6):
        price = minimum + (maximum - minimum) * i / 5
        parts.append(f'<text x="125" y="{y(price) + 5:.2f}" text-anchor="end" font-size="13">{price:.2f}</text>')
        x = 140 + 560 * i / 5
        parts.append(f'<text x="{x:.2f}" y="635" text-anchor="middle" font-size="12">{peak * i / 5:.2%}</text>')
    parts.append('<path d="M140 105V615H705" fill="none" stroke="#546e7a"/>'
                 '<text x="30" y="100" font-size="13">价格（元/股）</text>'
                 '<text x="365" y="664" font-size="14">单档估计权重（%）</text>')
    for i, (key, label, color) in enumerate((
            ("reference_price", "参考收盘价", "#263238"), ("weighted_avg_cost", "加权平均成本", "#b17c00"),
            ("median_cost", "中位成本", "#385fad"), ("main_peak_price", "主峰价", "#7e4196"))):
        value = metrics[key]
        parts.append(f'<path d="M140 {y(value):.3f}H705" stroke="{color}" stroke-dasharray="5 4"/>'
                     f'<text x="735" y="{130 + i * 34}" fill="{color}" font-size="15">{label}：{value:.4f}</text>')
    for i, text in enumerate((
            f"70%成本区间：{metrics['cost_70_low']:.2f}–{metrics['cost_70_high']:.2f}",
            f"90%成本区间：{metrics['cost_90_low']:.2f}–{metrics['cost_90_high']:.2f}",
            f"模型获利比例：{metrics['profit_ratio']:.2%}",
            f"有效成交日：{packet['model']['effective_days']}",
            f"初始化残留：{packet['model']['initial_residual_weight']:.2%}",
            f"实际箱宽：{packet['model']['bin_width']:.6g} 元",
            "主峰并列：" + ("是（取低价档）" if metrics["main_peak_tied"] else "否"))):
        parts.append(f'<text x="735" y="{300 + i * 32}" font-size="14">{escape(text)}</text>')
    parts.extend([f'<text x="40" y="704" font-size="13">算法：{ALGORITHM_VERSION}；历史窗口最多500个成交日；状态：{escape(packet["collection_status"])}</text>',
        '<text x="40" y="733" font-size="13">供应商换手衰减模型；忽略税费，不代表真实账户成本，也不产生投资评级。</text></g></svg>'])
    return "\n".join(parts) + "\n"


def save_chips_snapshot(packet: dict, workspace: Path) -> Path:
    validate_chips_snapshot(packet)
    workspace = Path(workspace).expanduser().resolve()
    base = workspace / "research/evidence/chips"
    if not base.resolve().is_relative_to(workspace):
        raise ValueError("Chip output directory escapes workspace")
    base.mkdir(parents=True, exist_ok=True)
    if packet["data_mode"] == "local_distribution":
        try:
            svg = render_chip_svg(packet)
            digest = hashlib.sha256(svg.encode("utf-8")).hexdigest()
            charts = base / "charts"
            if not charts.resolve().is_relative_to(base.resolve()):
                raise ValueError("Chip chart directory escapes chip artifacts")
            charts.mkdir(exist_ok=True)
            chart = charts / f"{digest}.svg"
            try:
                with chart.open("x", encoding="utf-8", newline="\n") as output:
                    output.write(svg)
            except FileExistsError:
                if chart.read_text(encoding="utf-8") != svg:
                    raise OSError("Existing chip chart differs from its content hash")
            packet["chart_path"] = chart.relative_to(workspace).as_posix()
        except OSError as exc:
            packet["chart_path"] = None
            packet["issues"].append(f"chart_unavailable: {exc}")
            packet["collection_status"] = "partial"
    validate_chips_snapshot(packet)
    stem = f"{packet['collected_at'][:10]}-{packet['target']['code']}"
    content = json.dumps(packet, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    for version in count(1):
        path = base / (f"{stem}.json" if version == 1 else f"{stem}-v{version}.json")
        try:
            with path.open("x", encoding="utf-8", newline="\n") as output:
                output.write(content)
        except FileExistsError:
            continue
        except OSError:
            path.unlink(missing_ok=True)
            raise
        try:
            if json.loads(path.read_text(encoding="utf-8")) != packet:
                raise OSError("Chip snapshot read-back differs")
        except (OSError, ValueError):
            path.unlink(missing_ok=True)
            raise
        return path
