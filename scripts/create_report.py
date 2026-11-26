#!/usr/bin/env python3
"""Edit a stock-research draft; explicitly publish after structural preflight.

This helper only creates a local report file. It does not fetch market data,
browse websites, call an LLM, calculate indicators, or generate ratings.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
TEMPLATE_PATH = SKILL_DIR / "references" / "report-template.md"

CODE_RE = re.compile(r"^[0-9A-Za-z._-]+$")
INVALID_NAME_CHARS = set('<>:"/\\|?*')
PUBLICATION_FIELDS = re.compile(
    r"(?m)^> (?:文档类型|发布状态|发布变更原因|替代发布版本)：[^\n]*\n?"
)


class PublicationValidationError(ValueError):
    def __init__(self, result: dict, draft: Path):
        super().__init__("Preflight failed; only the editable draft was saved.")
        self.result = result
        self.draft = draft


def sanitize_code(value: str) -> str:
    """Return a safe stock-code filename component."""
    raw = (value or "").strip()
    if not raw:
        raise ValueError("Stock code is required.")
    if raw in {".", ".."} or ".." in raw:
        raise ValueError(f"Invalid stock code: {value!r}")
    if not CODE_RE.fullmatch(raw):
        raise ValueError(
            f"Invalid stock code: {value!r}. Use letters, digits, dot, underscore, or hyphen."
        )
    return raw[:32]


def sanitize_name(value: str | None) -> str | None:
    """Return a safe optional Chinese stock-short-name filename component."""
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    cleaned = "".join(
        ch for ch in raw if ch not in INVALID_NAME_CHARS and ord(ch) >= 32
    )
    cleaned = re.sub(r"\s+", "", cleaned).strip(" .")
    if not cleaned:
        return None
    return cleaned[:40]


def validate_date(value: str) -> str:
    """Validate YYYY-MM-DD and return it unchanged."""
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"Invalid date {value!r}; expected YYYY-MM-DD.") from exc
    return value


def load_template() -> str:
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Report template not found: {TEMPLATE_PATH}")
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def render_template(code: str, name: str | None, report_date: str) -> str:
    display_name = name or "未识别简称"
    title = f"A股研究报告：{code} {display_name}"
    template = load_template()
    replacements = {
        "{{TITLE}}": title,
        "{{DATE}}": report_date,
        "{{CODE}}": code,
        "{{NAME}}": display_name,
    }
    for token, replacement in replacements.items():
        template = template.replace(token, replacement)
    return template


def build_report_path(
    code: str,
    name: str | None,
    report_date: str,
    output_dir: str | Path,
) -> Path:
    safe_code = sanitize_code(code)
    safe_name = sanitize_name(name)
    safe_date = validate_date(report_date)

    base_dir = Path(output_dir).expanduser().resolve()
    research_dir = base_dir / "research"
    filename = f"{safe_date}-{safe_code}"
    if safe_name:
        filename += f"-{safe_name}"
    filename += ".md"
    path = research_dir / filename

    resolved_parent = path.resolve().parent
    expected_parent = research_dir.resolve()
    if resolved_parent != expected_parent:
        raise ValueError(f"Refusing to write outside research directory: {path}")
    return path


def create_report(
    code: str,
    name: str | None,
    report_date: str,
    output_dir: str | Path,
    content: str | None = None,
    *,
    publish: bool = False,
    validate: bool = False,
    change_reason: str | None = None,
    supersedes: str | Path | None = None,
) -> Path:
    """Save a draft, or serialize publication for the entire ticker.

    The lock is transient and fails immediately on contention. It covers the
    history scan, validation and atomic publish, including alternative names.
    """
    arguments = dict(publish=publish, validate=validate,
                     change_reason=change_reason, supersedes=supersedes)
    if not publish:
        return _create_report(code, name, report_date, output_dir, content, **arguments)
    workspace = Path(output_dir).expanduser().resolve()
    lock = workspace / "research/.drafts" / f".publish-{sanitize_code(code)}.lock"
    if not lock.resolve().is_relative_to(workspace):
        raise ValueError("Publication lock escapes workspace")
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        handle = lock.open("x", encoding="ascii")
    except FileExistsError:
        raise FileExistsError(f"Another publication holds {lock}; check the publisher before retrying.") from None
    try:
        with handle:
            handle.write(str(os.getpid()))
        return _create_report(code, name, report_date, output_dir, content, **arguments)
    finally:
        lock.unlink(missing_ok=True)


def _create_report(
    code: str,
    name: str | None,
    report_date: str,
    output_dir: str | Path,
    content: str | None,
    *,
    publish: bool,
    validate: bool,
    change_reason: str | None,
    supersedes: str | Path | None,
) -> Path:
    """Update one draft, or publish a checked immutable report.

    Published files are never replaced. Editorial retries reuse the draft;
    identical publication retries reuse the latest report. A changed release
    needs an explicit reason, including changes that only correct presentation.
    """
    safe_code = sanitize_code(code)
    safe_name = sanitize_name(name)
    safe_date = validate_date(report_date)
    base_path = build_report_path(safe_code, safe_name, safe_date, output_dir)
    report = render_template(safe_code, safe_name, safe_date) if content is None else content
    if not report.strip():
        raise ValueError("Report content cannot be empty.")
    if publish and content is None:
        raise ValueError("Publishing requires --content-file with a completed report.")
    if not publish and (change_reason is not None or supersedes is not None):
        raise ValueError("--change-reason and --supersedes require --publish.")
    workspace = Path(output_dir).expanduser().resolve()
    draft = base_path.parent / ".drafts" / base_path.name
    if not draft.resolve().is_relative_to(workspace):
        raise ValueError("Draft path escapes workspace")
    if content is None and draft.is_file():
        report = draft.read_text(encoding="utf-8-sig")
    else:
        _atomic_write(draft, report, replace=True)
    if not publish and not validate:
        return draft

    history = _history(base_path.parent, safe_code)
    same_day = [item for item in history if item[0] == safe_date]
    eligible = [item for item in history if item[0] <= safe_date and item[3]]
    latest_entry = max(eligible, key=lambda item: (item[0], item[1])) if eligible else None
    latest = latest_entry[2] if latest_entry else None
    same = bool(latest_entry and latest_entry[0] == safe_date
                and _body(latest.read_text(encoding="utf-8-sig")) == _body(report))
    version = max((item[1] for item in same_day), default=0) + 1
    path = (latest if same else base_path if version == 1 else
            base_path.with_name(f"{base_path.stem}-v{version}.md"))
    predecessor = None
    if publish and not same:
        if latest_entry and latest_entry[0] != safe_date and supersedes is None:
            raise ValueError("A later-date report needs --supersedes identifying its exact predecessor.")
        if supersedes is not None:
            predecessor = Path(supersedes).expanduser()
            if not predecessor.is_absolute():
                predecessor = workspace / predecessor
            predecessor = predecessor.resolve()
            if (predecessor.parent != base_path.parent or not predecessor.is_file()
                    or not re.match(r"\d{4}-\d{2}-\d{2}-" + re.escape(safe_code) + r"(?:-|\.md$)", predecessor.name)):
                raise ValueError("--supersedes must identify an existing same-ticker report in research/.")
            if predecessor != latest:
                raise ValueError("--supersedes must match the latest eligible published full report.")
        else:
            predecessor = latest
        if predecessor and not (change_reason and change_reason.strip()):
            raise ValueError("A new publication needs --change-reason for traceability.")
    text = (latest.read_text(encoding="utf-8-sig") if same else
            _publication_text(report, change_reason, predecessor))
    from validate_report import validate_report
    result = validate_report(path, workspace, content=text)
    if result["errors"]:
        raise PublicationValidationError(result, draft)
    if not publish:
        return draft
    if same:
        return latest
    try:
        _atomic_write(path, text, replace=False)
    except FileExistsError:
        # Another publisher may have won after preflight. Reuse identical
        # bytes, but do not silently create an extra version for a conflict.
        if path.read_text(encoding="utf-8-sig") != text:
            raise FileExistsError(f"Concurrent publication conflict at {path}; review and retry.")
    return path


def _body(text: str) -> str:
    return PUBLICATION_FIELDS.sub("", text).strip()


def _history(research: Path, code: str) -> list[tuple[str, int, Path, bool]]:
    identity = re.compile(r"(\d{4}-\d{2}-\d{2})-" + re.escape(code) + r"(?:-|\.md$)")
    history = []
    for path in research.glob("*.md"):
        match = identity.match(path.name)
        if not match or not path.is_file():
            continue
        suffix = re.search(r"-v([1-9]\d*)\.md$", path.name)
        text = path.read_text(encoding="utf-8-sig")
        header = re.split(r"\n##\s", text, maxsplit=1)[0]
        document_type = re.search(r"(?m)^>\s*文档类型[:：]\s*(.+)$", header)
        state = re.search(r"(?m)^>\s*发布状态[:：]\s*(.+)$", header)
        explicit_draft = re.search(r"(?m)^>\s*报告验收状态[^：:\n]*[:：][^\n]*草稿", header)
        supplement = re.search(r"(?m)^>\s*补充日期[:：]", header)
        full = bool(document_type and document_type.group(1).strip() == "完整报告")
        if document_type is None:
            full = bool(re.search(r"(?m)^##\s+[^\n]*核心结论", text) and not supplement)
        eligible = full and not explicit_draft and (state is None or state.group(1).strip() == "已发布")
        history.append((match.group(1), int(suffix.group(1)) if suffix else 1, path, eligible))
    return history


def _publication_text(report: str, reason: str | None, predecessor: Path | None) -> str:
    report = PUBLICATION_FIELDS.sub("", report)
    fields = "> 文档类型：完整报告\n> 发布状态：已发布\n"
    fields += "> 发布变更原因：" + (" ".join(reason.split()) if reason and reason.strip() else "首次发布") + "\n"
    if predecessor:
        fields += f"> 替代发布版本：[{predecessor.name}]({predecessor.name})\n"
    title, separator, rest = report.partition("\n")
    return title + "\n" + fields + (rest if separator else "")


def _atomic_write(path: Path, text: str, *, replace: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=path.parent)
    staged = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        if staged.read_bytes() != data:
            raise OSError("Staged report did not read back unchanged")
        if replace:
            os.replace(staged, path)
        else:
            os.link(staged, path)
    finally:
        staged.unlink(missing_ok=True)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an A-share stock research Markdown report file."
    )
    parser.add_argument("--code", required=True, help="A-share stock code, e.g. 600519")
    parser.add_argument("--name", default=None, help="Optional stock short name")
    parser.add_argument(
        "--date",
        default=date.today().isoformat(),
        help="Research date in YYYY-MM-DD format; defaults to today",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Base directory where the research/ folder will be created",
    )
    parser.add_argument(
        "--content-file",
        help="UTF-8 Markdown source; omit to create a template draft",
    )
    parser.add_argument("--publish", action="store_true",
                        help="Preflight and atomically publish an immutable full report")
    parser.add_argument("--change-reason", help="Required for an update/correction of a published report")
    parser.add_argument("--supersedes", help="Exact prior report path, relative to workspace or absolute")
    parser.add_argument("--validate", action="store_true",
                        help="Preflight the draft at its final path without publishing; failure exits 1")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        content = Path(args.content_file).read_text(encoding="utf-8-sig") if args.content_file else None
        path = create_report(args.code, args.name, args.date, args.output_dir, content,
                             publish=args.publish, validate=args.validate,
                             change_reason=args.change_reason, supersedes=args.supersedes)
    except PublicationValidationError as exc:
        print(exc.draft)
        print(json.dumps(exc.result, ensure_ascii=False, indent=2), file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 1
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
