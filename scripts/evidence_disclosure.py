"""Complete CNINFO announcement index with official PDF links."""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone, timedelta
from pathlib import PurePosixPath
from urllib.parse import urlparse

from evidence_core import empty_fragment
from source_runtime import SourceRuntime


BJ_TZ = timezone(timedelta(hours=8))
DIRECTORY_URL = "https://www.cninfo.com.cn/new/data/szse_stock.json"
QUERY_URL = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
PDF_BASE = "https://static.cninfo.com.cn/"
PERIODIC = re.compile(r"年度报告|半年度报告|季度报告|年报|半年报|季报")
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.cninfo.com.cn/"}


def _two_years_ago(day):
    try:
        return day.replace(year=day.year - 2)
    except ValueError:
        return day.replace(year=day.year - 2, day=28)


def _listing(code: str, http_get) -> tuple[str, set[str]]:
    response = http_get(DIRECTORY_URL, headers=HEADERS, timeout=15)
    response.raise_for_status()
    listings = response.json().get("stockList")
    if not isinstance(listings, list) or not listings or not all(isinstance(item, dict) for item in listings):
        raise ValueError("CNINFO stock directory is empty or malformed")
    matches = [item for item in listings if str(item.get("code", "")).zfill(6) == code]
    if len(matches) != 1 or not matches[0].get("orgId"):
        raise ValueError("CNINFO stock directory has no unique organization ID")
    org_id = str(matches[0]["orgId"])
    aliases = {str(item.get("code", "")).zfill(6) for item in listings
               if str(item.get("orgId")) == org_id
               and re.fullmatch(r"\d{6}", str(item.get("code", "")))}
    return org_id, aliases


def _query_page(code: str, org_id: str, start: str, end: str, page: int,
                page_size: int, http_post) -> tuple[int, list[dict]]:
    payload = {
        "stock": f"{code},{org_id}", "tabName": "fulltext",
        "pageSize": str(page_size), "pageNum": str(page), "column": "szse", "category": "",
        "plate": "", "seDate": f"{start}~{end}", "searchkey": "",
        "secid": "", "sortName": "", "sortType": "", "isHLtitle": "true",
    }
    response = http_post(QUERY_URL, data=payload, headers=HEADERS, timeout=15)
    response.raise_for_status()
    data = response.json()
    total = data.get("totalAnnouncement")
    rows = data.get("announcements")
    if isinstance(total, bool) or not isinstance(total, int) or total < 0:
        raise ValueError("CNINFO response lacks a valid totalAnnouncement")
    if rows is None and total == 0 and "announcements" in data:
        rows = []
    if (not isinstance(rows, list) or len(rows) > page_size
            or not all(isinstance(row, dict) for row in rows)
            or (total > 0 and not rows) or (total == 0 and rows)):
        raise ValueError("CNINFO response has invalid announcement rows")
    return total, rows


def _official_count(code: str, start: str, end: str, *, http_get, http_post) -> tuple[int, set[str]]:
    """Retained for callers needing a count without downloading the whole index."""
    org_id, aliases = _listing(code, http_get)
    total, _ = _query_page(code, org_id, start, end, 1, 1, http_post)
    return total, aliases


def _date_time(raw) -> datetime:
    if isinstance(raw, (int, float)) or str(raw).isdigit():
        value = datetime.fromtimestamp(int(raw) / 1000, tz=BJ_TZ)
    elif isinstance(raw, datetime):
        value = raw
    else:
        value = datetime.fromisoformat(str(raw).strip())
    return value.replace(tzinfo=BJ_TZ) if value.tzinfo is None else value.astimezone(BJ_TZ)


def _pdf_url(raw: str) -> str:
    path = str(raw).strip()
    parsed = urlparse(path)
    pure = PurePosixPath(parsed.path)
    if (parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or path.startswith("/")
            or "\\" in path or ".." in pure.parts or not path.lower().endswith(".pdf")
            or not path.startswith("finalpage/")):
        raise ValueError("CNINFO announcement has an unsafe PDF path")
    return PDF_BASE + path


def _official_url(raw) -> str:
    parsed = urlparse(str(raw).strip())
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
        "www.cninfo.com.cn", "static.cninfo.com.cn",
    }:
        raise ValueError("Announcement does not have an official CNINFO link")
    return parsed._replace(scheme="https").geturl()


def collect_disclosures(code: str, market: str, retrieved_at: datetime, *,
                        ak_api, http_get, http_post, runtime: SourceRuntime | None = None) -> dict:
    """Return the complete two-year official announcement index."""
    fragment = empty_fragment()
    runtime = runtime or SourceRuntime()
    http_get = runtime.http("cninfo_announcements", http_get)
    http_post = runtime.http("cninfo_announcements", http_post)
    day = retrieved_at.astimezone(BJ_TZ).date()
    start, end = _two_years_ago(day).isoformat(), day.isoformat()
    query_range = f"{start}..{end}"
    result = {"source": "cninfo_announcements", "status": "source_failure",
              "method": "CNINFO hisAnnouncement/query full pagination",
              "source_url": QUERY_URL, "query_range": query_range}
    result["coverage"] = {"code": code, "market": market, "query_range": query_range}
    try:
        org_id, aliases = _listing(code, http_get)
        # CNINFO caps responses at 30 rows even when pageSize=100 is requested.
        page_size = 30
        total, rows = _query_page(code, org_id, start, end, 1, page_size, http_post)
        if total == 0:
            result.update(status="no_record", detail="Complete official query returned zero announcements")
            fragment["source_results"].append(runtime.result(result))
            return fragment
        for page in range(2, (total + page_size - 1) // page_size + 1):
            page_total, page_rows = _query_page(code, org_id, start, end, page, page_size, http_post)
            if page_total != total:
                raise ValueError("CNINFO totalAnnouncement changed during pagination")
            rows.extend(page_rows)
        if len(rows) != total:
            raise ValueError(f"CNINFO pagination incomplete: {len(rows)} rows, {total} official")
        seen = set()
        announcements = []
        for row in rows:
            announcement_id = str(row.get("announcementId", "")).strip()
            disclosure_code = str(row.get("secCode", "")).zfill(6)
            if not announcement_id or announcement_id in seen or disclosure_code not in aliases:
                raise ValueError("CNINFO announcement ID or code mismatch")
            seen.add(announcement_id)
            published = _date_time(row.get("announcementTime"))
            if not (start <= published.date().isoformat() <= end):
                raise ValueError("CNINFO announcement outside queried range")
            title = html.unescape(re.sub(r"<[^>]*>", "", str(row.get("announcementTitle", "")))).strip()
            if not title:
                raise ValueError("CNINFO announcement title is empty")
            announcements.append({
                "code": code, "disclosure_code": disclosure_code,
                "identity_basis": "exact_code" if disclosure_code == code else "same_cninfo_org_id",
                "announcement_id": announcement_id, "title": title,
                "published_at": published.isoformat(),
                "category": "periodic_report" if PERIODIC.search(title) else "announcement",
                "source_url": _pdf_url(row.get("adjunctUrl", "")),
                "query_range": query_range,
            })
        announcements.sort(key=lambda item: item["published_at"], reverse=True)
        fragment["announcements"] = announcements
        result["coverage"].update(official_total=total, collected=len(announcements))
        result.update(status="ok", detail=f"{total} official rows checked")
    except Exception as exc:
        fragment["issues"].append(f"巨潮公告索引取数或完整性校验失败：{exc}")
        result = runtime.result(result, error=exc)
        result["manual_review_urls"] = ["https://www.cninfo.com.cn/", {
            "sh": "https://www.sse.com.cn/disclosure/listedinfo/announcement/",
            "sz": "https://www.szse.cn/disclosure/listed/notice/index.html",
            "bj": "https://www.bse.cn/disclosure/announcement.html"}[market]]
    fragment["source_results"].append(runtime.result(result))
    return fragment
