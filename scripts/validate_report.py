"""Read-only checks for a Markdown report and its exact local evidence versions."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date
from pathlib import Path, PureWindowsPath
from urllib.parse import unquote, urlsplit

from evidence_core import validate_packet
from chips_core import validate_chips_snapshot
from market_phase import normalize_market_phase
from sentiment_core import validate_snapshot


LINK = re.compile(r"\[[^\]\n]*\]\(\s*(<[^>]+>|[^\s)]+)(?:\s+\"[^\"]*\")?\s*\)")
RANGE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:(?:—|–|-|~|～|至)\s*\d+(?:\.\d+)?|"
    r"(?:<=|>=|[<>≤≥＜＞])\s*(?:P|价格|股价)\s*(?:<=|>=|[<>≤≥＜＞])\s*\d+(?:\.\d+)?)"
)
PHASE = re.compile(r"premarket|intraday|lunch_break|closing_auction|postmarket|non_trading|unknown|"
                   r"盘前|集合竞价|连续交易|连续竞价|盘中|午休|收盘竞价|盘后|收盘|非交易日|未知")


def read_json(path: Path, *, allow_list: bool = False) -> dict | list:
    def reject_constant(value):
        raise ValueError(f"Non-finite JSON value: {value}")
    value = json.loads(path.read_text(encoding="utf-8-sig"), parse_constant=reject_constant)
    if not isinstance(value, dict) and not (allow_list and isinstance(value, list)):
        raise ValueError("Snapshot must be a JSON object")
    return value


def _field(text: str, labels: str) -> str:
    match = re.search(r"(?m)^[ \t]*(?:>[ \t]*|[-*][ \t]*)?(?:\*\*)?(?:" + labels +
                      r")(?:\*\*)?[ \t]*[:：][ \t]*(.+)$", text)
    return match.group(1).strip().strip("*") if match else ""


def _metadata_header(text: str) -> str:
    labels = (r"股票代码|代码|股票简称|股票名称|公司名称|研究日期|研究日|"
              r"(?:研究)?资料截[止至](?:时间)?|行情时间与交易状态|行情时间.*阶段|行情|当前行情|"
              r"(?:核心)?证据包.*|情绪(?:快照|包).*|筹码快照.*|最近完整(?:A股)?交易日.*")
    lines = []
    for line in text.splitlines():
        if re.match(r"^\s*#{2,6}\s", line):
            break
        parts = re.split(r"[；;]\s*(?=(?:\*\*)?(?:" + labels + r")(?:\*\*)?\s*[:：])", line)
        for part in parts:
            match = re.match(r"^\s*(?:>\s*|[-*]\s+)?([^:：]+)[:：]\s*(.+)$", part)
            if match:
                key = re.sub(r"[\s*]", "", match.group(1))
                if re.fullmatch(labels, key):
                    lines.append(f"> {key}: {match.group(2).strip().lstrip('*').strip()}")
    return "\n".join(lines)


def _band_lines(text: str, kind: str) -> list[str]:
    found = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not re.search(kind + r"(?:参考|考察|价格)?(?:区间|价带|价格带|范围|区)", line):
            continue
        if re.search(r"前次|历史|旧价|原区间|已失效", line):
            continue
        context = [line]
        if line.lstrip().startswith("#"):
            for following in lines[index + 1:]:
                if following.lstrip().startswith("#") or (not following.strip() and len(context) > 1):
                    break
                if following.strip():
                    context.append(following)
        found.append(" ".join(context))
    return found


def validate_report(report_path: Path, workspace: Path, *, content: str | None = None) -> dict:
    workspace = Path(workspace).expanduser().resolve()
    report_path = Path(report_path).expanduser()
    report_path = (report_path if report_path.is_absolute() else workspace / report_path).resolve()
    result = {"verification_scope": "structure_and_local_references_only",
              "errors": [], "warnings": [], "evidence_paths": [], "auxiliary_paths": [],
              "source_summary": {}, "rating_contract": {}}
    errors, warnings = result["errors"], result["warnings"]
    try:
        text = report_path.read_text(encoding="utf-8-sig") if content is None else content
    except (OSError, UnicodeError) as exc:
        errors.append(f"Report unreadable: {exc}")
        return result
    text = re.sub(r"<!--[\s\S]*?-->|```[\s\S]*?```", "", text)
    header = _metadata_header(text)
    title = next((line for line in text.splitlines() if line.startswith("# ")), "")
    code_match = re.search(r"(?<!\d)\d{6}(?!\d)", _field(header, "股票代码|代码") or title)
    code = code_match.group() if code_match else None
    if not code:
        errors.append("Missing target code in report metadata/title")
    filename = re.match(r"\d{4}-\d{2}-\d{2}-(\d{6})(?:-(.*?))?(?:-v\d+)?\.md$", report_path.name)
    if filename and code and filename.group(1) != code:
        errors.append("Report filename and target code disagree")
    name = _field(header, "股票简称|股票名称|公司名称")
    if not name and filename and filename.group(2):
        candidate = re.sub(r"-v\d+$", "", filename.group(2))
        if candidate in title:
            name = candidate
    if not name:
        errors.append("Missing stock name in metadata/title")
    for label, pattern in (
        ("研究日期", "研究日期|研究日"),
        ("资料截止时间", "研究资料截[止至]时间|研究资料截[止至]|资料截[止至](?:时间)?|资料截止"),
        ("行情时间/阶段", "行情时间与交易状态|行情时间.*阶段|行情|当前行情"),
        ("证据包及采集时间", "(?:核心)?证据包[^：:\\n]*"),
        ("情绪快照及采集时间", "情绪(?:快照|包)[^：:\\n]*"),
        ("最近完整交易日", "最近完整\\s*(?:A\\s*股\\s*)?交易日[^：:\\n]*"),
    ):
        value = _field(header, pattern)
        # Some historical headers combine cutoff and latest-completed-day on one line.
        if label == "最近完整交易日" and not value:
            value = re.search(r"最近完整\s*(?:A\s*股\s*)?交易日\s*[:：]\s*\d{4}-\d{2}-\d{2}", header)
        if not value or (isinstance(value, str) and re.search(r"\{\{|待填写|待补充", value)):
            errors.append(f"Missing metadata: {label}")
        elif label in {"证据包及采集时间", "情绪快照及采集时间"} and not re.search(r"\d{1,2}:\d{2}", value):
            if not re.search(r"未采集|不可用|失败|缺失|无法", value):
                errors.append(f"Missing collection time: {label}")
    research_date = _field(header, "研究日期|研究日")
    day_match = re.search(r"\d{4}-\d{2}-\d{2}", research_date)
    if day_match:
        try:
            date.fromisoformat(day_match.group())
        except ValueError:
            errors.append("Invalid research date")
        if filename and not report_path.name.startswith(day_match.group()):
            errors.append("Report filename and research date disagree")
    else:
        errors.append("Missing ISO research date")
    cutoff = _field(header, "研究资料截[止至]时间|研究资料截[止至]|资料截[止至](?:时间)?")
    if not re.search(r"\d{4}-\d{2}-\d{2}[ T]+\d{1,2}:\d{2}", cutoff):
        errors.append("Research cutoff needs a date and time")
    quote_header = _field(header, "行情时间与交易状态|行情时间.*阶段|行情|当前行情")
    if not re.search(r"\d{4}-\d{2}-\d{2}[ T]+\d{1,2}:\d{2}", quote_header) or not PHASE.search(quote_header):
        if re.search(r"不可核验|无法核验|未取得|来源失败|缺失|未知|不可用", quote_header):
            warnings.append("Quote unavailable; report must remain unrated")
        else:
            errors.append("Quote metadata needs provider timestamp and market phase")

    links = [(match.group(1).strip("<>"), False) for match in LINK.finditer(text)]
    links.extend((match.group(1), True) for match in re.finditer(r"`([^`\n]+\.(?:json|md))`", text)
                 if re.match(r"(?:research[/\\]|evidence[/\\]|[A-Za-z]:[/\\])", match.group(1)))
    resolved, previous_reports = {}, []
    linked_chip_charts, declared_chip_charts = {}, set()
    for raw, workspace_relative in links:
        if raw.startswith("#"):
            continue
        raw = unquote(raw.split("#", 1)[0]).replace("\\", "/")
        if re.match(r"^https?://", raw, re.I):
            continue
        if urlsplit(raw).scheme and not PureWindowsPath(raw).is_absolute():
            errors.append(f"Unsupported local link: {raw}")
            continue
        absolute = Path(raw).is_absolute() or PureWindowsPath(raw).is_absolute() or raw.startswith("//")
        if absolute:
            errors.append(f"Use a portable relative link instead of absolute path: {raw}")
            target = Path(raw).resolve()
        else:
            target = ((workspace if workspace_relative and raw.startswith("research/") else report_path.parent) / raw).resolve()
            if not workspace_relative and report_path.parent.name == "research" and raw.startswith("research/"):
                errors.append(f"Remove the extra research/ prefix from report-relative link: {raw}")
            if (".." in Path(raw).parts and target.suffix.lower() in {".json", ".md"}
                    and target.is_relative_to(report_path.parent)):
                errors.append(f"Normalize report/evidence link inside research/: {raw}")
        if not target.is_relative_to(workspace):
            errors.append(f"Local link escapes workspace: {raw}")
            continue
        is_chip_chart = target.suffix.lower() == ".svg" and target.is_relative_to(workspace / "research/evidence/chips/charts")
        if is_chip_chart:
            linked_chip_charts[target] = raw
        if target == report_path and content is not None:
            continue
        if not target.is_file():
            if not is_chip_chart:
                errors.append(f"Missing local link target: {raw}")
            continue
        if target.suffix.lower() == ".json":
            resolved[target] = raw
        elif (target.suffix.lower() == ".md" and target != report_path and target.parent == report_path.parent
              and code and re.search(r"-" + code + r"(?:-|\.md$)", target.name)):
            previous_reports.append(target)

    packets = []
    for path in resolved:
        relative = path.relative_to(workspace).as_posix()
        try:
            packet = read_json(path, allow_list=True)
            named_snapshot = bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}-\d{6}(?:-v\d+)?\.json", path.name)
                                  or (path.parent.name == "market" and re.fullmatch(
                                      r"\d{4}-\d{2}-\d{2}(?:-v\d+)?\.json", path.name)))
            structured_snapshot = isinstance(packet, dict) and (
                "source_results" in packet or packet.get("kind") in ("market", "stock")
                or ("schema_version" in packet and "target" in packet))
            if not named_snapshot and not structured_snapshot:
                result["auxiliary_paths"].append(relative)
                continue
            result["evidence_paths"].append(relative)
            if not isinstance(packet, dict):
                raise ValueError("Snapshot must be a JSON object")
            is_chips = packet.get("kind") == "chips"
            validator = (validate_chips_snapshot if is_chips else
                         validate_snapshot if packet.get("kind") in {"market", "stock"} else validate_packet)
            validator(packet)
            if packet.get("collection_status") == "failed" and not is_chips:
                raise ValueError("Diagnostic snapshot cannot serve as completed report evidence")
            if packet.get("kind") != "market" and packet["target"]["code"] != code:
                errors.append(f"Snapshot target differs from report: {relative}")
            identity = re.match(r"(\d{4}-\d{2}-\d{2})-(\d{6})(?:-v\d+)?\.json$", path.name)
            expected_day = packet["collected_at"][:10] if is_chips else packet.get("as_of_trade_date", packet["collected_at"][:10])
            if is_chips and (identity is None or path.parent != workspace / "research/evidence/chips"):
                errors.append(f"Chip snapshot needs its canonical dated path: {relative}")
            if identity and (identity.group(1) != expected_day or identity.group(2) != packet.get("target", {}).get("code")):
                errors.append(f"Snapshot filename and contents disagree: {relative}")
            if is_chips:
                if packet["collection_status"] != "complete":
                    warnings.append(f"Chip result is {packet['collection_status']}; disclose mode/date/limitations: {relative}")
                if packet["as_of_trade_date"] and packet["as_of_trade_date"] != packet["expected_trade_date"]:
                    warnings.append(f"Chip snapshot uses an older completed day: {relative}")
                if packet["chart_path"]:
                    chart = (workspace / packet["chart_path"]).resolve()
                    if (not chart.is_relative_to(workspace) or not chart.is_relative_to(
                            workspace / "research/evidence/chips/charts")):
                        raise ValueError("Chip chart escapes its artifact directory")
                    if not chart.is_file():
                        warnings.append(f"Declared chip chart is missing: {packet['chart_path']}")
                    elif hashlib.sha256(chart.read_bytes()).hexdigest() != chart.stem:
                        raise ValueError("Chip chart content hash differs from the snapshot path")
                    declared_chip_charts.add(chart)
            packets.append((path, packet))
            for line in header.splitlines():
                if not re.search(r"证据包|情绪快照|情绪包|筹码快照", line):
                    continue
                matches = list(LINK.finditer(line))
                for index, match in enumerate(matches):
                    raw = unquote(match.group(1).strip("<>").split("#", 1)[0]).replace("\\", "/")
                    if re.match(r"https?://", raw):
                        continue
                    if (report_path.parent / raw).resolve() != path:
                        continue
                    segment = line[match.end():matches[index + 1].start() if index + 1 < len(matches) else len(line)]
                    declared_clock = re.search(r"\d{1,2}:\d{2}(?::\d{2})?", segment)
                    if declared_clock and declared_clock.group() not in packet["collected_at"]:
                        errors.append(f"Reported collection time differs from snapshot: {relative}")
            summary = {"collected_at": packet["collected_at"], "statuses": {}, "fallbacks": []}
            if any("market_phase" in item and item["market_phase"] != "unknown"
                   and normalize_market_phase(item["market_phase"]) == "unknown"
                   for item in packet["observations"]):
                warnings.append(f"Unknown or ambiguous legacy market phase; verify manually: {relative}")
            for source in packet["source_results"]:
                summary["statuses"][source["status"]] = summary["statuses"].get(source["status"], 0) + 1
                if source.get("fallback_from"):
                    summary["fallbacks"].append({key: source.get(key) for key in
                        ("source", "status", "fallback_from", "coverage")})
                    prior = source["fallback_from"]
                    if isinstance(prior, str):
                        prior = [prior]
                    if source["source"] not in text or any(name not in text for name in prior):
                        warnings.append(f"Disclose failed source, final source and fallback coverage: {relative}")
            result["source_summary"][relative] = summary
            if packet.get("completeness") == "partial":
                warnings.append(f"Sentiment gaps remain; review exact coverage: {relative}")
        except (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError) as exc:
            errors.append(f"Invalid JSON evidence or attachment {relative}: {exc}")

    for path, raw in linked_chip_charts.items():
        if path not in declared_chip_charts:
            errors.append(f"Chip chart is not declared by a referenced valid chip snapshot: {raw}")
    evidence = [(path, packet) for path, packet in packets if "kind" not in packet]
    sentiments = [(path, packet) for path, packet in packets if packet.get("kind") == "stock"]
    if not evidence:
        errors.append("No readable core evidence packet referenced")
    if not sentiments:
        warnings.append("No readable stock sentiment snapshot referenced; disclose the gap")
    for _, packet in sentiments:
        if not isinstance(packet.get("market_five_days", []), list) or not isinstance(packet.get("market_snapshot_paths", []), list):
            errors.append("Invalid stock sentiment market-reference lists")
            continue
        expected_market_dates = {entry.get("snapshot_path"): entry.get("trade_date")
                                 for entry in packet.get("market_five_days", []) if isinstance(entry, dict)}
        for raw in packet.get("market_snapshot_paths", []):
            if raw is None:
                warnings.append("Stock sentiment references a missing market day")
                continue
            if not isinstance(raw, str):
                errors.append("Market snapshot path must be a string or null")
                continue
            target = Path(raw)
            if not target.is_absolute():
                target = workspace / target
            if not target.resolve().is_relative_to(workspace) or not target.is_file():
                errors.append(f"Missing or outside-workspace market snapshot reference: {raw}")
                continue
            try:
                market = read_json(target)
                validate_snapshot(market)
                if market.get("kind") != "market":
                    raise ValueError("Expected market snapshot")
                expected_date = expected_market_dates.get(raw)
                if expected_date and market["as_of_trade_date"] != expected_date:
                    raise ValueError("Referenced market date differs from stock snapshot")
            except (OSError, ValueError, KeyError, TypeError) as exc:
                errors.append(f"Invalid referenced market snapshot: {raw}: {exc}")

    core = re.split(r"\n##\s+", text, maxsplit=2)
    conclusion = core[1] if len(core) > 1 else text[:4000]
    rating = re.search(r"(?:评级\s*[:：]\s*\**\s*(买入|增持|持有|减持|回避))|(?:数据不足[，,、\s]*暂不评级)", conclusion)
    rating_value = rating.group(1) or "数据不足，暂不评级" if rating else None
    contract = result["rating_contract"]
    contract.update(rating=rating_value, code=code,
                    holding_period=_field(conclusion, "评级适用期限|持有期(?:限)?|适用期限"),
                    buy_bands=_band_lines(text, "买入"), hold_bands=_band_lines(text, "持有"),
                    reduce_bands=_band_lines(text, "减持"))
    if not rating:
        errors.append("Missing explicit rating or 数据不足，暂不评级")
    if rating_value == "数据不足，暂不评级":
        if any(RANGE.search(line) for line in contract["buy_bands"] + contract["hold_bands"] + contract["reduce_bands"]):
            errors.append("Unrated report must leave executable price bands empty")
    elif rating_value:
        if not contract["holding_period"] and not re.search(r"(?:\d+[—–~至-]?)?\d+\s*(?:个?月|年|周)", conclusion):
            errors.append("Rated report needs a holding period")
        if not re.search(r"公式|计算|×|乘|\d\s*\*\s*\d", text) or not re.search(r"失效|触发|重估|重新评估", text):
            errors.append("Rated report needs valuation formula and invalidation conditions")
        if not re.search(r"https://(?:[A-Za-z0-9-]+\.)*(?:cninfo\.com\.cn|szse\.cn|sse\.com\.cn|bse\.cn)/", text):
            errors.append("Rated report needs a direct original disclosure link")
        if "股本" not in text:
            errors.append("Rated report needs a share-basis disclosure for manual verification")
        if rating_value in {"买入", "增持", "持有"}:
            if not all(any(RANGE.search(line) for line in contract[key]) for key in ("buy_bands", "hold_bands")):
                errors.append("Positive/hold rating needs numeric buy and hold bands")
        elif "暂不买入" not in conclusion or any(RANGE.search(line) for line in contract["buy_bands"]):
            errors.append("Reduce/avoid rating must say 暂不买入 and omit numeric buy bands")
        if evidence:
            current_path, current = max(evidence, key=lambda item: item[1]["collected_at"])
            current_links = [unquote(match.group(1).strip("<>").split("#", 1)[0]).replace("\\", "/")
                             for line in header.splitlines() if "证据包" in line and "前次" not in line
                             for match in LINK.finditer(line)]
            declared = [(path, packet) for path, packet in evidence if any(
                (report_path.parent / raw).resolve() == path for raw in current_links)]
            if declared:
                current_path, current = declared[0]
            quotes = [item for item in current["observations"] if item["field"] == "price"]
            if not quotes or any(item.get("market_phase") == "unknown" for item in quotes):
                errors.append("Rated report lacks a verified timestamped quote/market phase in current evidence")
            elif quotes:
                quote = quotes[0]
                contract["evidence_quote"] = {key: quote.get(key) for key in
                    ("value", "period_or_market_time", "market_phase", "source_url")}
                if quote["period_or_market_time"][:10] not in quote_header:
                    errors.append("Report quote date differs from current evidence")
                clock = re.search(r"\d{1,2}:\d{2}(?::\d{2})?", quote_header)
                if clock and clock.group() not in quote["period_or_market_time"]:
                    errors.append("Report quote timestamp differs from current evidence")
                phase = normalize_market_phase(quote.get("market_phase"))
                if phase == "unknown":
                    errors.append("Rated report has an unknown or ambiguous evidence market phase")
                aliases = {"premarket": "premarket|盘前|开盘集合竞价", "intraday": "intraday|连续交易|连续竞价|盘中",
                           "lunch_break": "lunch_break|午休", "closing_auction": "closing_auction|收盘集合竞价|收盘竞价",
                           "postmarket": "postmarket|盘后|收盘", "non_trading": "non_trading|非交易日"}
                if phase in aliases and not re.search(aliases[phase], quote_header):
                    errors.append("Report market phase differs from current evidence")
                quote_field = _field(conclusion, "未复权现价[^：:\\n]*|当前未复权价格|当前未复权价|当前价格")
                stated_price = re.search(r"(?:^|[^\d])(\d+(?:\.\d+)?)\s*元", quote_field)
                if stated_price and abs(float(stated_price.group(1)) - quote["value"]) > 0.005:
                    errors.append("Report current price differs from current evidence")
                if not re.search(r"(?<!\d)" + re.escape(f"{quote['value']:g}") + r"(?:0*)\s*元", conclusion):
                    warnings.append("Manually reconcile the report's quoted price with current evidence")
    if re.search(r"与前次报告相比|前次报告|跟踪研究报告", text):
        if not previous_reports:
            errors.append("Follow-up report needs an exact previous report link")
        if len(evidence) < 2:
            errors.append("Follow-up report needs exact previous and current core evidence links")
        if not re.search(r"仍有效|需重算|无法判断", text):
            errors.append("Follow-up report needs the old conclusion's validity status")
    result["errors"] = list(dict.fromkeys(errors))
    result["warnings"] = list(dict.fromkeys(warnings))
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--workspace", default=".", type=Path)
    parser.add_argument("--content-file", type=Path,
                        help="Preflight UTF-8 draft text as --report, without creating that report")
    args = parser.parse_args(argv)
    try:
        content = args.content_file.read_text(encoding="utf-8-sig") if args.content_file else None
    except (OSError, UnicodeError) as exc:
        print(json.dumps({"errors": [str(exc)]}, ensure_ascii=False))
        return 1
    result = validate_report(args.report, args.workspace, content=content)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
