"""Stock heat, discussion ranking, news leads, and reviewed social posts."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time
import re

from sentiment_core import BJ_TZ, checked_time, checked_url, load_market_five_days, save_sentiment_snapshot
from sentiment_market import ACTIVITY_FIELDS, POOLS, collect_market_day, last_five_trade_dates
from market_phase import classify_market_phase
from source_runtime import RUNTIME_VERSION, SourceRuntime


RANK_URL = "https://guba.eastmoney.com/rank/stock?code={}"
RANK_LIST_URL = "https://guba.eastmoney.com/rank/"
DISCUSSION_URL = "https://xueqiu.com/hq"
NEWS_URL = "https://so.eastmoney.com/news/s?keyword={}"
THS_HEAT_ENDPOINT = "https://dq.10jqka.com.cn/fuyao/hot_list_data/out/hot_list/v1/stock"
THS_HEAT_URL = THS_HEAT_ENDPOINT + "?stock_type=a&type=day&list_type=normal"


def _source(packet: dict, name: str, status: str, url: str, detail: str = "", *, runtime=None, error=None) -> None:
    result = {"source": name, "status": status, "source_url": url, "detail": detail}
    if runtime:
        runtime.result(result, error=error)
    packet["source_results"].append(result)
    if result.get("detail"):
        packet["issues"].append(f"{name}: {result['detail']}")


def _rank_observation(field: str, rank: int, day: date, now: datetime, url: str,
                      source: str, scope: str) -> dict:
    return {"field": field, "value": rank, "unit": "名", "basis": "smaller rank means hotter; source date only",
            "source_name": source, "source_url": url, "observed_at": f"{day}T00:00:00+08:00",
            "observation_precision": "date", "source_trade_date": day.isoformat(),
            "retrieved_at": now.isoformat(), "scope": scope, "status": "ok"}


def _heat(packet: dict, code: str, market: str, days: list[date], now: datetime, ak_api,
          runtime: SourceRuntime) -> None:
    symbol = f"{market.upper()}{code}"
    url = RANK_URL.format(code)
    try:
        if not days:
            raise RuntimeError("Trade dates unavailable; heat coverage cannot be assigned")
        frame = runtime.call("eastmoney_heat_history", ak_api.stock_hot_rank_detail_em, symbol=symbol)
        if frame is None or frame.empty or not {"时间", "排名", "证券代码"}.issubset(frame.columns):
            raise ValueError("Empty or unrecognized heat history")
        else:
            allowed = set(days)
            daily = {}
            for _, row in frame.iterrows():
                day = date.fromisoformat(str(row["时间"])[:10])
                rank = _positive_rank(row["排名"])
                if str(row["证券代码"]).upper() != symbol:
                    raise ValueError("Heat history target code mismatch")
                if day not in allowed:
                    continue
                daily[day] = rank
            for day in days:
                if day in daily:
                    packet["heat_history"].append({"trade_date": day.isoformat(), "rank": daily[day],
                                                   "source_url": url})
                    packet["observations"].append(_rank_observation("heat_rank", daily[day], day, now,
                        url, "eastmoney_heat_history", "individual stock historical heat ranking"))
            _source(packet, "eastmoney_heat_history", "ok" if len(daily) == 5 else "partial" if daily else "no_record", url,
                    f"{len(daily)}/{len(days)} requested trade dates available")
    except Exception as exc:
        _source(packet, "eastmoney_heat_history", "source_failure", url, runtime=runtime, error=exc)
    try:
        frame = runtime.call("eastmoney_top100", ak_api.stock_hot_rank_em)
        if frame is None or frame.empty or not {"代码", "当前排名"}.issubset(frame.columns):
            raise ValueError("Empty or unrecognized top-100 list")
        codes = frame["代码"].astype(str).str.upper().tolist()
        ranks = [_positive_rank(value) for value in frame["当前排名"]]
        if (len(codes) != len(set(codes)) or len(ranks) != len(set(ranks))
                or any(not re.fullmatch(r"(?:SH|SZ|BJ)\d{6}", code) for code in codes)
                or max(ranks) > 100):
            raise ValueError("Invalid or duplicate top-100 codes/ranks")
        matches = frame[frame["代码"].astype(str).str.upper() == symbol]
        if matches.empty:
            packet["top100_coverage"] = "outside_top100"
            _source(packet, "eastmoney_top100", "no_record", RANK_LIST_URL, "Target outside current top 100")
        else:
            rank = _positive_rank(matches.iloc[0]["当前排名"])
            packet["top100_coverage"] = "in_top100"
            packet["current_heat_rank"] = {"rank": rank, "observed_at": now.isoformat(),
                                           "source_url": RANK_LIST_URL, "scope": "current top 100",
                                           "observation_time_basis": "retrieval_only"}
            packet["observations"].append({"field": "current_heat_rank", "value": rank, "unit": "名",
                "basis": "current top-100 list; smaller rank means hotter", "source_name": "eastmoney_top100",
                "source_url": RANK_LIST_URL, "observed_at": now.isoformat(), "retrieved_at": now.isoformat(),
                "scope": "current top 100", "status": "ok", "observation_time_basis": "retrieval_only"})
            _source(packet, "eastmoney_top100", "ok", RANK_LIST_URL)
    except Exception as exc:
        _source(packet, "eastmoney_top100", "source_failure", RANK_LIST_URL, runtime=runtime, error=exc)


def _ths_current_heat(packet: dict, code: str, now: datetime, http_get, runtime: SourceRuntime) -> None:
    """Record an independent current list when Eastmoney's current list failed."""
    try:
        response = runtime.http("ths_current_heat", http_get)(THS_HEAT_ENDPOINT,
                            params={"stock_type": "a", "type": "day", "list_type": "normal"},
                            headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
            raise ValueError("Unrecognized Tonghuashun heat response")
        entries = payload["data"].get("stock_list")
        if not isinstance(entries, list) or not entries:
            raise ValueError("Empty or unrecognized Tonghuashun heat list")
        matches = []
        seen_codes, seen_ranks = set(), set()
        for item in entries:
            if not isinstance(item, dict):
                raise ValueError("Heat list item is not an object")
            item_code = item.get("code")
            rank = item.get("order")
            if not isinstance(item_code, str) or not re.fullmatch(r"\d{6}", item_code):
                raise ValueError("Heat list contains an invalid stock code")
            if isinstance(rank, str) and re.fullmatch(r"[1-9]\d*", rank):
                rank = int(rank)
            if isinstance(rank, bool) or not isinstance(rank, int) or rank < 1:
                raise ValueError("Heat list contains an invalid rank")
            if item_code in seen_codes or rank in seen_ranks:
                raise ValueError("Heat list contains duplicate codes or ranks")
            seen_codes.add(item_code)
            seen_ranks.add(rank)
            if item_code == code:
                matches.append(rank)
        if len(matches) > 1:
            raise ValueError("Heat list contains duplicate target codes")
        scope = f"Tonghuashun A-share day normal current hot list; {len(entries)} returned entries"
        if not matches:
            packet["ths_current_heat_coverage"] = "outside_returned_list"
            _source(packet, "ths_current_heat", "no_record", THS_HEAT_URL,
                    f"Target outside valid current list of {len(entries)} entries")
            return
        rank = matches[0]
        packet["ths_current_heat_coverage"] = "in_returned_list"
        packet["ths_current_heat_rank"] = {"rank": rank, "list_size": len(entries),
            "scope": scope, "source_url": THS_HEAT_URL, "observed_at": now.isoformat(),
            "observation_time_basis": "retrieval_only"}
        packet["observations"].append({"field": "ths_current_heat_rank", "value": rank,
            "unit": "名", "basis": "Tonghuashun day hot list; smaller rank means hotter; current list only",
            "source_name": "ths_current_heat", "source_url": THS_HEAT_URL,
            "observed_at": now.isoformat(), "retrieved_at": now.isoformat(),
            "scope": scope, "status": "ok", "observation_time_basis": "retrieval_only"})
        _source(packet, "ths_current_heat", "ok", THS_HEAT_URL)
    except Exception as exc:
        packet["ths_current_heat_coverage"] = "unavailable"
        _source(packet, "ths_current_heat", "source_failure", THS_HEAT_URL,
                runtime=runtime, error=exc)


def _positive_rank(value) -> int:
    if isinstance(value, bool):
        raise ValueError("Boolean rank")
    number = float(value)
    if not number.is_integer() or number < 1:
        raise ValueError("Invalid positive rank")
    return int(number)


def _discussion(packet: dict, code: str, market: str, now: datetime, ak_api, runtime: SourceRuntime) -> None:
    symbol = f"{market.upper()}{code}"
    try:
        frame = runtime.call("xueqiu_discussion_rank", ak_api.stock_hot_tweet_xq, symbol="最热门")
        if frame is None or frame.empty or not {"股票代码", "关注"}.issubset(frame.columns):
            raise ValueError("Empty or unrecognized discussion ranking")
        codes = frame["股票代码"].astype(str).str.upper().tolist()
        if len(codes) != len(set(codes)) or any(not re.fullmatch(r"(?:SH|SZ|BJ)\d{6}", code) for code in codes):
            raise ValueError("Discussion ranking code format or uniqueness changed")
        matches = frame.index[frame["股票代码"].astype(str).str.upper() == symbol].tolist()
        if not matches:
            packet["discussion_coverage"] = "outside_returned_list"
            _source(packet, "xueqiu_discussion_rank", "no_record", DISCUSSION_URL,
                    f"Target outside returned {len(frame)} entries")
            return
        position = matches[0]
        row = frame.loc[position]
        packet["discussion_coverage"] = "in_returned_list"
        packet["discussion_rank"] = {"rank": int(frame.index.get_loc(position)) + 1,
                                     "raw_attention": str(row["关注"]),
                                     "list_name": "最热门", "list_size": len(frame),
                                     "observed_at": now.isoformat(), "source_url": DISCUSSION_URL,
                                     "observation_time_basis": "retrieval_only"}
        packet["observations"].append({"field": "discussion_rank", "value": packet["discussion_rank"]["rank"],
            "unit": "名", "basis": "position in full returned 最热门 ranking; 关注 is not a post count",
            "source_name": "xueqiu_discussion_rank", "source_url": DISCUSSION_URL,
            "observed_at": now.isoformat(), "retrieved_at": now.isoformat(),
            "scope": f"returned {len(frame)} entries", "status": "ok",
            "observation_time_basis": "retrieval_only"})
        _source(packet, "xueqiu_discussion_rank", "ok", DISCUSSION_URL)
    except Exception as exc:
        _source(packet, "xueqiu_discussion_rank", "source_failure", DISCUSSION_URL,
                runtime=runtime, error=exc)


def _published(value) -> datetime:
    parsed = datetime.fromisoformat(str(value).strip().replace("/", "-"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=BJ_TZ)


def _news(packet: dict, code: str, as_of_date: date, now: datetime, ak_api, runtime: SourceRuntime) -> None:
    url = NEWS_URL.format(code)
    try:
        frame = runtime.call("eastmoney_news", ak_api.stock_news_em, symbol=code)
        if frame is None or frame.empty:
            raise ValueError("Empty news frame; successful empty query cannot be confirmed")
        required = {"新闻标题", "发布时间", "文章来源", "新闻链接"}
        if not required.issubset(frame.columns):
            raise ValueError("News response lacks required fields")
        seen = set()
        candidates = []
        for _, row in frame.iterrows():
            link = checked_url(str(row["新闻链接"]), "news URL")
            published = _published(row["发布时间"])
            if not str(row["新闻标题"]).strip():
                raise ValueError("News title missing")
            if published > now or link in seen:
                continue
            seen.add(link)
            candidates.append({"title": str(row["新闻标题"]).strip(),
                "summary": str(row.get("新闻内容", "")).strip()[:300],
                "publisher": str(row["文章来源"]).strip(), "published_at": published.isoformat(),
                "source_url": link, "after_target_close": published > datetime.combine(as_of_date, time(15), BJ_TZ),
                "verification": "candidate_only"})
        packet["news_candidates"] = candidates
        _source(packet, "eastmoney_news", "ok" if packet["news_candidates"] else "no_record", url,
                "Recent limited list; five-day coverage is not guaranteed")
    except Exception as exc:
        _source(packet, "eastmoney_news", "source_failure", url, runtime=runtime, error=exc)


def _social_review(review: dict | None, code: str, now: datetime) -> dict:
    if review is None:
        return {"status": "not_reviewed", "posts": [], "reason": "No manual review file supplied"}
    try:
        if review.get("status") not in {"reviewed", "no_posts"}:
            raise ValueError("status must be reviewed or no_posts")
        sampled = checked_time(review.get("sampled_at"), "sampled_at")
        if sampled > now or not str(review.get("selection_method", "")).strip():
            raise ValueError("sampling time or selection method invalid")
        posts = review.get("posts")
        if not isinstance(posts, list) or (review["status"] == "no_posts" and posts):
            raise ValueError("posts must be a list and empty for no_posts")
        clean = []
        for post in posts:
            if str(post.get("code")) != code or not str(post.get("summary", "")).strip():
                raise ValueError("Post target or summary invalid")
            published = checked_time(post.get("published_at"), "post.published_at")
            if published > sampled:
                raise ValueError("Post was not available at sampled_at")
            clean.append({"code": code, "published_at": published.isoformat(),
                          "source_url": checked_url(post.get("source_url"), "post.source_url"),
                          "summary": str(post["summary"]).strip()})
        if review["status"] == "reviewed" and not clean:
            raise ValueError("reviewed needs at least one verifiable post")
        return {"status": review["status"], "sampled_at": sampled.isoformat(),
                "selection_method": review["selection_method"], "posts": clean}
    except (AttributeError, TypeError, ValueError) as exc:
        return {"status": "unverifiable", "posts": [], "reason": str(exc)}


def summarize_analysis_coverage(packet: dict) -> dict:
    """Describe saved auxiliary coverage without verifying facts or changing source statuses."""
    days = packet.get("five_day_coverage", {}).get("required_trade_dates", [])
    window_known = (packet.get("coverage", {}).get("calendar_verified") is True
                    and packet.get("collection_status") != "failed"
                    and isinstance(days, list) and len(days) == 5
                    and all(isinstance(day, str) for day in days)
                    and len(set(days)) == 5 and days == sorted(days)
                    and days[-1] == packet.get("as_of_trade_date"))
    days = days if window_known else []
    heat = packet.get("heat_history")
    market = packet.get("market_five_days")
    news = packet.get("news_candidates")
    missing = [key for key in ("heat_history", "market_five_days", "news_candidates")
               if not isinstance(packet.get(key), list)]
    missing.extend(key for key in ("social_review", "cross_market")
                   if not isinstance(packet.get(key), dict))

    def day_coverage(valid: set, present: bool) -> dict:
        return {"required_days": 5, "data_status": "recorded" if present else "missing",
                "valid_days": len(valid) if window_known and present else None,
                "missing_trade_dates": [day for day in days if day not in valid]
                                       if window_known and present else None}

    heat_days = {item.get("trade_date") for item in (heat if isinstance(heat, list) else [])
                 if item.get("trade_date") in days
                 and type(item.get("rank")) is int and item["rank"] > 0}
    market_fields = {}
    for field in (*ACTIVITY_FIELDS.values(), *(pool[0] for pool in POOLS)):
        valid = {entry.get("trade_date") for entry in (market if isinstance(market, list) else [])
                 if entry.get("trade_date") in days and any(
                     item.get("field") == field and item.get("status") == "ok"
                     and item.get("value") is not None for item in entry.get("observations", []))}
        market_fields[field] = day_coverage(valid, isinstance(market, list))
    return {"window_status": "available" if window_known else "unavailable",
            "required_trade_dates": list(days), "missing_fields": missing,
            "heat_history": day_coverage(heat_days, isinstance(heat, list)),
            "market_fields": market_fields,
            "news_candidates": {"saved_count": len(news) if isinstance(news, list) else None,
                                "verification": "candidates_only",
                                "note": "Saved leads only; zero or missing does not establish no news or reviewed coverage"},
            "social_review": {"status": packet["social_review"].get("status", "missing")
                              if isinstance(packet.get("social_review"), dict) else "missing"},
            "cross_market": {"selection_status": packet["cross_market"].get("selection_status", "missing")
                             if isinstance(packet.get("cross_market"), dict) else "missing"},
            "limits": ["Unavailable window or missing input means unknown day counts, not zero",
                       "Coverage only; original source statuses, review limits and rating gates still apply"]}


def collect_stock_day(code: str, market: str, as_of_date: date, *, now: datetime,
                      ak_api, http_get, social_review: dict | None, workspace=None,
                      runtime: SourceRuntime | None = None) -> dict:
    now = now.astimezone(BJ_TZ)
    runtime = runtime or SourceRuntime()
    packet = {"schema_version": 1, "kind": "stock", "target": {"code": code, "market": market},
              "as_of_trade_date": as_of_date.isoformat(), "collected_at": now.isoformat(),
              "runtime_version": RUNTIME_VERSION, "run_id": runtime.run_id, "market_phase": "unknown",
              "coverage": {"calendar_verified": False},
              "scope": f"{market.upper()}{code} and 沪深 market context", "source_results": [],
              "observations": [], "issues": [], "completeness": "partial", "heat_history": [],
              "top100_coverage": "unavailable", "discussion_coverage": "unavailable",
              "news_candidates": [], "cross_market": {"selection_status": "not_reviewed", "references": []}}
    try:
        days = last_five_trade_dates(as_of_date, ak_api, runtime)
        packet["coverage"].update(calendar_verified=True, calendar_status="verified")
        packet["market_phase"] = classify_market_phase(now, is_trading_day=(now.date() in runtime.calendar)
            if runtime.calendar and runtime.calendar[-1] >= now.date() else None)
        _source(packet, "sina_trade_calendar", "ok", "https://finance.sina.com.cn/realstock/company/klc_td_sh.txt", runtime=runtime)
    except Exception as exc:
        packet.update(as_of_trade_date=None, requested_trade_date=as_of_date.isoformat(), collection_status="failed")
        packet["coverage"].update(calendar_verified=False, calendar_status="failed")
        packet["issues"].append("calendar_unavailable")
        _source(packet, "sina_trade_calendar", "source_failure", "https://finance.sina.com.cn/realstock/company/klc_td_sh.txt", runtime=runtime, error=exc)
        packet["source_results"][-1]["coverage"] = dict(packet["coverage"])
        return packet
    if workspace is not None:
        for day in days:
            prior = load_market_five_days(workspace, [day])[0]
            statuses = {item["field"]: item["status"] for item in prior["observations"]}
            pools_known = all(statuses.get(field) == "ok"
                              for field in ("limit_up", "limit_down", "failed_board"))
            if prior["completeness"] == "complete" or (day < now.date() and pools_known):
                continue
            try:
                save_sentiment_snapshot(collect_market_day(day, now=now, ak_api=ak_api, runtime=runtime), workspace)
            except Exception as exc:
                packet["issues"].append(f"market_backfill {day}: {type(exc).__name__}: {exc}")
    packet["market_five_days"] = load_market_five_days(workspace, days) if workspace is not None else []
    packet["market_snapshot_paths"] = [entry["snapshot_path"] for entry in packet["market_five_days"]]
    valid_days = Counter(field for entry in packet["market_five_days"] for field in set(entry["valid_fields"]))
    packet["five_day_coverage"] = {"required_trade_dates": [day.isoformat() for day in days],
                                   "market_valid_days_by_field": dict(valid_days)}
    _heat(packet, code, market, days, now, ak_api, runtime)
    if any(result["source"] == "eastmoney_top100" and result["status"] in {"source_failure", "rate_limited", "malformed", "stale"}
           for result in packet["source_results"]):
        _ths_current_heat(packet, code, now, http_get, runtime)
    packet["five_day_coverage"]["heat_valid_days"] = len(packet["heat_history"])
    _discussion(packet, code, market, now, ak_api, runtime)
    _news(packet, code, as_of_date, now, ak_api, runtime)
    packet["social_review"] = _social_review(social_review, code, now)
    packet["completeness"] = ("complete" if all(result["status"] == "ok" for result in packet["source_results"])
                              and packet["social_review"]["status"] in {"reviewed", "no_posts"}
                              and len(packet["heat_history"]) == 5
                              and len(packet["market_five_days"]) == 5
                              and packet["market_five_days"][-1]["completeness"] == "complete"
                              and all(valid_days[field] == 5 for field in ("limit_up", "limit_down", "failed_board"))
                              else "partial")
    for result in packet["source_results"]:
        runtime.result(result)
        result["coverage"].update({"target": code, "as_of_trade_date": as_of_date.isoformat(),
                              "calendar_verified": True,
                              "scope": "independent current list" if result["source"] == "ths_current_heat"
                              else "source-defined; see observations", "detail": result.get("detail", "")})
    return packet
