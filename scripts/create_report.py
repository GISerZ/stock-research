#!/usr/bin/env python3
"""Save a stock-research Markdown report or create a draft from the template.

This helper only creates a local report file. It does not fetch market data,
browse websites, call an LLM, calculate indicators, or generate ratings.
"""

from __future__ import annotations

import argparse
import json
from itertools import count
import re
import sys
from datetime import date, datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
TEMPLATE_PATH = SKILL_DIR / "references" / "report-template.md"

CODE_RE = re.compile(r"^[0-9A-Za-z._-]+$")
INVALID_NAME_CHARS = set('<>:"/\\|?*')


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
) -> Path:
    safe_code = sanitize_code(code)
    safe_name = sanitize_name(name)
    safe_date = validate_date(report_date)
    base_path = build_report_path(safe_code, safe_name, safe_date, output_dir)
    report = render_template(safe_code, safe_name, safe_date) if content is None else content
    if not report.strip():
        raise ValueError("Report content cannot be empty.")
    base_path.parent.mkdir(parents=True, exist_ok=True)
    for version in count(1):
        path = base_path if version == 1 else base_path.with_name(
            f"{base_path.stem}-v{version}{base_path.suffix}"
        )
        try:
            with path.open("x", encoding="utf-8") as output:
                output.write(report)
            return path
        except FileExistsError:
            continue


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
        help="UTF-8 Markdown file containing the completed report; omit to create a draft",
    )
    parser.add_argument("--validate", action="store_true",
                        help="Check the saved report and evidence; keep draft on failure (exit 1)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        content = Path(args.content_file).read_text(encoding="utf-8") if args.content_file else None
        path = create_report(args.code, args.name, args.date, args.output_dir, content)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(path)
    if args.validate:
        from validate_report import validate_report
        result = validate_report(path, Path(args.output_dir))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result["errors"]:
            print("Report saved as draft; validation failed.", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
