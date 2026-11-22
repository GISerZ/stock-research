"""Read-only health summary for saved A-share market sentiment snapshots."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

from collect_sentiment import _completed_date
from sentiment_core import BJ_TZ, load_market_five_days
from sentiment_market import last_five_trade_dates


FIELDS = ("rising", "falling", "flat", "suspended", "limit_up", "limit_down", "failed_board")


def market_coverage(workspace: Path, *, now: datetime, ak_api) -> dict:
    """Summarize exact saved versions without collecting or writing data."""
    now = now.astimezone(BJ_TZ)
    try:
        latest = _completed_date(now, ak_api)
        dates = last_five_trade_dates(latest, ak_api)
    except Exception as exc:
        return {"status": "calendar_unavailable", "error": f"{type(exc).__name__}: {exc}"}
    try:
        snapshots = load_market_five_days(workspace, dates)
        base = Path(workspace) / "research/evidence/sentiment/market"
        for entry in snapshots:
            if entry["snapshot_path"] is not None:
                continue
            stem = entry["trade_date"]
            existing = [path for path in base.glob(f"{stem}*.json")
                        if re.fullmatch(re.escape(stem) + r"(?:-v\d+)?\.json", path.name)]
            if existing:
                raise ValueError(f"Saved snapshot versions for {stem} are unreadable or invalid")
    except Exception as exc:
        return {"status": "read_error", "latest_completed_trade_date": latest.isoformat(),
                "error": f"{type(exc).__name__}: {exc}"}

    days = []
    coverage = {field: {"valid_days": 0, "gap_dates": []} for field in FIELDS}
    for entry in snapshots:
        field_status = {item["field"]: item["status"] for item in entry["observations"]
                        if item.get("field") in FIELDS}
        for field in FIELDS:
            if field_status.get(field) == "ok":
                coverage[field]["valid_days"] += 1
            else:
                coverage[field]["gap_dates"].append(entry["trade_date"])
        days.append({"trade_date": entry["trade_date"], "snapshot_path": entry["snapshot_path"],
                     "completeness": entry["completeness"],
                     "field_status": {field: field_status.get(field, "missing") for field in FIELDS}})
    current = days[-1]
    return {"status": "ok" if current["completeness"] == "complete" else "incomplete",
            "latest_completed_trade_date": latest.isoformat(), "latest_snapshot_path": current["snapshot_path"],
            "latest_completeness": current["completeness"], "market_days": days,
            "five_day_field_coverage": coverage}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=".", help="Workspace containing research/")
    args = parser.parse_args(argv)
    try:
        import akshare
        summary = market_coverage(Path(args.output_dir).expanduser().resolve(),
                                  now=datetime.now(BJ_TZ), ak_api=akshare)
    except Exception as exc:
        summary = {"status": "read_error", "error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return {"ok": 0, "incomplete": 1}.get(summary["status"], 2)


if __name__ == "__main__":
    raise SystemExit(main())
