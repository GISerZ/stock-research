"""Download selected official CNINFO PDFs and retain traceable text excerpts."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from evidence_core import empty_fragment
from source_runtime import SourceRuntime


BJ_TZ = timezone(timedelta(hours=8))
MAX_PDF_BYTES = 30 * 1024 * 1024
TRADE_TITLE = re.compile(r"资产出售|资产收购|股权转让|转让.*(?:股权|股份)|关联交易|重大资产|重组|交割|收购.*股权|交易进展")
PRIORITY_TITLES = (
    re.compile(r"业绩预告|业绩快报|财务.*更正|会计差错"),
    re.compile(r"股份变动|股本变动|注销完成|权益分派实施|发行情况|发行结果"),
    re.compile(r"担保.*进展|担保.*逾期|债务.*违约|监管函|立案|行政处罚"),
)
EXCERPT_TOPICS = {
    "consideration": re.compile(r"交易对价|转让价(?:格|款)|交易价(?:格|款)"),
    "equity": re.compile(r"股权比例|\d+(?:\.\d+)?%[^。；\n]{0,20}(?:股权|股份)"),
    "consolidation": re.compile(r"不再纳入.*合并|不再并表|合并范围|合并报表"),
    "approval": re.compile(r"股东(?:大)?会.*(?:审议通过|批准)|批准本次交易"),
    "closing": re.compile(r"交割完成|完成交割|股权交割|工商变更|过户完成|尚未交割"),
    "disposal_gain": re.compile(r"处置损益|投资收益|处置收益"),
    "pro_forma": re.compile(r"备考|交易完成后.*(?:净利润|营业收入)"),
}
SECTION_TOPICS = {
    "restricted_cash": re.compile(r"受限(?:制)?(?:的)?货币资金|货币资金[^。；]{0,30}(?:受限|限制)|(?:所有权|使用权)[^。；]{0,15}(?:受限|限制)|受限资产"),
    "receivables_aging": re.compile(r"应收(?:账款|款项)[^。；]{0,45}账龄|账龄分析|按账龄披露"),
    "related_parties": re.compile(r"关联方|关联交易"),
    "commitments_contingencies": re.compile(r"承诺[、及和与]或有(?:事项|负债)|承诺事项|或有(?:事项|负债)|未决诉讼|对外担保"),
    "non_recurring_items": re.compile(r"非经常性损益(?:项目及金额|明细|的项目和金额|合计)?"),
    "management_discussion": re.compile(r"管理层(?:讨论与分析|分析与讨论)|经营情况(?:的)?讨论与分析|董事会报告"),
    "subsidiaries_minority_interests": re.compile(r"主要控股参股公司(?:分析|情况)?|主要子公司及对公司净利润的影响|控股子公司情况|在(?:子公司|其他主体)中的权益|少数股东(?:权益|损益)|重要的非全资子公司|合并范围的变化"),
}
SECTION_HEADING = re.compile(r"^(?:(第[一二三四五六七八九十百\d]+[节章])|[一二三四五六七八九十百\d]+[、.．])\s*(.+)$")
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.cninfo.com.cn/"}


def _save_content_file(path: Path, content: bytes) -> None:
    if path.exists():
        if path.read_bytes() != content:
            raise FileExistsError(f"Existing content differs; preserved without overwrite: {path}")
        return
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}-", suffix=".tmp",
                                         delete=False) as output:
            temporary = Path(output.name)
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != content:
                raise FileExistsError(f"Concurrent content differs; preserved without overwrite: {path}")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _select(announcements: list[dict], document_urls: list[str], limit: int) -> tuple[list[dict], list[dict]]:
    by_url = {item["source_url"]: item for item in announcements}
    missing = [url for url in document_urls if url not in by_url]
    if missing:
        raise ValueError(f"Document URL is absent from the verified company index: {missing[0]}")
    explicit = [by_url[url] for url in document_urls]
    periodic = [item for item in announcements
                if item.get("category") == "periodic_report" and "摘要" not in item["title"]]
    material = [item for item in announcements if TRADE_TITLE.search(item["title"])]
    priority = [next((item for item in announcements if pattern.search(item["title"])), None)
                for pattern in PRIORITY_TITLES]
    chosen = []
    seen = set()
    for item in explicit + periodic[:4] + [item for item in priority if item is not None] + material:
        if item["source_url"] not in seen:
            chosen.append(item)
            seen.add(item["source_url"])
    return chosen[:limit], chosen[limit:]


def _download(url: str, http_get) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "static.cninfo.com.cn" or not parsed.path.endswith((".PDF", ".pdf")):
        raise ValueError("Document URL is not an official CNINFO PDF")
    response = http_get(url, headers=HEADERS, timeout=30, stream=True, allow_redirects=False)
    try:
        response.raise_for_status()
        if response.status_code != 200 or response.url != url:
            raise ValueError("Official PDF request redirected or changed URL")
        declared = response.headers.get("Content-Length")
        if declared and int(declared) > MAX_PDF_BYTES:
            raise ValueError("PDF exceeds 30 MB")
        chunks = []
        size = 0
        for chunk in response.iter_content(chunk_size=65536):
            size += len(chunk)
            if size > MAX_PDF_BYTES:
                raise ValueError("PDF exceeds 30 MB")
            chunks.append(chunk)
        data = b"".join(chunks)
        if not data.startswith(b"%PDF"):
            raise ValueError("Response is not a PDF")
        return data
    finally:
        response.close()


def _excerpts(pages: list[str]) -> list[dict]:
    found = []
    counts = {topic: 0 for topic in EXCERPT_TOPICS}
    for number, page in enumerate(pages, start=1):
        compact = re.sub(r"\s+", " ", page)
        for topic, pattern in EXCERPT_TOPICS.items():
            if counts[topic] >= 3:
                continue
            for match in pattern.finditer(compact):
                start, end = max(0, match.start() - 90), min(len(compact), match.end() + 110)
                found.append({"page": number, "topic": topic,
                              "text": compact[start:end], "verification": "candidate"})
                counts[topic] += 1
                if counts[topic] >= 3:
                    break
    return found


def _section_candidates(pages: list[str]) -> list[dict]:
    """Rank keyword navigation candidates; page numbers are PDF positions."""
    found = {topic: [] for topic in SECTION_TOPICS}
    region = None
    for number, page in enumerate(pages, start=1):
        if not page.strip():
            region = None
            continue
        lines = [re.sub(r"\s+", "", line) for line in page.splitlines()]
        contents = "目录" in lines or sum(
            bool(re.search(r"(?:\.{3,}|…{2,}|·{3,})\d+$", line)) for line in lines) >= 3
        # shortcut: text-only region ranking, add layout/OCR only for actual difficult pages.
        if not contents:
            for line in lines:
                heading = SECTION_HEADING.fullmatch(line)
                title = heading.group(2) if heading else line
                if re.fullmatch(r"(?:重要|主要)会计政策(?:(?:及|和)会计估计)?", title):
                    region = "policy"
                elif re.fullmatch(r"(?:合并)?财务报表(?:项目)?(?:附注|注释)|补充资料", title):
                    region = "notes"
                elif SECTION_TOPICS["management_discussion"].fullmatch(title):
                    region = "management"
                elif heading and heading.group(1):
                    region = "body"
        compact = re.sub(r"\s+", " ", page)
        for topic, pattern in SECTION_TOPICS.items():
            match = pattern.search(compact)
            if match is None:
                continue
            preferred = "management" if topic == "management_discussion" else "notes"
            if contents:
                rank = 3
            elif region == "policy":
                rank = 2
            else:
                rank = 0 if region == preferred else 1
            start, end = max(0, match.start() - 90), min(len(compact), match.end() + 110)
            found[topic].append((rank, number, {"topic": topic, "page": number,
                                "text": compact[start:end], "verification": "candidate"}))
            found[topic].sort(key=lambda item: item[:2])
            del found[topic][3:]
    return [item[2] for candidates in found.values() for item in candidates]


def collect_documents(code: str, announcements: list[dict], retrieved_at: datetime,
                      workspace: Path, *, http_get, pymupdf_api,
                      document_urls: list[str], max_documents: int,
                      runtime: SourceRuntime | None = None) -> dict:
    """Save bounded official PDFs and page-linked candidate passages."""
    fragment = empty_fragment(schema_version=2)
    runtime = runtime or SourceRuntime()
    selected, skipped = _select(announcements, document_urls, max_documents)
    for item in skipped:
        fragment["issues"].append(f"skipped_due_limit: {item['announcement_id']} {item['title']}")
    if not selected:
        fragment["source_results"].append({
            "source": "cninfo_documents", "status": "no_record", "method": "title selection",
            "source_url": "https://www.cninfo.com.cn/", "detail": "No documents selected"})
        return fragment
    root = Path(workspace).expanduser().resolve()
    base = root / "research" / "evidence" / "documents"
    stamp = retrieved_at.astimezone(BJ_TZ).isoformat()
    for announcement in selected:
        url = announcement["source_url"]
        source = {"source": f"cninfo_document:{announcement['announcement_id']}",
                  "status": "source_failure", "method": "official PDF + PyMuPDF",
                  "source_url": url, "detail": ""}
        try:
            data = _download(url, runtime.http("cninfo_pdf_download", http_get))
            digest = hashlib.sha256(data).hexdigest()
            base.mkdir(parents=True, exist_ok=True)
            pdf = base / f"{digest}.pdf"
            _save_content_file(pdf, data)
            document = {"code": code, "announcement_id": announcement["announcement_id"],
                        "title": announcement["title"], "source_url": url,
                        "published_at": announcement["published_at"], "retrieved_time": stamp,
                        "pdf_sha256": digest, "pdf_path": pdf.relative_to(root).as_posix(),
                        "text_path": None, "page_count": None, "extraction_status": "source_failure",
                        "excerpts": []}
            fragment["documents"].append(document)
            try:
                pdf_doc = pymupdf_api.open(stream=data, filetype="pdf")
                try:
                    pages = [page.get_text("text") for page in pdf_doc]
                finally:
                    pdf_doc.close()
                document["page_count"] = len(pages)
                if any(page.strip() for page in pages):
                    txt = base / f"{digest}.txt"
                    text = "\n\n".join(f"===== PAGE {i} =====\n{page}" for i, page in enumerate(pages, 1))
                    # Preserve the previous text-mode newline convention on this platform.
                    _save_content_file(txt, text.replace("\n", os.linesep).encode("utf-8"))
                    document["text_path"] = txt.relative_to(root).as_posix()
                    document["extraction_status"] = "ok"
                    document["excerpts"] = _excerpts(pages)
                    document["section_candidates"] = _section_candidates(pages)
                    source["status"] = "ok"
                    source["detail"] = f"{len(pages)} pages; {len(document['excerpts'])} candidate excerpts"
                    source["detail"] += f"; {len(document['section_candidates'])} section candidates"
                    empty_pages = sum(not page.strip() for page in pages)
                    if empty_pages:
                        source["detail"] += f"; {empty_pages} pages without extractable text"
                        fragment["issues"].append(
                            f"PDF 部分页面无可提取文字（{empty_pages}/{len(pages)}页）：{url}；"
                            "可能为空白或扫描页，须查原件；候选仅覆盖可提取文字")
                else:
                    document["extraction_status"] = "text_unavailable"
                    source["detail"] = "PDF downloaded; no extractable text"
                    fragment["issues"].append(f"PDF 文字不可提取：{url}")
            except Exception as exc:
                source["detail"] = f"PDF saved, text extraction failed: {exc}"
                source["error_type"] = "storage_error" if isinstance(exc, OSError) else "parse_error"
                fragment["issues"].append(f"PDF 正文提取失败：{url}；{exc}")
        except Exception as exc:
            runtime.result(source, error=exc)
            fragment["issues"].append(f"PDF 下载或保存失败：{url}；{exc}")
        metadata = runtime.result({"source": "cninfo_pdf_download", "status": source["status"]})
        source.update({key: value for key, value in metadata.items() if key not in {"source", "status"}
                       and not (key == "error_type" and source.get("error_type"))})
        fragment["source_results"].append(source)
    return fragment
